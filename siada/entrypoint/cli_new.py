import json
import os
import re
import sys
import threading
import traceback
import webbrowser
from dataclasses import fields
from pathlib import Path

from siada.entrypoint.args_parser.args import get_parser
from siada.models.model_setting import ModelConfig
from siada.models.model_settings import ModelSettings
from siada.support.commands import SlashCommands, SwitchEvent
from siada.support.envprocessor import load_dotenv_files
from siada.support.repo import get_git_root
from siada.utils import SettingsUtils
from siada.provider.lazy_lite_llm import litellm
from siada.io.io import InputOutput

try:
    import git
except ImportError:
    git = None

import shtab
from dotenv import load_dotenv
from prompt_toolkit.enums import EditingMode




def main(argv=None, input=None, output=None):

    if argv is None:
        argv = sys.argv[1:]

    if git is None:
        git_root = None
    else:
        git_root = get_git_root()

    parser = get_parser(git_root=git_root)
    try:
        args, unknown = parser.parse_known_args(argv)
    except AttributeError as e:
        raise e

    # Load the .env file specified in the arguments
    loaded_dotenvs = load_dotenv_files(git_root, args.env_file, args.encoding)

    # Parse again to include any arguments that might have been defined in .env
    args = parser.parse_args(argv)

    if args.shell_completions:
        # Ensure parser.prog is set for shtab, though it should be by default
        parser.prog = "siadahub"
        print(shtab.complete(parser, shell=args.shell_completions))
        sys.exit(0)

    if git is None:
        args.git = False

    if not args.verify_ssl:
        import httpx

        os.environ["SSL_VERIFY"] = ""
        litellm._load_litellm()
        litellm._lazy_module.client_session = httpx.Client(verify=False)
        litellm._lazy_module.aclient_session = httpx.AsyncClient(verify=False)
        # Set verify_ssl on the model_info_manager
        # models.model_info_manager.set_verify_ssl(False)

    # Apply color theme configuration
    from siada.io.color_settings import ColorSettings
    
    # Apply selected theme
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
            pretty,
            args.yes_always,
            args.input_history_file,
            args.chat_history_file,
            input=input,
            output=output,
            user_input_color=args.user_input_color,
            tool_output_color=args.tool_output_color,
            tool_warning_color=args.tool_warning_color,
            tool_error_color=args.tool_error_color,
            completion_menu_color=args.completion_menu_color,
            completion_menu_bg_color=args.completion_menu_bg_color,
            completion_menu_current_color=args.completion_menu_current_color,
            completion_menu_current_bg_color=args.completion_menu_current_bg_color,
            assistant_output_color=args.assistant_output_color,
            code_theme=args.code_theme,
            dry_run=args.dry_run,
            encoding=args.encoding,
            line_endings=args.line_endings,
            llm_history_file=args.llm_history_file,
            editingmode=editing_mode,
            fancy_input=args.fancy_input,
            multiline_mode=args.multiline,
            notifications=args.notifications,
            notifications_command=args.notifications_command,
        )

    io = get_io(pretty=True)
    try:
        io.rule()
    except UnicodeEncodeError as err:
        if not io.pretty:
            raise err
        io = get_io(False)
        io.print_warning("Terminal does not support pretty output (UnicodeDecodeError)")

    # Process any environment variables set via --set-env
    if args.set_env:
        for env_setting in args.set_env:
            try:
                name, value = env_setting.split("=", 1)
                os.environ[name.strip()] = value.strip()
            except ValueError:
                io.print_error(f"Invalid --set-env format: {env_setting}")
                io.print_info("Format should be: ENV_VAR_NAME=value")
                return 1

    # Process any API keys set via --api-key
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


    if args.verbose:
        show = SettingsUtils.format_settings(parser, args)
        io.print_info(show)

    cmd_line = " ".join(sys.argv)
    io.print_info(cmd_line, log_only=True)

    if args.list_models:
        # TODO: Implement this
        return 0

    # TODO: Implement this
    # selected_model_name = select_default_model(args, io, analytics)
    # if not selected_model_name:
    #     # Error message and analytics event are handled within select_default_model
    #     # It might have already offered OAuth if no model/keys were found.
    #     # If it failed here, we exit.
    #     return 1
    # args.model = selected_model_name  # Update args with the selected model

    # Check if an OpenRouter model was selected/specified but the key is missing
    # if args.model.startswith("openrouter/") and not os.environ.get("OPENROUTER_API_KEY"):
    #     io.tool_warning(
    #         f"The specified model '{args.model}' requires an OpenRouter API key, which was not"
    #         " found."
    #     )
    #     # Attempt OAuth flow because the specific model needs it
    #     if offer_openrouter_oauth(io, analytics):
    #         # OAuth succeeded, the key should now be in os.environ.
    #         # Check if the key is now present after the flow.
    #         if os.environ.get("OPENROUTER_API_KEY"):
    #             io.tool_output(
    #                 "OpenRouter successfully connected."
    #             )  # Inform user connection worked
    #         else:
    #             # This case should ideally not happen if offer_openrouter_oauth succeeded
    #             # but check defensively.
    #             io.tool_error(
    #                 "OpenRouter authentication seemed successful, but the key is still missing."
    #             )
    #             analytics.event(
    #                 "exit",
    #                 reason="OpenRouter key missing after successful OAuth for specified model",
    #             )
    #             return 1
    #     else:
    #         # OAuth failed or was declined by the user
    #         io.tool_error(
    #             f"Unable to proceed without an OpenRouter API key for model '{args.model}'."
    #         )
    #         io.offer_url(urls.models_and_keys, "Open documentation URL for more info?")
    #         analytics.event(
    #             "exit",
    #             reason="OpenRouter key missing for specified model and OAuth failed/declined",
    #         )
    #         return 1

    model = ModelConfig(
        args.model
    )

    # Set reasoning effort and thinking tokens if specified
    if args.reasoning_effort is not None:
        model.set_reasoning_effort(args.reasoning_effort)

    if args.thinking_tokens is not None:
        model.set_thinking_tokens(args.thinking_tokens)

    if args.verbose:

        io.print_info("Model settings:")
        for attr in sorted(fields(ModelSettings), key=lambda x: x.name):
            val = getattr(model, attr.name)
            val = json.dumps(val, indent=4)
            io.print_info(f"{attr.name}: {val}")


    commands = SlashCommands(
        io,
        None,
        verify_ssl=args.verify_ssl,
        args=args,
        parser=parser,
        verbose=args.verbose,
        editor=args.editor,
    )

    # summarizer = ChatSummary(
    #     [main_model.weak_model, main_model],
    #     args.max_chat_history_tokens or main_model.max_chat_history_tokens,
    # )

    # if args.cache_prompts and args.map_refresh == "auto":
    #     args.map_refresh = "files"

    try:
        coder = Coder.create(
            main_model=model,
            edit_format=args.edit_format,
            io=io,
            repo=repo,
            fnames=fnames,
            read_only_fnames=read_only_fnames,
            show_diffs=args.show_diffs,
            auto_commits=args.auto_commits,
            dirty_commits=args.dirty_commits,
            dry_run=args.dry_run,
            map_tokens=map_tokens,
            verbose=args.verbose,
            stream=args.stream,
            use_git=args.git,
            restore_chat_history=args.restore_chat_history,
            auto_lint=args.auto_lint,
            auto_test=args.auto_test,
            lint_cmds=lint_cmds,
            test_cmd=args.test_cmd,
            commands=commands,
            summarizer=summarizer,
            analytics=analytics,
            map_refresh=args.map_refresh,
            cache_prompts=args.cache_prompts,
            map_mul_no_files=args.map_multiplier_no_files,
            num_cache_warming_pings=args.cache_keepalive_pings,
            suggest_shell_commands=args.suggest_shell_commands,
            chat_language=args.chat_language,
            commit_language=args.commit_language,
            detect_urls=args.detect_urls,
            auto_copy_context=args.copy_paste,
            auto_accept_architect=args.auto_accept_architect,
            add_gitignore_files=args.add_gitignore_files,
        )
    except UnknownEditFormat as err:
        io.print_error(str(err))
        io.offer_url(urls.edit_formats, "Open documentation about edit formats?")
        return 1
    except ValueError as err:
        io.print_error(str(err))
        return 1

    while True:
        try:
            coder.ok_to_warm_cache = bool(args.cache_keepalive_pings)
            coder.run()
            return 0
        except SwitchEvent as switch:
            coder.ok_to_warm_cache = False

            # Set the placeholder if provided
            if hasattr(switch, "placeholder") and switch.placeholder is not None:
                io.placeholder = switch.placeholder

            kwargs = dict(io=io, from_coder=coder)
            kwargs.update(switch.kwargs)
            if "show_announcements" in kwargs:
                del kwargs["show_announcements"]

            coder = Coder.create(**kwargs)

            if switch.kwargs.get("show_announcements") is not False:
                coder.show_announcements()


if __name__ == "__main__":
    status = main()
    sys.exit(status)
