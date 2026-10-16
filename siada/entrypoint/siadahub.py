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

# ---------------------------------------------------------------------------
# Agents-SDK import gate — keep before any other siada import: importing
# ``siada.foundation.sdk_patches`` installs a meta-path finder that serializes
# the SDK's *first* import from whichever thread needs it, so no import site has
# to remember calling ``ensure_agents_imported()``. The SDK is therefore no
# longer imported on this startup path (holding the ``agents`` module lock while
# the package initializes delayed the banner by ~0.5-0.6s). See
# ``_AgentsImportGate`` for details.
# ---------------------------------------------------------------------------
import siada.foundation.sdk_patches  # noqa: E402,F401  # installs the import gate

from siada.config.config_loader import Config, load_conf  # noqa: E402
from siada.entrypoint.interaction.running_config import RunningConfig
from siada.entrypoint.interaction.controller import Controller
from siada.entrypoint.interaction.nointeractive_controller import NoInteractiveController
from siada.entrypoint.helpers.daemon_commands import (
    ensure_daemon_running, handle_stop_daemon, handle_restart_daemon, handle_daemon_status, handle_task_list,
)
from siada.entrypoint.helpers.model_setup import (
    get_config,
    get_api_key_provider_models,
    merge_provider_models_into_user_settings,
)
from siada.foundation import herdr_reporter
from siada.foundation.logging import redirect_agents_logger, redirect_aiohttp_asyncio_logger, redirect_openhands_aci_logger, toggle_console_output, logger, get_log_directory, cleanup_old_logs
from siada.io.color_settings import RunningConfigColorSettings
from siada.session.session_manager import RunningSessionManager
from siada.support.envprocessor import load_dotenv_files
from siada.support.repo import get_git_root
from siada.utils import SettingsUtils
from siada.io.io import InputOutput



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


def _option_typo_hints(unknown, parser) -> list:
    """'did you mean' hints for unrecognized options (e.g. --browserr-host).

    Without them a typo'd flag only produces the error line plus a full help
    dump, which buries the actual mistake.
    """
    import difflib

    known = sorted({opt for action in parser._actions for opt in action.option_strings})
    hints = []
    for token in unknown:
        if not token.startswith("-"):
            continue
        match = difflib.get_close_matches(token, known, n=1, cutoff=0.8)
        if match:
            hints.append(f"did you mean: {token} -> {match[0]}")
    return hints


def _parse_args_and_setup_environment(argv):
    """Parse CLI arguments, detect git root, load dotenv files.

    Returns:
        (args, git_root, workspace_arg, parser, interactive_mode)
    """
    import argparse

    # --workspace must be resolved before building the full parser (affects git root detection)
    temp_parser = argparse.ArgumentParser(add_help=False)
    temp_parser.add_argument(
        "--workspace", "-w", nargs="?", const=".", default=os.environ.get("SIADA_WORKSPACE")
    )
    temp_args, _ = temp_parser.parse_known_args(argv)

    git_root = get_git_root(temp_args.workspace)

    from siada.entrypoint.args_parser.args import get_parser, SiadaArgs
    parser = get_parser(git_root=git_root, default_config_files=[])
    try:
        _raw_args, unknown = parser.parse_known_args(argv)
        if unknown:
            print(f"error: unrecognized arguments: {' '.join(unknown)}", file=sys.stderr)
            for hint in _option_typo_hints(unknown, parser):
                print(hint, file=sys.stderr)
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


def acp_enabled(args=None) -> bool:
    """Return True when this process talks ACP with the frontend.

    Two callers select ACP independently: the hosted UI spawns the backend with
    ``SIADA_ACP_MODE=1`` (no CLI flag), while a direct invocation passes
    ``--acp``. Login and runtime decisions must see the same answer in both
    cases, so they go through this helper instead of reading one source each.
    The accepted env values match the IO-layer detector
    (``siada.io.acp.legacy_adapter.ACPModeDetector``).
    """
    if args is not None and getattr(args, 'acp', False):
        return True
    return os.environ.get('SIADA_ACP_MODE', '').lower() in ('1', 'true', 'yes')


