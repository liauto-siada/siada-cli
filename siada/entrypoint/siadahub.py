import time as _siadahub_time
_MODULE_LOAD_START = _siadahub_time.perf_counter()

import os
import sys
import time
from pathlib import Path
from typing import Optional
import warnings

# Fix sys.path for direct script execution (python siada/entrypoint/siadahub.py)
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_script_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from prompt_toolkit.completion import Completer  # noqa: E402
from siada.config.config_loader import Config, load_conf  # noqa: E402
from siada.entrypoint.interaction.running_config import RunningConfig
from siada.entrypoint.interaction.controller import Controller
from siada.entrypoint.interaction.nointeractive_controller import NoInteractiveController
from siada.entrypoint.helpers.daemon_commands import (
    ensure_daemon_running, handle_stop_daemon, handle_restart_daemon, handle_daemon_status, handle_task_list,
)
from siada.entrypoint.helpers.model_setup import get_config, get_api_key_provider_models
from siada.foundation.logging import redirect_agents_logger, redirect_aiohttp_asyncio_logger, redirect_openhands_aci_logger, toggle_console_output, logger, get_log_directory, cleanup_old_logs
from siada.io.color_settings import RunningConfigColorSettings
from siada.session.session_manager import RunningSessionManager
from siada.support.envprocessor import load_dotenv_files
from siada.support.repo import get_git_root
from siada.utils import SettingsUtils
from siada.io.io import InputOutput
from prompt_toolkit.enums import EditingMode

try:
    import git
except ImportError:
    git = None



def _maybe_print_auto_update_notice(io) -> None:
    """Show a lightweight notice when daemon already installed a newer version."""
    from siada.services.auto_update import get_restart_required_message
    message = get_restart_required_message()
    if message:
        io.print_warning(message)


# MCP bootstrap helpers were moved to siada.services.mcp.setup so that other
# entry points (LarkController, A2A server, daemons, etc.) can register the
# MCPConfig with the global ``_mcp_manager_service`` singleton in the same
# way the CLI does. The aliases below preserve the original symbol names
# for any external callers that may still import them from this module.
from siada.services.mcp.setup import setup_mcp_config as _setup_mcp_config  # noqa: E402
from siada.services.mcp.setup import validate_mcp_config as _validate_mcp_config  # noqa: E402



def _suppress_third_party_warnings():
    """Suppress harmless warnings from third-party libraries."""
    # pydub: no audio features used in Siada
    warnings.filterwarnings("ignore", message="Couldn't find ffmpeg or avconv.*", category=RuntimeWarning)
    warnings.filterwarnings("ignore", message="invalid escape sequence.*", category=SyntaxWarning)
    # jieba: uses deprecated pkg_resources API
    warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*", category=UserWarning, module="jieba._compat")
    redirect_aiohttp_asyncio_logger()
    redirect_agents_logger()
    redirect_openhands_aci_logger()


def _parse_args_and_setup_environment(argv):
    """Parse CLI arguments, detect git root, load dotenv files.

    Returns:
        (args, git_root, workspace_arg, parser, interactive_mode)
    """
    import argparse

    # --workspace must be resolved before building the full parser (affects git root detection)
    temp_parser = argparse.ArgumentParser(add_help=False)
    temp_parser.add_argument("--workspace", default=None)
    temp_args, _ = temp_parser.parse_known_args(argv)

    git_root = get_git_root(temp_args.workspace) if git is not None else None

    from siada.entrypoint.args_parser.args import get_parser, SiadaArgs
    parser = get_parser(git_root=git_root, default_config_files=[])
    try:
        _raw_args, unknown = parser.parse_known_args(argv)
        if unknown:
            print(f"error: unrecognized arguments: {' '.join(unknown)}", file=sys.stderr)
            parser.print_help(sys.stderr)
            sys.exit(2)
    except AttributeError as e:
        logger.error(f"Argument parsing failed: {e}")
        raise

    args = SiadaArgs(_raw_args)
    toggle_console_output(not args.disable_console_output)

    loaded_dotenvs = load_dotenv_files(git_root, args.env_file, args.encoding)
    if args.verbose:
        for fname in loaded_dotenvs:
            logger.info(f"Loaded {fname}")

    interactive_mode = not bool(args.prompt)
    if not interactive_mode:
        args.pretty = False

    return args, git_root, temp_args.workspace, parser, interactive_mode


def get_io(args, pretty=None):
    """Create and return a configured InputOutput instance.

    Raises:
        ValueError: if the theme name is invalid.
    """
    from siada.io.color_settings import ColorSettings

    acp_enabled = args.acp or os.environ.get('SIADA_ACP_MODE') == '1'

    color_settings = ColorSettings.from_theme(args.theme)
    running_color_settings = RunningConfigColorSettings(color_settings=color_settings, pretty=args.pretty)
    color_settings.apply_to_args(args)

    editing_mode = EditingMode.VI if args.vim else EditingMode.EMACS
    if acp_enabled:
        # In ACP mode, stdin is a pipe (not a TTY).  The Node.js frontend
        # writes \x03 (ETX) to the pipe as the primary interrupt mechanism
        # on ALL platforms.  Start the StdinInterruptMonitor to read stdin
        # byte-by-byte, detect ETX immediately, and inject KeyboardInterrupt
        # into the main thread.
        #
        # A custom SIGINT handler is also installed so that any OS-level
        # SIGINT (e.g., Windows CTRL_C_EVENT, or macOS kill -2) goes through
        # the same debounce logic, preventing double KeyboardInterrupt.
        from siada.io.stdin_interrupt_monitor import start_stdin_monitor, install_sigint_handler
        start_stdin_monitor()
        install_sigint_handler()
        logger.info("Started StdinInterruptMonitor and custom SIGINT handler for ACP mode")

        return InputOutput(
            pretty=args.pretty,
            running_color_settings=running_color_settings,
            encoding=args.encoding,
            line_endings=args.line_endings,
            editingmode=editing_mode,
            fancy_input=args.fancy_input,
            multiline_mode=False,
            notifications=True,
            acp_enabled=acp_enabled,
            acp_fallback=True,
        ), running_color_settings
    else:
        return InputOutput(
            pretty=args.pretty,
            running_color_settings=running_color_settings,
            encoding=args.encoding,
            line_endings=args.line_endings,
            editingmode=editing_mode,
            fancy_input=args.fancy_input,
            multiline_mode=False,
            notifications=True,
        ), running_color_settings


