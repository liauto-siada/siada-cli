import json
import os
import sys
import threading
import time
import atexit
import asyncio
from dataclasses import fields
import warnings
from prompt_toolkit.completion import Completer

from siada.config.config_loader import Config, load_conf
from siada.entrypoint.interaction.running_config import RunningConfig
from siada.entrypoint.interaction.controller import Controller
from siada.entrypoint.interaction.nointeractive_controller import NoInteractiveController
from siada.foundation.logging import redirect_agents_logger, toggle_console_output, logger
from siada.io.color_settings import RunningConfigColorSettings
from siada.models.model_run_config import ModelRunConfig
from siada.session.session_manager import RunningSessionManager
from siada.support.completer import AutoCompleter
from siada.support.envprocessor import load_dotenv_files
from siada.support.repo import get_git_root
from siada.support.slash_commands import SlashCommands
from siada.utils import SettingsUtils
from siada.io.io import InputOutput
from siada.services.siada_memory import load_siada_memory
from siada.services.version_checker import version_checker

try:
    import git
except ImportError:
    git = None

from prompt_toolkit.enums import EditingMode
from siada.services.model_info_service import ModelInfoService

def _init_mcp_service(config):
    """Validate and store MCP configuration (no connection establishment)"""
    if not config.mcp_config or not config.mcp_config.enabled:
        return

    # Check if there are any servers configured
    if not config.mcp_config.servers:
        # No servers configured, return silently without any prompts
        return

    try:
        from siada.services.mcp_service import mcp_service

        # Validate MCP configuration
        _validate_mcp_config(config)

        # Store configuration in global manager for delayed initialization
        mcp_service.set_io(config.io)
        mcp_service.set_mcp_config(config.mcp_config)

        # Register cleanup hook for program exit
        if config.interactive:
            atexit.register(lambda: mcp_service.cleanup_sync())

        # Show configuration summary
        server_count = len(config.mcp_config.servers) if config.mcp_config.servers else 0
        config.io.print_info(f"MCP: Configuration validated with {server_count} servers")

    except Exception as e:
        if hasattr(config, 'io'):
            config.io.print_warning(f"MCP configuration validation failed: {e}")
        import logging
        logging.error(f"MCP config validation error: {e}")


def _validate_mcp_config(config):
    """Validate MCP configuration without establishing connections"""
    mcp_config = config.mcp_config

    if not mcp_config.servers:
        raise ValueError("No MCP servers configured")

    for server_name, server_config in mcp_config.servers.items():
        try:
            # Validate server configuration
            transport_type = server_config.get_transport_type()

            if transport_type.value == "stdio":
                if not server_config.command:
                    raise ValueError(f"Server '{server_name}': command is required for stdio transport")
            elif transport_type.value == "http":
                # HTTP transport can use either url or http_url field
                if not (server_config.url or server_config.http_url):
                    raise ValueError(f"Server '{server_name}': url or http_url is required for http transport")
            elif transport_type.value == "sse":
                if not server_config.url:
                    raise ValueError(f"Server '{server_name}': url is required for sse transport")
            else:
                raise ValueError(f"Server '{server_name}': unsupported transport type '{transport_type}'")

            # Validate timeout
            if server_config.timeout <= 0:
                raise ValueError(f"Server '{server_name}': timeout must be positive")

        except Exception as e:
            raise ValueError(f"Invalid configuration for server '{server_name}': {e}")

    import logging
    logging.info(f"MCP configuration validation passed for {len(mcp_config.servers)} servers")


def _suppress_third_party_warnings():
    """Suppress harmless warnings from third-party libraries"""
    # Suppress pydub ffmpeg/avconv warning - not relevant for Siada as we don't use audio features
    warnings.filterwarnings(
        "ignore", 
        message="Couldn't find ffmpeg or avconv.*", 
        category=RuntimeWarning
    )
    
    # Suppress all SyntaxWarning from pydub - use message pattern to catch invalid escape sequences
    warnings.filterwarnings(
        "ignore", 
        message="invalid escape sequence.*", 
        category=SyntaxWarning
    )
    
    redirect_agents_logger()


def _parse_args_and_setup_environment(argv):
    """
    Parse command line arguments and set up environment
    
    Args:
        argv: Command line argument list
        
    Returns:
        tuple: (args, unknown, loaded_dotenvs, git_root, workspace, parser) parsed arguments, unknown arguments, loaded environment variable files, git root directory, workspace path and parser
    """
    # workspace is specific for development and needs to be parsed early
    import argparse

    temp_parser = argparse.ArgumentParser(add_help=False)
    temp_parser.add_argument("--workspace", default=None)
    temp_args, _ = temp_parser.parse_known_args(argv)

    # Now get git root from the specified workspace or current directory
    if git is None:
        git_root = None
    else:
        git_root = get_git_root(temp_args.workspace)
    from siada.entrypoint.args_parser.args import get_parser
    parser = get_parser(git_root=git_root, default_config_files=[])
    try:
        args, unknown = parser.parse_known_args(argv)
    except AttributeError as e:
        raise e

    # Configure console output based on parsed arguments
    if hasattr(args, 'disable_console_output') and args.disable_console_output:
        toggle_console_output(False)
    else:
        toggle_console_output(True)

    loaded_dotenvs = load_dotenv_files(git_root, args.env_file, args.encoding)

    if args.verbose:
        for fname in loaded_dotenvs:
            logger.info(f"Loaded {fname}")

    return args, unknown, loaded_dotenvs, git_root, temp_args.workspace, parser


