import json
import os
import sys
from dataclasses import fields
from pathlib import Path

from prompt_toolkit.completion import Completer

from siada.entrypoint.args_parser.args import get_parser
from siada.entrypoint.interaction.config import InteractionConfig
from siada.entrypoint.interaction.interaction_controller import InteractionController
from siada.foundation.logging import toggle_console_output, logger
from siada.models.model_setting import ModelRunConfig
from siada.models.model_settings import ModelSettings
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
    """配置LiteLLM的全局日志设置，抑制调试日志"""
    try:
        import litellm      

        
        # 配置litellm全局属性
        litellm.set_verbose = False
        litellm.turn_off_message_logging = True
        litellm.suppress_debug_info = True
        litellm.drop_params = True
        
        
        # 尝试禁用内部调试日志
        try:
            litellm._logging._disable_debugging()
        except Exception:
            pass  # 如果方法不存在就忽略
        
        # 禁用消息日志和跟踪
        litellm.turn_off_message_logging = True
        litellm.success_callback = []
        litellm.failure_callback = []
        
        logger.de("LiteLLM 日志配置完成")
        
    except ImportError:
        logger.debug("LiteLLM 未安装，跳过日志配置")
    except Exception as e:
        logger.debug(f"配置 LiteLLM 日志时出错: {e}")


def main():
    # Configure litellm globally to suppress debug logs
    _configure_litellm_logging()

    argv = sys.argv[1:]

    # workspace and disable-console-output are sepcific for development
    import argparse

    temp_parser = argparse.ArgumentParser(add_help=False)
    temp_parser.add_argument("--workspace", default=None)
    temp_parser.add_argument(
        "--enable-console-output", action="store_true", default=False
    )
    temp_args, _ = temp_parser.parse_known_args(argv)

    if temp_args.enable_console_output:
        toggle_console_output(True)
    else:
        toggle_console_output(False)

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

    loaded_dotenvs = load_dotenv_files(git_root, args.env_file, args.encoding)

    args = parser.parse_args(argv)

    if args.shell_completions:
        parser.prog = "siadahub"
        print(shtab.complete(parser, shell=args.shell_completions))
        sys.exit(0)

    if git is None:
        args.git = False

    # if not args.verify_ssl:
    #     import httpx

    #     os.environ["SSL_VERIFY"] = ""
    #     litellm._load_litellm()
    #     litellm._lazy_module.client_session = httpx.Client(verify=False)
    #     litellm._lazy_module.aclient_session = httpx.AsyncClient(verify=False)
    #     # models.model_info_manager.set_verify_ssl(False)

    from siada.io.color_settings import ColorSettings

    try:
        color_settings = ColorSettings.from_theme(args.theme)
        color_settings.apply_to_args(args)
        if args.verbose:
            print(f"Applied color theme: {args.theme}")
    except ValueError as e:
        print(f"Invalid theme configuration: {e}")
        return 1

    editing_mode = EditingMode.VI if args.vim else EditingMode.EMACS

    def get_io(pretty):
        return InputOutput(
            pretty=pretty,
            yes=args.yes_always,
            color_settings=color_settings,
            encoding=args.encoding,
            line_endings=getattr(args, "line_endings", "platform"),
            editingmode=editing_mode,
            fancy_input=args.fancy_input,
            multiline_mode=args.multiline,
            notifications=args.notifications,
            notifications_command=getattr(args, "notifications_command", None),
        )

    io = get_io(args.pretty)

    # Show SIADA HUB banner with gradient effect
    from siada.io.banner import show_siada_banner

    try:
        io.rule()
        show_siada_banner(pretty=io.pretty, console=io.console)
    except UnicodeEncodeError as err:
        if not io.pretty:
            raise err
        io = get_io(False)
        # Re-show banner in plain mode if we fall back to non-pretty
        show_siada_banner(pretty=False)
        io.print_warning("Terminal does not support pretty output (UnicodeDecodeError)")

    if args.set_env:
        for env_setting in args.set_env:
            try:
                name, value = env_setting.split("=", 1)
                os.environ[name.strip()] = value.strip()
            except ValueError:
                io.print_error(f"Invalid --set-env format: {env_setting}")
                io.print_info("Format should be: ENV_VAR_NAME=value")
                return 1

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

    if args.verbose:
        for fname in loaded_dotenvs:
            io.print_info(f"Loaded {fname}")

    # Set workspace - prioritize user-specified workspace, then git root, then current directory
    if temp_args.workspace:
        workspace = os.path.abspath(temp_args.workspace)
        # Ensure the workspace directory exists
        if not os.path.exists(workspace):
            logger.error(f"Workspace directory does not exist: {workspace}")
            return 1
        if not os.path.isdir(workspace):
            logger.error(f"Workspace path is not a directory: {workspace}")
            return 1
        # Change to the specified workspace directory
        os.chdir(workspace)
        logger.debug(f"Changed to workspace directory: {workspace}")
    else:
        workspace = git_root if git_root else os.getcwd()
        logger.debug(f"Using default workspace: {workspace}")

    if args.verbose:
        io.print_info(f"Using agent: {args.agent}")
        io.print_info(f"Workspace: {workspace}")

    if args.verbose:
        show = SettingsUtils.format_settings(parser, args)
        io.print_info(show)

        # Show command line in verbose mode only
        cmd_line = " ".join(sys.argv)
        io.print_info(f"Command: {cmd_line}")

    if args.list_models:
        # TODO: Implement this
        return 0

    if args.model is None:
        model = ModelRunConfig.get_default_model()
    else:
        model = ModelRunConfig(args.model)

    # Set reasoning effort and thinking tokens if specified
    if args.reasoning_effort is not None:
        model.set_reasoning_effort(args.reasoning_effort)

    if args.thinking_tokens is not None:
        model.set_thinking_tokens(args.thinking_tokens)

    if args.verbose:
        io.print_info("Model settings:")
        for attr in sorted(fields(ModelRunConfig), key=lambda x: x.name):
            val = getattr(model, attr.name)
            val = json.dumps(val, indent=4)
            io.print_info(f"{attr.name}: {val}")

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

    interaction_config = InteractionConfig(
        model=model,
        io=io,
        workspace=workspace,
        agent_name=args.agent,
        completer=completer,
    )

    controller = InteractionController(interaction_config, commands)
    controller.show_announcements()
    controller.run()


if __name__ == "__main__":
    status = main()
    sys.exit(status)