def set_env(args, io):
    """Apply --set-env assignments to os.environ. Returns 0 on success, 1 on error."""
    if args.set_env:
        for env_setting in args.set_env:
            try:
                name, value = env_setting.split("=", 1)
                os.environ[name.strip()] = value.strip()
            except ValueError:
                io.print_error(f"Invalid --set-env format: {env_setting}")
                io.print_info("Format should be: ENV_VAR_NAME=value")
                return 1
    
    return 0


def get_workspace(workspace_arg, git_root):
    """Resolve and chdir to the workspace. Priority: --workspace > git root > cwd."""
    if workspace_arg:
        workspace = os.path.abspath(workspace_arg)
        if not os.path.exists(workspace):
            logger.error(f"Workspace directory does not exist: {workspace}")
            sys.exit(1)
        if not os.path.isdir(workspace):
            logger.error(f"Workspace path is not a directory: {workspace}")
            sys.exit(1)
        os.chdir(workspace)
    else:
        workspace = git_root if git_root else os.getcwd()
    return workspace


def validate_agent_compatibility(agent_name, interactive_mode, io, verbose=False):
    """Exit with error if the agent's supported_modes conflicts with the current execution mode."""
    from siada.config.agent_config_loader import load_agent_config
    agent_config_collection = load_agent_config()
    agent_config = agent_config_collection.get_agent_config(agent_name)

    if agent_config and agent_config.supported_modes == "non_interactive" and interactive_mode:
        io.print_error(f"Agent '{agent_name}' only supports non-interactive mode, but current execution is in interactive mode.")
        io.print_info("Please use --prompt (-p) option to run in non-interactive mode.")
        sys.exit(1)
    elif agent_config and agent_config.supported_modes == "interactive" and not interactive_mode:
        io.print_error(f"Agent '{agent_name}' only supports interactive mode, but current execution is in non-interactive mode.")
        io.print_info("Please remove --prompt (-p) option to run in interactive mode.")
        sys.exit(1)


def show_banner(io):
    """Clear the terminal and display the Siada banner."""
    from siada.io.banner import show_siada_banner
    os.system('clear' if os.name != 'nt' else 'cls')
    try:
        io.rule()
        show_siada_banner(pretty=io.pretty, console=io.console)
    except UnicodeEncodeError as err:
        io.print_error("Terminal does not support pretty output (UnicodeDecodeError)")
        sys.exit(1)
    except Exception as err:
        io.print_error(f"Error showing banner: {err}")
        sys.exit(1)


def is_home_directory(workspace: str = None) -> bool:
    """Return True if workspace resolves to the user's home directory."""
    home_dir = Path.home()
    workspace_path = Path(workspace).resolve() if workspace else Path.cwd().resolve()
    return workspace_path == home_dir


def get_checkpointing_config(args, conf: Config = None, interactive_mode: bool = True):
    """Build CheckpointConfig. Priority: CLI args > config file > defaults.

    Non-interactive mode always disables checkpointing.
    """
    from siada.config.config_loader import CheckpointConfig

    if not interactive_mode:
        return CheckpointConfig(enable=False, max_checkpoint_files=50)

    # enable: args > conf > False
    if args.checkpointing is not None:
        enable = args.checkpointing
    elif conf and conf.checkpoint_config and conf.checkpoint_config.enable is not None:
        enable = conf.checkpoint_config.enable
    else:
        enable = False

    # max_checkpoint_files: args > conf > 50
    if args.max_checkpoint_files is not None:
        max_files = args.max_checkpoint_files
    elif conf and conf.checkpoint_config and conf.checkpoint_config.max_checkpoint_files is not None:
        max_files = conf.checkpoint_config.max_checkpoint_files
    else:
        max_files = 50

    return CheckpointConfig(enable=enable, max_checkpoint_files=max_files)


def _send_startup_error_to_ui(error_message: str, args=None):
    """Send a fatal startup error to the frontend before IO is initialised.

    In ACP mode sends a FAILED session-update so the UI can exit the
    "Loading configuration…" state; in TTY mode prints to stderr.
    """
    if args:
        acp_enabled = args.acp or os.environ.get('SIADA_ACP_MODE') == '1'
    else:
        acp_enabled = os.environ.get('SIADA_ACP_MODE') == '1'

    if not acp_enabled:
        print(f"Error: {error_message}", file=sys.stderr)
        return

    try:
        from siada.io.acp.message_builder import ACPMessageBuilder, SessionUpdateReason
        from siada.io.acp.transport.stdio import StdioTransport

        builder = ACPMessageBuilder()
        transport = StdioTransport()

        msg = builder.build_session_update(
            reason=SessionUpdateReason.FAILED,
            content=error_message,
            metadata={
                "type": "startup_error",
                "fatal": True
            }
        )

        transport.send_sync(msg)

        logger.info(f"Sent startup error to UI: {error_message}")

    except Exception as e:
        logger.error(f"Failed to send startup error to UI: {e}")


def _maybe_start_debugpy():
    """Start debugpy debug server if SIADA_DEBUG_PYTHON env var is set.
    
    This is triggered by the VSCode launch configuration 
    'npm-siada (with Python debugpy)' which sets SIADA_DEBUG_PYTHON=1.
    The debugpy server listens on port 5678 so VSCode can attach to it.
    """
    if not os.environ.get('SIADA_DEBUG_PYTHON'):
        return
    
    try:
        import debugpy
        debugpy_port = int(os.environ.get('DEBUGPY_PORT', '5678'))
        debugpy.listen(("127.0.0.1", debugpy_port))
        logger.info(f"debugpy listening on 127.0.0.1:{debugpy_port}")
        
        # If DEBUGPY_WAIT_FOR_ATTACH is set, block until debugger connects
        if os.environ.get('DEBUGPY_WAIT_FOR_ATTACH', '0') == '1':
            logger.info("Waiting for debugger to attach...")
            debugpy.wait_for_client()
            logger.info("Debugger attached!")
    except ImportError:
        logger.warning("debugpy not installed, skipping debug server setup")
    except Exception as e:
        logger.warning(f"Failed to start debugpy: {e}")