def get_io(args, pretty=None):
    """
    Create InputOutput instance with complete IO configuration
    
    Args:
        args: Parsed command line arguments
        pretty: Whether to enable pretty mode, defaults to args.pretty
        
    Returns:
        InputOutput: Configured IO instance
        
    Raises:
        ValueError: When theme configuration is invalid
    """
    from siada.io.color_settings import ColorSettings
    
    # Configure color settings
    color_settings = ColorSettings.from_theme(args.theme)
    running_color_settings = RunningConfigColorSettings(color_settings=color_settings, pretty=args.pretty)
    color_settings.apply_to_args(args)
    if args.verbose:
        print(f"Applied color theme: {args.theme}")
    
    # Configure editing mode
    editing_mode = EditingMode.VI if args.vim else EditingMode.EMACS
        
    return InputOutput(
        pretty=args.pretty,
        running_color_settings=running_color_settings,
        encoding=args.encoding,
        line_endings=getattr(args, "line_endings", "platform"),
        editingmode=editing_mode,
        fancy_input=args.fancy_input,
        multiline_mode=False,
        notifications=True,
    ), running_color_settings


def set_env(args, io):
    """
    Set environment variables, including general environment variables and API keys
    
    Args:
        args: Parsed command line arguments
        io: InputOutput instance for printing error messages
        
    Returns:
        int: 0 for success, 1 for error
    """
    # Set general environment variables
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
    """
    Get and set workspace directory
    
    Args:
        workspace_arg: User-specified workspace path
        git_root: Git root directory path
        
    Returns:
        str: Workspace path
        
    Raises:
        SystemExit: When workspace directory does not exist or is not a directory
    """
    # Set workspace - prioritize user-specified workspace, then git root, then current directory
    if workspace_arg:
        workspace = os.path.abspath(workspace_arg)
        # Ensure the workspace directory exists
        if not os.path.exists(workspace):
            logger.error(f"Workspace directory does not exist: {workspace}")
            sys.exit(1)
        if not os.path.isdir(workspace):
            logger.error(f"Workspace path is not a directory: {workspace}")
            sys.exit(1)
        # Change to the specified workspace directory
        os.chdir(workspace)
        logger.debug(f"Changed to workspace directory: {workspace}")
    else:
        workspace = git_root if git_root else os.getcwd()
        logger.debug(f"Using default workspace: {workspace}")
    
    return workspace


def validate_agent_compatibility(agent_name, interactive_mode, io, verbose=False):
    """
    Validate agent compatibility with the execution mode

    Args:
        agent_name: Name of the agent to validate
        interactive_mode: Whether running in interactive mode
        io: InputOutput instance for displaying messages
        verbose: Whether to show verbose warnings
    """
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
    """
    Display SIADA HUB banner with error handling
    
    Args:
        io: InputOutput instance
        
    Raises:
        Exception: When banner display fails
    """
    # Show SIADA HUB banner with gradient effect
    from siada.io.banner import show_siada_banner

    try:
        io.rule()
        show_siada_banner(pretty=io.pretty, console=io.console)
    except UnicodeEncodeError as err:
        io.print_error("Terminal does not support pretty output (UnicodeDecodeError)")
        sys.exit(1)
    except Exception as err:
        io.print_error(f"Error showing banner: {err}")
        sys.exit(1)


def get_enable_checkpointing(args, conf: Config = None, interactive_mode: bool = True):
    """
    Get enable_checkpointing setting with priority: args > config file > default

    Args:
        args: Parsed command line arguments
        conf: Loaded configuration from config file
        interactive_mode: Whether running in interactive mode

    Returns:
        bool: Final enable_checkpointing value
    """
    # Non-interactive mode always disables checkpointing
    if not interactive_mode:
        return False

    # Priority: args > config file > default (False)
    if args.checkpointing is not None:
        return args.checkpointing

    if conf and conf.checkpoint_config and conf.checkpoint_config.enable is not None:
        return conf.checkpoint_config.enable

    return False


