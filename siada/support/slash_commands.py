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
from siada.services.mcp.manager_service import _mcp_manager_service as mcp_service
from siada.foundation.logging import logger

# Import custom commands modules directly to avoid circular dependencies
from siada.services.custom_commands.command_loader import FileCommandLoader
from siada.services.custom_commands.command_service import CommandService
from siada.services.custom_commands.types import CommandContext, CommandResult


class SwitchEvent:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


_marketplace_update_lock = threading.Lock()


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
            current_provider = session.siada_config.llm_config.provider
            new_llm_config = ModelRunConfig(model_name)
            new_llm_config.provider = current_provider
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
            prefix = "* " if m == current_model else "  "
            lines.append(f"{prefix}{m}")
        lines.append("\nUsage: /model <model_name>")
        self.io.print_info("\n".join(lines))

    def is_command(self, inp):
        return inp[0] in "/!"

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

        elif result.startswith("liid:"):
            from siada.models.model_base_config import MODEL_SETTING, set_user_model_settings
            from siada.models.model_run_config import ModelRunConfig
            set_user_model_settings(list(MODEL_SETTING))
            default_model = MODEL_SETTING[0].model_name
            new_llm = ModelRunConfig(default_model)
            new_llm.provider = 'li'
            session.siada_config.llm_config = new_llm
            return SwitchEvent(model=default_model)

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
            await session.state.openai_session.reset_items(restore_history)
            
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

        try:
            # Restore the project state
            session.checkpoint_tracker.git_service.restore_project_from_snapshot(
                target_commit_hash
            )
            return True
        except BaseException as e:
            # When restoring project state fails, rollback the OpenAI session
            self.io.print_error(f"Failed to restore project state: {str(e)}")
            
            async def rollback_operations():
                await session.state.openai_session.reset_items(old_items)
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
        else:
            error_message = result[1] if result else "Unknown error"
            self.io.print_error(error_message)

    def _send_history_to_ui(self, items: list):
        """发送历史消息到前端 UI"""
        try:
            from siada.io.acp.message_builder import ACPMessageBuilder

            # Prepare message list
            messages = []
            for item in items:
                item_type = item.get('type', '')
                role = item.get('role', 'assistant')

                # function_call: use ToolCallFormatter to generate formatted text consistent with normal runtime
                if item_type == 'function_call':
                    from siada.tools.tool_call_format.formatter_factory import ToolCallFormatterFactory
                    name = item.get('name', 'unknown')
                    arguments = item.get('arguments', '{}')
                    call_id = item.get('call_id', item.get('id', ''))
                    formatter = ToolCallFormatterFactory.get_formatter(name)
                    content, _ = formatter.format_input(call_id, name, arguments)
                    if content:
                        messages.append({
                            "role": "assistant",
                            "content": content,
                            "subtype": "tool_use"
                        })
                    continue

                # function_call_output: not sent to frontend in normal flow, kept consistent
                if item_type == 'function_call_output':
                    continue

                # Extract text content (supports different message formats)
                content = item.get('content', '')
                text = ''

                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get('type') in ('output_text', 'text'):
                            text += part.get('text', '')

                if not text:
                    continue

                # Strip <task>...</task> wrapper added by agent and appended path comments (user messages only)
                if role == 'user':
                    import re
                    text = re.sub(r'^\s*<task>\s*', '', text)
                    text = re.sub(r'\s*</task>.*$', '', text, flags=re.DOTALL)
                    text = text.strip()

                if not text:
                    continue

                messages.append({
                    "role": role,
                    "content": text
                })

            # Batch send all history messages
            batch_notification = ACPMessageBuilder().build_custom_notification(
                method="ui/loadHistory",
                params={
                    "messages": messages
                }
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

    def cmd_issue_fix(self, session, args):
        """Fix an issue from Siada Patch Review by issue ID, Only supported internally"""
        try:
            # Check current agent
            current_agent = session.siada_config.agent_name
            
            # If not in gerritissuefix agent, prompt user to restart with correct agent
            if current_agent != "gerritissuefix":
                self.io.print_info("This command requires GerritIssueFixAgent\nPlease restart with: siada-cli --gerritissuefix")
                return
            
            # ========== Step 1: Parse and validate issue_id ==========
            issue_id = args.strip()
            
            # Check if issue_id is provided
            if not issue_id:
                self.io.print_error("Please provide an issue ID")
                self.io.print_info("Usage: /issue_fix <issue_id>\nExample: /issue_fix 10244b08-ea69-401a-b833-8caabce26ab9")
                return
            
            # Validate UUID format
            uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
            if not re.match(uuid_pattern, issue_id, re.IGNORECASE):
                self.io.print_error(f"Invalid issue ID format: {issue_id}")
                self.io.print_info("Issue ID should be a valid UUID (e.g., 10244b08-ea69-401a-b833-8caabce26ab9)")
                return
            
            # ========== Step 2: Check MCP service ==========    
            if not mcp_service.has_config():
                self.io.print_error("MCP service is not configured")
                self.io.print_info("Please configure li-mate MCP server in ~/.siada-cli/mcp_config.json:")
                return
            
            # Check if li-mate server is configured
            mcp_config = mcp_service.get_mcp_config()
            if mcp_config and mcp_config.servers and 'li-mate' not in mcp_config.servers:
                self.io.print_error("li-mate MCP server is not configured")
                self.io.print_info("Please add li-mate server configuration in ~/.siada-cli/mcp_config.json")
                return
            
            # ========== Step 3: Display info and return issue_id ==========
            self.io.print_info(f"Starting issue fix for: {issue_id}")
            
            # Return issue_id as input for the agent
            return SwitchEvent(ai_analysis_prompt=issue_id)
            
        except Exception as e:
            self.io.print_error(f"Failed to start issue fix: {str(e)}")
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
    # Plugin Manager (/plugin)
    # =========================================================================

    def _is_acp_mode(self) -> bool:
        """Return True when running inside an ACP (UI) session."""
        return (
            hasattr(self.io, 'acp_adapter') and self.io.acp_adapter is not None
        )

    def _plugin_log(self, msg: str):
        """Buffer a plugin status message for later flush."""
        if not hasattr(self, '_plugin_buf'):
            self._plugin_buf: list = []
        self._plugin_buf.append(msg)

    def _plugin_flush(self):
        """Print all buffered plugin messages as a single box, then clear buffer."""
        if not getattr(self, '_plugin_buf', None):
            return
        combined = '\n'.join(self._plugin_buf)
        self._plugin_buf = []
        self.io.print_info(combined)

    _DEFAULT_MARKETPLACES = [
        {
            "name": "lixiang-skills-marketplace",
            "repo": "https://gitlab.chehejia.com/ai-market/lixiang-skills-marketplace.git",
            "url": "https://gitlab.chehejia.com/ai-market/lixiang-skills-marketplace.git",
        },
    ]

    def _get_plugin_config(self) -> dict:
        """Read plugin config, injecting default marketplaces if missing."""
        import json
        from siada.foundation.constants import SIADA_HOME
        config_path = SIADA_HOME / "plugin_config.json"
        if not config_path.exists():
            config = {"marketplaces": [], "disabled_skills": []}
        else:
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception:
                config = {"marketplaces": [], "disabled_skills": []}

        # Ensure default marketplaces are present (keyed by name)
        existing_names = {m.get("name") for m in config.get("marketplaces", [])}
        added = False
        for default_mp in self._DEFAULT_MARKETPLACES:
            if default_mp["name"] not in existing_names:
                config.setdefault("marketplaces", []).insert(0, dict(default_mp))
                added = True
        if added:
            try:
                SIADA_HOME.mkdir(parents=True, exist_ok=True)
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
        return config

    def _save_plugin_config(self, config: dict):
        """Save plugin config to ~/.siada-cli/plugin_config.json"""
        import json
        from siada.foundation.constants import SIADA_HOME
        SIADA_HOME.mkdir(parents=True, exist_ok=True)
        config_path = SIADA_HOME / "plugin_config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    def _fetch_marketplace_skills(self, marketplace: dict, installed_names: set) -> list:
        """Fetch available skills from marketplace.json first, fallback to repo scan."""
        import json as _json
        import urllib.request
        import urllib.error
        from urllib.parse import quote

        repo_val = marketplace.get("repo", "")
        url_val = marketplace.get("url", "")
        ref_url = url_val or repo_val
        configured_path = marketplace.get("path", "skills")
        mp_name = marketplace.get("name", repo_val.split("/")[-1] if "/" in repo_val else repo_val)

        if not ref_url:
            return []

        # ── Detect provider ──────────────────────────────────────────────
        is_gitlab = False
        gitlab_host = ""
        gitlab_project = ""
        github_repo = ""  # owner/repo

        if ref_url.startswith("http://") or ref_url.startswith("https://"):
            from urllib.parse import urlparse
            parsed = urlparse(ref_url)
            host = parsed.hostname or ""
            path_parts = parsed.path.strip("/").removesuffix(".git")
            if "github.com" in host:
                github_repo = path_parts  # owner/repo
            else:
                # Assume GitLab-compatible (self-hosted or gitlab.com)
                is_gitlab = True
                gitlab_host = f"{parsed.scheme}://{host}"
                gitlab_project = path_parts  # owner/repo
        elif "/" in ref_url and not ref_url.startswith("git@"):
            # Short owner/repo form — assume GitHub
            github_repo = ref_url.removesuffix(".git")
        else:
            return []

        def _parse_description(content: str) -> str:
            in_fm = False
            for line in content.splitlines():
                if line.strip() == "---":
                    in_fm = not in_fm
                    continue
                if in_fm and line.startswith("description:"):
                    return line[len("description:"):].strip().strip('"').strip("'")
            return ""

        def _fetch_url(url: str, headers: dict | None = None, timeout: int = 8) -> bytes | None:
            try:
                req = urllib.request.Request(url, headers=headers or {"User-Agent": "siada-cli"})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return r.read()
            except Exception:
                return None

        def _normalize_marketplace_json(payload: dict) -> list:
            items = payload.get("skills") if isinstance(payload, dict) else None
            if not isinstance(items, list):
                return []
            skills = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                skill_name = item.get("name") or item.get("id") or item.get("slug")
                if not skill_name:
                    continue
                skills.append({
                    "name": skill_name,
                    "description": item.get("description", "") or f"Skill from {mp_name}",
                    "marketplace": repo_val,
                    "marketplaceName": mp_name,
                    "installed": skill_name in installed_names,
                    "installs": str(item.get("installs", "")) if item.get("installs") is not None else "",
                })
            return skills

        # ── marketplace.json first ────────────────────────────────────────
        marketplace_json = None
        if is_gitlab:
            encoded_proj = quote(gitlab_project, safe="")
            for branch_name in (marketplace.get("branch", "main"), "main", "master"):
                encoded_file = quote(".claude-plugin/marketplace.json", safe="")
                url = (
                    f"{gitlab_host}/api/v4/projects/{encoded_proj}/repository/files/{encoded_file}/raw"
                    f"?ref={quote(branch_name)}"
                )
                data = _fetch_url(url)
                if data:
                    try:
                        marketplace_json = _json.loads(data.decode("utf-8", errors="replace"))
                        break
                    except Exception:
                        pass
        elif github_repo:
            for branch_name in (marketplace.get("branch", "main"), "main", "master"):
                url = f"https://raw.githubusercontent.com/{github_repo}/{branch_name}/.claude-plugin/marketplace.json"
                data = _fetch_url(url)
                if data:
                    try:
                        marketplace_json = _json.loads(data.decode("utf-8", errors="replace"))
                        break
                    except Exception:
                        pass

        if marketplace_json is not None:
            skills = _normalize_marketplace_json(marketplace_json)
            if skills:
                return skills

        # ── Fetch directory listing ───────────────────────────────────────
        def list_dirs_github(path: str) -> list[str]:
            url = f"https://api.github.com/repos/{github_repo}/contents/{path}"
            data = _fetch_url(url, {"User-Agent": "siada-cli", "Accept": "application/vnd.github.v3+json"})
            if not data:
                return []
            try:
                entries = _json.loads(data)
                return [e["name"] for e in entries if e.get("type") == "dir" and not e["name"].startswith(".")]
            except Exception:
                return []

        def list_dirs_gitlab(path: str) -> list[str]:
            encoded = quote(gitlab_project, safe="")
            results = []
            page = 1
            while True:
                url = (
                    f"{gitlab_host}/api/v4/projects/{encoded}/repository/tree"
                    f"?path={quote(path)}&per_page=100&page={page}&recursive=false"
                )
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "siada-cli"})
                    with urllib.request.urlopen(req, timeout=8) as r:
                        data = r.read()
                        next_page = r.headers.get("X-Next-Page", "")
                except Exception:
                    break
                try:
                    entries = _json.loads(data)
                    results.extend(
                        e["name"] for e in entries
                        if e.get("type") == "tree" and not e["name"].startswith(".")
                    )
                except Exception:
                    break
                if not next_page:
                    break
                page += 1
            return results

        list_dirs = list_dirs_gitlab if is_gitlab else list_dirs_github

        def has_skill_md(path: str) -> bool:
            """Return True if the given path contains a SKILL.md file."""
            if is_gitlab:
                encoded_proj = quote(gitlab_project, safe="")
                encoded_file = quote(f"{path}/SKILL.md", safe="")
                url = f"{gitlab_host}/api/v4/projects/{encoded_proj}/repository/files/{encoded_file}/raw"
            else:
                url = f"https://raw.githubusercontent.com/{github_repo}/HEAD/{path}/SKILL.md"
            return _fetch_url(url, timeout=4) is not None

        # Try configured path first
        skill_names = list_dirs(configured_path)
        actual_path = configured_path

        if not skill_names:
            # Fall back: list root directories
            root_dirs = list_dirs("")
            if root_dirs:
                # Check if root dirs are containers (no SKILL.md themselves)
                # by looking inside each one for sub-directories
                for container in root_dirs:
                    sub_dirs = list_dirs(container)
                    if sub_dirs:
                        # Verify at least one sub-dir looks like a skill
                        sample = sub_dirs[0]
                        if has_skill_md(f"{container}/{sample}"):
                            skill_names = sub_dirs
                            actual_path = container
                            break
                if not skill_names:
                    # Root dirs themselves are likely skills
                    skill_names = root_dirs
                    actual_path = ""

        if not skill_names:
            return []

        # ── Fetch SKILL.md description for each skill ─────────────────────
        def fetch_skill_md_github(skill: str) -> str:
            prefix = f"{actual_path}/{skill}" if actual_path else skill
            url = f"https://raw.githubusercontent.com/{github_repo}/HEAD/{prefix}/SKILL.md"
            data = _fetch_url(url, timeout=5)
            return _parse_description(data.decode("utf-8", errors="replace")) if data else ""

        def fetch_skill_md_gitlab(skill: str) -> str:
            prefix = f"{actual_path}/{skill}" if actual_path else skill
            encoded_proj = quote(gitlab_project, safe="")
            encoded_file = quote(f"{prefix}/SKILL.md", safe="")
            url = f"{gitlab_host}/api/v4/projects/{encoded_proj}/repository/files/{encoded_file}/raw"
            data = _fetch_url(url, timeout=5)
            return _parse_description(data.decode("utf-8", errors="replace")) if data else ""

        fetch_desc = fetch_skill_md_gitlab if is_gitlab else fetch_skill_md_github

        skills = []
        for skill_name in skill_names:
            description = ""
            try:
                description = fetch_desc(skill_name)
            except Exception:
                pass
            skills.append({
                "name": skill_name,
                "description": description or f"Skill from {mp_name}",
                "marketplace": repo_val,
                "marketplaceName": mp_name,
                "installed": skill_name in installed_names,
                "installs": "",
            })

        return skills

    def _send_plugin_manager_ui(self, session):
        """Collect data and send ui/showPluginManager notification to frontend."""
        from siada.services.skills import SkillsManager
        from siada.io.acp.message_builder import ACPMessageBuilder
        from pathlib import Path

        workspace = Path(session.siada_config.workspace)
        manager = SkillsManager.get_instance()
        outcome = manager.get_skills(workspace)
        plugin_config = self._get_plugin_config()

        disabled_skills = plugin_config.get("disabled_skills", [])
        marketplaces_cfg = plugin_config.get("marketplaces", [])

        # Build installed skills data
        installed = []
        installed_names = set()
        for skill in outcome.skills:
            installed.append({
                "name": skill.name,
                "description": skill.description[:200] if skill.description else "",
                "scope": skill.scope.name.lower(),
                "path": str(skill.path),
            })
            installed_names.add(skill.name)

        # Build errors data
        errors = []
        for err in outcome.errors:
            errors.append({
                "path": str(err.path),
                "message": err.message,
                "scope": err.scope.name.lower(),
            })

        # Build marketplaces data (counts based on locally installed)
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

        # Use cached discover skills stored by 'marketplace update' — no live fetch here
        discover = []
        for mp in marketplaces_cfg:
            for skill in mp.get("_cached_skills", []):
                skill["installed"] = skill.get("name", "") in installed_names
                discover.append(skill)

        params = {
            "installed": installed,
            "marketplaces": marketplaces,
            "errors": errors,
            "discover": discover,
            "disabledSkills": disabled_skills,
        }

        try:
            message = ACPMessageBuilder().build_custom_notification(
                method="ui/showPluginManager",
                params=params,
            )
            if self.io.acp_adapter.transport and self.io.acp_adapter.transport.is_connected:
                self.io.acp_adapter.transport.send_sync(message)
                logger.info("Sent ui/showPluginManager notification")
        except Exception as e:
            logger.error(f"Failed to send plugin manager notification: {e}")

    def cmd_plugin(self, session, args: str):
        """Manage skills/plugins (discover, install, disable, remove, marketplace)

        Usage:
            /plugin                              - Open plugin manager UI
            /plugin install <repo> <skill>       - Install a skill from a marketplace repo
            /plugin remove <skill>               - Remove an installed user-scope skill
            /plugin disable <skill>              - Disable a skill (exclude from context)
            /plugin enable <skill>               - Re-enable a disabled skill
            /plugin marketplace add <owner/repo> - Add a marketplace repository
            /plugin marketplace remove <name>    - Remove a marketplace
            /plugin marketplace update <name>    - Refresh marketplace skill list
        """
        args_stripped = args.strip()

        # Open UI (no args)
        if not args_stripped:
            if hasattr(self.io, 'acp_adapter') and self.io.acp_adapter is not None:
                try:
                    self._send_plugin_manager_ui(session)
                except Exception as e:
                    self.io.print_error(f"Failed to open plugin manager: {e}")
            else:
                # Non-ACP mode: print installed skills list
                try:
                    from siada.services.skills import SkillsManager
                    from pathlib import Path
                    manager = SkillsManager.get_instance()
                    outcome = manager.get_skills(Path(session.siada_config.workspace))
                    config = self._get_plugin_config()
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
                    lines.append("\nUsage: /plugin install <repo> <skill> | /plugin marketplace add <owner/repo>")
                    self.io.print_info("\n".join(lines))
                except Exception as e:
                    self.io.print_error(f"Error: {e}")
            return

        parts = args_stripped.split(None, 2)
        subcmd = parts[0].lower()

        # ── install <skill> [@marketplace] ────────────────────────────────
        if subcmd == "install":
            rest = args_stripped[len(subcmd):].strip()
            if not rest:
                self.io.print_error("Usage: /plugin install <skill_name> [@marketplace]")
                return
            # Detect @marketplace anywhere in the string (handles any whitespace type)
            at_idx = rest.find('@')
            if at_idx > 0:
                skill_name = rest[:at_idx].strip()
                repo = rest[at_idx + 1:].strip()
            else:
                tokens = rest.split(None, 1)
                skill_name = tokens[0]
                repo = tokens[1].lstrip('@').strip() if len(tokens) > 1 else None
            if not skill_name:
                self.io.print_error("Usage: /plugin install <skill_name> [@marketplace]")
                return
            self._plugin_install(session, repo or None, skill_name)
            self._plugin_flush()

        # ── remove <skill> ────────────────────────────────────────────────
        elif subcmd == "remove":
            if len(parts) < 2:
                self.io.print_error("Usage: /plugin remove <skill_name>")
                return
            self._plugin_remove(session, parts[1])
            self._plugin_flush()

        # ── disable <skill> ───────────────────────────────────────────────
        elif subcmd == "disable":
            if len(parts) < 2:
                self.io.print_error("Usage: /plugin disable <skill_name>")
                return
            self._plugin_set_disabled(parts[1], disabled=True)
            self._plugin_flush()

        # ── enable <skill> ────────────────────────────────────────────────
        elif subcmd == "enable":
            if len(parts) < 2:
                self.io.print_error("Usage: /plugin enable <skill_name>")
                return
            self._plugin_set_disabled(parts[1], disabled=False)
            self._plugin_flush()

        # ── marketplace <action> ──────────────────────────────────────────
        elif subcmd == "marketplace":
            if len(parts) < 3:
                self.io.print_error("Usage: /plugin marketplace add|remove|update <name_or_repo>")
                return
            mp_action = parts[1].lower()
            mp_arg = parts[2]
            if mp_action == "add":
                self._plugin_marketplace_add(mp_arg)
            elif mp_action == "remove":
                self._plugin_marketplace_remove(mp_arg)
            elif mp_action == "update":
                self._plugin_marketplace_update(session, mp_arg)
            else:
                self.io.print_error(f"Unknown marketplace action: {mp_action}")
            self._plugin_flush()

        else:
            self.io.print_error(f"Unknown /plugin subcommand: {subcmd}")
            self.io.print_info("Available: install, remove, disable, enable, marketplace")

    def _plugin_install(self, session, repo, skill_name: str):
        """Install a skill via git clone.

        repo may be None (search all marketplaces), a marketplace name/query,
        a full URL, or an owner/repo slug. Leading '@' is stripped by the caller.
        """
        import shutil
        import subprocess
        import tempfile
        from pathlib import Path
        from siada.foundation.constants import SIADA_HOME

        plugin_config = self._get_plugin_config()
        branch = "main"
        skill_path_prefix = "skills"
        clone_url = None  # full git-clonable URL

        # ── resolve which marketplace to use ──────────────────────────────
        if repo is None:
            marketplaces = plugin_config.get("marketplaces", [])
            if not marketplaces:
                self.io.print_error(
                    "No marketplaces configured. "
                    "Add one with: /plugin marketplace add <url_or_owner/repo>"
                )
                return
            matched = marketplaces[0]  # default fallback
            for mp in marketplaces:
                mp_skills = self._fetch_marketplace_skills(mp, set())
                if any(s["name"] == skill_name for s in mp_skills):
                    matched = mp
                    break
            branch = matched.get("branch", "main")
            skill_path_prefix = matched.get("path", "skills")
            clone_url = matched.get("url") or matched.get("repo", "")
        else:
            # repo is a name / short slug / full URL — try marketplace lookup first
            for mp in plugin_config.get("marketplaces", []):
                if self._mp_matches(mp, repo):
                    branch = mp.get("branch", "main")
                    skill_path_prefix = mp.get("path", "skills")
                    clone_url = mp.get("url") or mp.get("repo", "")
                    break
            if clone_url is None:
                # treat as a direct URL or owner/repo (GitHub default)
                clone_url = repo
                if not clone_url.startswith("http") and not clone_url.startswith("git@"):
                    clone_url = f"https://github.com/{clone_url}"

        dest_dir = SIADA_HOME / "skills" / skill_name
        if dest_dir.exists():
            self.io.print_error(f"Skill '{skill_name}' already exists at {dest_dir}")
            return

        self._plugin_log(f"Installing '{skill_name}' from {clone_url}...")

        # ── git clone into a temp dir, then copy skill subdirectory ──────
        with tempfile.TemporaryDirectory() as tmp:

            def _send_clone_progress(phase: str, pct: int):
                """Forward git clone progress to the frontend via ACP."""
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

            def _run_clone(extra_args: list) -> tuple:
                """Run git clone with progress streaming. Returns (returncode, stderr_text)."""
                import re as _re
                import threading as _threading
                _progress_re = _re.compile(r'([A-Za-z][A-Za-z ]+):\s+(\d+)%')

                proc = subprocess.Popen(
                    ["git", "clone", "--progress", "--depth=1"] + extra_args + [clone_url, tmp],
                    stderr=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                )
                stderr_lines = []

                def _read_stderr():
                    buf = b""
                    try:
                        while True:
                            chunk = proc.stderr.read(256)
                            if not chunk:
                                break
                            buf += chunk
                            parts = _re.split(b"[\r\n]", buf)
                            buf = parts[-1]
                            for part in parts[:-1]:
                                line = part.decode("utf-8", errors="replace").strip()
                                if line:
                                    stderr_lines.append(line)
                                m = _progress_re.search(line)
                                if m:
                                    _send_clone_progress(m.group(1).strip(), int(m.group(2)))
                    except Exception:
                        pass

                t = _threading.Thread(target=_read_stderr, daemon=True)
                t.start()
                try:
                    proc.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                    return -1, "git clone timed out"
                t.join(timeout=5)
                return proc.returncode, "\n".join(stderr_lines[-5:])

            rc, err_text = _run_clone([f"--branch={branch}"])
            if rc != 0:
                # Branch not found — clear tmp and retry with remote default
                for item in Path(tmp).iterdir():
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                rc, err_text = _run_clone([])
            if rc != 0:
                self.io.print_error(f"git clone failed: {err_text}")
                return

            skill_src = Path(tmp) / skill_path_prefix / skill_name
            if not skill_src.exists():
                # Fall back: search one level deep for a directory named skill_name
                found = next(
                    (
                        p
                        for p in Path(tmp).rglob(skill_name)
                        if p.is_dir() and p.parent != Path(tmp).parent
                    ),
                    None,
                )
                if found is None:
                    self.io.print_error(
                        f"Skill '{skill_name}' not found in {clone_url}"
                    )
                    return
                skill_src = found

            _send_clone_progress("done", 100)
            try:
                shutil.copytree(str(skill_src), str(dest_dir))
            except Exception as e:
                self.io.print_error(f"Failed to copy skill: {e}")
                return

        # ── success ───────────────────────────────────────────────────────
        try:
            from siada.services.skills import SkillsManager
            SkillsManager.get_instance().invalidate_cache()
        except Exception:
            pass
        self._plugin_log(f"✓ Installed '{skill_name}'")
        self._plugin_log("Restart Siada to pick up the new skill.")

    def _plugin_remove(self, session, skill_name: str):
        """Remove a user-scope skill directory."""
        import shutil
        from siada.foundation.constants import SIADA_HOME

        dest_dir = SIADA_HOME / "skills" / skill_name
        if not dest_dir.exists():
            self.io.print_error(f"Skill '{skill_name}' not found in user skills ({dest_dir})")
            return

        try:
            shutil.rmtree(dest_dir)
            # Invalidate cache
            from siada.services.skills import SkillsManager
            SkillsManager.get_instance().invalidate_cache()
            self._plugin_log(f"✓ Removed skill '{skill_name}'")
        except Exception as e:
            self.io.print_error(f"Failed to remove skill: {e}")

    def _plugin_set_disabled(self, skill_name: str, disabled: bool):
        """Add or remove a skill from the disabled list in plugin config."""
        config = self._get_plugin_config()
        disabled_list: list = config.get("disabled_skills", [])

        if disabled:
            if skill_name not in disabled_list:
                disabled_list.append(skill_name)
            config["disabled_skills"] = disabled_list
            self._save_plugin_config(config)
            self._plugin_log(f"✓ Disabled skill '{skill_name}'")
        else:
            if skill_name in disabled_list:
                disabled_list.remove(skill_name)
            config["disabled_skills"] = disabled_list
            self._save_plugin_config(config)
            self._plugin_log(f"✓ Enabled skill '{skill_name}'")

    @staticmethod
    def _mp_matches(mp: dict, query: str) -> bool:
        """Return True if marketplace entry matches the given name/repo/url query."""
        q = query.strip().lstrip("@")
        for field in ("name", "repo", "url"):
            val = mp.get(field, "")
            if val == q:
                return True
            # strip .git suffix for comparison
            if val.rstrip("/").removesuffix(".git") == q.removesuffix(".git"):
                return True
        return False

    def _plugin_marketplace_add(self, repo_input: str):
        """Add a marketplace repository to plugin config.

        Accepts a full URL (https://github.com/owner/repo.git or
        https://gitlab.example.com/owner/repo.git) or a short owner/repo slug.
        """
        config = self._get_plugin_config()
        marketplaces: list = config.get("marketplaces", [])

        # Check for duplicate
        for mp in marketplaces:
            if self._mp_matches(mp, repo_input):
                self.io.print_error(f"Marketplace '{repo_input}' is already configured")
                return

        # Derive a clean name (last path component, no .git)
        raw_name = repo_input.rstrip("/").split("/")[-1]
        name = raw_name.removesuffix(".git")

        entry: dict = {
            "name": name,
            "repo": repo_input,   # keep original value as the canonical lookup key
            "branch": "main",
            "path": "skills",
            "available": 0,
            "installed": 0,
        }
        # If it looks like a full URL, store it as "url" so install can use git clone
        if repo_input.startswith("http://") or repo_input.startswith("https://") or repo_input.startswith("git@"):
            entry["url"] = repo_input

        marketplaces.append(entry)
        config["marketplaces"] = marketplaces
        self._save_plugin_config(config)
        self._plugin_log(f"✓ Added marketplace '{name}' ({repo_input})")
        # Fetch skill list immediately so Discover tab is populated right away
        self._plugin_marketplace_update(None, name)

    def _plugin_marketplace_remove(self, name_or_repo: str):
        """Remove a marketplace from plugin config."""
        config = self._get_plugin_config()
        marketplaces: list = config.get("marketplaces", [])
        before = len(marketplaces)
        marketplaces = [mp for mp in marketplaces if not self._mp_matches(mp, name_or_repo)]
        if len(marketplaces) == before:
            self.io.print_error(f"Marketplace '{name_or_repo}' not found")
            return
        config["marketplaces"] = marketplaces
        self._save_plugin_config(config)
        self._plugin_log(f"✓ Removed marketplace '{name_or_repo}'")

    def _plugin_marketplace_update(self, session, name_or_repo: str):
        """Refresh available count for a marketplace."""
        config = self._get_plugin_config()
        marketplaces: list = config.get("marketplaces", [])
        target = None
        for mp in marketplaces:
            if self._mp_matches(mp, name_or_repo):
                target = mp
                break
        if target is None:
            self.io.print_error(f"Marketplace '{name_or_repo}' not found")
            return

        if not _marketplace_update_lock.acquire(blocking=False):
            self.io.print_error("A marketplace update is already in progress. Please wait.")
            return

        try:
            self._plugin_log(f"Updating marketplace '{target.get('name')}'...")
            from siada.services.skills import SkillsManager
            from pathlib import Path
            if session is not None:
                outcome = SkillsManager.get_instance().get_skills(
                    Path(session.siada_config.workspace)
                )
                installed_names = {s.name for s in outcome.skills}
            else:
                installed_names = set()
            skills = self._fetch_marketplace_skills(target, installed_names)
            target["available"] = len(skills)
            target["installed"] = sum(1 for s in skills if s["installed"])
            target["_cached_skills"] = skills
            import time as _time
            target["updatedAt"] = _time.strftime("%m/%d/%Y")
            config["marketplaces"] = marketplaces
            self._save_plugin_config(config)
            self._plugin_log(
                f"✓ Updated '{target.get('name')}': "
                f"{target['available']} available, {target['installed']} installed"
            )
        except Exception as e:
            self.io.print_error(f"Failed to update marketplace: {e}")
        finally:
            _marketplace_update_lock.release()

def main():
    md = SlashCommands(None, None).get_help_md()
    print(md)

if __name__ == "__main__":
    status = main()
    sys.exit(status)