def get_io(args, pretty=None):
    """Create and return a configured InputOutput instance.

    Raises:
        ValueError: if the theme name is invalid.
    """
    from siada.io.color_settings import ColorSettings

    acp_mode = acp_enabled(args)

    color_settings = ColorSettings.from_theme(args.theme)
    running_color_settings = RunningConfigColorSettings(color_settings=color_settings, pretty=args.pretty)
    color_settings.apply_to_args(args)

    editing_mode = "VI" if args.vim else "EMACS"
    if acp_mode:
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
            acp_enabled=acp_mode,
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
    # The launcher has ACP bootstrap side effects; parsing must not import it.
    from siada.entrypoint.env_assignments import parse_env_assignments

    try:
        assignments = parse_env_assignments(args)
    except ValueError:
        io.print_error("Invalid --set-env format. Use ENV_VAR_NAME=value.")
        return 1
    os.environ.update(assignments)
    return 0


def get_workspace(workspace_arg, git_root):
    """Use the explicit workspace or cwd; git_root is only for environment loading."""
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
        workspace = os.getcwd()
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
    if not acp_enabled(args):
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


def _handle_browser_commands(args) -> Optional[int]:
    """Dispatch --browser-* flags to the browser-addon CLI implementation.

    The flags map 1:1 onto the ``siada-browser`` subcommands and reuse the
    same code path (``siada.browser_addon.cli``), so both entries stay in
    sync. Returns None when no browser flag was passed.
    """
    if args.browser_setup is not None:
        argv = ["setup"]
        if args.browser_setup:
            argv.append(args.browser_setup)
        if args.browser_port is not None:
            argv += ["--port", str(args.browser_port)]
        if args.browser_host is not None:
            argv += ["--host", args.browser_host]
        if args.browser_base_url:
            argv += ["--base-url", args.browser_base_url]
    elif args.browser_start:
        argv = ["start"]
    elif args.browser_stop:
        argv = ["stop"]
    elif args.browser_restart:
        argv = ["restart"]
    elif args.browser_status:
        argv = ["status"]
    else:
        return None

    from siada.browser_addon.cli import main as browser_main
    return browser_main(argv)


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

    # Browser proxy (chrome-acp) management
    if (exit_code := _handle_browser_commands(args)) is not None:
        return exit_code

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

    # Sign out: drop the stored provider API-key config from conf.yaml.
    if args.logout:
        try:
            from siada.entrypoint.login.login_prompt import clear_api_key_config
            cleared = clear_api_key_config()
        except Exception as exc:
            logger.warning(f"[logout] Failed to clear the stored API-key config: {exc}")
            cleared = False
        if cleared:
            io.print_info("Signed out. The stored provider API key was removed from conf.yaml.")
        else:
            io.print_info("No stored provider API key to sign out from.")
        return 0

    # --user-id / --access-token configured LiId (domain-account) credentials in
    # the closed-source build. The public CLI authenticates with user-supplied
    # provider API keys only, so these options fail with actionable guidance
    # rather than an ImportError.
    if args.user_id or args.access_token:
        io.print_error(
            "--user-id/--access-token are not supported: this build authenticates "
            "with a provider API key, not LiId/domain-account credentials."
        )
        io.print_info(
            "Configure a provider API key instead, e.g. "
            "`siada-cli --set-env BASE_URL=<provider-base-url> --set-env API_KEY=<your-api-key>`, "
            "or run `siada-cli` and choose \"Provide API key\" in the login prompt."
        )
        return 1

    return None


