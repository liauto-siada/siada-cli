import json
import os
import sys
from dataclasses import fields
from pathlib import Path
import warnings

from prompt_toolkit.completion import Completer

from siada.config.config_loader import Config, load_conf
from siada.entrypoint.args_parser.args import get_parser
from siada.entrypoint.interaction.config import RunningConfig
from siada.entrypoint.interaction.controller import Controller
from siada.entrypoint.interaction.nointeractive_controller import NoInteractiveController
from siada.foundation.logging import toggle_console_output, logger
from siada.io.color_settings import RunningConfigColorSettings
from siada.models.model_run_config import ModelRunConfig
from siada.models.model_base_config import ModelBaseConfig
from siada.support.completer import AutoCompleter
from siada.support.slash_commands import SlashCommands, SwitchEvent
from siada.support.envprocessor import load_dotenv_files
from siada.support.repo import get_git_root
from siada.utils import SettingsUtils
from siada.io.io import InputOutput

try:
    import git
except ImportError:
    git = None

import shtab
from dotenv import load_dotenv
from prompt_toolkit.enums import EditingMode
from siada.services.model_info_service import ModelInfoService


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


def _configure_litellm_logging():
    """Configure LiteLLM global logging settings to suppress debug logs"""
    try:
        import litellm      

        # Configure litellm global properties
        litellm.set_verbose = False
        litellm.turn_off_message_logging = True
        litellm.suppress_debug_info = True
        litellm.drop_params = True
        
        
        # Try to disable internal debug logging
        try:
            litellm._logging._disable_debugging()
        except Exception:
            pass  # Ignore if method doesn't exist
        
        # Disable message logging and tracing
        litellm.turn_off_message_logging = True
        litellm.success_callback = []
        litellm.failure_callback = []
        
        logger.debug("LiteLLM logging configuration completed")
        
    except ImportError:
        logger.debug("LiteLLM not installed, skipping logging configuration")
    except Exception as e:
        logger.debug(f"Error configuring LiteLLM logging: {e}")


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

    # Configure litellm globally to suppress debug logs
    _configure_litellm_logging()
    
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

    commands = SlashCommands(
        io=io,
        verbose=args.verbose,
        editor=args.editor,
    )

    completer: Completer = AutoCompleter(
        root=workspace,
        commands=commands,
        encoding=args.encoding,
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
    )
    show_banner(io)

    if not interactive_mode:
        controller = NoInteractiveController(running_config)
        controller.run(args.prompt)
        return 0

    controller = Controller(running_config, commands)
    controller.show_announcements()
    controller.run()


if __name__ == "__main__":
    status = main()
    sys.exit(status)
