import asyncio
import inspect
import os
import re
import concurrent
import threading
import siada
import siada.tools.read_many_files_tool
import sys
import json
import time
from typing import Any, Optional

from prompt_toolkit.completion import Completion, PathCompleter
from prompt_toolkit.document import Document

import siada.io.io
from siada.services.model_info_service import ModelInfoService
from siada.support.editor import pipe_editor
from siada.support.spinner import WaitingSpinner
from siada.tools.coder.cmd_runner import run_cmd_impl as run_cmd
from siada.support.checkpoint_tracker import CheckPointData
from siada.support.usage_utils import deserialize_usage
from siada.support.message_classifier import get_role_and_type_from_item
from siada.utils import DirectoryUtils
from siada.config.language_config import normalize_language, get_language_display_name, SUPPORTED_LANGUAGES
# mcp.manager_service is lazy-loaded on first access to avoid pulling in
# agents.mcp (part of agents SDK, ~500ms) at startup.
class _LazyMCPService:
    """Transparent proxy that imports _mcp_manager_service on first attribute access."""
    def __getattr__(self, name):
        from siada.services.mcp.manager_service import _mcp_manager_service
        return getattr(_mcp_manager_service, name)

mcp_service = _LazyMCPService()
from siada.foundation.logging import logger

# Import custom commands modules directly to avoid circular dependencies
from siada.services.custom_commands.command_loader import FileCommandLoader
from siada.services.custom_commands.command_service import CommandService
from siada.services.custom_commands.types import CommandContext, CommandResult


class SwitchEvent:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


# Common path prefixes on macOS/Linux that users frequently paste.
# When a slash input starts with one of these, we suppress "invalid command"
# telemetry to avoid polluting metrics with false positives.
_PATH_PREFIX_WHITELIST = ("/var", "/tmp", "/private")


def _looks_like_command(command_name: str) -> bool:
    """Check if a command name contains only valid characters: [a-zA-Z0-9:_-]."""
    return bool(re.fullmatch(r"[a-zA-Z0-9:_\-]+", command_name))


def _looks_like_filepath(slash_input: str) -> bool:
    """Check if a slash-prefixed input is likely a file path (not a command)."""
    parts = slash_input.lstrip("/").split()
    if not parts:
        return False
    command_name = parts[0]
    if not _looks_like_command(command_name):
        return True
    # Even if chars are valid, check if the path exists on disk
    try:
        return os.path.exists("/" + command_name)
    except (ValueError, OSError):
        return False


# Concise, Claude-Code-style argument hints shown inline in the CLI input box
# right after a fully-typed command name (before the user has typed any
# argument yet), e.g. "/goal " renders as "/goal [<objective> | clear]" with
# the hint dimmed. Keys use the same hyphenated command name exposed via
# get_commands()/matching_commands() (cmd_pre_plan_mode -> "pre-plan-mode"),
# i.e. the `cmd_name` built in Controller.show_announcements(). Commands that
# take no meaningful argument, or only open a picker/UI with no argument, are
# intentionally omitted (empty hint -> nothing is rendered).
ARGUMENT_HINTS: dict[str, str] = {
    "btw": "<question>",
    "memory": "[enable | disable]",
    "web": "[enable | disable]",
    "goal": "[<objective> | clear]",
    "model": "[<model_name>]",
    "rule-global-add": "<text>",
    "compare": "<checkpoint_filename>",
    "undo": "<checkpoint_filename>",
    "restore": "<checkpoint_filename>",
    "resume": "[<index> | <session_id> | latest | --all]",
    "lang": "<en | zh-CN>",
    "pre-plan-mode": "<true | false>",
    "plugin": "[install | remove | enable | disable | validate | marketplace] <args>",
}


def get_argument_hint(cmd_name: str) -> str:
    """Return a concise argument-format hint for a slash command, or "" if none."""
    return ARGUMENT_HINTS.get(cmd_name, "")