def _handle_pre_init_commands() -> Optional[int]:
    """
    Handle commands that don't require full initialization (config loading, imports, etc.).

    Checked against raw sys.argv before load_conf() is called, so these commands
    produce no startup noise (no timing logs, no MCP config loading, no litellm import).

    Returns:
        Exit code if command was handled, None to continue normal flow
    """
    if '--stop-daemon' in sys.argv or '--restart-daemon' in sys.argv or '--daemon-status' in sys.argv:
        # Silence openai.agents DEBUG "Shutting down trace provider" chatter
        # emitted during atexit.  Pre-init path bypasses
        # _suppress_third_party_warnings(), so apply the redirect directly here.
        try:
            redirect_agents_logger()
        except Exception:
            pass
    if '--stop-daemon' in sys.argv:
        return handle_stop_daemon()
    if '--restart-daemon' in sys.argv:
        return handle_restart_daemon()
    if '--daemon-status' in sys.argv:
        return handle_daemon_status()
    return None


def handle_special_commands(args, conf: Config, io) -> Optional[int]:
    """Handle special commands that don't need full initialization.

    Returns exit code if a command was handled, None to continue normal flow.
    """
    # Daemon management
    if args.stop_daemon:
        return handle_stop_daemon()
    if args.restart_daemon:
        return handle_restart_daemon()
    if args.daemon_status:
        return handle_daemon_status()
    if args.task_list:
        return handle_task_list()

    # Model list
    if args.list_models:
        from siada.services.model_info_service import ModelInfoService
        models = ModelInfoService.get_model_names()
        io.print_info("\n".join(f"- {model}" for model in models))
        return 0

    # Version management
    if args.just_check_update:
        from siada.services.version_checker import version_checker
        update_available = version_checker.check_version(io, just_check=True, verbose=args.verbose)
        return 0 if not update_available else 1

    if args.upgrade:
        from siada.services.version_checker import version_checker
        return 0 if version_checker.install_upgrade(io) else 1

    # Logout
    if args.logout:
        try:
            from siada.internal.services.idaas.auth_store import clear_login_state
            user_id = clear_login_state()
        except ImportError:
            user_id = None
        if user_id:
            io.print_info(f"Signed out from {user_id}.")
        else:
            io.print_info("You were not signed in.")
        return 0

    # Set credentials directly via --user-id / --access-token
    if args.user_id or args.access_token:
        try:
            from siada.internal.services.idaas.auth_store import save_login_state, get_stored_user_id, get_stored_access_token
        except ImportError:
            io.print_error("Credential management requires siada.internal (not available in this build).")
            return 1
        user_id = args.user_id or get_stored_user_id() or ""
        access_token = args.access_token or get_stored_access_token() or ""
        if not user_id:
            io.print_error("--user-id is required when setting credentials.")
            return 1
        if not access_token:
            io.print_error("--access-token is required when setting credentials.")
            return 1
        save_login_state(user_id=user_id, access_token=access_token)
        io.print_info(f"Credentials saved: user_id={user_id}")
        # The telemetry singleton was initialized at import time (before this save),
        # so update its in-memory user_id to reflect the newly saved credentials.
        try:
            from siada.internal.foundation.telemetry import telemetry as _telemetry
            _telemetry.config.user_id = user_id
        except Exception:
            pass
        if not args.prompt:
            return 0

    return None


def _apply_login(io, args, model, controller) -> Optional[int]:
    """
    Verify login state and apply any API-key provider config to the running model.

    Returns None on success, or an exit code on failure.
    """
    logger.info("Checking IDaaS login state")
    try:
        from siada.entrypoint.login.login_prompt import ensure_logged_in
        logged_in_user = ensure_logged_in(io, acp_mode=args.acp)
        if logged_in_user is None:
            logger.error("Login required but not completed. Exiting.")
            io.print_error("Login is required to use Siada. Please sign in and try again.")
            return 1
    except SystemExit:
        raise
    except Exception as exc:
        logger.error(f"Login check failed: {exc}")
        io.print_error(f"Login error: {exc}")
        return 1

    # If user logged in via API key (provider=default), apply to running model
    if logged_in_user and logged_in_user.startswith("api-key-"):
        try:
            from siada.entrypoint.login.login_prompt import get_applied_api_key_config
            from siada.models.model_base_config import set_user_model_settings, _user_model_settings
            api_cfg = get_applied_api_key_config()
            if api_cfg:
                model.provider = 'default'
                provider_id = api_cfg.get('provider_id', '')
                new_model_name = (api_cfg.get('model') or '').strip()
                base_url = (api_cfg.get('base_url') or '').strip()
                provider_models = get_api_key_provider_models(provider_id, new_model_name, base_url)
                if provider_models:
                    if _user_model_settings is not None:
                        # User already has models.json loaded (authoritative config).
                        # Only append models that don't already exist, preserving
                        # user-defined fields like default_thinking_tokens.
                        existing_names = {m.model_name for m in _user_model_settings}
                        for pm in provider_models:
                            if pm.model_name not in existing_names:
                                _user_model_settings.append(pm)
                    else:
                        # No models.json — use provider models as-is
                        set_user_model_settings(provider_models)
                if new_model_name:
                    try:
                        model.configure_model_settings(new_model_name)
                    except ValueError:
                        logger.warning(f"Could not configure model settings for {new_model_name}, keeping existing")
                logger.info(f"[login] Applied API key config: provider=default, model={model.model_name}")
                # Update the global provider tracker so the litellm token-refresh
                # callback knows to skip IDaaS auth for 'default' provider calls.
                try:
                    from siada.entrypoint import set_current_provider
                    set_current_provider('default')
                except Exception:
                    pass
                # NOTE: Do NOT call controller.show_announcements() here.
                # _run_interactive() calls it right after _apply_login() returns,
                # so it will pick up the updated model name automatically.
        except Exception as exc:
            logger.warning(f"[login] Failed to apply API key config to running model: {exc}")

    return None


