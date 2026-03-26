import os
import sys
import time
from pathlib import Path
from typing import Optional
import warnings
from prompt_toolkit.completion import Completer

# Fix sys.path for direct script execution (python siada/entrypoint/siadahub.py)
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_script_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from siada.config.config_loader import Config, load_conf
from siada.entrypoint.interaction.running_config import RunningConfig
from siada.entrypoint.interaction.controller import Controller
from siada.entrypoint.interaction.nointeractive_controller import NoInteractiveController
from siada.entrypoint.helpers.daemon_commands import (
    ensure_daemon_running, handle_stop_daemon, handle_daemon_status, handle_task_list,
)
from siada.entrypoint.helpers.model_setup import get_config, get_api_key_provider_models
from siada.foundation.logging import redirect_agents_logger, redirect_aiohttp_asyncio_logger, toggle_console_output, logger, get_log_directory, cleanup_old_logs
from siada.io.color_settings import RunningConfigColorSettings
from siada.session.session_manager import RunningSessionManager
from siada.support.completer import AutoCompleter
from siada.support.envprocessor import load_dotenv_files
from siada.support.repo import get_git_root
from siada.support.slash_commands import SlashCommands
from siada.utils import SettingsUtils
from siada.io.io import InputOutput
from siada.services.version_checker import version_checker

try:
    import git
except ImportError:
    git = None

from prompt_toolkit.enums import EditingMode
from siada.services.model_info_service import ModelInfoService


def _setup_mcp_config(config):
    """Setup MCP configuration synchronously without establishing connections."""
    if not config.mcp_config or not config.mcp_config.enabled:
        return
    if not config.mcp_config.servers:
        return

    try:
        from siada.services.mcp.manager_service import _mcp_manager_service as mcp_service
        from siada.foundation.constants import SIADA_HOME

        _validate_mcp_config(config)

        # Store config in global manager; connections are deferred to agent execution
        mcp_service.set_io(config.io)
        mcp_service.set_mcp_config(config.mcp_config)
        mcp_service.config_path = SIADA_HOME / "mcp_config.json"

        server_count = len(config.mcp_config.servers)
        logger.info(f"MCP: {server_count} servers configured (connections deferred)")
        if hasattr(config, 'io'):
            config.io.print_info(f"MCP: Configuration validated with {server_count} servers")

    except Exception as e:
        logger.error(f"MCP configuration setup failed: {e}", exc_info=True)
        if hasattr(config, 'io'):
            config.io.print_warning(f"MCP configuration setup failed: {e}")
        # Don't exit — MCP failure should not block startup


def _validate_mcp_config(config):
    """Validate MCP configuration without establishing connections"""
    mcp_config = config.mcp_config

    if not mcp_config.servers:
        raise ValueError("No MCP servers configured")

    for server_name, server_config in mcp_config.servers.items():
        try:
            transport_type = server_config.get_transport_type()

            if transport_type.value == "stdio":
                if not server_config.command:
                    raise ValueError(f"Server '{server_name}': command is required for stdio transport")
            elif transport_type.value == "http":
                # http transport accepts either url or http_url
                if not (server_config.url or server_config.http_url):
                    raise ValueError(f"Server '{server_name}': url or http_url is required for http transport")
            elif transport_type.value == "sse":
                if not server_config.url:
                    raise ValueError(f"Server '{server_name}': url is required for sse transport")
            else:
                raise ValueError(f"Server '{server_name}': unsupported transport type '{transport_type}'")

            if server_config.timeout <= 0:
                raise ValueError(f"Server '{server_name}': timeout must be positive")

        except Exception as e:
            raise ValueError(f"Invalid configuration for server '{server_name}': {e}")

    logger.info(f"MCP configuration validation passed for {len(mcp_config.servers)} servers")


def _suppress_third_party_warnings():
    """Suppress harmless warnings from third-party libraries."""
    # pydub: no audio features used in Siada
    warnings.filterwarnings("ignore", message="Couldn't find ffmpeg or avconv.*", category=RuntimeWarning)
    warnings.filterwarnings("ignore", message="invalid escape sequence.*", category=SyntaxWarning)
    # jieba: uses deprecated pkg_resources API
    warnings.filterwarnings("ignore", message=".*pkg_resources is deprecated.*", category=UserWarning, module="jieba._compat")
    redirect_aiohttp_asyncio_logger()
    redirect_agents_logger()


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
            logger.warning(f"Unknown arguments: {unknown}")
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
    if '--stop-daemon' in sys.argv:
        return handle_stop_daemon()
    if '--daemon-status' in sys.argv:
        return handle_daemon_status()
    return None