class SlashCommands:

    def clone(self):
        return SlashCommands(
            io=self.io,
            verbose=self.verbose,
            editor=self.editor,
        )

    def __init__(
        self,
        io : siada.io.io.InputOutput,
        verbose=False,
        editor=None,
    ):
        self.io = io
        self.verbose = verbose
        self.help = None
        self.editor = editor
        self.custom_command_service = None  # Initialized on first use
        # Initialize plugin hook runner
        try:
            from siada.services.plugins.hook_runner import HookRunner
            from siada.services.plugins.plugin_loader import PluginLoader
            self.hook_runner = HookRunner()
            for _plugin in PluginLoader().load_all():
                self.hook_runner.register_plugin_hooks(_plugin)
        except Exception:
            from siada.services.plugins.hook_runner import HookRunner
            self.hook_runner = HookRunner()

    # ============================================================================
    # Lifecycle Event Methods (Agent Lifecycle Integration)
    # ============================================================================
    
    def _send_lifecycle_event(self, event_type: str, **kwargs):
        """
        Send lifecycle event to ACP
        
        Args:
            event_type: Event type (task_start, task_complete, task_error)
            **kwargs: Event parameters
        """
        # Only send in ACP mode
        if not hasattr(self.io, 'acp_enabled') or not self.io.acp_enabled:
            return
        
        if not hasattr(self.io, 'acp_adapter') or not self.io.acp_adapter:
            return
        
        try:
            # Build event data
            event_data = {
                "type": event_type,
                "timestamp": time.time(),
                **kwargs
            }
            
            # Use acp_adapter's builder to create custom message
            message = self.io.acp_adapter.builder.build_session_update(
                reason="lifecycle_event",
                metadata=event_data
            )
            
            # Send message
            adapter = self.io.acp_adapter
            if adapter.transport and adapter.transport.is_connected:
                # Use send_sync() directly, no event loop needed
                adapter.transport.send_sync(message)
                
        except Exception as e:
            # Silent failure, don't break command execution
            if self.verbose:
                logger.error(f"Failed to send lifecycle event: {e}")
    
    def _emit_task_start(self, cmd_name: str, args: str):
        """Send task start event"""
        self._send_lifecycle_event(
            "task_start",
            task_id=f"slash_{cmd_name}_{int(time.time() * 1000)}",
            command=cmd_name,
            args=args,
            category="slash_command"
        )
    
    def _emit_task_complete(self, cmd_name: str, result: Any):
        """Send task complete event"""
        # Convert result to serializable string; skip SwitchEvent (internal control object)
        result_str = None
        if result is not None and not isinstance(result, SwitchEvent):
            try:
                result_str = str(result)[:500]  # Limit length
            except:
                result_str = "<non-serializable>"
        
        self._send_lifecycle_event(
            "task_complete",
            command=cmd_name,
            result=result_str,
            category="slash_command"
        )
    
    def _emit_task_error(self, cmd_name: str, error: Exception):
        """Send task error event"""
        self._send_lifecycle_event(
            "task_error",
            command=cmd_name,
            error=str(error),
            error_type=type(error).__name__,
            category="slash_command"
        )
    
    # ============================================================================
    # End of Lifecycle Event Methods
    # ============================================================================

    # def cmd_model(self, args):

    #     model_name = args.strip()
    #     if not model_name:
    #         self.io.print_info("No model name provided")
    #         return

    #     model = ModelRunConfig(model_name)
    #     return SwitchEvent(model=model)

    # def cmd_agent(self, args):
    #     "Switch to a different agent type"

    #     agent_name = args.strip()

    #     try:
    #         from siada.services.siada_runner import SiadaRunner

    #         # Load agent configurations
    #         agent_configs = SiadaRunner._load_agent_config()
    #         # Get all available agent types (only enabled ones)
    #         available_agents = {name: config for name, config in agent_configs.items()
    #                           if config.get('class') and config.get('enabled', True)}

    #         if not agent_name:
    #             self.io.print_info("Available agents:\n")
    #             max_name_length = max(len(name) for name in available_agents.keys()) if available_agents else 0
    #             for name, config in available_agents.items():
    #                 description = config.get('description', f'{name.title()} agent')
    #                 self.io.print_info(f"- {name:<{max_name_length}} : {description}")
    #             self.io.print_info("\nUsage: /agent <agent_name>")
    #             return

    #         # Normalize agent name (lowercase, remove underscores/hyphens)
    #         normalized_name = agent_name.lower().replace('_', '').replace('-', '')

    #         # Find matching agent config
    #         agent_config = available_agents.get(normalized_name)

    #         if agent_config is None:
    #             available_names = list(available_agents.keys())
    #             self.io.print_error(f"Unknown agent: '{agent_name}'")
    #             self.io.print_info(f"Available agents: {', '.join(available_names)}")
    #             return

    #         # Check if agent class is implemented
    #         if not agent_config.get('class'):
    #             self.io.print_error(f"Agent '{agent_name}' is not implemented yet")
    #             return

    #         self.io.print_info(f"Switching to {agent_name} agent...")

    #         # Return SwitchEvent to change agent
    #         return SwitchEvent(agent=normalized_name)

    #     except Exception as e:
    #         self.io.print_error(f"Failed to switch agent: {e}")
    #         if self.verbose:
    #             import traceback
    #             self.io.print_error(traceback.format_exc())

    def cmd_compact(self, session, args):
        """Manually compact conversation history to reduce context window usage"""
        import threading

        # 1. Look up the cached CodeAgentContext for the current workspace
        from siada.services.siada_runner import SiadaRunner
        workspace = session.siada_config.workspace
        context = None
        for (_, ws), ctx in SiadaRunner._context_cache.items():
            if ws == workspace:
                context = ctx
                break

        if context is None:
            self.io.print_error(
                "No agent context found. Please send a message first to initialize the agent."
            )
            return

        # 2. Bind the current session so strategy helpers read the right config
        context.session = session

        # 3. Gather current real API messages
        real_api_messages = session.task_message_state.get_real_messages()
        if not real_api_messages:
            self.io.print_info("No conversation history to compact.")
            return

        before_count = len(real_api_messages)

        # 4. Run async compaction in a dedicated thread (safe regardless of event-loop state)
        compacted: list = [None]
        error: list = [None]

        def _run_compact():
            import asyncio

            async def _do_compact():
                from siada.agent_hub.context_filter.compaction_strategy import (
                    CompactionStrategy,
                    get_compaction_strategy,
                )
                strategy = get_compaction_strategy(context)
                fixed_overhead = CompactionStrategy.calculate_fixed_overhead(context)
                return await strategy.compact(
                    model_run_config=context.model_run_config,
                    real_api_messages=real_api_messages,
                    fixed_overhead_tokens=fixed_overhead,
                )

            loop = asyncio.new_event_loop()
            try:
                compacted[0] = loop.run_until_complete(_do_compact())
            except Exception as exc:
                error[0] = exc
            finally:
                loop.close()

        self.io.print_info("Compacting context...")
        t = threading.Thread(target=_run_compact, daemon=True)
        t.start()
        t.join()

        if error[0]:
            self.io.print_error(f"Compaction failed: {error[0]}")
            return

        result = compacted[0]

        # `result.compacted` is an explicit flag set by the strategy itself
        # (CompactionStrategy.compact(), see compaction_strategy.py) rather
        # than a list-identity guess.
        if not result.compacted:
            self.io.print_info(
                "Nothing to compact (conversation too short or already compact)."
            )
            return

        new_messages = result.messages
        after_count = len(new_messages)

        # 4.5 Manual /compact just ran (the "active" trigger, as opposed to
        # the per-LLM-call threshold check in ApiMessageTransferFilter) —
        # re-inject the goal reminder in case the turn that originally
        # carried it was just summarized or pruned away by either
        # compaction strategy. Mirrors
        # ApiMessageTransferFilter._maybe_reinject_goal_reminder so both the
        # active and passive compaction triggers behave the same way.
        from siada.agent_hub.context_filter.api_message_transfer_filter import (
            ApiMessageTransferFilter,
        )
        new_messages = ApiMessageTransferFilter._maybe_reinject_goal_reminder(
            context, new_messages,
        )
        after_count = len(new_messages)

        # 5. Compute tracking info anchored to the current end of the original
        # message history so the next LLM call uses an incremental update
        # (compacted + delta) rather than a full refresh that would undo compaction.
        from siada.agent_hub.context_filter.utils import compute_message_signature
        from siada.session.task_message_state import RealApiMessage
        api_messages = session.task_message_state.get_messages()
        if api_messages:
            new_last_index = len(api_messages) - 1
            new_last_signature = compute_message_signature(api_messages[-1])
        else:
            new_last_index = -1
            new_last_signature = ""

        session.task_message_state.set_real_messages(
            RealApiMessage(
                real_api_history=new_messages,
                last_index=new_last_index,
                last_signature=new_last_signature,
            )
        )

        # 6. Persist compacted messages with correct tracking to api_messages.json
        from siada.agent_hub.context_filter.api_message_transfer_filter import (
            ApiMessageTransferFilter,
        )
        ApiMessageTransferFilter()._sync_api_message_to_file(
            context, new_messages, tokens_count=0,
            last_index=new_last_index, last_signature=new_last_signature,
        )

        self.io.print_info(
            f"Compacted: {before_count} → {after_count} messages "
            f"({before_count - after_count} removed)"
        )

    def cmd_btw(self, session, args):
        """Ask a quick side question without polluting main conversation"""
        question = args.strip()
        if not question:
            # In ACP/UI mode the frontend intercepts blank /btw and renders the
            # usage hint in the side panel itself, so this path is only reached
            # in plain terminal mode where a simple info line is appropriate.
            self.io.print_info("Usage: /btw <your question>")
            return

        from siada.services.side_question import run_side_question

        spinner = WaitingSpinner(
            "Answering...", text_color="#79B8FF", io_instance=self.io
        )

        spinner.start()
        try:
            answer = run_side_question(session, question)
        except Exception as e:
            self.io.print_error(f"/btw failed: {e}")
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())
            return
        finally:
            try:
                spinner.stop()
            except Exception:
                pass

        self._render_btw_answer(question, answer)
        # 不返回任何 SwitchEvent —— controller 不进入下一轮，主对话状态零变更

    def _render_btw_answer(self, question: str, answer: str):
        """渲染 /btw 答案：ACP 模式发通知，终端模式用 rich Panel。"""
        if hasattr(self.io, "acp_adapter") and self.io.acp_adapter is not None:
            try:
                from siada.io.acp.message_builder import ACPMessageBuilder
                msg = ACPMessageBuilder().build_custom_notification(
                    method="ui/showSideQuestion",
                    params={"question": question, "answer": answer},
                )
                if (
                    self.io.acp_adapter.transport
                    and self.io.acp_adapter.transport.is_connected
                ):
                    self.io.acp_adapter.transport.send_sync(msg)
                    logger.info("[btw] ui/showSideQuestion sent via ACP")
                    return
                else:
                    logger.warning("[btw] ACP transport not connected, fallback to terminal")
            except Exception as e:
                logger.warning(f"[btw] ACP notification failed, fallback to terminal: {e}")

        # 终端渲染：黄色 Panel + Markdown
        try:
            from rich.panel import Panel
            from rich.markdown import Markdown
            self.io.console.print(
                Panel(
                    Markdown(answer),
                    title=f"[bold yellow]/btw[/bold yellow]  {question}",
                    border_style="yellow",
                    padding=(1, 2),
                )
            )
        except Exception:
            # 最后兜底：纯文本
            self.io.print_info(f"[/btw] {question}\n\n{answer}")

    def cmd_status(self, session, args):
        "Show the current status"
        # Collect all status information into a single string
        status_lines = [
            f"Model: {session.siada_config.llm_config.model_name}",
            f"Agent: {session.siada_config.agent_name}",
            f"Session id: {session.session_id}",
            f"WorkSpace: {session.siada_config.workspace}",
            f"Project Hash: {DirectoryUtils.get_file_path_hash(session.siada_config.workspace)}"
        ]
        self.io.print_info("\n".join(status_lines))

    def cmd_memory(self, session, args: str):
        """Enable or disable the memory subsystem

        Usage:
            /memory          - Show current memory status
            /memory enable   - Enable all memory features
            /memory disable  - Disable all memory features
        """
        sub = args.strip().lower()

        if sub not in ('', 'enable', 'disable'):
            self.io.print_error(
                f"Unknown subcommand: '{sub}'. Usage: /memory [enable|disable]"
            )
            return

        # Locate the cached CodeAgentContext for this workspace
        from siada.services.siada_runner import SiadaRunner
        workspace = session.siada_config.workspace
        context = None
        for (_, ws), ctx in SiadaRunner._context_cache.items():
            if ws == workspace:
                context = ctx
                break

        if not sub:
            # Show current status
            if context is not None:
                enabled = getattr(context, 'memory_tools_enabled', True)
            else:
                try:
                    from siada.config.config_loader import load_conf
                    enabled = load_conf().memory_config.enabled
                except Exception:
                    enabled = True
            status = "enabled" if enabled else "disabled"
            self.io.print_info(f"Memory: {status}")
            return

        # Toggle
        enabled = (sub == 'enable')

        # Update live context immediately — next turn picks it up automatically
        # because configure_tools_for_context() is called at the start of every run().
        if context is not None:
            context.memory_tools_enabled = enabled

            # Also rebuild combined_memory so the system prompt reflects the
            # new state.  On disable we pass both stores as None so all
            # memory-layer guidance sections (Common Rules, Inline Memory,
            # Session Search, Holographic) are stripped.  On enable we reuse
            # whatever stores were initialised at session start; if the session
            # started with memory disabled those stores are None — guidance
            # won't appear until the next session, which is the expected
            # degraded-but-safe behaviour.
            try:
                from siada.services.memory.combined_memory import build_combined_memory
                _ws = workspace
                if not enabled:
                    context.combined_memory = build_combined_memory(_ws, None, None)
                else:
                    context.combined_memory = build_combined_memory(
                        _ws,
                        getattr(context, 'memory_store', None),
                        getattr(context, 'holographic_provider', None),
                    )
                logger.info(
                    "[memory] combined_memory rebuilt after toggle (enabled=%s)", enabled
                )
            except Exception as _e:
                logger.warning("[memory] Failed to rebuild combined_memory: %s", _e)

        # Persist to conf.yaml so restarts also pick it up
        from siada.config.config_loader import save_conf_field
        if not save_conf_field('memory.enabled', enabled):
            if self.verbose:
                logger.error("[memory] Failed to persist memory.enabled to conf.yaml")

        status_str = "enabled" if enabled else "disabled"
        self.io.print_info(f"Memory {status_str}.")
        logger.info(f"[memory] {status_str} (persisted to conf.yaml)")

        # Notify frontend in ACP mode
        self._notify_memory_status(enabled)

    def _notify_memory_status(self, enabled: bool) -> None:
        """Send ui/memoryStatusChanged ACP notification to update frontend state."""
        if not (hasattr(self.io, 'acp_adapter') and self.io.acp_adapter is not None):
            return
        try:
            from siada.io.acp.message_builder import ACPMessageBuilder
            msg = ACPMessageBuilder().build_custom_notification(
                method="ui/memoryStatusChanged",
                params={"enabled": enabled},
            )
            adapter = self.io.acp_adapter
            if adapter.transport and adapter.transport.is_connected:
                adapter.transport.send_sync(msg)
                logger.info(f"[memory] ui/memoryStatusChanged sent: enabled={enabled}")
            else:
                logger.warning("[memory] ACP transport not connected, skip ui/memoryStatusChanged")
        except Exception as e:
            logger.warning(f"[memory] Failed to send ACP notification: {e}")

    def cmd_web(self, session, args: str):
        """Toggle the web search tools (web_search / web_fetch)

        Usage:
            /web          - Show current web tools status
            /web enable   - Enable web tools (overrides provider default)
            /web disable  - Disable web tools (overrides provider default)

        When neither is set, web tools follow the provider default:
        ON for "li", OFF for every other provider.
        """
        sub = args.strip().lower()

        if sub not in ('', 'enable', 'disable'):
            self.io.print_error(
                f"Unknown subcommand: '{sub}'. Usage: /web [enable|disable]"
            )
            return

        # Locate the cached CodeAgentContext for this workspace
        from siada.services.siada_runner import SiadaRunner
        workspace = session.siada_config.workspace
        context = None
        for (_, ws), ctx in SiadaRunner._context_cache.items():
            if ws == workspace:
                context = ctx
                break

        # Current configured mode (None=auto/follow-provider-default, True=on, False=off)
        if context is not None:
            mode_val = getattr(context, 'web_tools_enabled', None)
        else:
            try:
                from siada.config.config_loader import load_conf
                mode_val = load_conf().web_config.enabled
            except Exception:
                mode_val = None

        def _mode_label(v):
            if v is True:
                return "enable"
            if v is False:
                return "disable"
            return "auto"

        def _effective(v, provider):
            from siada.tools.web import resolve_web_tools_enabled
            return resolve_web_tools_enabled(provider, v)

        # Resolve current provider for the effective-state display. Prefer the
        # resolved provider name written by _build_run_config (context.provider),
        # which is the actual provider used for model calls. Fall back to the raw
        # llm_config value with model-based routing applied when the context has
        # not been through a run yet, and finally to the current session's
        # llm_config (e.g. when no run has populated the context cache).
        from siada.tools.web import resolve_provider_from_context
        provider = resolve_provider_from_context(context)
        if not provider:
            try:
                from siada.provider.provider_factory import resolve_provider_by_model
                llm_cfg = session.siada_config.llm_config
                provider = resolve_provider_by_model(
                    getattr(llm_cfg, "model_name", None),
                    getattr(llm_cfg, "provider", None),
                )
            except Exception:
                provider = None



        if not sub:
            mode = _mode_label(mode_val)
            eff = _effective(mode_val, provider)
            provider_str = provider or "(unknown)"
            self.io.print_info(
                f"Web tools: mode={mode}, effective={'on' if eff else 'off'} "
                f"(provider={provider_str})"
            )
            return

        # enable / disable
        new_val = (sub == 'enable')

        # Update live context immediately — configure_tools_for_context() runs
        # at the start of every run() and picks up the new value automatically.
        if context is not None:
            context.web_tools_enabled = new_val

        # Persist to conf.yaml so restarts also pick it up
        from siada.config.config_loader import save_conf_field
        if not save_conf_field('web.enabled', new_val):
            if self.verbose:
                logger.error("[web] Failed to persist web.enabled to conf.yaml")

        eff = _effective(new_val, provider)
        self.io.print_info(
            f"Web tools {'enabled' if new_val else 'disabled'} (effective: {'on' if eff else 'off'})."
        )
        logger.info(f"[web] set to {_mode_label(new_val)} (persisted to conf.yaml)")

    def cmd_goal(self, session, args: str):
        """Set or clear a standing goal for this session, then kick off work.

        Usage:
            /goal <objective>   - Set a new goal, overwriting the current one
                                   (any status) — no /goal clear needed first.
                                   Immediately hands the objective to the agent
                                   as the first real turn (same "SwitchEvent"
                                   channel as /init and /issue_fix) — /goal
                                   is not a silent no-op background flag flip,
                                   it actually starts work on the objective.
            /goal clear         - Remove the current goal entirely

        Once set, an independent verifier checks after every turn whether the
        goal has been met. On failure it automatically forces another turn
        with feedback — no /goal complete command exists, because completion
        is judged by the verifier, never self-declared. There is also no
        pause/resume/status subcommand by design — a "complete" goal is
        dropped automatically, and a "blocked" goal (auto-tripped after
        repeated verifier failures) is automatically reactivated, as soon as
        the user sends their next conversational message — see
        Controller._maybe_reset_goal_on_new_turn.

        Setting or clearing a goal always archives whatever goal it replaces
        to <session_dir>/goal_history.jsonl first (see
        goal_storage.append_goal_history) — goal.json itself only ever holds
        the current goal, so nothing is silently lost.
        """
        from siada.services.goal.models import Goal
        from siada.services.goal import goal_storage

        sub = args.strip()
        sub_lower = sub.lower()

        session_dir = None
        if session.state.openai_session and session.state.openai_session.session_folder:
            session_dir = session.state.openai_session.session_folder

        from siada.services.siada_runner import SiadaRunner
        workspace = session.siada_config.workspace
        context = None
        for (_, ws), ctx in SiadaRunner._context_cache.items():
            if ws == workspace:
                context = ctx
                break

        current_goal = getattr(context, 'goal', None) if context is not None else None
        if current_goal is None and session_dir is not None:
            current_goal = goal_storage.load_goal(session_dir)

        if sub_lower == 'clear':
            if current_goal is not None and session_dir is not None:
                goal_storage.append_goal_history(session_dir, current_goal)
            if context is not None:
                context.goal = None
            else:
                # No agent context has been built yet for this workspace (e.g.
                # /goal clear is the very first command in a fresh session) --
                # there's nothing live to clear, but drop any not-yet-consumed
                # staged goal too (see the "set a new goal" branch below for
                # why pending_goal exists) so it can't resurrect itself into
                # whatever context the next turn builds.
                session.state.pending_goal = None
            if session_dir is not None:
                goal_storage.clear_goal(session_dir)

            # In ACP mode the frontend already reflects this via the
            # goalState push below (status bar disappears + transient
            # notice) — printing a plain chat line here would just show up
            # as a redundant boxed system message (ProcessBox groups any
            # plain print_info line into a bordered box). Non-ACP/plain
            # terminal mode has no such status bar, so it still needs this.
            if not self._is_acp_mode():
                self.io.print_info("Goal cleared.")
            if hasattr(self.io, "acp_adapter") and self.io.acp_adapter is not None:
                self.io.acp_adapter._send_if_acp(
                    self.io.acp_adapter.builder.build_custom_notification,
                    method="context/goalState",
                    params={"goal": None, "verifying": False},
                )
            return

        if not sub:
            self.io.print_error("Usage: /goal <objective>  |  /goal clear")
            return

        # Anything else is the objective text for a new goal. Overwriting is
        # always allowed regardless of the current goal's status (active,
        # blocked, or complete) — the new goal starts a fresh "active" state
        # (consecutive_failures reset via Goal.create), and the goal it
        # replaces is archived to history first so it isn't lost.
        if current_goal is not None and session_dir is not None:
            goal_storage.append_goal_history(session_dir, current_goal)

        new_goal = Goal.create(sub)
        if context is not None:
            context.goal = new_goal
        else:
            # BUGFIX: no agent context exists yet for this workspace -- this
            # happens whenever /goal is the very first command sent in a
            # fresh session, i.e. SiadaRunner._context_cache has no entry
            # for this workspace yet because no conversation turn has run.
            # Without this branch the goal was ONLY ever written to
            # goal.json on disk (see goal_storage.save_goal below) and never
            # attached to any context object -- the SwitchEvent-triggered
            # conversation turn that immediately follows builds a brand new
            # context with context.goal defaulting to None, so
            # turn_hooks.maybe_run_goal_verifier's `if goal is None: return
            # result` guard silently no-ops forever: the verifier never
            # runs and the goal status bar never advances past "active",
            # even though the agent is genuinely doing real work.
            #
            # Fix: stage it the same way ResumeService does for a goal
            # recovered from disk on session resume (see
            # resume_service.py's `pending_goal` comment) --
            # SiadaRunner._prepare_context_for_run() unconditionally
            # consumes session.state.pending_goal into context.goal as soon
            # as the very next turn builds/prepares its context, which for
            # /goal is exactly the SwitchEvent(ai_analysis_prompt=sub) turn
            # returned below.
            session.state.pending_goal = new_goal
        if session_dir is not None:
            goal_storage.save_goal(session_dir, new_goal)

        # In ACP mode the frontend already reflects this via the goalState
        # push below (persistent "Goal (active): ..." status bar + transient
        # notice) — see the comment on the /goal clear branch above for why
        # this print_info is skipped there.
        if not self._is_acp_mode():
            self.io.print_info(f"Goal set: {sub}")
        if hasattr(self.io, "acp_adapter") and self.io.acp_adapter is not None:
            self.io.acp_adapter._send_if_acp(
                self.io.acp_adapter.builder.build_custom_notification,
                method="context/goalState",
                params={
                    "goal": {
                        "objective": new_goal.objective,
                        "status": new_goal.status,
                        # See turn_hooks.push_goal_state_via_acp for why this
                        # is included: drives the frontend's live elapsed-
                        # time counter next to the status label.
                        "createdAt": new_goal.created_at,
                    },
                    "verifying": False,
                    "notice": f"Goal set: {sub}",
                },
            )

        # /goal must actually DO something, not just flip a background flag —
        # hand the objective straight to the agent as the first real turn via
        # the same SwitchEvent(ai_analysis_prompt=...) channel /init and
        # /issue_fix use. Controller.run() picks this up as `pending_input`
        # for the next loop iteration, which runs it as a normal CONVERSATION
        # turn — so it also gets goal-verified afterward, same as any other
        # turn taken while this goal is active.
        #
        # ai_analysis_prompt itself stays the bare objective string, exactly
        # like /init and /issue_fix — other consumers of this generic
        # SwitchEvent kwarg (e.g. the Feishu slash-command bridge's
        # _handle_ai_analysis) only know how to deal with a plain string
        # here and must keep working unchanged.
        #
        # goal_command=True is an extra marker read only by
        # Controller.run(): it tells the CLI loop to persist this turn's
        # *actual* user message as the full "/goal <objective>" text (not
        # just the stripped objective), formatted as a Responses-API input
        # list rather than a bare string. That list shape is also what
        # keeps it safe from recursive re-parsing — TurnFactory routes list
        # inputs straight to ConversationTurn (CommandTurn.can_handle() /
        # SlashCommands.is_command() only ever inspect strings), so a
        # literal "/goal " prefix embedded in the text can never be
        # mistaken for a brand new slash command on the next loop
        # iteration.
        return SwitchEvent(ai_analysis_prompt=sub, goal_command=True)



    # def cmd_shell(self, args):
    #     "Open a shell"
    #     self.io.print_info("Switching to shell mode...")
    #     return SwitchEvent(shell=True)

    def completions_model(self):
        return ModelInfoService.get_model_names()

    # def cmd_models(self, args):
    #     "Search the list of available models"
    #     # Removed: /model already provides this functionality
    #     args = args.strip()
    #     models = ModelInfoService.get_model_names()
    #     model_lines = [f"- {model}" for model in models]
    #     self.io.print_info("\n".join(model_lines))

    def cmd_model(self, session, args: str):
        """Switch to a different model

        Usage:
            /model              - Show model selector (opens UI picker in UI mode)
            /model <model_name> - Switch to the specified model
        """
        args_stripped = args.strip()

        if not args_stripped:
            # No model name provided - show model selector UI or list
            if hasattr(self.io, 'acp_adapter') and self.io.acp_adapter is not None:
                try:
                    from siada.io.acp.message_builder import ACPMessageBuilder
                    models = ModelInfoService.get_model_names()
                    current_model = session.siada_config.llm_config.model_name

                    message = ACPMessageBuilder().build_custom_notification(
                        method="ui/showModelSelector",
                        params={
                            "models": models,
                            "currentModel": current_model,
                        }
                    )

                    if self.io.acp_adapter.transport and self.io.acp_adapter.transport.is_connected:
                        self.io.acp_adapter.transport.send_sync(message)
                        logger.info(f"Sent ui/showModelSelector notification to frontend")
                    else:
                        logger.warning("ACP transport not connected, falling back to text mode")
                        self._print_models_list(session)
                except Exception as e:
                    logger.error(f"Failed to send ModelSelector notification: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    self._print_models_list(session)
            else:
                self._print_models_list(session)
            return

        # Switch to the specified model
        model_name = args_stripped

        if not ModelInfoService.is_model_supported(model_name):
            available = ModelInfoService.get_model_names()
            self.io.print_error(f"Model '{model_name}' not supported.")
            self.io.print_info(f"Available models: {', '.join(available)}")
            return

        try:
            from siada.models.model_run_config import ModelRunConfig
            from siada.provider.provider_factory import resolve_provider_by_model
            new_llm_config = ModelRunConfig(model_name)
            # Use the config-file default provider as the fallback, NOT the current session's
            # provider. This avoids inheriting a force-assigned provider (e.g. "openai_agents"
            # was set because the session was running gpt-5.x) when switching to a model that
            # belongs to a different provider family (e.g. claude-sonnet-4.6 -> "li").
            default_provider = ModelRunConfig.get_default_config().provider
            # Resolve the new model's provider (handles legacy keys like
            # "openai_agents" -> "li"), so users don't need to juggle the
            # provider concept when switching models.
            new_llm_config.provider = resolve_provider_by_model(model_name, default_provider)
            session.siada_config.llm_config = new_llm_config

            # Reset real API messages to force fresh context with new model
            # This avoids stale context issues when switching models
            session.state.task_message_state.reset_real_messages()
            # Also reset the persisted tracking in api_messages.json so that
            # _needs_full_refresh returns True on the next LLM call. Without
            # this, the stale last_index/last_signature in the file causes
            # _try_incremental_update to use an empty base list, losing all history.
            if session.state.openai_session and session.state.openai_session.session_folder:
                from siada.services.session_management import SessionManager
                SessionManager.update_api_messages_tracking(
                    session.state.openai_session.session_folder, -1, ""
                )

            # Persist the new model to ~/.siada-cli/conf.yaml
            self._persist_model_to_conf(model_name)

            # In ACP mode, send history to UI to refresh display with new model in banner
            if hasattr(self.io, 'acp_adapter') and self.io.acp_adapter is not None:
                items = session.state.task_message_state.get_messages()
                if items:
                    self._send_history_to_ui(items)

            return SwitchEvent(model=model_name)

        except Exception as e:
            self.io.print_error(f"Failed to switch model: {e}")

    def cmd_todo_task(self, session, args: str):
        """Restore the last todo_write state to the frontend display.

        Useful after the TodoDisplay has been closed — re-sends the most recent
        todo list so you can select a task and press Enter to view its messages.
        """
        from siada.tools.todo.recovery import extract_todos_from_messages

        messages = session.task_message_state.get_messages()
        todos = extract_todos_from_messages(messages)

        if not todos:
            self.io.print_info("No todo_write call found in current session history.")
            return

        # Push to frontend via ACP (same path as todo_write_impl)
        if hasattr(self.io, "acp_adapter") and self.io.acp_adapter is not None:
            try:
                todo_dicts = [{"content": t.content, "status": t.status} for t in todos]
                self.io.acp_adapter._send_if_acp(
                    self.io.acp_adapter.builder.build_custom_notification,
                    method="context/todoState",
                    params={"todos": todo_dicts},
                )
                self.io.print_info(f"Restored {len(todos)} todo items.")
            except Exception as e:
                self.io.print_error(f"Failed to push todo state: {e}")
        else:
            # Terminal fallback: print the list
            from siada.tools.tool_call_format.formatters import _TODO_STATUS_ICONS  # type: ignore
            lines = [f"{_TODO_STATUS_ICONS.get(t.status, '?')}  {t.content}" for t in todos]
            self.io.print_info("\n".join(lines))

    def cmd_task_list(self, session, args: str):
        """Show discovered pending tasks and select one to execute

        Usage:
            /task-list  - Open task selector (UI picker in UI mode, text list in terminal mode)
        """
        try:
            from siada.agent_hub.proactive.task_storage import TaskStorage
            from siada.agent_hub.proactive.models import TaskList

            storage = TaskStorage()
            task_list = storage.load()

            # Walk back to find the most recent file with tasks
            if task_list is None or len(task_list) == 0:
                task_files = sorted(storage.storage_dir.glob("tasks_*.json"), reverse=True)
                for task_file in task_files:
                    date_str = task_file.stem.replace("tasks_", "")
                    task_list = storage.load(date=date_str)
                    if task_list and len(task_list) > 0:
                        break

            if task_list is None or len(task_list) == 0:
                self.io.print_info("No tasks found. Run the proactive daemon to discover tasks.")
                return

            priority_order = {"high": 0, "medium": 1, "low": 2}
            tasks = sorted(task_list.tasks, key=lambda t: priority_order.get(t.priority, 3))
            tasks_data = [t.to_dict() for t in tasks]

            if hasattr(self.io, 'acp_adapter') and self.io.acp_adapter is not None:
                try:
                    from siada.io.acp.message_builder import ACPMessageBuilder

                    message = ACPMessageBuilder().build_custom_notification(
                        method="ui/showTaskSelector",
                        params={"tasks": tasks_data}
                    )

                    if self.io.acp_adapter.transport and self.io.acp_adapter.transport.is_connected:
                        self.io.acp_adapter.transport.send_sync(message)
                        logger.info(f"Sent ui/showTaskSelector notification with {len(tasks)} tasks")
                    else:
                        logger.warning("ACP transport not connected, falling back to text mode")
                        self._print_task_list(tasks)
                except Exception as e:
                    logger.error(f"Failed to send TaskSelector notification: {e}")
                    self._print_task_list(tasks)
            else:
                self._print_task_list(tasks)
        except Exception as e:
            self.io.print_error(f"Failed to load task list: {e}")
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())

    def _print_task_list(self, tasks):
        """Print task list in plain text (non-ACP fallback)"""
        if not tasks:
            self.io.print_info("No tasks found.")
            return
        priority_icons = {"high": "!!!", "medium": "!  ", "low": "   "}
        status_icons = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]", "cancelled": "[-]"}
        lines = [f"Pending Tasks ({len(tasks)} total)\n"]
        lines.append(f"{'#':<3} {'P':<4} {'S':<4} {'Cat':<6} {'Conf':<6} Title")
        lines.append("-" * 68)
        for i, task in enumerate(tasks, 1):
            prio = priority_icons.get(task.priority, "   ")
            status = status_icons.get(task.status, "[ ]")
            cat = task.category[:5]
            conf = f"{task.confidence:.2f}"
            confirm = " [confirm]" if task.needs_confirmation else ""
            lines.append(f"{i:<3} {prio:<4} {status:<4} {cat:<6} {conf:<6} {task.title}{confirm}")
        self.io.print_info("\n".join(lines))

    def _persist_model_to_conf(self, model_name: str):
        """Persist the selected model to ~/.siada-cli/conf.yaml"""
        from siada.config.config_loader import save_conf_field
        if not save_conf_field('llm_config.model', model_name):
            if self.verbose:
                logger.error(f"Failed to persist model to conf.yaml")

    def _print_models_list(self, session):
        """Print available models list to output"""
        current_model = session.siada_config.llm_config.model_name
        models = ModelInfoService.get_model_names()
        lines = [f"Available models (current: {current_model}):"]
        for m in models:
            note = " (slowly)" if m == "lpai-glm-5.2" else ""
            lines.append(f"  {m}{note}")
        lines.append("\nUsage: /model <model_name>")
        self.io.print_info("\n".join(lines))

    def is_command(self, inp):
        """Check if input is a command (not a file path).
        
        Three-level filtering (ref: slash-command-vs-filepath.md):
        1. Starts with / or !
        2. Characters check: command name must match [a-zA-Z0-9:_-]
        3. Filesystem check: if path exists on disk, treat as text
        """
        if not (inp.startswith("/") or inp.startswith("!")):
            return False
        if inp.startswith("!"):
            return True
        # Valid commands start with exactly one "/". Inputs starting with "//"
        # (e.g. code comments like "// nihao", or plain "//") are not commands
        # and should be treated as regular text sent to the model.
        if inp.startswith("//"):
            return False
        # For "/" inputs, check if it's a file path, not a command
        return not _looks_like_filepath(inp)

    def get_raw_completions(self, cmd):
        assert cmd.startswith("/")
        cmd = cmd[1:]
        cmd = cmd.replace("-", "_")

        raw_completer = getattr(self, f"completions_raw_{cmd}", None)
        return raw_completer

    def get_completions(self, cmd):
        assert cmd.startswith("/")
        cmd = cmd[1:]

        cmd = cmd.replace("-", "_")
        fun = getattr(self, f"completions_{cmd}", None)
        if not fun:
            return
        return sorted(fun())

    def _load_custom_commands(self, session):
        """
        Load custom commands from file system.
        Called lazily on first command execution.
        """
        if self.custom_command_service is not None:
            return
        
        try:
            workspace = session.siada_config.workspace if session else os.getcwd()
            loader = FileCommandLoader(workspace, verbose=self.verbose)
            self.custom_command_service = CommandService.create([loader])
            
            if self.verbose:
                custom_cmds = self.custom_command_service.get_commands()
                self.io.print_info(f"Loaded {len(custom_cmds)} custom commands")
        except Exception as e:
            if self.verbose:
                self.io.print_error(f"Failed to load custom commands: {e}")
            # Create empty service to avoid repeated loading attempts
            self.custom_command_service = CommandService([])

    def get_commands(self, session=None):
        commands = []
        
        # Built-in commands
        for attr in dir(self):
            if not attr.startswith("cmd_"):
                continue
            cmd = attr[4:]
            cmd = cmd.replace("_", "-")
            commands.append("/" + cmd)
        
        # Custom commands
        if session:
            self._load_custom_commands(session)
            if self.custom_command_service:
                for name in self.custom_command_service.get_command_names():
                    commands.append("/" + name)
        
        # Skill commands
        if session:
            try:
                from siada.services.skills import SkillsManager
                from pathlib import Path
                workspace = Path(session.siada_config.workspace)
                manager = SkillsManager.get_instance()
                outcome = manager.get_skills(workspace)
                existing = set(commands)
                for skill in outcome.skills:
                    skill_cmd = "/" + skill.name
                    if skill_cmd not in existing:
                        commands.append(skill_cmd)
            except Exception:
                pass
        
        return commands

    def do_run(self, session, cmd_name, args):
        """Execute command with lifecycle event tracking"""
        
        # Normalize command name for internal use
        normalized_cmd_name = cmd_name.replace("-", "_")
        
        # 1. Send task start event
        self._emit_task_start(cmd_name, args)
        
        try:
            cmd_method_name = f"cmd_{normalized_cmd_name}"
            cmd_method = getattr(self, cmd_method_name, None)
            
            # Try built-in command first
            if cmd_method:
                try:
                    # Check the method parameter signature
                    sig = inspect.signature(cmd_method)
                    params = list(sig.parameters.keys())

                    # If the method has a session parameter, pass session and args
                    if 'session' in params:
                        result = cmd_method(session, args)
                    else:
                        # Otherwise only pass args
                        result = cmd_method(args)
                    
                    # 2. Send task complete event (built-in command success)
                    self._emit_task_complete(cmd_name, result)
                    return result
                    
                except Exception as err:
                    # 3. Send task error event (built-in command error)
                    self._emit_task_error(cmd_name, err)
                    self.io.print_error(f"Unable to complete {cmd_name}: {err}")
                    return
            
            # Try custom command
            self._load_custom_commands(session)
            if self.custom_command_service:
                # Convert back from underscore to original format
                original_name = normalized_cmd_name.replace("_", ":")
                custom_cmd = self.custom_command_service.get_command(original_name)
                
                if custom_cmd and custom_cmd.action:
                    spinner = None
                    try:
                        # Build command context
                        context = CommandContext(
                            session=session,
                            workspace=session.siada_config.workspace if session else os.getcwd(),
                            io=self.io,
                            invocation={
                                'raw': f"/{original_name} {args}".strip(),
                                'name': original_name,
                                'args': args,
                            },
                            verbose=self.verbose,
                        )

                        # Only show spinner in interactive mode (same behavior as thinking spinner)
                        try:
                            interactive = (
                                hasattr(session, "siada_config")
                                and getattr(session.siada_config, "interactive", True)
                            )
                        except Exception:
                            interactive = True

                        if interactive:
                            spinner_text = f"Running custom command /{original_name}..."
                            # Pass IO instance so spinner can respect rich panel state if needed
                            spinner = WaitingSpinner(
                                spinner_text,
                                text_color="#79B8FF",
                                io_instance=self.io,
                            )
                            spinner.start()

                        # Execute custom command
                        result = custom_cmd.action(context, args)

                        # Handle result
                        if result.type == "submit_prompt" and result.content:
                            # Return the processed prompt as a SwitchEvent
                            result_to_return = SwitchEvent(ai_analysis_prompt=result.content)
                        else:
                            result_to_return = result

                        # 4. Send task complete event (custom command success)
                        self._emit_task_complete(cmd_name, result_to_return)
                        return result_to_return

                    except Exception as err:
                        # 5. Send task error event (custom command error)
                        self._emit_task_error(cmd_name, err)
                        self.io.print_error(f"Unable to execute custom command {cmd_name}: {err}")
                        if self.verbose:
                            import traceback
                            self.io.print_error(traceback.format_exc())
                        return
                    finally:
                        if spinner is not None:
                            try:
                                spinner.stop()
                            except Exception:
                                # Ignore spinner cleanup errors to avoid breaking command flow
                                pass
            
            # Try skill command
            try:
                from siada.services.skills import SkillsManager
                from pathlib import Path
                workspace = Path(session.siada_config.workspace) if session else Path(os.getcwd())
                manager = SkillsManager.get_instance()
                skill = manager.get_skill_by_name(workspace, cmd_name)
                if skill:
                    prompt = (
                        f"Use the {skill.name} skill.\n\n{args}"
                        if args.strip()
                        else f"Use the {skill.name} skill."
                    )
                    self._emit_task_complete(cmd_name, None)
                    return SwitchEvent(ai_analysis_prompt=prompt)
            except Exception:
                pass

            # Command not found
            error = ValueError(f"Command {cmd_name} not found")
            self._emit_task_error(cmd_name, error)
            self.io.print_info(f"Error: Command {cmd_name} not found.")
            
        except Exception as e:
            # Catch any unexpected errors
            self._emit_task_error(cmd_name, e)
            raise

    def matching_commands(self, inp, session=None):
        words = inp.strip().split()
        if not words:
            return

        first_word = words[0]
        rest_inp = inp[len(words[0]) :].strip()

        all_commands = self.get_commands(session)
        matching_commands = [cmd for cmd in all_commands if cmd.startswith(first_word)]
        return matching_commands, first_word, rest_inp

    def run(self, session, inp):
        """
        Run a command.
        any method called cmd_xxx becomes a command automatically.
        each one must take an args param.
        """
        if inp.startswith("!"):
            return self.do_run(session, "run", inp[1:])

        res = self.matching_commands(inp, session)
        if res is None:
            return
        matching_commands, first_word, rest_inp = res
        if len(matching_commands) == 1:
            command = matching_commands[0][1:]
            return self.do_run(session, command, rest_inp)
        elif first_word in matching_commands:
            command = first_word[1:]
            return self.do_run(session, command, rest_inp)
        elif len(matching_commands) > 1:
            self.io.print_error(f"Ambiguous command: {', '.join(matching_commands)}")
        else:
            # Suppress telemetry for known file-path prefixes to avoid
            # false-positive "invalid command" metrics.
            is_filepath_like = any(
                inp.startswith(prefix) for prefix in _PATH_PREFIX_WHITELIST
            )
            if not is_filepath_like:
                logger.info(
                    f"Unknown command: {first_word}",
                    extra={"event": "slash_command_invalid", "input": first_word},
                )
            self.io.print_error(f"Invalid command: {first_word}")

    def completions_raw_read_only(self, document, complete_event):
        # Get the text before the cursor
        text = document.text_before_cursor

        # Skip the first word and the space after it
        after_command = text.split()[-1]

        # Create a new Document object with the text after the command
        new_document = Document(after_command, cursor_position=len(after_command))

        def get_paths():
            return [self.coder.root] if self.coder.root else None

        path_completer = PathCompleter(
            get_paths=get_paths,
            only_directories=False,
            expanduser=True,
        )

        # Adjust the start_position to replace all of 'after_command'
        adjusted_start_position = -len(after_command)

        # Collect all completions
        all_completions = []

        # Iterate over the completions and modify them
        for completion in path_completer.get_completions(new_document, complete_event):
            quoted_text = self.quote_fname(after_command + completion.text)
            all_completions.append(
                Completion(
                    text=quoted_text,
                    start_position=adjusted_start_position,
                    display=completion.display,
                    style=completion.style,
                    selected_style=completion.selected_style,
                )
            )

        # Add completions from the 'add' command
        add_completions = self.completions_add()
        for completion in add_completions:
            if after_command in completion:
                all_completions.append(
                    Completion(
                        text=completion,
                        start_position=adjusted_start_position,
                        display=completion,
                    )
                )

        # Sort all completions based on their text
        sorted_completions = sorted(all_completions, key=lambda c: c.text)

        # Yield the sorted completions
        for completion in sorted_completions:
            yield completion

    # def cmd_run(self, session, args, add_on_nonzero_exit=False):
    #     "Run a shell command (alias: !)"
    #     exit_status, combined_output = run_cmd(
    #         args,
    #         verbose=self.verbose,
    #         error_print=self.io.print_error,
    #         cwd=session.siada_config.workspace,
    #     )
    #     return combined_output

    def cmd_logout(self, args):
        "Sign out and clear all stored credentials (LiId token and API key)"
        try:
            from siada.internal.services.idaas.auth_store import clear_login_state
            user_id = clear_login_state()
        except ImportError:
            user_id = None
        from siada.entrypoint.login.login_prompt import clear_api_key_config
        api_cleared = clear_api_key_config()
        if user_id:
            self.io.print_info(f"Signed out from {user_id}.")
            logger.info(f"[logout] Signed out: {user_id}")
        elif api_cleared:
            self.io.print_info("API key configuration removed.")
            logger.info("[logout] API key config cleared")
        else:
            self.io.print_info("You were not signed in.")
        sys.exit()

    def cmd_configure(self, session, args):
        "Reconfigure provider API key or switch login method without restarting"
        if not (hasattr(self.io, 'acp_adapter') and self.io.acp_adapter
                and getattr(getattr(self.io.acp_adapter, 'transport', None), 'is_connected', False)):
            self.io.print_error("This command requires the Siada UI.")
            return

        from siada.entrypoint.login.login_prompt import reconfigure_acp, get_applied_api_key_config
        result = reconfigure_acp(self.io)

        if result is None:
            return  # Cancelled — no change

        if result.startswith("api-key-"):
            from siada.provider.models_dev import get_provider_model_configs
            from siada.models.model_base_config import set_user_model_settings
            from siada.models.model_run_config import ModelRunConfig

            api_cfg = get_applied_api_key_config()
            if not api_cfg:
                return
            provider_id = api_cfg.get('provider_id', '')
            new_model = (api_cfg.get('model') or '').strip()
            base_url = (api_cfg.get('base_url') or '').strip()

            provider_models = get_provider_model_configs(provider_id, new_model, base_url)
            if provider_models:
                set_user_model_settings(provider_models)

            if new_model:
                new_llm = ModelRunConfig(new_model)
                new_llm.provider = 'default'
                session.siada_config.llm_config = new_llm
            else:
                session.siada_config.llm_config.provider = 'default'

            return SwitchEvent(model=new_model or session.siada_config.llm_config.model_name)

    def cmd_exit(self, args):
        "Exit the application"
        sys.exit()

    # def cmd_quit(self, args):
    #     "Exit the application"
    #     self.cmd_exit(args)

    def basic_help(self):
        commands = sorted(self.get_commands())
        pad = max(len(cmd) for cmd in commands)
        pad = "{cmd:" + str(pad) + "}"
        
        # Collect all help lines into a list
        help_lines = []
        for cmd in commands:
            cmd_method_name = f"cmd_{cmd[1:]}".replace("-", "_")
            cmd_method = getattr(self, cmd_method_name, None)
            cmd = pad.format(cmd=cmd)
            if cmd_method:
                description = cmd_method.__doc__
                help_lines.append(f"{cmd} {description}")
            else:
                help_lines.append(f"{cmd} No description available.")
        
        # Add empty line and usage tip
        # help_lines.append("")
        # help_lines.append("Use `/help <question>` to ask questions about how to use siadahub.")
        
        # Print all help information in one call
        self.io.print_info("\n".join(help_lines))

    def get_help_md(self):
        "Show help about all commands in markdown"

        res = """
|Command|Description|
|:------|:----------|
"""
        commands = sorted(self.get_commands())
        for cmd in commands:
            cmd_method_name = f"cmd_{cmd[1:]}".replace("-", "_")
            cmd_method = getattr(self, cmd_method_name, None)
            if cmd_method:
                description = cmd_method.__doc__
                res += f"| **{cmd}** | {description} |\n"
            else:
                res += f"| **{cmd}** | |\n"

        res += "\n"
        return res

    # def cmd_map(self, args):
    #     "Print out the current repository map"
    #     repo_map = self.coder.get_repo_map()
    #     if repo_map:
    #         self.io.print_info(repo_map)
    #     else:
    #         self.io.print_info("No repository map available.")

    # def cmd_map_refresh(self, args):
    #     "Force a refresh of the repository map"
    #     repo_map = self.coder.get_repo_map(force_refresh=True)
    #     if repo_map:
    #         self.io.print_info("The repo map has been refreshed, use /map to view it.")

    # def cmd_multiline_mode(self, args):
    #     "Toggle multiline mode (swaps behavior of Enter and Meta+Enter)"
    #     self.io.toggle_multiline_mode()

    def cmd_editor(self, initial_content=""):
        "Open an editor to write a prompt"

        user_input = pipe_editor(initial_content, suffix="md", editor=self.editor)
        if user_input.strip():
            self.io.set_placeholder(user_input.rstrip())

    # def cmd_edit(self, args=""):
    #     "Siada for /editor: Open an editor to write a prompt"
    #     return self.cmd_editor(args)

    def cmd_statusbar(self):
        "Toggle status bar items visibility (handled by frontend UI)"
        # This command is intercepted by the frontend (InputPromptWithWrapUseKPC)
        # and never reaches the backend in ACP mode. The method exists only so
        # that get_commands() includes it in the slash command autocomplete list.
        pass

    def cmd_init(self, session, args):
        """Analyze the project and create a tailored SIADA.md file"""
        try:
            # Get workspace directory from session
            workspace = session.siada_config.workspace
            siada_md_path = os.path.join(workspace, 'SIADA.md')

            # Parse command arguments
            force_overwrite = '--force' in args.strip()

            # Check if file already exists before any operations
            file_exists = os.path.exists(siada_md_path)

            # Check if SIADA.md already exists and user doesn't want to force overwrite
            if file_exists and not force_overwrite:
                self.io.print_info('A SIADA.md file already exists in this directory. No changes were made.')
                self.io.print_info('Use `/init --force` to overwrite the existing file.')
                return

            # Create/overwrite SIADA.md file
            with open(siada_md_path, 'w', encoding='utf-8') as f:
                f.write('')

            # Display appropriate message based on whether file existed
            if file_exists:
                self.io.print_info('Existing SIADA.md overwritten. Now analyzing the project...')
            else:
                self.io.print_info('Empty SIADA.md created. Now analyzing the project...')

            # Generate the analysis prompt
            init_prompt = self._create_init_analysis_prompt(workspace)

            # Return special event to trigger AI analysis with full streaming support
            return SwitchEvent(ai_analysis_prompt=init_prompt)

        except PermissionError:
            self.io.print_error('Permission denied: Unable to create SIADA.md file.')
        except Exception as e:
            self.io.print_error(f'Error during project analysis: {str(e)}')
            import traceback
            self.io.print_error(traceback.format_exc())

    def cmd_context_file_refresh(self, session, args):
        """Refresh SIADA.md and AGENTS.md context files and show content overview"""
        try:
            from siada.services.siada_memory import refresh_siada_memory

            workspace = session.siada_config.workspace
            _, status_message = refresh_siada_memory(workspace)
            self.io.print_info(status_message)

        except Exception as e:
            self.io.print_error(f'Error refreshing context files: {str(e)}')
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())

    # ==================== Rule Memory Commands ====================

    def cmd_rule_init(self, session, args):
        """Create an empty siada_rule.md file"""
        try:
            from siada.services.rule_memory import get_rule_config
            
            workspace = session.siada_config.workspace
            config = get_rule_config()
            file_name = config.get_file_names()[0]
            rule_md_path = os.path.join(workspace, file_name)
            
            # Parse command arguments
            force_overwrite = '--force' in args.strip()
            
            # Check if file already exists
            file_exists = os.path.exists(rule_md_path)
            
            if file_exists and not force_overwrite:
                self.io.print_info(f'A {file_name} file already exists in this directory. No changes were made.\nUse `/rule init --force` to overwrite the existing file.')
                return
            
            # Create/overwrite empty file
            with open(rule_md_path, 'w', encoding='utf-8') as f:
                f.write('')
            
            # Display appropriate message
            message_lines = []
            if file_exists:
                message_lines.append(f'Existing {file_name} overwritten with empty file.')
            else:
                message_lines.append(f'Empty {file_name} file created.')
            
            message_lines.append(f'File location: {rule_md_path}')
            message_lines.append(f'You can now edit this file to add your context.')
            self.io.print_info('\n'.join(message_lines))
            
        except PermissionError:
            self.io.print_error(f'Permission denied: Unable to create {file_name} file.')
        except Exception as e:
            self.io.print_error(f'Error creating file: {str(e)}')
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())
    
    def cmd_rule_show(self, session, args):
        """Display combined hierarchical context content"""
        try:
            from siada.services.rule_memory import load_hierarchical_context
            
            workspace = session.siada_config.workspace
            
            self.io.print_info("Loading hierarchical context...")
            
            combined_content, file_count, file_paths = load_hierarchical_context(
                workspace,
                debug=self.verbose,
                process_imports=True
            )
            
            if not combined_content:
                self.io.print_info("No context files found.\nUse `/rule init` to create a context file.")
                return
            
            # Collect all output into a single string
            output_lines = [
                f"\nLoaded {file_count} context file(s):\n",
                "=" * 80,
                combined_content,
                "=" * 80,
                f"\nTotal content length: {len(combined_content)} characters"
            ]
            self.io.print_info("\n".join(output_lines))
            
        except Exception as e:
            self.io.print_error(f'Error showing context: {str(e)}')
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())
    
    def cmd_rule_refresh(self, session, args):
        """Refresh hierarchical context content"""
        try:
            from siada.services.rule_memory import load_hierarchical_context
            
            workspace = session.siada_config.workspace
            
            self.io.print_info("Refreshing hierarchical context...")
            
            combined_content, file_count, file_paths = load_hierarchical_context(
                workspace,
                debug=self.verbose,
                process_imports=True
            )

            if file_count > 0:
                self.io.print_info(f"Successfully refreshed {file_count} context file(s)\nTotal content: {len(combined_content)} characters")
            else:
                self.io.print_info("No context files found\nUse `/rule init` to create a context file")
            
        except Exception as e:
            self.io.print_error(f'Error refreshing context: {str(e)}')
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())
    
    def cmd_rule_list(self, session, args):
        """List all loaded hierarchical context files"""
        try:
            from siada.services.rule_memory import load_hierarchical_context
            
            workspace = session.siada_config.workspace
            
            combined_content, file_count, file_paths = load_hierarchical_context(
                workspace,
                debug=False,
                process_imports=False  # Don't process imports, just list files
            )
            
            if file_count == 0:
                self.io.print_info("No context files found\nUse `/rule init` to create a context file")
                return
            
            # Collect all file information
            output_lines = [f"Found {file_count} context file(s):\n"]
            
            for i, file_path in enumerate(file_paths, 1):
                # Show relative path if possible
                try:
                    rel_path = os.path.relpath(file_path, workspace)
                    output_lines.append(f"{i}. {rel_path}")
                except ValueError:
                    output_lines.append(f"{i}. {file_path}")
                
                # Show file size
                try:
                    size = os.path.getsize(file_path)
                    output_lines.append(f"   Size: {size} bytes")
                except:
                    pass
            
            self.io.print_info("\n".join(output_lines))
            
        except Exception as e:
            self.io.print_error(f'Error listing context files: {str(e)}')
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())
    
    def cmd_rule_global_add(self, session, args):
        """Add memory entry to global context file"""
        try:
            from siada.services.rule_memory import get_rule_config
            
            if not args.strip():
                self.io.print_error("Please provide text to add")
                self.io.print_info("Usage: /rule add <text>")
                return
            
            config = get_rule_config()
            global_file = config.get_global_file_path()
            
            # Read existing content
            if os.path.exists(global_file):
                with open(global_file, 'r', encoding='utf-8') as f:
                    content = f.read()
            else:
                content = ""
            
            # Find or create "## Rule Added Memories" section
            memory_section = "## Rule Added Memories"
            
            if memory_section in content:
                # Append to existing section
                new_entry = f"- {args.strip()}"
                # Add after the section header
                parts = content.split(memory_section, 1)
                if len(parts) == 2:
                    # Find the end of the section (next ## or end of file)
                    after_section = parts[1]
                    next_section = after_section.find('\n##')
                    
                    if next_section > 0:
                        # Insert before next section
                        updated_content = (
                            parts[0] + memory_section + 
                            after_section[:next_section] + 
                            f"\n{new_entry}\n" +
                            after_section[next_section:]
                        )
                    else:
                        # Append at end
                        updated_content = content.rstrip() + f"\n{new_entry}\n"
                else:
                    updated_content = content + f"\n{new_entry}\n"
            else:
                # Create new section
                if content:
                    updated_content = content.rstrip() + f"\n\n{memory_section}\n- {args.strip()}\n"
                else:
                    updated_content = f"{memory_section}\n- {args.strip()}\n"
            
            # Collect all output into a single string
            output_lines = [
                "\nAdding to global context file:",
                f"File: {global_file}",
                f"\nNew entry: {args.strip()}"
            ]
            
            # Write to file
            os.makedirs(os.path.dirname(global_file), exist_ok=True)
            with open(global_file, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            
            output_lines.append("\n✓ Memory added successfully")
            self.io.print_info("\n".join(output_lines))
            
        except Exception as e:
            self.io.print_error(f'Error adding memory: {str(e)}')
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())
    
    def cmd_rule_status(self, session, args):
        """Display current hierarchical context status"""
        try:
            from siada.services.rule_memory import load_hierarchical_context, get_rule_config
            
            workspace = session.siada_config.workspace
            config = get_rule_config()
            
            # Collect all status information
            status_lines = [
                "Rule Memory Status\n",
                "Configuration:",
                f"  File names: {', '.join(config.get_file_names())}",
                f"  Import format: {config.get_import_format()}",
                f"  Max directories: {config.get_max_dirs()}",
                f"  Enable subdirectories: {config.get_enable_subdirectories()}",
                f"  Respect .gitignore: {config.get_respect_gitignore()}",
                f"  Respect .siadaignore: {config.get_respect_siadaignore()}",
                "\nDiscovering context files..."
            ]
            
            combined_content, file_count, file_paths = load_hierarchical_context(
                workspace,
                debug=False,
                process_imports=False
            )
            
            status_lines.append(f"\nFiles found: {file_count}")
            
            if file_count > 0:
                status_lines.append(f"Total content size: {len(combined_content)} characters")
            else:
                status_lines.append("\nNo context files found")
                status_lines.append("Use `/rule init` to create a context file")
            
            self.io.print_info("\n".join(status_lines))
            
        except Exception as e:
            self.io.print_error(f'Error checking status: {str(e)}')
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())

    # ==================== MCP Helper Methods ====================
    
    def _refresh_mcp_connection(self):
        """
        Refresh MCP connections after configuration changes (e.g., OAuth token update).
        
        Instead of establishing new connections in a temporary event loop (which would
        die when the temp loop closes), we invalidate the current state and reload config.
        The lazy initialization in SiadaRunner._configure_mcp_servers() will establish
        new connections in the correct event loop when the next agent run begins.
        """
        try:
            success = mcp_service.reload_config()
            if success:
                self.io.print_info("✅ MCP configuration reloaded. New connections will be established on next message.")
            else:
                self.io.print_warning("⚠️ MCP configuration reload failed")
            return success
        except Exception as e:
            self.io.print_error(f"Error refreshing MCP connection: {e}")
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())
            return False
    
    # ==================== Migrate Commands ====================

    def cmd_migrate_detect(self, session, args):
        """Detect migratable config/skills/context from Claude Code and Codex"""
        try:
            from pathlib import Path
            from siada.config.external_agent_migration import ExternalAgentMigrationService

            workspace = session.siada_config.workspace
            svc = ExternalAgentMigrationService()
            items = svc.detect(include_home=True, cwds=[Path(workspace)])

            if not items:
                self.io.print_info(
                    "Nothing to migrate – no Claude Code or Codex config found,\n"
                    "or everything has already been imported."
                )
                return

            lines = [f"Found {len(items)} item(s) to migrate:\n"]
            for i, item in enumerate(items, 1):
                lines.append(f"  {i}. [{item.source.value}] {item.description}")
            lines.append("\nRun `/migrate-import` to import all items.")
            self.io.print_info("\n".join(lines))

        except Exception as e:
            self.io.print_error(f"Error during migration detection: {e}")
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())

    def cmd_migrate_import(self, session, args):
        """Import config/skills/context from Claude Code and Codex into Siada"""
        try:
            from pathlib import Path
            from siada.config.external_agent_migration import ExternalAgentMigrationService

            workspace = session.siada_config.workspace
            svc = ExternalAgentMigrationService()
            items = svc.detect(include_home=True, cwds=[Path(workspace)])

            if not items:
                self.io.print_info(
                    "Nothing to migrate – no Claude Code or Codex config found,\n"
                    "or everything has already been imported."
                )
                return

            self.io.print_info(f"Importing {len(items)} item(s)...")
            svc.import_items(items)

            lines = [f"Migration complete. Imported {len(items)} item(s):\n"]
            for item in items:
                lines.append(f"  ✓ [{item.source.value}] {item.description}")
            self.io.print_info("\n".join(lines))

        except Exception as e:
            self.io.print_error(f"Error during migration: {e}")
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())

    # ==================== MCP Commands ====================

    def cmd_mcp_server(self, session, args):
        """List all MCP servers and their connection status"""
        try:
            # Use the already imported mcp_service from top of file (manager_service)
            if not mcp_service.has_config():
                self.io.print_info("No MCP servers configured")
                return

            if not mcp_service.is_initialized:
                self.io.print_info("MCP service not initialized\nMCP servers will be initialized when first needed")
                return

            # Get server status using asyncio in a thread
            def get_status():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(mcp_service.get_real_server_status())
                    finally:
                        loop.close()
                except Exception as e:
                    self.io.print_error(f"Failed to get server status: {e}")
                    return {}

            with WaitingSpinner("Checking server status..."):
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(get_status)
                    server_status = future.result()

            if not server_status:
                self.io.print_info("No MCP servers available")
                return

            # Collect all server status information
            status_lines = ["MCP Server Status:", ""]

            for server_name, status in server_status.items():
                # Status icon
                if status == "connected":
                    icon = "🟢"
                    status_text = "Ready"
                elif status == "timeout":
                    icon = "🟡"
                    status_text = "Timeout"
                else:
                    icon = "🔴"
                    status_text = "Failed"

                status_lines.append(f"{icon} {server_name} - {status_text}")
            
            self.io.print_info("\n".join(status_lines))

        except Exception as e:
            self.io.print_error(f"Error listing MCP servers: {e}")
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())

    def cmd_mcp_list(self, session, args):
        """List all MCP servers and their available tools"""
        try:
            # Use the already imported mcp_service from top of file (manager_service)
            if not mcp_service.has_config():
                self.io.print_info("No MCP servers configured")
                return

            if not mcp_service.is_initialized:
                self.io.print_info("MCP service not initialized\nMCP servers will be initialized when first needed")
                return

            # Get server status and tools using asyncio in a thread
            def get_server_info():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        status_task = mcp_service.get_real_server_status()
                        tools_task = mcp_service.list_tools_async()
                        status = loop.run_until_complete(status_task)
                        tools_by_server = loop.run_until_complete(tools_task)
                        return status, tools_by_server
                    finally:
                        loop.close()
                except Exception as e:
                    self.io.print_error(f"Failed to get server info: {e}")
                    return {}, {}

            with WaitingSpinner("Loading MCP server information..."):
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(get_server_info)
                    server_status, tools_by_server = future.result()

            if not server_status and not tools_by_server:
                self.io.print_info("No MCP servers available")
                return

            # Collect all server and tool information
            output_lines = ["MCP Servers and Tools:", ""]

            # Combine all server names from status and tools
            all_servers = set(server_status.keys()) | set(tools_by_server.keys())

            for server_name in sorted(all_servers):
                status = server_status.get(server_name, "unknown")
                tools = tools_by_server.get(server_name, [])

                # Status icon
                if status == "connected":
                    icon = "🟢"
                    status_text = "Ready"
                elif status == "timeout":
                    icon = "🟡"
                    status_text = "Timeout"
                else:
                    icon = "🔴"
                    status_text = "Failed"

                # Display server info with tool count
                tool_count = len(tools)
                output_lines.append(f"{icon} {server_name} - {status_text} ({tool_count} tools)")

                # Display tools if available
                if tools:
                    output_lines.append("  Tools:")
                    for tool_name in sorted(tools):
                        output_lines.append(f"  - {tool_name}")
                elif status == "connected":
                    output_lines.append("  No tools available")

                output_lines.append("")
            
            self.io.print_info("\n".join(output_lines))

        except Exception as e:
            self.io.print_error(f"Error listing MCP tools: {e}")
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())

    # ==================== Lark OAuth Commands ====================

    def cmd_lark_auth(self, session, args):
        """Authenticate with Lark MCP server using OAuth 2.0"""
        try:
            # Use the already imported mcp_service from top of file (manager_service)
            from siada.services.mcp.oauth import LarkOAuthManager
            from siada.foundation.constants import SIADA_HOME
            from pathlib import Path

            # Check if lark-mcp is configured
            if not mcp_service.has_config():
                self.io.print_error("MCP service is not configured")
                return

            mcp_config = mcp_service.get_mcp_config()
            if not mcp_config or 'lark-mcp' not in mcp_config.servers:
                self.io.print_error("lark-mcp server is not configured")
                self.io.print_info("Please add lark-mcp server configuration in ~/.siada-cli/mcp_config.json")
                return

            # Find config file path
            config_path = SIADA_HOME / "mcp_config.json"
            if not config_path.exists():
                # Try project config
                config_path = Path.cwd() / "siada_mcp_config.json"
                if not config_path.exists():
                    self.io.print_error("MCP config file not found")
                    return

            # Start OAuth flow
            def do_auth():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        manager = LarkOAuthManager(mcp_config, config_path)
                        return loop.run_until_complete(manager.start_oauth_flow())
                    finally:
                        loop.close()
                except Exception as e:
                    raise e

            self.io.print_info("Starting Lark OAuth authentication...")
            self.io.print_info("Your browser will open for authorization.\n")

            with WaitingSpinner("Waiting for authorization..."):
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(do_auth)
                    try:
                        token_data = future.result()
                        self.io.print_info("\n✅ Authorization successful!")
                        self.io.print_info("MCP configuration has been updated.\n")
                        
                        # Refresh MCP connections after successful authentication
                        self._refresh_mcp_connection()
                    except Exception as e:
                        self.io.print_error(f"\n❌ Authorization failed: {e}")
                        if self.verbose:
                            import traceback
                            self.io.print_error(traceback.format_exc())

        except Exception as e:
            self.io.print_error(f"Error during Lark authentication: {e}")
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())

    def cmd_lark_status(self, session, args):
        """Show Lark MCP authentication status"""
        try:
            # Use the already imported mcp_service from top of file (manager_service)
            import time

            # Check if lark-mcp is configured
            if not mcp_service.has_config():
                self.io.print_error("MCP service is not configured")
                return

            mcp_config = mcp_service.get_mcp_config()
            if not mcp_config or 'lark-mcp' not in mcp_config.servers:
                self.io.print_error("lark-mcp server is not configured")
                return

            server_config = mcp_config.servers['lark-mcp']
            oauth_data = server_config.oauth

            status_lines = ["Lark MCP Authentication Status:", ""]

            if not oauth_data:
                status_lines.append("🔴 Not authenticated")
                status_lines.append("\nUse '/lark auth' to authenticate")
            else:
                token_created_time = oauth_data.get('token_created_time', 0)
                expires_in = oauth_data.get('expires_in', 7200)
                refresh_token_expires_in = oauth_data.get('refresh_token_expires_in', 604800)

                # Calculate expiry times
                current_time = int(time.time() * 1000)
                token_expiry_time = token_created_time + (expires_in * 1000)
                refresh_expiry_time = token_created_time + (refresh_token_expires_in * 1000)

                # Token status
                if current_time >= token_expiry_time:
                    status_lines.append("🟡 Access token expired")
                elif current_time >= (token_expiry_time - 5 * 60 * 1000):
                    status_lines.append("🟡 Access token expiring soon")
                else:
                    status_lines.append("🟢 Access token valid")

                # Time remaining
                token_remaining_sec = max(0, (token_expiry_time - current_time) // 1000)
                if token_remaining_sec > 0:
                    token_remaining_min = token_remaining_sec // 60
                    status_lines.append(f"   Expires in: {token_remaining_min} minutes")
                else:
                    status_lines.append("   Expired")

                status_lines.append("")

                # Refresh token status
                if current_time >= refresh_expiry_time:
                    status_lines.append("🔴 Refresh token expired")
                    status_lines.append("   Use '/lark auth' to re-authenticate")
                else:
                    refresh_remaining_sec = (refresh_expiry_time - current_time) // 1000
                    refresh_remaining_hours = refresh_remaining_sec // 3600
                    status_lines.append("🟢 Refresh token valid")
                    status_lines.append(f"   Expires in: {refresh_remaining_hours} hours")

            self.io.print_info("\n".join(status_lines))

        except Exception as e:
            self.io.print_error(f"Error checking Lark status: {e}")
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())

    def cmd_lark_refresh(self, session, args):
        """Manually refresh Lark access token"""
        try:
            # Use the already imported mcp_service from top of file (manager_service)
            from siada.services.mcp.oauth import LarkOAuthManager
            from siada.foundation.constants import SIADA_HOME
            from pathlib import Path

            # Check if lark-mcp is configured
            if not mcp_service.has_config():
                self.io.print_error("MCP service is not configured")
                return

            mcp_config = mcp_service.get_mcp_config()
            if not mcp_config or 'lark-mcp' not in mcp_config.servers:
                self.io.print_error("lark-mcp server is not configured")
                return

            # Find config file path
            config_path = SIADA_HOME / "mcp_config.json"
            if not config_path.exists():
                config_path = Path.cwd() / "siada_mcp_config.json"
                if not config_path.exists():
                    self.io.print_error("MCP config file not found")
                    return

            # Refresh token
            def do_refresh():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        manager = LarkOAuthManager(mcp_config, config_path)
                        return loop.run_until_complete(manager.refresh_access_token())
                    finally:
                        loop.close()
                except Exception as e:
                    raise e

            self.io.print_info("Refreshing Lark access token...")

            with WaitingSpinner("Refreshing..."):
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(do_refresh)
                    try:
                        token_data = future.result()
                        self.io.print_info("\n✅ Token refreshed successfully!\n")
                        
                        # Refresh MCP connections after successful token refresh
                        self._refresh_mcp_connection()
                    except Exception as e:
                        error_msg = str(e)
                        if "expired" in error_msg.lower():
                            self.io.print_error("\n❌ Refresh token expired")
                            self.io.print_info("Use '/lark auth' to re-authenticate")
                        else:
                            self.io.print_error(f"\n❌ Token refresh failed: {e}")
                            if self.verbose:
                                import traceback
                                self.io.print_error(traceback.format_exc())

        except Exception as e:
            self.io.print_error(f"Error refreshing Lark token: {e}")
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())

    def _create_init_analysis_prompt(self, workspace):
        """Create the analysis prompt for /init command"""

        init_prompt = """You are an AI agent that brings the power of Siada directly into the terminal. Your task is to analyze the current directory and generate a comprehensive SIADA.md file to be used as instructional context for future interactions.

**Analysis Process:**

1.  **Initial Exploration:**
    *   Start by listing the files and directories to get a high-level overview of the structure.
    *   Read the README file (e.g., `README.md`, `README.txt`) if it exists. This is often the best place to start.

2.  **Iterative Deep Dive (up to 10 files):**
    *   Based on your initial findings, select a few files that seem most important (e.g., configuration files, main source files, documentation).
    *   Read them. As you learn more, refine your understanding and decide which files to read next. You don't need to decide all 10 files at once. Let your discoveries guide your exploration.

3.  **Identify Project Type:**
    *   **Code Project:** Look for clues like `package.json`, `requirements.txt`, `pom.xml`, `go.mod`, `Cargo.toml`, `build.gradle`, or a `src` directory. If you find them, this is likely a software project.
    *   **Non-Code Project:** If you don't find code-related files, this might be a directory for documentation, research papers, notes, or something else.

**SIADA.md Content Generation:**

**For a Code Project:**

*   **Project Overview:** Write a clear and concise summary of the project's purpose, main technologies, and architecture.
*   **Building and Running:** Document the key commands for building, running, and testing the project. Infer these from the files you've read (e.g., `scripts` in `package.json`, `Makefile`, etc.). If you can't find explicit commands, provide a placeholder with a TODO.
*   **Development Conventions:** Describe any coding styles, testing practices, or contribution guidelines you can infer from the codebase.

**For a Non-Code Project:**

*   **Directory Overview:** Describe the purpose and contents of the directory. What is it for? What kind of information does it hold?
*   **Key Files:** List the most important files and briefly explain what they contain.
*   **Usage:** Explain how the contents of this directory are intended to be used.

**Final Output:**

Write the complete content to the `SIADA.md` file. The output must be well-formatted Markdown."""

        return init_prompt.strip()

    def cmd_compare(self, session, args: str):
        "Compare files between working directory and checkpoint"

        from rich.syntax import Syntax
        from rich.panel import Panel
        from rich import box

        # Parse checkpoint filename from args
        checkpoint_filename = args.strip()
        if not checkpoint_filename:
            self.io.print_error("Please provide a checkpoint filename. Usage: /compare <checkpoint_filename>")
            return

        # Check if checkpoint_tracker is available
        if not hasattr(session, 'checkpoint_tracker') or not session.checkpoint_tracker:
            self.io.print_error("Checkpoint tracking is not enabled for this session")
            return

        try:
            # Get the checkpoint data
            checkpoint_data: CheckPointData = (
                session.checkpoint_tracker.get_checkpoint_data_by_file_name(
                    checkpoint_filename
                )
            )
            if not checkpoint_data:
                self.io.print_error(f"Checkpoint file '{checkpoint_filename}' not found")
                return

            # Get diff hunks between checkpoint and working directory
            diff_hunks = session.checkpoint_tracker.get_diff_set_hunks(
                checkpoint_data.last_commit_hash,
                None  # None means compare with working directory
            )

            # Check if pretty output is enabled
            if self.io.pretty and False:
                # Pretty output with Rich formatting
                # Create a header panel
                header_text = f"[bold cyan]Comparing with checkpoint:[/bold cyan] [yellow]{checkpoint_filename}[/yellow]"
                header_panel = Panel(
                    header_text,
                    box=box.DOUBLE_EDGE,
                    border_style="bright_blue",
                    padding=(0, 2)
                )

                # Use io.console to print Rich components
                self.io.console.print(header_panel)
                self.io.console.print()

                # Print the diff hunks with syntax highlighting
                if diff_hunks.strip():
                    # Get code theme from running config
                    code_theme = session.siada_config.running_color_settings.code_theme or "monokai"

                    # Create a diff syntax object with highlighting
                    syntax = Syntax(
                        diff_hunks,
                        "diff",
                        theme=code_theme,  # Use theme from running config
                        line_numbers=True,
                        word_wrap=True,
                        background_color="default"
                    )

                    # Wrap the syntax-highlighted diff in a panel
                    diff_panel = Panel(
                        syntax,
                        title="[bold]Differences between checkpoint and working directory[/bold]",
                        border_style="green",
                        box=box.ROUNDED,
                        padding=(1, 2)
                    )

                    # Use io.console to print the diff panel
                    self.io.console.print(diff_panel)
                else:
                    # No differences found - display a friendly message
                    no_diff_panel = Panel(
                        "[green]✓[/green] No differences found between checkpoint and working directory",
                        border_style="green",
                        box=box.ROUNDED,
                        padding=(0, 2)
                    )
                    # Use io.console to print the panel
                    self.io.console.print(no_diff_panel)
            else:
                # Simple text output for non-pretty mode
                # Combine all output into a single print_info call to reduce lifecycle events
                output_lines = [
                    f"Comparing with checkpoint: {checkpoint_filename}",
                    ""
                ]
                
                if diff_hunks.strip():
                    output_lines.extend([
                        "Differences between checkpoint and working directory:",
                        "=" * 60,
                        diff_hunks
                    ])
                else:
                    output_lines.append("No differences found between checkpoint and working directory")
                
                self.io.print_info("\n".join(output_lines))

        except Exception as e:
            self.io.print_error(f"Failed to compare with checkpoint: {str(e)}")
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())

    def _validate_checkpoint_operation(self, session, checkpoint_filename: str, operation_name: str) -> CheckPointData:
        """
        Validate checkpoint operation prerequisites and return checkpoint data.

        Args:
            session: The current session
            checkpoint_filename: Name of the checkpoint file
            operation_name: Name of the operation (for error messages)

        Returns:
            CheckPointData if validation successful, None otherwise
        """
        # Parse checkpoint filename from args
        if not checkpoint_filename:
            self.io.print_error(f"Please provide a checkpoint filename. Usage: /{operation_name} <checkpoint_filename>")
            return None

        # Check if checkpoint_tracker is available
        if not hasattr(session, 'checkpoint_tracker') or not session.checkpoint_tracker:
            self.io.print_error("Checkpoint tracking is not enabled for this session")
            return None

        # Get the checkpoint data
        checkpoint_data: CheckPointData = (
            session.checkpoint_tracker.get_checkpoint_data_by_file_name(
                checkpoint_filename
            )
        )
        if not checkpoint_data:
            self.io.print_error(f"Checkpoint file '{checkpoint_filename}' not found")
            return None

        return checkpoint_data

    def _process_checkpoint_history(self, checkpoint_data: CheckPointData, operation_type: str) -> list:
        """
        Process checkpoint history and add appropriate function call output.

        Args:
            checkpoint_data: The checkpoint data
            operation_type: 'undo' or 'restore' to determine the message content

        Returns:
            Processed history list or None if processing failed
        """
        import copy
        restored_history = copy.deepcopy(checkpoint_data.history)

        if restored_history:
            last_message = restored_history[-1]
            # Use message_classifier to identify message type
            role, item_type = get_role_and_type_from_item(last_message)

            # Fast fail: only process function_call_output from tool
            if not (role == "tool" and item_type == "function_call_output"):
                # Not a function call, skip processing
                self.io.print_error(
                    f"{operation_type} checkpoint failed: last message is not a function call from assistant"
                )
                return None
            else:
                if operation_type == "undo":
                    # if operation_type = undo, add a user message indicating undo
                    last_message = restored_history[-2]
                    function = last_message.get("name", "unknown_function")
                    restored_history.append(
                        {
                            "role": "user",
                            "content": f"The user reverted the changes made by the {function} tool",
                        }
                    )

        return restored_history

    def _sync_api_message_to_file(self, session) -> None:
        """
        Sync the current in-memory real API messages to api_messages.json for persistence.

        Called after checkpoint undo/restore so the file reflects the restored state.
        Delegates to SessionManager.sync_api_messages for the actual file I/O.
        """
        from siada.services.session_management import SessionManager

        # Resolve session directory path via SessionManager helper
        session_path = SessionManager.resolve_session_path(
            session.siada_config.workspace, session.session_id
        )

        # Extract real API messages from in-memory state
        real_messages = session.task_message_state._real_messages
        if real_messages is not None:
            real_api_history = real_messages.real_api_history
            last_index = real_messages.last_index
            last_signature = real_messages.last_signature
        else:
            real_api_history = []
            last_index = -1
            last_signature = ""

        # Derive tokens_count from restored usage (best-effort)
        tokens_count = 0
        usage = getattr(session.state, "usage", None)
        if usage is not None:
            tokens_count = getattr(usage, "total_tokens", 0) or 0

        # Delegate to SessionManager (raises OSError on failure → triggers rollback)
        SessionManager.sync_api_messages(
            session_path=session_path,
            session_id=session.session_id,
            api_messages=real_api_history,
            tokens_count=tokens_count,
            last_index=last_index,
            last_signature=last_signature,
        )

    def _manage_session_and_restore(self, session, target_commit_hash, restore_history, checkpoint_data):
        """
        Manage OpenAI session clearing and project state restoration with rollback.

        Args:
            session: The current session
            target_commit_hash: The commit hash to restore to
            restore_history: The history to restore
            checkpoint_data: The checkpoint data containing real_api_message and usage

        Returns:
            True if successful, False otherwise
        """
        import asyncio

        async def async_operations():
            # Save old messages and usage for rollback
            old_real_items = session.task_message_state._real_messages
            old_items = await session.state.openai_session.get_items()
            old_usage = session.state.usage
            
            # Reset the openai session with the restore history
            await session.state.openai_session.safe_reset_items(restore_history)
            
            # Restore RealApiMessage object (if checkpoint has it saved)
            if checkpoint_data.real_api_message is not None:
                from siada.session.task_message_state import RealApiMessage
                real_api_message = RealApiMessage.from_dict(checkpoint_data.real_api_message)
                session.task_message_state.set_real_messages(real_api_message)
            else:
                # Old checkpoint without real_api_message, reset it
                session.task_message_state.reset_real_messages()
            
            # Restore Usage object using utility function
            restored_usage = deserialize_usage(checkpoint_data.usage)
            session.state.usage = restored_usage
            
            return old_items, old_real_items, old_usage

        # Run all async operations in one event loop
        old_items, old_real_items, old_usage = asyncio.run(async_operations())

        # Backup api_messages.json before mutating, so we can roll it back
        # if the subsequent git restore fails.
        from siada.services.session_management import SessionManager
        api_messages_file = SessionManager.resolve_api_messages_file(
            session.siada_config.workspace, session.session_id
        )
        file_existed_before = api_messages_file.exists()
        file_backup_bytes = api_messages_file.read_bytes() if file_existed_before else None

        try:
            # Step 1: Sync restored real API messages to api_messages.json first.
            # If file I/O fails here, git hasn't been touched yet — safe to fail fast.
            self._sync_api_message_to_file(session)
            # Step 2: Restore the project state via git.
            session.checkpoint_tracker.git_service.restore_project_from_snapshot(
                target_commit_hash
            )
            return True
        except BaseException as e:
            # On any failure (file sync or git restore), roll back everything:
            # api_messages.json, then the in-memory OpenAI session / task state / usage.
            self.io.print_error(f"Failed to restore project state: {str(e)}")

            # Roll back api_messages.json to its pre-sync content
            try:
                if file_existed_before:
                    api_messages_file.write_bytes(file_backup_bytes)
                elif api_messages_file.exists():
                    api_messages_file.unlink()
            except OSError as rollback_err:
                self.io.print_error(
                    f"Failed to rollback api_messages.json: {rollback_err}"
                )

            async def rollback_operations():
                await session.state.openai_session.safe_reset_items(old_items)
                session.task_message_state.set_real_messages(old_real_items)
                session.state.usage = old_usage

            asyncio.run(rollback_operations())
            return False

    def cmd_resume(self, session, args: str):
        """Resume a previous session

        Usage:
            /resume              - List current project sessions (opens UI browser in UI mode)
            /resume --all        - List all projects sessions
            /resume --global     - List all projects sessions (alias)
            /resume latest       - Resume the most recent session
            /resume <index>      - Resume session by index number
            /resume <session_id> - Resume session by ID
        """
        from siada.support.resume_service import ResumeService

        resume_service = ResumeService(session.siada_config.workspace)

        args_stripped = args.strip()
        scope = 'current'
        identifier = None

        if args_stripped in ['--all', '--global']:
            scope = 'all'
        elif args_stripped.startswith('--all ') or args_stripped.startswith('--global '):
            scope = 'all'
            identifier = args_stripped.split(maxsplit=1)[1] if ' ' in args_stripped else None
        else:
            identifier = args_stripped if args_stripped else None

        if not identifier:
            # Check if in UI mode (has ACP adapter)
            if hasattr(self.io, 'acp_adapter') and self.io.acp_adapter is not None:
                # UI mode: send notification to let frontend open SessionBrowser
                try:
                    from siada.io.acp.message_builder import ACPMessageBuilder

                    # Build notification message to open SessionBrowser
                    message = ACPMessageBuilder().build_custom_notification(
                        method="ui/showSessionBrowser",
                        params={
                            "scope": scope,
                            "projectRoot": session.siada_config.workspace
                        }
                    )

                    # Send to frontend (using transport.send_sync)
                    if self.io.acp_adapter.transport and self.io.acp_adapter.transport.is_connected:
                        self.io.acp_adapter.transport.send_sync(message)
                        logger.info(f"Sent ui/showSessionBrowser notification to frontend with scope={scope}")
                    else:
                        logger.warning("ACP transport not connected, falling back to text mode")
                        result = resume_service.list_sessions(scope=scope)
                        self.io.tool_output(result)
                except Exception as e:
                    logger.error(f"Failed to send SessionBrowser notification: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    # Fall back to print mode
                    result = resume_service.list_sessions(scope=scope)
                    self.io.tool_output(result)
            else:
                # Non-UI mode: print list directly
                result = resume_service.list_sessions(scope=scope)
                self.io.tool_output(result)
            return

        # Fast workspace check before loading full session data
        session_info = resume_service.get_session_info(identifier)
        if session_info is None:
            self.io.print_error(f"Session not found: {identifier}")
            return
        origin_root = session_info.project_root or ''
        current_ws = session.siada_config.workspace
        if origin_root and origin_root != 'Unknown' and os.path.normpath(origin_root) != os.path.normpath(current_ws):
            self.io.print_warning(f"Session belongs to workspace: {origin_root}")
            self.io.print_info(
                f"To resume this session, run:  cd {origin_root} && siada-cli --resume {session_info.session_id}"
            )
            return

        # Execute resume
        result = resume_service.execute(identifier)

        if result and result[0]:
            session_data, message = result
            # Restore session
            resume_service.restore_to_running_session(session_data, session)

            # Re-send banner so frontend gets the resumed session's correct session_id
            if hasattr(self, '_controller') and self._controller is not None:
                self._controller.show_announcements()

            # In UI mode, send history messages to frontend
            if hasattr(self.io, 'acp_adapter') and self.io.acp_adapter is not None:
                self._send_history_to_ui(session_data.items)

            # Re-push the resumed session's goal state (if any) so the
            # GoalStatusBar reappears immediately, instead of staying blank
            # until the next conversation turn happens to run
            # SiadaRunner._prepare_context_for_run's lazy
            # pending_goal -> context.goal consumption. restore_to_running_
            # session() already staged (or explicitly cleared) this on
            # session.state.pending_goal -- see its docstring/comment for
            # why that's the reliable place to read it from here rather
            # than re-deriving it.
            self._push_resumed_goal_state_to_ui(session)
        else:
            error_message = result[1] if result else "Unknown error"
            self.io.print_error(error_message)

    def _push_resumed_goal_state_to_ui(self, session) -> None:
        """Push the just-resumed session's goal state (or an explicit
        "no goal" clear) to the frontend via ``context/goalState``.

        Only relevant in ACP/UI mode -- plain-terminal mode has no
        GoalStatusBar to update. objective/status/createdAt/turns are all
        already persisted to goal.json on every save_goal() call throughout
        the goal's lifecycle (see goal_storage.py / turn_hooks.py), so no
        extra persistence work is needed here -- this only needs to
        RE-SEND that already-durable state to a freshly (re)connected
        frontend.
        """
        if not (hasattr(self.io, 'acp_adapter') and self.io.acp_adapter is not None):
            return

        goal = session.state.pending_goal
        if goal is None:
            # No goal.json for this session (never set, or cleared before
            # disconnecting) -- explicitly clear any stale status bar the
            # frontend might still be showing from a previous session.
            self.io.acp_adapter._send_if_acp(
                self.io.acp_adapter.builder.build_custom_notification,
                method="context/goalState",
                params={"goal": None, "verifying": False},
            )
            return

        self.io.acp_adapter._send_if_acp(
            self.io.acp_adapter.builder.build_custom_notification,
            method="context/goalState",
            params={
                "goal": {
                    "objective": goal.objective,
                    "status": goal.status,
                    "createdAt": goal.created_at,
                    "turns": goal.turns,
                },
                "verifying": False,
            },
        )


    def _send_history_to_ui(self, items: list):
        """Send history messages to frontend UI via ui/loadHistory notification.

        Uses shared format_native_items_for_display() to convert native items
        to display messages, then sends as ui/loadHistory (clear + load).
        """
        try:
            from siada.io.acp.message_builder import ACPMessageBuilder
            from siada.support.message_classifier import format_native_items_for_display

            messages = format_native_items_for_display(items)
            
            batch_notification = ACPMessageBuilder().build_custom_notification(
                method="ui/loadHistory",
                params={"messages": messages},
            )

            if self.io.acp_adapter.transport and self.io.acp_adapter.transport.is_connected:
                self.io.acp_adapter.transport.send_sync(batch_notification)
                logger.info(f"Sent {len(messages)} history messages to UI (batch)")
                
        except Exception as e:
            logger.warning(f"Failed to send history to UI: {e}")

    def cmd_undo(self, session, args: str):
        "Undo the target checkpoint"

        checkpoint_filename = args.strip()

        try:
            # Validate checkpoint operation
            checkpoint_data = self._validate_checkpoint_operation(session, checkpoint_filename, "undo")
            if not checkpoint_data:
                return

            # Get the commit_hash from checkpoint data
            current_commit_hash = checkpoint_data.last_commit_hash

            # Get the previous commit_hash (the state before this checkpoint)
            previous_commit_hash = session.checkpoint_tracker.git_service.get_previous_commit_hash(current_commit_hash)
            if not previous_commit_hash:
                self.io.print_error(f"Cannot undo checkpoint '{checkpoint_filename}': No previous commit found (this might be the first checkpoint)")
                return

            # Display undo information
            # self.io.print_info(f"Undoing checkpoint: {checkpoint_filename}")
            # self.io.print_info(f"Reverting files: {', '.join(checkpoint_data.modified_file_names)}")

            # Process checkpoint history
            restored_history = self._process_checkpoint_history(checkpoint_data, "undo")
            if restored_history is None:
                return

            # Manage session and restore project state
            if not self._manage_session_and_restore(session, previous_commit_hash, restored_history, checkpoint_data):
                return

            self.io.print_info(f"Successfully undone checkpoint '{checkpoint_filename}'")

            # Return the SwitchEvent with the restored history
            # return SwitchEvent(undone=True, history=restored_history)
            return

        except Exception as e:
            self.io.print_error(f"Failed to undo checkpoint: {str(e)}")
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())

    def cmd_restore(self, session, args: str):
        "Restore files from a checkpoint"

        checkpoint_filename = args.strip()

        try:
            # Validate checkpoint operation
            checkpoint_data = self._validate_checkpoint_operation(session, checkpoint_filename, "restore")
            if not checkpoint_data:
                return

            # Display checkpoint information
            # self.io.print_info(f"Restoring from checkpoint: {checkpoint_filename}")
            # self.io.print_info(f"Restoring files: {', '.join(checkpoint_data.modified_file_names)}")

            # Process checkpoint history
            restored_history = self._process_checkpoint_history(checkpoint_data, "restore")
            if restored_history is None:
                return

            # Manage session and restore project state
            if not self._manage_session_and_restore(session, checkpoint_data.last_commit_hash, restored_history, checkpoint_data):
                return

            self.io.print_info(f"Successfully restored from checkpoint '{checkpoint_filename}'")
            # return SwitchEvent(restored=True, history=restored_history)
            return

        except Exception as e:
            self.io.print_error(f"Failed to restore from checkpoint: {str(e)}")
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())

    def cmd_clear(self, session, args: str):
        "Start a new task session without previous conversation history"
        
        try:
            # Return a SwitchEvent to signal the controller to create a new session
            return SwitchEvent(clear=True)
            
        except Exception as e:
            self.io.print_error(f"Failed to start new task: {str(e)}")
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())

    def cmd_lang(self, session, args):
        """Switch language preference between English and Chinese (en/zh-CN)"""
        
        lang = args.strip().lower()

        from siada.config.config_loader import load_conf, save_conf_field

        # Display current language setting
        if not lang:
            from siada.config.language_config import get_agent_default_language
            _conf = load_conf()
            agent_name = session.siada_config.agent_name if session else None
            current = _conf.preferred_language or get_agent_default_language(agent_name)
            current_display = get_language_display_name(current)
            info_lines = [
                f"Current language: {current_display}",
                f"Available languages: {', '.join(SUPPORTED_LANGUAGES)}",
                "Usage: /lang <language>"
            ]
            self.io.print_info("\n".join(info_lines))
            return

        # Normalize and validate language input
        normalized_lang = normalize_language(lang)

        if not normalized_lang:
            self.io.print_error(f"Invalid language: {lang}")
            self.io.print_info(f"Supported languages: {', '.join(SUPPORTED_LANGUAGES)}")
            return

        # Save to conf.yaml
        if save_conf_field('preferred_language', normalized_lang):
            display_name = get_language_display_name(normalized_lang)
            self.io.print_info(f"✓ Language switched to {display_name}\nSaved to ~/.siada-cli/conf.yaml, takes effect on next message")
        else:
            self.io.print_warning("Failed to save language setting to conf.yaml")

    def cmd_pre_plan_mode(self, session, args):
        """Toggle plan mode for tool execution"""
        try:
            # Parse arguments
            arg = args.strip().lower()
            
            from siada.config.config_loader import load_conf, save_conf_field

            if not arg:
                # No argument provided, show current status
                _conf = load_conf()
                status = "enabled" if _conf.pre_plan else "disabled"
                info_lines = [
                    f"Pre-plan mode is currently: {status}",
                    "",
                    "Usage:",
                    "  /pre-plan-mode true   - Enable pre-plan mode",
                    "  /pre-plan-mode false  - Disable pre-plan mode"
                ]
                self.io.print_info("\n".join(info_lines))
                return

            # Determine the new state - only support true/false
            if arg == 'true':
                new_state = True
            elif arg == 'false':
                new_state = False
            else:
                self.io.print_error(f"Invalid argument: {arg}")
                self.io.print_info("Usage: /pre-plan-mode <true|false>")
                return

            # Get old state
            old_state = load_conf().pre_plan

            # Save to conf.yaml
            if save_conf_field('pre_plan', new_state):
                self.io.print_info("✓ Setting saved globally to ~/.siada-cli/conf.yaml")
            else:
                self.io.print_warning("Failed to save global setting")
            
            # Display result
            if old_state == new_state:
                status = "enabled" if new_state else "disabled"
                self.io.print_info(f"Plan mode is already {status}")
            else:
                status = "enabled" if new_state else "disabled"
                result_lines = [f"✓ Plan mode {status}"]
                if new_state:
                    result_lines.append("Agent will now request approval before executing plan")
                else:
                    result_lines.append("Agent will finish plan automatically without approval")
                self.io.print_info("\n".join(result_lines))
            
        except Exception as e:
            self.io.print_error(f"Failed to toggle pre-plan mode: {str(e)}")
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())

    def cmd_skill_list(self, session, args):
        """List all available skills"""
        try:
            from siada.services.skills import SkillsManager
            from pathlib import Path
            
            workspace = Path(session.siada_config.workspace)
            verbose = '--verbose' in args.strip()
            
            # Get skills via manager
            manager = SkillsManager.get_instance()
            outcome = manager.get_skills(workspace)
            
            if not outcome.skills:
                info_lines = [
                    "No skills found.\n",
                    "Tips:",
                    "- Create a skill in <project>/.siada/skills/<skill-name>/SKILL.md (repo level)",
                    "- Create a skill in ~/.siada-cli/skills/<skill-name>/SKILL.md (user level)",
                    "- Use the built-in skill-creator: just ask \"help me create a new skill\""
                ]
                self.io.print_info("\n".join(info_lines))
                return
            
            # Collect all skill information
            output_lines = [f"Skills ({len(outcome.skills)}):"]
            
            # Sort skills by scope priority then name
            sorted_skills = sorted(
                outcome.skills,
                key=lambda s: (s.scope.value, s.name.lower())
            )
            
            for skill in sorted_skills:
                scope_name = skill.scope.name
                
                if verbose:
                    output_lines.append(f"  {skill.name} [{scope_name}]")
                    output_lines.append(f"    Path: {skill.path}")
                    desc = skill.description
                    if len(desc) > 100:
                        desc = desc[:97] + "..."
                    self.io.print_info(f"    {desc}")
                    self.io.print_info("")
                else:
                    desc = skill.description
                    if len(desc) > 50:
                        desc = desc[:47] + "..."
                    output_lines.append(f"  {skill.name} [{scope_name}] - {desc}")
            
            # Show errors if any
            if outcome.errors:
                output_lines.append(f"\nWarnings ({len(outcome.errors)} error(s) during loading):")
                for error in outcome.errors:
                    output_lines.append(f"  - {error.path}: {error.message}")
            
            self.io.print_info("\n".join(output_lines))
                    
        except Exception as e:
            self.io.print_error(f'Error listing skills: {str(e)}')
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())

    def cmd_skill_reload(self, session, args):
        """Reload skills (clear cache and rediscover)"""
        try:
            from siada.services.skills import SkillsManager
            from pathlib import Path
            
            workspace = Path(session.siada_config.workspace)
            clear_all = '--all' in args.strip()
            
            # Get manager and invalidate cache
            manager = SkillsManager.get_instance()
            
            if clear_all:
                manager.invalidate_cache()  # Clear all cwd caches
            else:
                manager.invalidate_cache(workspace)  # Clear current cwd cache only
            
            # Force reload
            outcome = manager.get_skills(workspace, force_reload=True)
            
            # Build result message
            skill_count = len(outcome.skills)
            error_count = len(outcome.errors)
            
            # Collect all output
            output_lines = []
            if error_count > 0:
                output_lines.append(f"✓ Skills reloaded ({skill_count} loaded, {error_count} errors)")
            else:
                output_lines.append(f"✓ Skills reloaded ({skill_count} loaded)")
            
            # List skills
            if outcome.skills:
                for skill in sorted(outcome.skills, key=lambda s: (s.scope.value, s.name.lower())):
                    output_lines.append(f"  {skill.name} [{skill.scope.name}]")
            
            # List errors
            if outcome.errors:
                output_lines.append("Errors:")
                for error in outcome.errors:
                    output_lines.append(f"  {error.path}: {error.message}")
            
            self.io.print_info("\n".join(output_lines))
                    
        except Exception as e:
            self.io.print_error(f'Error reloading skills: {str(e)}')
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())

    def cmd_help(self, session, args):
        "Show help about all commands"
        self.basic_help()


    # =========================================================================
    # Plugin Manager (/plugin) — delegates to siada.services.plugins
    # =========================================================================

    def _is_acp_mode(self) -> bool:
        """Return True when running inside an ACP (UI) session."""
        return (
            hasattr(self.io, 'acp_adapter') and self.io.acp_adapter is not None
        )

    def _plugin_log(self, msg: str):
        """Buffer a plugin status message for later flush."""
        if not hasattr(self, "_plugin_buf"):
            self._plugin_buf: list = []
        self._plugin_buf.append(msg)

    def _plugin_flush(self):
        """Print all buffered plugin messages as a single box, then clear buffer."""
        if not getattr(self, "_plugin_buf", None):
            return
        combined = "\n".join(self._plugin_buf)
        self._plugin_buf = []
        self.io.print_info(combined)

    def _send_plugin_manager_ui(self, session):
        """Collect data and send ui/showPluginManager notification to frontend with detailed elapsed timing."""
        import time
        t0 = time.time()
        from siada.services.skills import SkillsManager
        from siada.services.plugins import MarketplaceManager
        from siada.io.acp.message_builder import ACPMessageBuilder
        from pathlib import Path

        workspace = Path(session.siada_config.workspace)
        manager = SkillsManager.get_instance()
        outcome = manager.get_skills(workspace)
        t_skills = time.time()

        plugin_config = MarketplaceManager().get_config()
        t_config = time.time()

        disabled_skills = plugin_config.get("disabled_skills", [])
        marketplaces_cfg = plugin_config.get("marketplaces", [])

        # Build: skill_dir_name -> plugin_display_name
        # Uses directory names (no file reads) so it's fast, and works even when
        # a skill is deduplicated to ~/.siada-cli/skills/ (path-based detection fails).
        from siada.foundation.constants import SIADA_HOME as _SIADA_HOME
        import json as _json
        _plugins_root = _SIADA_HOME / "plugins"
        installed_plugin_names: set = set()
        # Map: skill directory name -> plugin display name
        _skill_dir_to_plugin: dict = {}
        if _plugins_root.exists():
            for _pd in sorted(_plugins_root.iterdir()):
                if not _pd.is_dir():
                    continue
                _mp = _pd / ".claude-plugin" / "plugin.json"
                if _mp.exists():
                    try:
                        _pname = _json.loads(_mp.read_text()).get("name", _pd.name)
                    except Exception:
                        _pname = _pd.name
                else:
                    _pname = _pd.name
                installed_plugin_names.add(_pname)
                # Enumerate skill dirs: check 'skills/' subdir first, then plugin root
                _skills_base = _pd / "skills"
                _scan_root = _skills_base if _skills_base.is_dir() else _pd
                try:
                    for _sd in _scan_root.iterdir():
                        if _sd.is_dir() and (_sd / "SKILL.md").exists():
                            if _sd.name not in _skill_dir_to_plugin:
                                _skill_dir_to_plugin[_sd.name] = _pname
                except PermissionError:
                    pass
        t_plugins = time.time()

        installed = []
        installed_names = set()
        for skill in outcome.skills:
            # First try: match by skill directory name (fast, handles deduplication)
            _skill_dir = skill.path.parent.name
            plugin_name = _skill_dir_to_plugin.get(_skill_dir)
            installed.append({
                "name": skill.name,
                "description": skill.description[:200] if skill.description else "",
                "scope": skill.scope.name.lower(),
                "path": str(skill.path),
                "plugin_name": plugin_name,
            })
            installed_names.add(skill.name)
        t_installed = time.time()

        errors = []
        for err in outcome.errors:
            errors.append({
                "path": str(err.path),
                "message": err.message,
                "scope": err.scope.name.lower(),
            })

        marketplaces = []
        for mp in marketplaces_cfg:
            mp_repo = mp.get("repo", "")
            marketplaces.append({
                "name": mp.get("name", mp_repo.split("/")[-1]),
                "repo": mp_repo,
                "available": mp.get("available", 0),
                "installed": mp.get("installed", 0),
                "updatedAt": mp.get("updatedAt", ""),
            })

        discover = []
        for mp in marketplaces_cfg:
            for skill in mp.get("_cached_skills", []):
                sname = skill.get("name", "")
                skill["installed"] = sname in installed_plugin_names or sname in installed_names
                discover.append(skill)
        t_discover = time.time()

        mcp_servers = []
        try:
            from siada.config.mcp_config_loader import MCPConfigLoader
            mcp_cfg = MCPConfigLoader.load_config()
            if mcp_cfg and mcp_cfg.servers:
                for sname, sval in mcp_cfg.servers.items():
                    mcp_servers.append({
                        "name": sname,
                        "command": sval.command or "",
                        "args": sval.args or [],
                        "url": sval.url or "",
                    })
        except Exception as e:
            logger.warning(f"Failed to load MCP servers for plugin manager: {e}")

        params = {
            "installed": installed,
            "marketplaces": marketplaces,
            "errors": errors,
            "discover": discover,
            "disabledSkills": disabled_skills,
            "mcp_servers": mcp_servers,
        }

        try:
            message = ACPMessageBuilder().build_custom_notification(
                method="ui/showPluginManager",
                params=params,
            )
            if self.io.acp_adapter.transport and self.io.acp_adapter.transport.is_connected:
                self.io.acp_adapter.transport.send_sync(message)
                logger.info(
                    f"Sent ui/showPluginManager notification. Timings: "
                    f"get_skills={t_skills - t0:.3f}s, "
                    f"get_config={t_config - t_skills:.3f}s, "
                    f"scan_plugins={t_plugins - t_config:.3f}s, "
                    f"build_installed={t_installed - t_plugins:.3f}s, "
                    f"build_discover={t_discover - t_installed:.3f}s, "
                    f"total={t_discover - t0:.3f}s"
                )
        except Exception as e:
            logger.error(f"Failed to send plugin manager notification: {e}")

    def cmd_plugin(self, session, args: str):
        """Manage skills/plugins (discover, install, disable, remove, marketplace, validate)

        Usage:
            /plugin                              - Open plugin manager UI
            /plugin install <skill> [@mp]        - Install a skill from a marketplace
            /plugin remove <skill>               - Remove an installed user-scope skill
            /plugin disable <skill>              - Disable a skill
            /plugin enable <skill>               - Re-enable a disabled skill
            /plugin validate [path]              - Validate a local plugin directory
            /plugin marketplace add <url/repo>   - Add a marketplace repository
            /plugin marketplace remove <name>    - Remove a marketplace
            /plugin marketplace update <name>    - Refresh marketplace skill list
        """
        from siada.services.plugins import PluginLoader, MarketplaceManager
        from pathlib import Path

        args_stripped = args.strip()
        loader = PluginLoader()
        manager = MarketplaceManager()

        if not args_stripped:
            if self._is_acp_mode():
                try:
                    self._send_plugin_manager_ui(session)
                except Exception as e:
                    self.io.print_error(f"Failed to open plugin manager: {e}")
            else:
                try:
                    import time
                    t0 = time.time()
                    from siada.services.skills import SkillsManager
                    outcome = SkillsManager.get_instance().get_skills(
                        Path(session.siada_config.workspace)
                    )
                    t_skills = time.time()
                    config = manager.get_config()
                    t_config = time.time()
                    disabled = set(config.get("disabled_skills", []))
                    lines = ["Skills:"]
                    for s in sorted(outcome.skills, key=lambda x: (x.scope.value, x.name.lower())):
                        status = " [disabled]" if s.name in disabled else ""
                        lines.append(f"  {s.name} [{s.scope.name.lower()}]{status}")
                    if not outcome.skills:
                        lines.append("  (none installed)")
                    lines.append("\nMarketplaces:")
                    for mp in config.get("marketplaces", []):
                        lines.append(f"  {mp.get('name', '')} - {mp.get('repo', '')}")
                    if not config.get("marketplaces"):
                        lines.append("  (none configured)")
                    self.io.print_info("\n".join(lines))
                    logger.info(
                        f"/plugin CLI timing: get_skills={t_skills - t0:.3f}s, "
                        f"get_config={t_config - t_skills:.3f}s, "
                        f"total={t_config - t0:.3f}s"
                    )
                except Exception as e:
                    self.io.print_error(f"Error: {e}")
            return

        parts = args_stripped.split(None, 2)
        subcmd = parts[0].lower()

        if subcmd == "install":
            rest = args_stripped[len(subcmd):].strip()
            if not rest:
                self.io.print_error("Usage: /plugin install <skill_name> [@marketplace]")
                return
            at_idx = rest.find("@")
            if at_idx > 0:
                skill_name = rest[:at_idx].strip()
                repo = rest[at_idx + 1:].strip()
            else:
                tokens = rest.split(None, 1)
                skill_name = tokens[0]
                repo = tokens[1].lstrip("@").strip() if len(tokens) > 1 else None
            if not skill_name:
                self.io.print_error("Usage: /plugin install <skill_name> [@marketplace]")
                return

            def _acp_progress(phase, pct):
                if not self._is_acp_mode():
                    return
                try:
                    from siada.io.acp.message_builder import ACPMessageBuilder
                    msg = ACPMessageBuilder().build_custom_notification(
                        method="ui/pluginInstallProgress",
                        params={"skillName": skill_name, "phase": phase, "percent": pct},
                    )
                    if self.io.acp_adapter.transport and self.io.acp_adapter.transport.is_connected:
                        self.io.acp_adapter.transport.send_sync(msg)
                except Exception:
                    pass

            self._plugin_log(f"Installing '{skill_name}'...")
            self._plugin_flush()
            try:
                plugin = loader.install(skill_name, repo or None, progress_callback=_acp_progress)
                self._plugin_log(f"✓ Installed '{skill_name}'")
                # Hot-reload: register the new plugin's hooks into the running hook_runner
                if hasattr(self, "hook_runner") and plugin is not None:
                    self.hook_runner.register_plugin_hooks(plugin)
            except Exception as e:
                self.io.print_error(f"Install failed: {e}")
            self._plugin_flush()
            if self._is_acp_mode():
                try:
                    self._send_plugin_manager_ui(session)
                except Exception:
                    pass

        elif subcmd == "remove":
            if len(parts) < 2:
                self.io.print_error("Usage: /plugin remove <skill_name>")
                return
            try:
                loader.uninstall(parts[1], Path(session.siada_config.workspace))
                self._plugin_log(f"✓ Removed plugin '{parts[1]}'")
            except Exception as e:
                self.io.print_error(f"Remove failed: {e}")
            self._plugin_flush()
            if self._is_acp_mode():
                try:
                    self._send_plugin_manager_ui(session)
                except Exception:
                    pass

        elif subcmd == "disable":
            if len(parts) < 2:
                self.io.print_error("Usage: /plugin disable <skill_name>")
                return
            loader.set_enabled(parts[1], False)
            self._plugin_log(f"✓ Disabled skill '{parts[1]}'")
            self._plugin_flush()

        elif subcmd == "enable":
            if len(parts) < 2:
                self.io.print_error("Usage: /plugin enable <skill_name>")
                return
            loader.set_enabled(parts[1], True)
            self._plugin_log(f"✓ Enabled skill '{parts[1]}'")
            self._plugin_flush()

        elif subcmd == "validate":
            path = parts[1] if len(parts) > 1 else "."
            self.io.print_info(f"Validating plugin at {path} ...")
            errors, warnings = PluginLoader.validate(path)
            for e in errors:
                self.io.print_info(f"  ✗ {e}")
            for w in warnings:
                self.io.print_info(f"  ⚠ {w}")
            if not errors and not warnings:
                self.io.print_info("  ✓ Plugin is valid")
            self.io.print_info(f"\nResult: {len(errors)} error(s), {len(warnings)} warning(s)")

        elif subcmd == "marketplace":
            if len(parts) < 3:
                self.io.print_error("Usage: /plugin marketplace add|remove|update <name_or_repo>")
                return
            mp_action = parts[1].lower()
            mp_arg = parts[2]
            try:
                if mp_action == "add":
                    manager.add_marketplace(mp_arg)
                    self._plugin_log(f"✓ Added marketplace '{mp_arg}'")
                    raw_name = mp_arg.rstrip("/").split("/")[-1].removesuffix(".git")
                    try:
                        manager.update_marketplace(raw_name)
                    except Exception:
                        pass
                elif mp_action in ("remove", "rm"):
                    manager.remove_marketplace(mp_arg)
                    self._plugin_log(f"✓ Removed marketplace '{mp_arg}'")
                elif mp_action == "update":
                    manager.update_marketplace(mp_arg)
                    self._plugin_log(f"✓ Updated marketplace '{mp_arg}'")
                else:
                    self.io.print_error(f"Unknown marketplace action: {mp_action}")
            except Exception as e:
                self.io.print_error(f"Marketplace operation failed: {e}")
            self._plugin_flush()
            if self._is_acp_mode():
                try:
                    self._send_plugin_manager_ui(session)
                except Exception:
                    pass

        else:
            self.io.print_error(f"Unknown /plugin subcommand: {subcmd}")
            self.io.print_info("Available: install, remove, disable, enable, validate, marketplace")

def main():
    md = SlashCommands(None, None).get_help_md()
    print(md)

if __name__ == "__main__":
    status = main()
    sys.exit(status)