def _build_session(args, conf, io, running_color_settings, model, workspace, interactive_mode):
    """Build all runtime components and create the session."""
    from siada.support.slash_commands import SlashCommands
    commands = SlashCommands(io=io, verbose=args.verbose, editor=args.editor)
    from siada.foundation.id_generator import generate_session_id
    session_id = generate_session_id()
    logger.info(f"Session ID: {session_id}")

    from siada.support.completer import AutoCompleter
    completer: Completer = AutoCompleter(
        root=workspace,
        commands=commands,
        encoding=args.encoding,
        session_id=session_id,
    )
    logger.log_timing("init_commands_and_completer")

    checkpointing_config = get_checkpointing_config(args, conf, interactive_mode)
    if checkpointing_config.enable and is_home_directory(workspace):
        io.print_warning("Warning: workspace is home directory, disabling checkpointing for safety.")
        from siada.config.config_loader import CheckpointConfig
        checkpointing_config = CheckpointConfig(
            enable=False, max_checkpoint_files=checkpointing_config.max_checkpoint_files
        )

    running_config = RunningConfig(
        llm_config=model,
        io=io,
        workspace=workspace,
        agent_name=args.agent,
        completer=completer,
        running_color_settings=running_color_settings,
        console_output=not args.disable_console_output if interactive_mode else True,
        interactive=interactive_mode,
        mcp_config=conf.mcp_config,
        checkpointing_config=checkpointing_config,
        acp_mode=args.acp,
        compaction_strategy=conf.compaction_strategy,
        memory_enabled=conf.memory_config.enabled,
        enable_notification=conf.enable_notification,
    )
    logger.log_timing("create_running_config")

    session = RunningSessionManager.create_session(siada_config=running_config, session_id=session_id)
    completer.append_custom_command(session=session)
    logger.log_timing("create_session")

    validate_agent_compatibility(args.agent, interactive_mode, io, args.verbose)

    if running_config.mcp_config and running_config.mcp_config.enabled and running_config.mcp_config.servers:
        try:
            _setup_mcp_config(running_config)
            _start_mcp_warmup_async()
        except Exception as e:
            logger.error(f"MCP configuration setup failed: {e}", exc_info=True)
    logger.log_timing("validate_and_mcp_setup")

    return session, running_config, commands


def _try_restore_session(args, session, io):
    """Restore a previous session if --resume was given.

    Returns:
        None               – --resume not specified
        (True, session_data) – restored successfully
        (False, None)      – failed, error already printed to io
    """
    if args.resume is None:
        return None
    from siada.support.resume_service import ResumeService
    resume_id = args.resume or 'latest'
    logger.info(f"Restoring session: {resume_id!r}")
    current_ws = session.siada_config.workspace
    resume_service = ResumeService(current_ws)

    # Fast workspace check before loading full session data
    session_info = resume_service.get_session_info(resume_id)
    if session_info is None:
        io.print_error(f"Session not found: {resume_id}")
        return False, None
    origin_root = session_info.project_root or ''
    if origin_root and origin_root != 'Unknown' and os.path.normpath(origin_root) != os.path.normpath(current_ws):
        io.print_warning(f"Session belongs to workspace: {origin_root}")
        io.print_info(
            f"To resume this session, run:  cd {origin_root} && siada-cli --resume {session_info.session_id}"
        )
        return False, None

    result = resume_service.execute(resume_id)
    if result and result[0]:
        session_data, msg = result
        resume_service.restore_to_running_session(session_data, session)
        logger.info(f"Session resumed: {msg}")
        return True, session_data
    else:
        io.print_error(result[1] if result else "Failed to resume session")
        return False, None


def _run_noninteractive(args, session, running_config, io, model) -> int:
    """Run non-interactive (--prompt) mode. Returns exit code."""
    logger.info(f"Starting non-interactive mode, prompt: {args.prompt}")

    outcome = _try_restore_session(args, session, io)
    if outcome is not None and not outcome[0]:
        return 1

    controller = NoInteractiveController(config=running_config, session=session)

    # Apply login / API-key provider config (same as interactive path)
    login_err = _apply_login(io, args, model, controller)
    if login_err is not None:
        return login_err

    # FileSession lazily imports agents.memory.session on first access.
    # Join the agents-init thread now so the import lock is free.
    _ensure_agents_ready()
    controller.run(args.prompt)
    logger.info("Non-interactive controller finished")

    try:
        io.print_info(f"Session history: {session.state.openai_session.session_file}")
        model_name = getattr(model, 'model_name', '') or getattr(model, 'model', '')
        io.print_info(f"Model: {model_name}")
        io.print_info(f"To continue this session, run: siada-cli --resume {session.session_id}")
    except Exception:
        pass

    return 0


def _run_interactive(args, session, running_config, commands, io, model) -> Optional[int]:
    """Run interactive mode. Returns exit code on error, None on clean exit."""
    controller = Controller(config=running_config, slash_commands=commands, session=session)
    logger.log_timing("create_controller")

    commands._controller = controller

    # ACP fast-path: if stored credentials exist, defer login verification to a
    # background thread so banner_info is sent immediately (~800ms saved).
    # Falls back to synchronous login when no credentials exist at all (new user /
    # logged-out) — must block before banner to avoid showing the main view then
    # flashing a login overlay on top.
    if args.acp and _has_stored_credentials():
        _start_login_init_async(io, args, model, controller)
    else:
        login_err = _apply_login(io, args, model, controller)
        if login_err is not None:
            return login_err

    controller.show_announcements()
    logger.log_timing("ui_ready")

    outcome = _try_restore_session(args, session, io)
    if outcome is not None and outcome[0]:
        _, session_data = outcome
        controller.show_announcements()
        if args.acp:
            commands._send_history_to_ui(session_data.items)
            # Re-push the resumed session's goal state (if any) so the
            # GoalStatusBar reappears immediately on startup, rather than
            # staying blank until the next conversation turn happens to
            # run SiadaRunner._prepare_context_for_run's lazy
            # pending_goal -> context.goal consumption. This is the
            # `siada-cli --resume <id>` startup path -- SlashCommands.
            # cmd_resume (the interactive `/resume` slash command) has its
            # own identical push right after its own
            # restore_to_running_session() call; this path bypasses
            # cmd_resume entirely, so it needs the same push here too.
            commands._push_resumed_goal_state_to_ui(session)


    # Join login thread before first prompt — user typing takes long enough that
    # this is typically a no-op (0 ms wait).
    login_err = _ensure_login_ready()
    if login_err is not None:
        return login_err

    # FileSession lazily imports agents.memory.session on first access.
    # Join the agents-init thread now so the import lock is free.
    _ensure_agents_ready()
    logger.info("Entering main interaction loop")
    controller.run()
    io.print_info(f"To continue this session, run: siada-cli --resume {session.session_id}")