def handle_internal_commands(args, io) -> Optional[int]:
    """Handle internal (non-open-source) commands.

    Returns exit code if a command was handled, None to continue normal flow.
    """
    if args.stop_api_server or args.api_server:
        try:
            from siada.entrypoint.a2a.a2a_commands import handle_a2a_commands
        except ImportError as e:
            logger.warning("A2A internal commands are unavailable: %s", e)
            return 1

        return handle_a2a_commands(args, io)

    return None


def handle_special_commands(args, conf: Config, io) -> Optional[int]:
    """Handle special commands that don't need full initialization.

    Returns exit code if a command was handled, None to continue normal flow.
    """
    if (exit_code := handle_internal_commands(args, io)) is not None:
        return exit_code

    # Daemon management
    if args.stop_daemon:
        return handle_stop_daemon()
    if args.daemon_status:
        return handle_daemon_status()
    if args.task_list:
        return handle_task_list()

    # Model list
    if args.list_models:
        models = ModelInfoService.get_model_names()
        io.print_info("\n".join(f"- {model}" for model in models))
        return 0

    # Version management
    if args.just_check_update:
        update_available = version_checker.check_version(io, just_check=True, verbose=args.verbose)
        return 0 if not update_available else 1

    if args.upgrade:
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
                # NOTE: Do NOT call controller.show_announcements() here.
                # _run_interactive() calls it right after _apply_login() returns,
                # so it will pick up the updated model name automatically.
        except Exception as exc:
            logger.warning(f"[login] Failed to apply API key config to running model: {exc}")

    return None


def _build_session(args, conf, io, running_color_settings, model, workspace, interactive_mode):
    """Build all runtime components and create the session."""
    commands = SlashCommands(io=io, verbose=args.verbose, editor=args.editor)
    session_id = str(int(time.time() * 1000))
    logger.info(f"Session ID: {session_id}")

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
    )
    logger.log_timing("create_running_config")

    session = RunningSessionManager.create_session(siada_config=running_config, session_id=session_id)
    completer.append_custom_command(session=session)
    logger.log_timing("create_session")

    validate_agent_compatibility(args.agent, interactive_mode, io, args.verbose)

    if running_config.mcp_config and running_config.mcp_config.enabled and running_config.mcp_config.servers:
        try:
            _setup_mcp_config(running_config)
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


def _run_noninteractive(args, session, running_config, io) -> int:
    """Run non-interactive (--prompt) mode. Returns exit code."""
    logger.info(f"Starting non-interactive mode, prompt: {args.prompt}")

    outcome = _try_restore_session(args, session, io)
    if outcome is not None and not outcome[0]:
        return 1

    controller = NoInteractiveController(config=running_config, session=session)
    controller.run(args.prompt)
    logger.info("Non-interactive controller finished")

    try:
        io.print_info(f"Session history: {session.state.openai_session.session_file}")
        io.print_info(f"To continue this session, run: siada-cli --resume {session.session_id}")
    except Exception:
        pass

    return 0


def _run_interactive(args, session, running_config, commands, io, model) -> Optional[int]:
    """Run interactive mode. Returns exit code on error, None on clean exit."""
    controller = Controller(config=running_config, slash_commands=commands, session=session)
    logger.log_timing("create_controller")

    commands._controller = controller

    # Must check login BEFORE show_announcements(): show_announcements() sends the
    # `ready` signal + banner to the frontend, which immediately switches the UI to
    # the 'main' view.  If we then send ui/showLoginSelector afterwards, the user
    # sees the full main view rendered first, then the login overlay on top of it.
    # By checking login first, the frontend never enters the main view until we are
    # actually logged in.
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

    logger.info("Entering main interaction loop")
    controller.run()
    io.print_info(f"To continue this session, run: siada-cli --resume {session.session_id}")


def _prepare_startup():
    _maybe_start_debugpy()
    _suppress_third_party_warnings()
    from siada.entrypoint import _configure_litellm_logging
    _configure_litellm_logging()


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
        version_checker.check_version(io, just_check=args.acp, verbose=args.verbose)
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

    # 4.5 Early resume workspace check — fast fail before expensive setup
    if (exit_code := _check_resume_workspace_early(args, git_root, workspace_arg, io)) is not None:
        return exit_code

    # 5. Special commands
    if (exit_code := handle_special_commands(args, conf, io)) is not None:
        return exit_code

    # 6. Ensure daemon (only in interactive mode)
    if interactive_mode:
        ensure_daemon_running(conf, verbose=args.verbose)
    logger.log_timing("ensure_daemon")

    # 7. Setup & build session
    err, session, running_config, commands, model = _setup_and_build_session(
        args, conf, io, running_color_settings, git_root, workspace_arg, parser, interactive_mode
    )
    if err is not None:
        return err

    # 8. Run
    if not interactive_mode:
        return _run_noninteractive(args, session, running_config, io)

    return _run_interactive(args, session, running_config, commands, io, model)


if __name__ == "__main__":
    status = main()
    sys.exit(status)