def _local_model_settings_entry(model_name: str):
    """Build a model-settings entry for ``model_name`` without any lookup.

    ``--model`` may name a model the provider catalogue does not list (a
    private/custom deployment). The provider lookup then only returns the
    catalogue's models, so the entry is built locally — reusing the built-in
    defaults when they know the name — to keep the running model under the name
    the user selected instead of silently falling back to another model.
    """
    from siada.models.model_base_config import MODEL_SETTING, ModelBaseConfig

    for entry in MODEL_SETTING:
        if entry.model_name == model_name:
            return entry
    return ModelBaseConfig(
        model_name=model_name,
        context_window=128_000,
        max_tokens=8192,
        parallel_tool_calls=True,
    )


def _apply_login(io, args, model, controller) -> Optional[int]:
    """
    Verify that usable credentials exist and apply the API-key config to the
    running model.

    Credentials in this build are provider API keys (stored ``llm_config`` in
    conf.yaml, or entered through the interactive API-key prompt). Returns None
    on success, or an exit code on failure — including when the credentials
    cannot be applied to the running model, so a broken sign-in is never
    reported as success.
    """
    logger.info("Checking stored credentials")
    try:
        from siada.entrypoint.login.login_prompt import ensure_logged_in
        logged_in_user = ensure_logged_in(io, acp_mode=acp_enabled(args))
        if logged_in_user is None:
            logger.error("No usable credentials found. Exiting.")
            io.print_error(
                "No usable credentials found: Siada CLI requires a provider API key."
            )
            io.print_info(
                "Configure one with `--set-env BASE_URL=<provider-base-url> "
                "--set-env API_KEY=<your-api-key>`, or run `siada-cli` and choose "
                "\"Provide API key\" in the login prompt."
            )
            return 1
    except SystemExit:
        raise
    except Exception as exc:
        logger.error(f"Credential check failed: {exc}")
        io.print_error(f"Could not verify credentials: {exc}")
        io.print_info(
            "Configure a provider API key with "
            "`--set-env BASE_URL=<provider-base-url> --set-env API_KEY=<your-api-key>`, "
            "or choose \"Provide API key\" in the login prompt."
        )
        return 1

    # If the user is authenticated with a provider API key (provider=default),
    # apply that provider config to the running model.
    if logged_in_user and logged_in_user.startswith("api-key-"):
        from siada.entrypoint.login.login_prompt import (
            get_applied_api_key_config,
            _field_text,
        )

        api_cfg = get_applied_api_key_config()
        if not api_cfg:
            # The api-key identity was reported without a config to apply:
            # continuing would run the session with credentials the model does
            # not know about, so fail the launch instead.
            logger.error("[login] API-key sign-in reported no applied provider config")
            io.print_error(
                "Signed in with a provider API key, but the provider configuration "
                "could not be applied."
            )
            io.print_info(
                "Run `siada-cli` again and choose \"Provide API key\" to reconfigure it."
            )
            return 1

        try:
            model.provider = 'default'
            # Defensive reads: the payload is normally strings (login_prompt
            # validates it), but a wrongly-typed field must not crash here —
            # an empty value simply reads as "not provided".
            provider_id = _field_text(api_cfg.get('provider_id')) or ''
            base_url = _field_text(api_cfg.get('base_url')) or ''
            stored_model = _field_text(api_cfg.get('model')) or ''
            # An explicit `--model` is a per-invocation choice and wins over the
            # model stored with the API-key config; the model `--model` /
            # conf.yaml selected is kept otherwise (env credentials carry no
            # model). getattr keeps callers whose args lack `model` working.
            args_model = getattr(args, 'model', None)
            args_model = args_model.strip() if isinstance(args_model, str) else ''
            selected_model = args_model or stored_model

            provider_models = get_api_key_provider_models(provider_id, selected_model, base_url)
            if args_model and not any(pm.model_name == args_model for pm in provider_models):
                # `--model` names a model the catalogue does not list: add its
                # settings entry locally (no catalogue/network lookup) so the
                # running model keeps the selected name.
                provider_models = list(provider_models) + [_local_model_settings_entry(args_model)]
            if provider_models:
                # Never replace an already-loaded user catalogue (models.json):
                # the user's custom fields (thinking budgets, prices, …) are
                # authoritative, so only missing models are appended.
                merge_provider_models_into_user_settings(provider_models)
            if selected_model:
                model.configure_model_settings(selected_model)
            logger.info(f"[login] Applied API key config: provider=default, model={model.model_name}")
            # Update the global provider tracker so the shared litellm
            # callbacks know that user-supplied credentials are in use.
            try:
                from siada.entrypoint import set_current_provider
                set_current_provider('default')
            except Exception:
                pass
            # NOTE: Do NOT call controller.show_announcements() here.
            # _run_interactive() calls it right after _apply_login() returns,
            # so it will pick up the updated model name automatically.
        except Exception as exc:
            # The running model/provider could not be pointed at the API-key
            # credentials: surface it as a failed sign-in rather than logging a
            # success and running with unauthenticated model settings.
            logger.error(f"[login] Failed to apply API key config to running model: {exc}")
            io.print_error(f"Could not apply the provider API key configuration: {exc}")
            io.print_info(
                "Check `--model` / `--provider` and ~/.siada-cli/conf.yaml, then try again."
            )
            return 1

    return None