_litellm_init_thread = None
_agents_init_thread = None
_login_init_thread = None
_login_init_result: Optional[int] = None  # None = not done, int = exit code (0 = ok, nonzero = fail)


def _start_litellm_init_async():
    """Start litellm import + configuration in a background thread.

    Kicks off immediately at process start so the heavy import overlaps with
    all other startup work (arg parsing, IO init, session build, etc.).
    Call _ensure_litellm_ready() before the first LLM call to join.
    """
    import threading
    from siada.entrypoint import _configure_litellm

    global _litellm_init_thread
    _litellm_init_thread = threading.Thread(
        target=_configure_litellm,
        daemon=True,
        name="litellm-init",
    )
    _litellm_init_thread.start()


def _ensure_litellm_ready():
    """Join the litellm init thread before the first LLM call.

    Safe to call multiple times: after the first join the thread reference is
    cleared so subsequent calls are instant no-ops.
    """
    global _litellm_init_thread
    if _litellm_init_thread is None:
        # Thread not set: either we're in the daemon process (litellm already loaded)
        # or the thread was already joined on a previous call. Either way, nothing to do.
        return
    if _litellm_init_thread.is_alive():
        _litellm_init_thread.join(timeout=15)
    logger.log_timing("litellm_ready")
    _litellm_init_thread = None  # mark consumed — future calls return immediately


def _start_agents_init_async():
    """Start openai-agents SDK import in a background thread.

    Agents SDK and provider discovery run sequentially in the *same* thread.
    Running them as two concurrent threads caused Windows import-lock deadlocks:
    both threads race to acquire the `agents` module lock simultaneously, and
    `providers-init` then holds that lock while importing google.adk (slow on
    Windows), blocking the main thread when it later needs `from agents import …`
    (e.g. inside siada_runner.py). Sequential execution eliminates the race.

    _ensure_agents_ready() joins this combined thread before the first LLM call.
    """
    import threading

    def _warmup_agents_then_providers():
        try:
            from agents import ModelProvider  # noqa: F401
            from agents.memory.session import SessionABC  # noqa: F401
        except Exception:
            pass
        # Apply siada-side monkey-patches to the agents SDK in this same
        # background thread — the patch imports `agents.run_internal.
        # turn_resolution`, which is heavy. Doing it here keeps it in
        # parallel with the main thread instead of forcing a synchronous
        # heavy import on whoever first touches `siada.foundation.setting`.
        try:
            from siada.foundation.sdk_patches import apply_sdk_patches
            apply_sdk_patches()
        except Exception:
            pass
        # Provider discovery runs AFTER agents SDK is fully in sys.modules so
        # `from agents import ModelProvider` inside _discover_providers() is a
        # no-op cache hit and cannot race with the agents-init import above.
        try:
            import siada.provider.provider_factory as _pf  # noqa: F401
            _pf._discover_providers()
        except Exception:
            pass

    global _agents_init_thread
    _agents_init_thread = threading.Thread(
        target=_warmup_agents_then_providers,
        daemon=True,
        name="agents-init",
    )
    _agents_init_thread.start()


def _start_mcp_warmup_async():
    """Start MCP service warmup in a background thread as early as possible during boot.

    IMPORTANT: We must NOT call ``_mcp_manager_service.initialize()`` here.
    MCP stdio/HTTP/SSE clients are anyio-based and bind their connections to the
    event loop that created them. If we open the connections in a temporary
    event loop in this background thread and then close that loop, the
    connections become "orphans" tied to a dead loop. The agent later runs in
    a different loop (the main asyncio loop) and any ``call_tool`` against
    those orphan servers raises a cross-loop error that anyio swallows,
    producing empty tool results and an infinite retry loop on the model side.

    Therefore the warmup is now restricted to lightweight, loop-agnostic work:
      * preloading litellm / agents SDK modules
      * refreshing the Lark OAuth token via plain HTTP
    Real MCP server connections are established lazily by ``MCPManagerService.
    initialize()`` inside the agent's own event loop on first use.
    """
    import threading
    def _warmup():
        try:
            import asyncio
            import time

            # Wait for litellm, agents SDK, and model providers to be fully loaded and registered
            # to prevent Python multi-threading module import & registry race conditions.
            _ensure_litellm_ready()
            _ensure_agents_ready()

            from siada.services.mcp.manager_service import _mcp_manager_service

            # Wait a split second to avoid overlapping with lock file creation
            time.sleep(0.3)
            if _mcp_manager_service.has_config() and not _mcp_manager_service.is_initialized:
                logger.info("[MCP Warmup] Starting background MCP token warmup...")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    # ONLY refresh tokens here (loop-agnostic HTTP call).
                    # Do NOT call _mcp_manager_service.initialize() — see docstring above.
                    loop.run_until_complete(_mcp_manager_service.check_and_refresh_lark_token())
                    logger.info("[MCP Warmup] Background MCP token warmup complete (connections deferred)")
                finally:
                    loop.close()
        except Exception as e:
            logger.debug(f"[MCP Warmup] Background MCP warmup failed: {e}")

    threading.Thread(target=_warmup, daemon=True, name="mcp-warmup").start()


def _ensure_agents_ready():
    """Join the agents SDK thread before create_session().

    Only waits for agents.memory.session to be importable (race-condition
    guard for FileSession).  Provider discovery runs independently.
    Safe to call multiple times: clears the thread reference after first join.
    """
    global _agents_init_thread
    if _agents_init_thread is None:
        return
    if _agents_init_thread.is_alive():
        _agents_init_thread.join(timeout=15)
    _agents_init_thread = None  # mark consumed


