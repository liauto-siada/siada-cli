"""LarkSlashCommandHandler - IM-mode slash command adapter.

Handles slash command parsing, filtering (blocked commands for IM),
IO capture, and execution delegation to SlashCommands.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Optional

from siada.im.feishu.card_sender import LarkCardSender
from siada.im.feishu.verbose_config import VerboseConfig
from siada.im.models import IMMessage

if TYPE_CHECKING:
    from siada.entrypoint.interaction.lark_controller import LarkController
    from siada.io.feishu_io import LarkIO
    from siada.session.session_models import RunningSession
    from siada.support.slash_commands import SlashCommands, SwitchEvent

logger = logging.getLogger("siada.im.lark.slash_command_handler")


class LarkSlashCommandHandler:
    """IM-mode slash command adapter with blocked command filtering.

    Responsibilities:
    - Determine whether a message is a slash command
    - Filter out CLI-only commands not supported in IM
    - Execute allowed commands and capture IO output
    - Build IM-specific help text
    - Return SwitchEvent for caller to handle side effects
    """

    # CLI-only commands that don't make sense in IM context.
    # Allowed commands are dynamically derived: all registered minus this set.
    #
    # Note: ``/plugin`` is intentionally *not* blocked. Its code paths fall
    # back to plain text output (``io.print_info``/``print_error``) whenever
    # the IO does not expose an ACP adapter, which is exactly the Lark case,
    # so the command captures fine via this handler's IO buffering. This
    # lets IM users list, install, remove, enable/disable skills and manage
    # marketplaces remotely (e.g. ``/plugin install idaas-doctor``).
    #
    # ``goal`` is temporarily blocked too: the standing-goal feature's
    # GoalStatusBar / verifier UX is currently ACP-frontend-only, so there
    # is no good way to surface goal state in IM yet. Remove once IM-side
    # goal status rendering is designed.
    _IM_BLOCKED_COMMANDS = {
        "agent", "compare", "configure",
        "edit", "editor", "exit", "goal", "init", "issue-fix",
        "lark-auth", "logout",
        "map", "map-refresh",
        "migrate-detect", "migrate-import",
        "models", "multiline-mode",
        "quit",
        "restore", "resume", "run",
        "shell", "task-list", "undo",
    }


    def __init__(
        self, lark_io: "LarkIO", card_sender: LarkCardSender,
        verbose_config: Optional[VerboseConfig] = None,
        controller: Optional["LarkController"] = None,
    ):
        self._lark_io = lark_io
        self._card_sender = card_sender
        self._slash_commands: Optional["SlashCommands"] = None
        self._verbose_config = verbose_config
        self._controller = controller
        # Track chat_ids that currently have a /btw side question in flight,
        # so each chat can only run one /btw at a time. The handler runs on a
        # single event loop, so a plain set (no lock) is enough: the check and
        # the add happen synchronously without an intervening await.
        self._btw_running_chats: set[str] = set()
        # Strong references to in-flight /btw background tasks. Without this the
        # event loop may garbage-collect a pending task. Entries are removed via
        # an add_done_callback when each task finishes.
        self._btw_tasks: set[asyncio.Task] = set()

    @staticmethod
    def is_slash_command(content: str) -> bool:
        """Check if message content is a slash command (not a file path)."""
        content = content.strip()
        if not content.startswith("/"):
            return False
        from siada.support.slash_commands import _looks_like_filepath
        return not _looks_like_filepath(content)

    def _get_slash_commands(self) -> "SlashCommands":
        """Lazily create SlashCommands instance for IM mode."""
        if self._slash_commands is None:
            from siada.support.slash_commands import SlashCommands
            self._slash_commands = SlashCommands(io=self._lark_io)
        return self._slash_commands

    def _get_im_allowed_commands(
        self, session: Optional["RunningSession"] = None,
    ) -> set[str]:
        """Dynamically compute IM-allowed commands by excluding blocked ones.

        Fetches all registered commands from SlashCommands.get_commands()
        and removes those in the _IM_BLOCKED_COMMANDS set.

        When ``session`` is provided, the returned set also includes user
        custom commands and skill-based commands (``/skill-name``), since
        resolving those requires a workspace obtained from the session.
        """
        slash_cmds = self._get_slash_commands()
        # get_commands returns ["/cmd-name", ...], strip the leading "/".
        # Pass session so custom commands and skills are included as well.
        all_commands = {
            cmd.lstrip("/") for cmd in slash_cmds.get_commands(session)
        }
        return all_commands - self._IM_BLOCKED_COMMANDS

    def _get_skill_descriptions(
        self, session: Optional["RunningSession"],
    ) -> dict[str, str]:
        """Collect {skill_name: description} for skills visible to session.

        Failures are swallowed so that /help never breaks when skill loading
        has issues.
        """
        descriptions: dict[str, str] = {}
        if session is None:
            return descriptions
        try:
            from pathlib import Path
            from siada.services.skills import SkillsManager

            workspace = Path(session.siada_config.workspace)
            outcome = SkillsManager.get_instance().get_skills(workspace)
            for skill in outcome.skills:
                descriptions[skill.name] = (skill.description or "").strip()
        except Exception as e:
            logger.debug("Failed to collect skill descriptions: %s", e)
        return descriptions

    def _build_im_help(
        self, session: Optional["RunningSession"] = None,
    ) -> str:
        """Build help text showing only IM-allowed commands with descriptions.

        Includes built-in commands, custom commands, and skill-based
        ``/skill-name`` commands (when ``session`` is provided).
        """
        slash_cmds = self._get_slash_commands()
        allowed = self._get_im_allowed_commands(session)
        commands = sorted(f"/{name}" for name in allowed)
        pad = max(len(cmd) for cmd in commands) if commands else 0
        fmt = "{cmd:" + str(pad) + "}"

        # Pre-resolve skill descriptions once so we don't reload for each line.
        skill_descriptions = self._get_skill_descriptions(session)

        help_lines = []
        for cmd in commands:
            name = cmd[1:]
            cmd_method_name = f"cmd_{name}".replace("-", "_")
            cmd_method = getattr(slash_cmds, cmd_method_name, None)
            padded = fmt.format(cmd=cmd)
            # Built-in command: read docstring
            if cmd_method and cmd_method.__doc__:
                help_lines.append(f"{padded} {cmd_method.__doc__.strip()}")
                continue
            # Skill command: use SkillMetadata.description
            if name in skill_descriptions:
                desc = skill_descriptions[name] or "Skill command."
                # Keep help compact in IM: first line of the skill description
                first_line = desc.splitlines()[0] if desc else "Skill command."
                help_lines.append(f"{padded} {first_line}")
                continue
            help_lines.append(f"{padded} No description available.")

        return "\n".join(help_lines)


    async def handle(
        self, msg: IMMessage, session: "RunningSession",
    ) -> bool:
        """Handle a slash command message.

        Returns:
            True if the message was a slash command (even unsupported).
            All switch events (clear, model, ai_analysis) are handled internally.
        """
        from siada.im.feishu.utils import format_exception_for_user

        content = msg.content.strip()
        if not content.startswith("/"):
            return False

        parts = content.split(None, 1)
        cmd_word = parts[0]
        cmd_name = cmd_word.lstrip("/")

        # Intercept IM-only commands before allowed-commands check
        # (not registered in generic SlashCommands)
        if cmd_name == "verbose":
            await self._handle_verbose_command(msg, parts)
            return True

        if cmd_name == "resume":
            await self._handle_resume_command(msg, parts)
            return True

        # /btw runs a read-only side question in its own thread, so it never
        # interrupts the main agent flow. Intercept it here to render the
        # answer as a purple card instead of going through the generic
        # IO-capture path (which would only produce plain text).
        if cmd_name == "btw":
            await self._handle_btw_command(msg, parts, session)
            return True

        # Allowed-commands check needs the session so that ``/skill-name``
        # and user custom commands (both resolved via session.workspace)
        # are recognized as valid IM commands instead of being rejected.
        if cmd_name not in self._get_im_allowed_commands(session):
            await self._card_sender.send_im(
                msg.request_id, msg.chat_id,
                f"⚠️ Command `/{cmd_name}` is not supported in IM mode.\n\n"
                f"Type `/help` to see available commands.",
                content_type="text",
            )
            return True

        # Intercept /help to only show IM-allowed commands (including skills)
        if cmd_name == "help":
            help_text = self._build_im_help(session)
            await self._card_sender.send_im(
                msg.request_id, msg.chat_id, help_text, content_type="text",
            )
            return True


        slash_cmds = self._get_slash_commands()

        # Capture IO output by temporarily buffering print_info/print_error
        output_lines: list[str] = []
        original_print_info = self._lark_io.print_info
        original_print_error = self._lark_io.print_error

        def _capture_info(text, *args, **kwargs):
            output_lines.append(text)

        def _capture_error(text, *args, **kwargs):
            output_lines.append(f"❌ {text}")

        self._lark_io.print_info = _capture_info
        self._lark_io.print_error = _capture_error

        try:
            result = slash_cmds.run(session, content)
        except Exception as e:
            logger.error(f"Slash command error: {e}", exc_info=True)
            output_lines.append(f"❌ Command failed: {format_exception_for_user(e)}")
            result = None
        finally:
            self._lark_io.print_info = original_print_info
            self._lark_io.print_error = original_print_error

        if output_lines:
            combined = "\n".join(output_lines)
            if len(combined) > 4000:
                combined = combined[:3997] + "..."
            await self._card_sender.send_im(
                msg.request_id, msg.chat_id, combined, content_type="text",
            )

        # Handle SwitchEvent internally via controller
        from siada.support.slash_commands import SwitchEvent
        if isinstance(result, SwitchEvent):
            await self._handle_switch_event(result, msg, session)

        return True

    # ── Switch event handling ────────────────────────────────────────

    async def _handle_switch_event(
        self, event: "SwitchEvent", msg: IMMessage, session: "RunningSession",
    ) -> None:
        """Handle all switch events from slash commands.

        Uses the controller reference to access session management
        and agent execution capabilities.
        """
        kwargs = event.kwargs

        if kwargs.get("clear"):
            await self._handle_clear(msg, session)
        elif kwargs.get("model"):
            await self._card_sender.send_im(
                msg.request_id, msg.chat_id,
                f"✅ Model switched to: {kwargs['model']}", content_type="text",
            )
        elif kwargs.get("ai_analysis_prompt"):
            await self._handle_ai_analysis(msg, session, kwargs["ai_analysis_prompt"])

    async def _handle_clear(
        self, msg: IMMessage, session: "RunningSession",
    ) -> None:
        """Handle /clear [workspace]: create a new session without deleting the old one.

        In Lark/Feishu mode, an optional workspace path can be specified to
        initialize the new session under a different directory.
        Usage: /clear [workspace_path]
        """
        if self._controller is None:
            logger.warning("No controller reference, cannot create new session")
            return

        try:
            running_config = self._controller._build_running_config()

            # Parse optional workspace argument from the message content
            workspace = self._parse_workspace_arg(msg.content)
            if workspace is not None:
                from pathlib import Path
                ws_path = Path(workspace).expanduser().resolve()
                if not ws_path.is_dir():
                    await self._card_sender.send_im(
                        msg.request_id, msg.chat_id,
                        f"❌ Workspace path does not exist or is not a directory: `{workspace}`",
                        content_type="text",
                    )
                    return
                # Override workspace in running_config for the new session
                running_config.workspace = str(ws_path)

            is_single_chat = msg.chat_type == "p2p"
            # Delegate to ImController.create_new_session() which handles
            # session creation, routing update, cache, and persistence.
            new_session = self._controller.create_new_session(
                msg.chat_id, running_config, is_single_chat=is_single_chat,
            )
            logger.info(
                "Created new session for clear: chat_id=%s, old_session=%s, new_session=%s, workspace=%s",
                msg.chat_id, session.session_id, new_session.session_id,
                running_config.workspace,
            )

            workspace_info = f"\n📂 Workspace: `{running_config.workspace}`" if workspace else ""
            await self._card_sender.send_im(
                msg.request_id, msg.chat_id,
                f"✅ New task session created.{workspace_info}", content_type="text",
            )
        except Exception as e:
            logger.error("Failed to create new session on /clear: %s", e, exc_info=True)
            await self._card_sender.send_im(
                msg.request_id, msg.chat_id,
                f"❌ Failed to create new session: {e}",
                content_type="text",
            )

    @staticmethod
    def _parse_workspace_arg(content: str) -> Optional[str]:
        """Extract workspace path from /clear command content.

        Supports:
            /clear /path/to/workspace
            /clear ~/projects/my-repo
        Returns None if no workspace argument is provided.
        """
        parts = content.strip().split(None, 1)
        if len(parts) < 2:
            return None
        arg = parts[1].strip()
        return arg if arg else None

    async def _handle_ai_analysis(
        self, msg: IMMessage, session: "RunningSession", prompt: str,
    ) -> None:
        """Handle /ai-analysis: run agent with the analysis prompt."""
        if self._controller is None:
            logger.warning("No controller reference, cannot run AI analysis")
            return

        analysis_msg = IMMessage(
            request_id=msg.request_id, platform=msg.platform,
            user_id=msg.user_id, chat_id=msg.chat_id, chat_type=msg.chat_type,
            content_type="text", content=prompt,
            timestamp=msg.timestamp, raw=msg.raw, message_id=msg.message_id,
            sender_name=msg.sender_name, sender_open_id=msg.sender_open_id,
        )
        await self._controller._agent_executor.run_agent_for_message(
            analysis_msg, session,
        )

    async def _handle_resume_command(self, msg: IMMessage, parts: list[str]) -> None:
        """Handle /resume <session_id> — switch to a target session.

        Supported in both P2P and group chats; the routing table is selected
        based on chat_type so the idle-reset /resume hint works everywhere.
        """
        if self._controller is None:
            logger.warning("No controller reference, cannot resume session")
            return

        target_session_id = parts[1].strip() if len(parts) > 1 else ""
        if not target_session_id:
            await self._card_sender.send_im(
                msg.request_id, msg.chat_id,
                "⚠️ Usage: `/resume <session_id>`\n"
                "Switches the current chat to the specified session.",
                content_type="text",
            )
            return

        # Delegate to session resolver's switch_and_notify, routing to the
        # correct table (P2P vs group) based on the chat type.
        is_single_chat = msg.chat_type == "p2p"
        running_config = self._controller._build_running_config()
        session = await self._controller._session_resolver._switch_and_notify(
            msg, target_session_id, running_config, is_single_chat=is_single_chat,
        )
        if not session:
            await self._card_sender.send_im(
                msg.request_id, msg.chat_id,
                f"❌ Failed to resume session `{target_session_id}`. "
                f"The session may not exist or could not be loaded from disk.",
                content_type="text",
            )

    async def _handle_btw_command(
        self, msg: IMMessage, parts: list[str], session: "RunningSession",
    ) -> None:
        """Handle /btw <question> — answer a quick side question.

        The side question runs as a read-only fork in its own thread (see
        ``run_side_question``), so it NEVER interrupts the main agent flow and
        leaves the main conversation state untouched. The answer is returned
        as a purple interactive card whose header shows the original question
        and whose body holds the answer content.

        Concurrency: only one /btw may run at a time per ``chat_id``. The actual
        work is dispatched as a *background task* (not awaited here) so the IM
        message loop keeps processing — otherwise a second /btw would only be
        handled after the first finished, and the per-chat guard could never
        observe an in-flight one. A second /btw issued while the first is still
        running is therefore detected and rejected immediately.
        """
        question = parts[1].strip() if len(parts) > 1 else ""
        if not question:
            await self._card_sender.send_im(
                msg.request_id, msg.chat_id,
                "⚠️ Usage: `/btw <your question>`\n"
                "Ask a quick side question without interrupting the main task.",
                content_type="text",
            )
            return

        # Enforce a single in-flight /btw per chat_id. The check-and-add is
        # synchronous (no await in between), so it is race-free on the single
        # IM event loop.
        if msg.chat_id in self._btw_running_chats:
            logger.info("[btw] rejected concurrent /btw for chat_id=%s", msg.chat_id)
            await self._card_sender.send_im(
                msg.request_id, msg.chat_id,
                "⚠️ A `/btw` side question is already running in this chat. "
                "Please wait for it to finish before asking another.",
                content_type="text",
            )
            return
        self._btw_running_chats.add(msg.chat_id)
        logger.info("[btw] accepted /btw for chat_id=%s (in-flight=%d)",
                    msg.chat_id, len(self._btw_running_chats))

        # Dispatch as a background task so this handler returns immediately and
        # the message loop is not blocked for the duration of the side question.
        task = asyncio.create_task(self._run_btw_side_question(msg, question, session))
        self._btw_tasks.add(task)
        task.add_done_callback(self._btw_tasks.discard)

    async def _run_btw_side_question(
        self, msg: IMMessage, question: str, session: "RunningSession",
    ) -> None:
        """Background worker for /btw: run the side question and post the card.

        Always releases the per-chat slot in ``finally`` so a chat is never left
        permanently blocked, even if the run fails.
        """
        from siada.im.feishu.utils import format_exception_for_user
        from siada.services.side_question import run_side_question

        # Add a "Typing" emoji reaction on the user's /btw message as a loading
        # indicator; it is removed once the answer (or error) is posted. Uses a
        # caller-owned reaction state so it never clobbers the main agent turn's
        # per-chat typing indicator.
        reaction_state = await self._card_sender.add_reaction(msg.message_id)

        try:
            # run_side_question spawns its own thread + event loop and blocks
            # (join) until the fork finishes. Offload that blocking call to a
            # worker thread so the IM event loop — and the main agent run — are
            # never blocked or interrupted.
            answer = await asyncio.to_thread(run_side_question, session, question)
            answer = (answer or "").strip() or "(model returned an empty response)"
            # Purple card: header title is the question, body is the answer.
            # Reply directly to the user's /btw command message so the card is
            # threaded under it; fall back to a standalone card if the original
            # message_id is unavailable.
            card_title = f"/btw {question}"
            if msg.message_id:
                await self._card_sender.reply_card_message(
                    msg.message_id,
                    title=card_title,
                    content=answer,
                    header_template="purple",
                )
            else:
                await self._card_sender.send_card_message(
                    msg.chat_id,
                    title=card_title,
                    content=answer,
                    header_template="purple",
                )
        except Exception as e:
            logger.error("/btw failed: %s", e, exc_info=True)
            await self._card_sender.send_im(
                msg.request_id, msg.chat_id,
                f"❌ /btw failed: {format_exception_for_user(e)}",
                content_type="text",
            )
        finally:
            # Remove the loading reaction and release the chat slot so the chat
            # is never left blocked or stuck showing a typing indicator.
            await self._card_sender.remove_reaction(reaction_state)
            self._btw_running_chats.discard(msg.chat_id)

    async def _handle_verbose_command(self, msg: IMMessage, parts: list[str]) -> None:
        """Handle /verbose [on|off] — IM-only verbose output control."""
        if self._verbose_config is None:
            await self._card_sender.send_im(
                msg.request_id, msg.chat_id,
                "⚠️ Verbose configuration is not available.",
                content_type="text",
            )
            return

        arg = parts[1].strip().lower() if len(parts) > 1 else ""

        if arg == "on":
            # Persist per chat_type (p2p / group) into conf.yaml im.verbose.*
            self._verbose_config.set_verbose(msg.chat_type, True)
            await self._card_sender.send_im(
                msg.request_id, msg.chat_id,
                f"✅ Verbose mode **on** for `{msg.chat_type}` "
                f"— will show thinking, tool calls, and answer.\n"
                f"Persisted to `conf.yaml` under `im.verbose.{msg.chat_type}`.",
                content_type="text",
            )
        elif arg == "off":
            self._verbose_config.set_verbose(msg.chat_type, False)
            await self._card_sender.send_im(
                msg.request_id, msg.chat_id,
                f"✅ Verbose mode **off** for `{msg.chat_type}` "
                f"— will show answer only.\n"
                f"Persisted to `conf.yaml` under `im.verbose.{msg.chat_type}`.",
                content_type="text",
            )
        else:
            status_text = self._verbose_config.get_status_text(
                msg.chat_id, msg.chat_type,
            )
            await self._card_sender.send_im(
                msg.request_id, msg.chat_id, status_text, content_type="text",
            )