def _build_session(args, conf, io, running_color_settings, model, workspace, interactive_mode):
    """Build all runtime components and create the session."""
    from siada.support.slash_commands import SlashCommands
    commands = SlashCommands(io=io, verbose=args.verbose, editor=args.editor)
    from siada.foundation.id_generator import generate_session_id
    session_id = generate_session_id()
    logger.info(f"Session ID: {session_id}")

    completer = None
    if io.prompt_session is not None:
        from siada.support.completer import AutoCompleter
        completer = AutoCompleter(
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
        acp_mode=acp_enabled(args),
        compaction_strategy=conf.compaction_strategy,
        memory_enabled=conf.memory_config.enabled,
        enable_notification=conf.enable_notification,
    )
    logger.log_timing("create_running_config")

    session = RunningSessionManager.create_session(siada_config=running_config, session_id=session_id)
    if completer is not None:
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
    """Run the ACP terminal controller and return its exit code."""
    if not running_config.acp_mode:
        io.print_error("The legacy Python interactive UI is no longer supported. "
                       "Launch siada-cli without --no-ui, or use --prompt.")
        return 1
    controller = Controller(config=running_config, slash_commands=commands, session=session)
    logger.log_timing("create_controller")

    commands._controller = controller

    # ACP fast-path: if a stored provider API-key config exists, defer the
    # credential check to a background thread so fresh sessions send
    # banner_info immediately (~800ms saved). Falls back to the synchronous
    # check when no credentials are stored (new user / signed out) — it must
    # block before banner to avoid showing the main view then flashing a login
    # overlay on top.
    if acp_enabled(args) and _has_stored_credentials():
        _start_login_init_async(io, args, model, controller)
    else:
        login_err = _apply_login(io, args, model, controller)
        if login_err is not None:
            controller.ui.close()
            return login_err

    # On --resume, the newly created session is only a placeholder. Restore its
    # original session_id before sending the first banner_info: otherwise the
    # UI paints the placeholder's banner, then remounts Static to paint the
    # resumed session's banner a second time a few hundred milliseconds later.
    # Without --resume this check returns immediately, preserving fast startup.
    outcome = _try_restore_session(args, session, io)
    controller.show_announcements()
    logger.log_timing("ui_ready")

    if outcome is not None and outcome[0]:
        _, session_data = outcome
        if acp_enabled(args):
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
        controller.ui.close()
        return login_err

    # FileSession lazily imports agents.memory.session on first access.
    # Join the agents-init thread now so the import lock is free.
    _ensure_agents_ready()
    logger.info("Entering main interaction loop")
    return controller.run()


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
        # Publish readiness for other siada threads (agent-class preload) even
        # if one of the steps below fails.
        from siada.foundation.sdk_patches import mark_agents_ready
        try:
            _warmup_agents_then_providers_inner()
        finally:
            mark_agents_ready()

    def _warmup_agents_then_providers_inner():
        # Serialize the SDK's first import against the other siada background
        # threads (agent-class preload, patch application): importing a
        # submodule while another thread is still initializing the ``agents``
        # package surfaces as "partially initialized module 'agents.items'".
        try:
            from siada.foundation.sdk_patches import ensure_agents_imported
            ensure_agents_imported()
        except Exception:
            pass
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
    try:
        from siada.foundation.sdk_patches import begin_agents_warmup
        begin_agents_warmup()
    except Exception:
        pass
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
    # Publishing readiness here too: if the warmup thread exited early (or the
    # join timed out), threads waiting on the handshake must not block further.
    try:
        from siada.foundation.sdk_patches import mark_agents_ready
        mark_agents_ready()
    except Exception:
        pass


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
        try:
            result = _apply_login(io, args, model, controller)
        except BaseException as exc:  # noqa: BLE001 - fail closed, see below
            # ``_login_init_result`` staying None would read as "sign-in fine"
            # (the success sentinel), so any failure in the worker must publish
            # an explicit non-zero exit code — including SystemExit raised by a
            # prompt that gave up on stdin.
            logger.error(f"[login] Login verification failed unexpectedly: {exc}")
            try:
                io.print_error(
                    "Could not verify the login credentials. "
                    "Run `siada-cli` again to reconfigure the provider API key."
                )
            except Exception:
                pass
            _login_init_result = 1
            return
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
    if _login_init_thread.is_alive():
        # Still blocked after the wait (e.g. the sign-in is waiting for a
        # frontend answer that never came): the credentials were never
        # verified, so fail the first prompt instead of letting an
        # unauthenticated session continue. The thread reference is kept so a
        # later caller can still observe/join the worker.
        logger.error("[login] Login verification did not finish within 30s")
        return 1
    _login_init_thread = None
    result = _login_init_result
    _login_init_result = None
    return result if result else None