def get_config(args, io, conf: Config = None):
    """
    Configure and create model instance

    Args:
        args: Parsed command line arguments
        io: InputOutput instance for displaying information

    Returns:
        ModelRunConfig: Configured model instance, returns None if exit is needed
    """
    # Configuration priority: args > config file > defaults
    config = ModelRunConfig.get_default_config()
    
    # Determine final values using priority order
    final_model = args.model or (conf.llm_config.model if conf and conf.llm_config else None)
    final_provider = args.provider or (conf.llm_config.provider if conf and conf.llm_config else None)
    
    # Apply final configuration
    if final_model is not None:
        config.model_name = final_model
        config.configure_model_settings(config.model_name)
    
    if final_provider is not None:
        config.provider = final_provider

    # Check if provider is set
    if config.provider is None:
        io.print_error("No provider specified. Please set provider in agent_config.yaml or use --provider option")
        sys.exit(1)

    if config.provider == "openrouter":
        ## check the openrouter api key is set
        if os.getenv("OPENROUTER_API_KEY") is None:
            io.print_error("OPENROUTER_API_KEY is not set for openrouter provider")
            sys.exit(1)

    # Set reasoning effort and thinking tokens if specified
    if args.reasoning_effort is not None:
        if (
            not config.supports_extra_params
            or "reasoning_effort" not in config.supports_extra_params
        ):
            io.print_error(f"Model {config.model_name} does not support reasoning effort")
            sys.exit(1)
        else:
            config.set_reasoning_effort(args.reasoning_effort)

    if args.thinking_tokens is not None:
        if (
            not config.supports_extra_params
            or "thinking_tokens" not in config.supports_extra_params
        ):
            io.print_error(f"Model {config.model_name} does not support thinking tokens")
            sys.exit(1)
        else:
            config.set_thinking_tokens(args.thinking_tokens)

    # Display model settings in verbose mode
    if args.verbose:
        io.print_info("Model settings:")
        for attr in sorted(fields(ModelRunConfig), key=lambda x: x.name):
            value = getattr(config, attr.name)
            if value is None:
                val_str = "None"
            else:
                val_str = json.dumps(value, indent=4)
            io.print_info(f"{attr.name}: {val_str}")

    return config


def main():
    # Suppress harmless warnings from third-party libraries
    _suppress_third_party_warnings()

    conf: Config = load_conf()

    argv = sys.argv[1:]

    args, _, _, git_root, workspace_arg, parser = _parse_args_and_setup_environment(argv)

    interactive_mode = True
    if args.prompt:
        interactive_mode = False
        args.pretty = False

    try:
        io, running_color_settings = get_io(args)
    except ValueError as e:
        print(f"Invalid theme configuration: {e}")
        return 1

    if args.list_models:
        models = ModelInfoService.get_model_names()
        io.print_info("\n".join(f"- {model}" for model in models))
        return 0

    # Configure model
    model = get_config(args, io, conf)
    # Display banner

    # Set environment variables
    if set_env(args, io) != 0:
        return 1

    # Get workspace
    workspace = get_workspace(workspace_arg, git_root)

    if args.verbose:
        io.print_info(f"Using agent: {args.agent}")
        io.print_info(f"Workspace: {workspace}")

    if args.verbose:
        show = SettingsUtils.format_settings(parser, args)
        io.print_info(show)

        # Show command line in verbose mode only
        cmd_line = " ".join(sys.argv)
        io.print_info(f"Command: {cmd_line}")

    if model is None:
        return 0

    if args.just_check_update:
        update_available = version_checker.check_version(io, just_check=True, verbose=args.verbose)
        return 0 if not update_available else 1

    if args.upgrade:
        success = version_checker.install_upgrade(io)
        return 0 if success else 1

    if args.check_update:
        version_checker.check_version(io, verbose=args.verbose)

    commands = SlashCommands(
        io=io,
        verbose=args.verbose,
        editor=args.editor,
    )

    session_id = str(int(time.time() * 1000))

    completer: Completer = AutoCompleter(
        root=workspace,
        commands=commands,
        encoding=args.encoding,
        session_id=session_id
    )

    # get the enable_checkpointing flag with priority: args > config file > default
    enable_checkpointing = get_enable_checkpointing(args, conf, interactive_mode)

    # Load user memory from siada.md file
    user_memory = load_siada_memory(workspace)

    running_config = RunningConfig(
        llm_config=model,
        io=io,
        workspace=workspace,
        agent_name=args.agent,
        completer=completer,
        running_color_settings=running_color_settings,
        console_output=not args.disable_console_output if interactive_mode else True,
        interactive=interactive_mode,
        user_memory=user_memory,
        mcp_config=conf.mcp_config,
        enable_checkpointing=enable_checkpointing,
    )

    # create session
    session = RunningSessionManager.create_session(
        siada_config=running_config,
        session_id=session_id
    )

    # Validate agent compatibility with interactive mode
    validate_agent_compatibility(args.agent, interactive_mode, io, args.verbose)

    show_banner(io)

    # Initialize MCP service if configured
    _init_mcp_service(running_config)

    if not interactive_mode:
        controller = NoInteractiveController(config=running_config, session=session)
        controller.run(args.prompt)
        return 0

    controller = Controller(
        config=running_config, slash_commands=commands, session=session
    )
    controller.show_announcements()
    controller.run()


if __name__ == "__main__":
    status = main()
    sys.exit(status)
