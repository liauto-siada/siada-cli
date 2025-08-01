import json
import os
import sys
from dataclasses import fields
from pathlib import Path

from prompt_toolkit.completion import Completer

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

    # Set API key environment variables
    if args.api_key:
        for api_setting in args.api_key:
            try:
                provider, key = api_setting.split("=", 1)
                env_var = f"{provider.strip().upper()}_API_KEY"
                os.environ[env_var] = key.strip()
            except ValueError:
                io.print_error(f"Invalid --api-key format: {api_setting}")
                io.print_info("Format should be: provider=key")
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


def set_model(args, io):
    """
    Configure and create model instance
    
    Args:
        args: Parsed command line arguments
        io: InputOutput instance for displaying information
        
    Returns:
        ModelRunConfig: Configured model instance, returns None if exit is needed
    """
    if args.list_models:
        # TODO: Implement this
        return None

    # Create model instance
    if args.model is None:
        model = ModelRunConfig.get_default_model()
    else:
        model = ModelRunConfig(args.model)

    # Set reasoning effort and thinking tokens if specified
    if args.reasoning_effort is not None:
        model.set_reasoning_effort(args.reasoning_effort)

    if args.thinking_tokens is not None:
        model.set_thinking_tokens(args.thinking_tokens)

    # Display model settings in verbose mode
    if args.verbose:
        io.print_info("Model settings:")
        for attr in sorted(fields(ModelRunConfig), key=lambda x: x.name):
            val = getattr(model, attr.name)
            val = json.dumps(val, indent=4)
            io.print_info(f"{attr.name}: {val}")

    return model


def main():
    # Configure litellm globally to suppress debug logs
    _configure_litellm_logging()

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

    # Display banner
    show_banner(io)

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

    # Configure model
    model = set_model(args, io)
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
        model=model,
        io=io,
        workspace=workspace,
        agent_name=args.agent,
        completer=completer,
        running_color_settings=running_color_settings,
        console_output=not args.disable_console_output if interactive_mode else True,
        interactive=interactive_mode,
    )

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