def _has_stored_credentials() -> bool:
    """Fast check: does conf.yaml contain a stored provider API-key config?

    Reads conf.yaml directly without importing any provider/login modules, so
    it stays cheap enough for the ACP fast path. Only public API-key metadata
    counts as a credential: ``llm_config.provider == "default"`` plus a
    non-empty, string ``base_url`` *and* ``api_key``. Anything else — a
    missing/blank half of the pair, or a field of the wrong type — cannot
    authenticate this build and must not defer the login check.
    """
    from siada.config.conf_store import get_conf_section

    llm_config = get_conf_section("llm_config")
    if llm_config.get("provider") != "default":
        return False
    api_key = llm_config.get("api_key")
    base_url = llm_config.get("base_url")
    if not isinstance(api_key, str) or not isinstance(base_url, str):
        return False
    return bool(api_key.strip()) and bool(base_url.strip())


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

    # Make the agent visible to a hosting Herdr pane before the first turn, so
    # the pane reads as siada/idle instead of an unknown terminal process.
    herdr_reporter.report_state(
        herdr_reporter.STATE_IDLE, session_id=getattr(session, "session_id", None)
    )

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
        current_ws = os.getcwd()

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
        # One-shot commands return while background daemon threads may still
        # hold locks the interpreter finalizer needs: in ACP mode the stdin
        # interrupt monitor keeps reading stdin (fatal `_enter_buffered_busy`
        # at shutdown → SIGABRT), and the litellm/agents warmup threads may
        # still be importing. Flush and hard-exit to skip finalization.
        import logging
        logging.shutdown()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(exit_code if isinstance(exit_code, int) else 0)

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