def _start_login_init_async(io, args, model, controller):
    """Start _apply_login() in a background thread (~800ms cold).

    Kicks off immediately after the controller and IO are ready so login
    verification overlaps with UI rendering.  Call _ensure_login_ready()
    before the first user interaction to join.

    Only used in ACP interactive mode where a fast-path check confirms a
    stored user_id already exists.  If no credentials exist at all we fall
    back to synchronous login (must block before sending banner_info).
    """
    import threading

    def _run():
        global _login_init_result
        result = _apply_login(io, args, model, controller)
        _login_init_result = result if result is not None else 0

    global _login_init_thread, _login_init_result
    _login_init_result = None
    _login_init_thread = threading.Thread(
        target=_run,
        daemon=True,
        name="login-init",
    )
    _login_init_thread.start()


def _ensure_login_ready() -> Optional[int]:
    """Join the login init thread before the first prompt is processed.

    Returns the login exit code (None or 0 = success, nonzero = failure).
    Safe to call multiple times.
    """
    global _login_init_thread, _login_init_result
    if _login_init_thread is None:
        return None
    if _login_init_thread.is_alive():
        _login_init_thread.join(timeout=30)
    _login_init_thread = None
    result = _login_init_result
    _login_init_result = None
    return result if result else None


def _has_stored_credentials() -> bool:
    """Fast check: does conf.yaml contain a user_id or provider=default config?

    Reads conf.yaml directly without importing any heavy IDaaS modules.
    Used to decide whether login can be deferred to a background thread.
    """
    try:
        import yaml
        conf_path = __import__('pathlib').Path.home() / ".siada-cli" / "conf.yaml"
        if not conf_path.exists():
            return False
        with open(conf_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        # LiId login path
        if data.get("user_id", "").strip():
            return True
        # API-key login path
        if data.get("provider", "") == "default" and data.get("api_key", ""):
            return True
        return False
    except Exception:
        return False


def _preload_c_extensions_on_main_thread():
    """Phase 1: Load all high-risk C extensions (.pyd/.so) on the main thread.

    Must run BEFORE any background thread is started.

    On Windows, loading a C extension DLL acquires the OS Loader Lock and may
    execute DllMain / TLS callbacks that require the main thread to be
    responsive.  If the main thread is blocked (e.g. waiting for a worker
    thread that is itself waiting for the Loader Lock), a permanent deadlock
    occurs.

    By importing the C extensions here (main thread, no other threads alive),
    the DLLs get loaded safely.  Subsequent ``import`` from any thread only
    hits ``sys.modules`` (a dict lookup) — no DLL loading, no deadlock risk.

    High-risk packages in this venv:
      - numpy (OpenBLAS/MKL init in DllMain)
      - pandas (depends on numpy)
      - pydantic_core (Rust extension, litellm types)
      - aiohttp (4 C extensions, litellm HTTP layer)
      - yaml (C extension, config loading)
      - cryptography (Rust extension, token/auth)

    On macOS/Linux this is a no-op perf-wise (dlopen has no main-thread
    requirement), but it's harmless and makes the code uniformly safe.
    """
    import sys
    if sys.platform == "win32":
        # Only pay the cost on Windows where the deadlock actually occurs.
        # Each import is individually try/except'd so a missing optional
        # package doesn't block startup.
        try:
            import pydantic_core  # noqa: F401 — Rust extension, litellm types
        except ImportError:
            pass
        try:
            import yaml  # noqa: F401 — C extension (PyYAML)
        except ImportError:
            pass
        try:
            import numpy  # noqa: F401 — OpenBLAS DllMain
        except ImportError:
            pass
        try:
            import aiohttp  # noqa: F401 — 4 C extensions (httpparser etc.)
        except ImportError:
            pass
        try:
            import cryptography  # noqa: F401 — Rust extension
        except ImportError:
            pass


def _prepare_startup():
    _maybe_start_debugpy()
    _suppress_third_party_warnings()
    # litellm init runs in background thread started at top of main()


def _setup_and_build_session(args, conf, io, running_color_settings, git_root, workspace_arg, parser, interactive_mode):
    """Configure model, workspace, and build the session.

    Returns (None, session, running_config, commands, model) on success,
    or (exit_code, None, None, None, None) on failure.
    """
    try:
        model = get_config(args, io, conf)
    except ValueError as e:
        io.print_error(str(e))
        _send_startup_error_to_ui(str(e), args)
        return 1, None, None, None, None
    logger.log_timing("configure_model")

    if set_env(args, io) != 0:
        error_msg = "Failed to set environment variables. Please check your API keys configuration."
        _send_startup_error_to_ui(error_msg, args)
        return 1, None, None, None, None

    workspace = get_workspace(workspace_arg, git_root)
    if args.verbose:
        io.print_info(f"Agent: {args.agent}")
        io.print_info(f"Workspace: {workspace}")
        io.print_info(SettingsUtils.format_settings(parser, args))

    if args.check_update and not args.prompt:
        _maybe_print_auto_update_notice(io)
        if args.verbose:
            from siada.services.version_checker import version_checker
            version_checker.check_version(io, just_check=True, verbose=True)
    logger.log_timing("setup_workspace")

    session, running_config, commands = _build_session(
        args, conf, io, running_color_settings, model, workspace, interactive_mode
    )
    logger.log_timing("build_session")

    return None, session, running_config, commands, model


def _load_conf_and_args():
    conf = load_conf()
    args, git_root, workspace_arg, parser, interactive_mode = _parse_args_and_setup_environment(sys.argv[1:])
    return conf, args, git_root, workspace_arg, parser, interactive_mode


def _check_resume_workspace_early(args, git_root, workspace_arg, io) -> Optional[int]:
    """Early workspace check for --resume flag, before expensive session building.

    Reads only session metadata (fast). Returns 1 to abort, None to continue.
    """
    if args.resume is None:
        return None

    resume_id = args.resume or 'latest'

    # Resolve current workspace cheaply — same logic as get_workspace() but no chdir side-effect
    if workspace_arg:
        current_ws = os.path.abspath(workspace_arg)
    else:
        current_ws = git_root if git_root else os.getcwd()

    # resume_service.py imports agents.models.chatcmpl_converter at module level.
    # If _agents_init_thread still holds the agents package import lock, Python raises
    # _DeadlockError and the backend crashes silently.  Join the thread first.
    _ensure_agents_ready()

    from siada.support.resume_service import ResumeService
    resume_service = ResumeService(current_ws)
    session_info = resume_service.get_session_info(resume_id)

    if session_info is None:
        io.print_error(f"Session not found: {resume_id}")
        return 1

    origin_root = session_info.project_root or ''
    if origin_root and origin_root != 'Unknown' and \
            os.path.normpath(origin_root) != os.path.normpath(current_ws):
        io.print_warning(f"Session belongs to workspace: {origin_root}")
        io.print_info(
            f"To resume this session, run:  cd {origin_root} && siada-cli --resume {session_info.session_id}"
        )
        return 1

    return None


def _resolve_headroom_config(args, conf):
    """Merge CLI args + conf.yaml into a HeadroomProxyConfig.

    Precedence (high -> low): CLI args > conf.yaml > dataclass defaults.
    ``--no-headroom`` always wins and forces enabled=False.
    Upstream URLs are NOT configurable (hard-coded in the manager module).

    Headroom is an internal-only proxy integration (siada.internal). This
    resolver is called unconditionally on every startup (see main()), so in
    an open-source build lacking siada.internal it must degrade to a
    permanently-disabled config instead of crashing the CLI.
    """
    try:
        from siada.internal.services.headroom_proxy_manager import HeadroomProxyConfig
    except ImportError:
        from types import SimpleNamespace
        return SimpleNamespace(enabled=False)

    hc = getattr(conf, "headroom_config", None)

    enabled = bool(getattr(hc, "enabled", False))
    if args.headroom:
        enabled = True
    if args.no_headroom:
        enabled = False

    host = getattr(hc, "host", "127.0.0.1")
    port = args.headroom_port if args.headroom_port is not None else getattr(hc, "port", 8787)
    budget = args.headroom_budget if args.headroom_budget is not None else getattr(hc, "budget", None)
    budget_period = getattr(hc, "budget_period", "daily")
    telemetry = bool(getattr(hc, "telemetry", False))
    startup_timeout = float(getattr(hc, "startup_timeout", 30.0))


    return HeadroomProxyConfig(
        enabled=enabled,
        host=host,
        port=int(port),
        budget=budget,
        budget_period=budget_period,
        telemetry=telemetry,
        startup_timeout=startup_timeout,
    )


def _inject_headroom_mcp_config(conf):
    """Inject the headroom MCP server into conf.mcp_config (in-memory only).

    Does not touch ~/.siada-cli/mcp_config.json. If MCP was globally disabled,
    re-enable it so that _setup_mcp_config() runs for the injected server.
    """
    from siada.config.mcp_config import MCPServerConfig

    mcp_config = getattr(conf, "mcp_config", None)
    if mcp_config is None:
        return
    if "headroom" not in mcp_config.servers:
        mcp_config.servers["headroom"] = MCPServerConfig(
            type="stdio",
            command="headroom",
            args=["mcp", "serve"],
            env={},
        )
    # MCPConfig is a frozen dataclass; use object.__setattr__ to flip enabled.
    if not mcp_config.enabled:
        object.__setattr__(mcp_config, "enabled", True)
    logger.info('[headroom] MCP server "headroom" injected into config')


def _ensure_headroom_proxy(args, conf, io):
    """Phase 6.6: connect THIS CLI process to a daemon-managed headroom proxy.

    The proxy lifecycle (spawn/stop) is owned entirely by the proactive daemon
    (see SiadaDaemon._start_headroom / shutdown). Here we only:
      1. resolve whether headroom is desired (--headroom flag or conf.yaml);
      2. block-probe the daemon's /health endpoint until ready (or timeout);
      3. inject env vars + MCP config so this process routes LLM traffic through
         the proxy.
    We never spawn or kill the proxy. A timeout is NON-fatal: we warn and fall
    back to a direct connection (returning None so startup continues).

    Returns None always (never aborts startup).
    """
    hp_config = _resolve_headroom_config(args, conf)
    if not hp_config.enabled:
        return None

    import time as _t

    host = hp_config.host
    port = hp_config.port
    io.print_info("[headroom] Checking daemon-managed proxy ...")

    # Bounded wait: the daemon owns the proxy and reports an authoritative
    # in-memory status over IPC. We poll it so we can (a) fast-fail the moment
    # the daemon reports a terminal-unavailable state, and (b) keep waiting only
    # while it is still "starting" (or the daemon is still cold-booting and its
    # IPC endpoint is not up yet).
    #
    # OWNERSHIP RULE: we connect ONLY to a proxy the daemon itself spawned, i.e.
    # when the daemon reports status == "running". We deliberately do NOT run an
    # independent /health probe as a fast path: a healthy headroom that the
    # daemon did NOT start (e.g. one launched manually on the same port, which
    # the daemon reports as "port_conflict") must never be adopted — its upstream
    # routing is unknown and it is not part of siada's lifecycle. The /health
    # check is used only to confirm readiness AFTER the daemon claims "running".
    deadline = _t.time() + max(hp_config.startup_timeout, 30.0)

    unavailable = ("not_installed", "port_conflict", "error", "disabled", "stopped")
    connected = False
    while _t.time() < deadline:
        status = _query_daemon_headroom_status()
        if status is not None:
            st = status.get("status")
            if st in unavailable:
                io.print_warning(
                    f"[headroom] proxy unavailable (status={st}); "
                    "falling back to direct connection."
                )
                return None
            if st == "running":
                # Trust only a daemon-owned proxy. Adopt the exact host/port the
                # daemon chose, then confirm readiness via /health before use.
                host = status.get("host") or host
                port = int(status.get("port") or port)
                if _probe_headroom_health(host, port):
                    connected = True
                    break
        # status is None (daemon IPC not up yet) or "starting": keep waiting.
        # Never probe /health independently here — see OWNERSHIP RULE above.
        _t.sleep(0.4)


    if not connected:
        io.print_warning(
            f"[headroom] proxy at {host}:{port} not ready; "
            "falling back to direct connection."
        )
        return None

    os.environ["SIADA_USE_HEADROOM"] = "1"
    os.environ["SIADA_LLM_BASE_URL"] = f"http://{host}:{port}"
    _inject_headroom_mcp_config(conf)
    io.print_info(
        f"[headroom] Connected ({host}:{port}); routing LLM traffic through proxy."
    )
    logger.info(
        "[headroom] env injected: SIADA_USE_HEADROOM=1, "
        f"SIADA_LLM_BASE_URL=http://{host}:{port}"
    )
    return None


def _query_daemon_headroom_status():
    """Query the daemon's in-memory headroom status over IPC (best-effort).

    Returns the status dict, or None if the daemon is unreachable. Uses a short
    IPC timeout so a missing/booting daemon never blocks startup.
    """
    try:
        from siada.foundation.ipc_client import DaemonIPCClient
    except Exception:
        return None
    client = DaemonIPCClient(timeout=2.0)
    try:
        if not client.connect():
            return None
        return client.headroom_status()
    except Exception:
        return None
    finally:
        try:
            client.disconnect()
        except Exception:
            pass


def _probe_headroom_health(host, port) -> bool:
    """Return True if a headroom proxy answers /health at host:port.

    Short timeout (2s) so a dead/absent proxy never blocks startup for long.
    """
    import json as _json
    import urllib.request

    url = f"http://{host}:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            data = _json.loads(resp.read())
        return data.get("service") == "headroom-proxy" and bool(data.get("ready"))
    except Exception:
        return False


def main():
    """CLI main entry point.

    Startup sequence:
      1. Pre-init commands  — handle --stop-daemon / --daemon-status before any imports
      2. Prepare startup    — start debugpy if requested, suppress noisy third-party warnings
      3. Load conf & args   — read conf.yaml, parse CLI args, detect git root, load .env files
      4. Init IO            — create InputOutput (theme, color settings, ACP mode)
      5. Special commands   — handle one-shot flags (--api-server, --list-models, --upgrade …)
      6. Ensure daemon      — start background daemon if not already running
      7. Setup & build      — configure LLM model, resolve workspace, build the session object
      8. Run                — dispatch to interactive or non-interactive controller
    """
    logger.start_timing("main")
    _module_load_ms = (_siadahub_time.perf_counter() - _MODULE_LOAD_START) * 1000
    logger.debug(f"[startup-timing] module_imports (before main): {_module_load_ms:.1f} ms")

    # 0. Phase 1: Pre-load all C extensions on the MAIN thread BEFORE any
    #    background thread starts.
    #
    #    On Windows, loading a C extension (.pyd / DLL) acquires the OS Loader
    #    Lock.  If that first load happens on a non-main thread while the main
    #    thread is blocked waiting for that thread, the DllMain / TLS callbacks
    #    that need the main thread create a deadlock:
    #
    #      non-main thread: Import Lock → dlopen(.pyd) → waits Loader Lock
    #      main thread:     Loader Lock (DllMain/TLS needs main) → waits Import Lock
    #
    #    macOS dlopen() has no such requirement, so this is Windows-specific.
    #    Once the C extensions are in sys.modules, subsequent imports from any
    #    thread are just dict lookups — safe and instant.
    _preload_c_extensions_on_main_thread()

    # Phase 2: Background threads can now safely import pure-Python heavy
    # modules (litellm, agents SDK) that depend on the C extensions above.
    _start_litellm_init_async()   # litellm (~960ms cold)
    _start_agents_init_async()    # openai-agents SDK / provider_factory (~474ms cold)

    # 1. Pre-init commands
    if (exit_code := _handle_pre_init_commands()) is not None:
        return exit_code

    # 2. Prepare startup
    _prepare_startup()
    logger.log_timing("startup_preparation")

    # 3. Load conf & args
    conf, args, git_root, workspace_arg, parser, interactive_mode = _load_conf_and_args()
    logger.log_timing("load_conf_and_args")

    # 4. Init IO
    try:
        io, running_color_settings = get_io(args)
    except ValueError as e:
        _send_startup_error_to_ui(f"Invalid theme configuration: {e}", args)
        return 1
    logger.log_timing("init_io")

    # 5. Special commands
    if (exit_code := handle_special_commands(args, conf, io)) is not None:
        return exit_code

    # If headroom is desired, signal the daemon (spawned just below, which
    # inherits this process's env) to start the proxy. The daemon owns the
    # proxy's full lifecycle; the CLI only connects to it in Phase 6.6.
    if _resolve_headroom_config(args, conf).enabled:
        os.environ["SIADA_HEADROOM_ENABLED"] = "1"

    # 6. Ensure daemon (only in interactive mode, unless explicitly suppressed)
    # `--no-daemon` is honored by benchmark / scripted callers that must not
    # have background ProactiveScheduler jobs (cleanup_memory, daily_summary, ...)
    # mutating ~/.siada-cli/workspace/memory while a controlled run is in flight.
    if interactive_mode and not args.no_daemon:
        ensure_daemon_running(conf, verbose=args.verbose)
    elif args.no_daemon:
        logger.info("Skipping daemon startup: --no-daemon was passed")
    logger.log_timing("ensure_daemon")

    # 6.5 Early resume workspace check — fast fail before expensive session setup
    if (exit_code := _check_resume_workspace_early(args, git_root, workspace_arg, io)) is not None:
        return exit_code

    # 6.6 Ensure headroom proxy (if enabled) — SYNCHRONOUS, blocks until ready.
    # Must run before session build (Phase 7) so env vars are set before the
    # first LLM call and the headroom MCP server is injected before
    # _setup_mcp_config() runs.
    if (exit_code := _ensure_headroom_proxy(args, conf, io)) is not None:
        return exit_code
    logger.log_timing("ensure_headroom")

    # 7. Setup & build session
    # Initialize built-in plugin registry before session setup
    try:
        from siada.services.plugins.builtin_registry import init_builtin_plugins
        init_builtin_plugins()
    except Exception:
        pass

    err, session, running_config, commands, model = _setup_and_build_session(
        args, conf, io, running_color_settings, git_root, workspace_arg, parser, interactive_mode
    )
    if err is not None:
        return err

    # 8. Run
    if not interactive_mode:
        return _run_noninteractive(args, session, running_config, io, model)

    return _run_interactive(args, session, running_config, commands, io, model)


if __name__ == "__main__":
    status = main()
    sys.exit(status)
