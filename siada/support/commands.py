import glob
import os
import re
import siada.io.io
import subprocess
import sys
import tempfile
from collections import OrderedDict
from os.path import expanduser
from pathlib import Path
from prompt_toolkit.completion import Completion, PathCompleter
from prompt_toolkit.document import Document

from siada.models.model_setting import ModelConfig
from siada.support.completer import CommandCompletionException
from siada.support.editor import pipe_editor
from siada.tools.coder import do_run_cmd as run_cmd
from siada.utils import SettingsUtils
from siada.provider.lazy_lite_llm import litellm


class SwitchEvent(Exception):
    def __init__(self, placeholder=None, **kwargs):
        self.kwargs = kwargs
        self.placeholder = placeholder


class SlashCommands:
    voice = None
    scraper = None

    def clone(self):
        return SlashCommands(
            self.io,
            None,
            verify_ssl=self.verify_ssl,
            args=self.args,
            parser=self.parser,
            verbose=self.verbose,
            editor=self.editor,
        )

    def __init__(
        self,
        io : siada.io.io.InputOutput,
        session,
        verify_ssl=True,
        args=None,
        parser=None,
        verbose=False,
        editor=None,
    ):
        self.io = io
        self.session = session
        self.parser = parser
        self.args = args
        self.verbose = verbose

        self.verify_ssl = verify_ssl

        self.help = None
        self.editor = editor


    def cmd_model(self, args):

        model_name = args.strip()
        if not model_name:
            self.io.print_info("No model name provided")
            return

        model = ModelConfig(model_name)
        raise SwitchEvent(main_model=model)

    def cmd_chat_mode(self, args):
        "Switch to a new chat mode"

        ef = args.strip()
        valid_formats = OrderedDict(
            sorted(
                (
                    coder.edit_format,
                    coder.__doc__.strip().split("\n")[0] if coder.__doc__ else "No description",
                )
                for coder in coders.__all__
                if getattr(coder, "edit_format", None)
            )
        )

        show_formats = OrderedDict(
            [
                ("help", "Get help about using aider (usage, config, troubleshoot)."),
                ("ask", "Ask questions about your code without making any changes."),
                ("code", "Ask for changes to your code (using the best edit format)."),
                (
                    "architect",
                    (
                        "Work with an architect model to design code changes, and an editor to make"
                        " them."
                    ),
                ),
                (
                    "context",
                    "Automatically identify which files will need to be edited.",
                ),
            ]
        )

        if ef not in valid_formats and ef not in show_formats:
            if ef:
                self.io.print_error(f'Chat mode "{ef}" should be one of these:\n')
            else:
                self.io.print_info("Chat mode should be one of these:\n")

            max_format_length = max(len(format) for format in valid_formats.keys())
            for format, description in show_formats.items():
                self.io.print_info(f"- {format:<{max_format_length}} : {description}")

            self.io.print_info("\nOr a valid edit format:\n")
            for format, description in valid_formats.items():
                if format not in show_formats:
                    self.io.print_info(f"- {format:<{max_format_length}} : {description}")

            return

        summarize_from_coder = True
        edit_format = ef

        if ef == "code":
            edit_format = self.coder.main_model.edit_format
            summarize_from_coder = False
        elif ef == "ask":
            summarize_from_coder = False

        raise SwitchEvent(
            edit_format=edit_format,
            summarize_from_coder=summarize_from_coder,
        )

    def completions_model(self):
        models = litellm.model_cost.keys()
        return models

    def cmd_models(self, args):
        "Search the list of available models"

        args = args.strip()

        if args:
            # models.print_matching_models(self.io, args)
            pass
        else:
            self.io.print_info("Please provide a partial model name to search for.")

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

    def get_commands(self):
        commands = []
        for attr in dir(self):
            if not attr.startswith("cmd_"):
                continue
            cmd = attr[4:]
            cmd = cmd.replace("_", "-")
            commands.append("/" + cmd)

        return commands

    def do_run(self, cmd_name, args):
        cmd_name = cmd_name.replace("-", "_")
        cmd_method_name = f"cmd_{cmd_name}"
        cmd_method = getattr(self, cmd_method_name, None)
        if not cmd_method:
            self.io.print_info(f"Error: Command {cmd_name} not found.")
            return

        try:
            return cmd_method(args)
        except Exception as err:
            self.io.print_error(f"Unable to complete {cmd_name}: {err}")

    def matching_commands(self, inp):
        words = inp.strip().split()
        if not words:
            return

        first_word = words[0]
        rest_inp = inp[len(words[0]) :].strip()

        all_commands = self.get_commands()
        matching_commands = [cmd for cmd in all_commands if cmd.startswith(first_word)]
        return matching_commands, first_word, rest_inp


    def run(self, inp):
        """
        Run a command.
        any method called cmd_xxx becomes a command automatically.
        each one must take an args param.
        """
        if inp.startswith("!"):
            return self.do_run("run", inp[1:])

        res = self.matching_commands(inp)
        if res is None:
            return
        matching_commands, first_word, rest_inp = res
        if len(matching_commands) == 1:
            command = matching_commands[0][1:]
            return self.do_run(command, rest_inp)
        elif first_word in matching_commands:
            command = first_word[1:]
            return self.do_run(command, rest_inp)
        elif len(matching_commands) > 1:
            self.io.print_error(f"Ambiguous command: {', '.join(matching_commands)}")
        else:
            self.io.print_error(f"Invalid command: {first_word}")

    

    def cmd_clear(self, args):
        "Clear the chat history"

        self._clear_chat_history()
        self.io.print_info("All chat history cleared.")

    def _clear_chat_history(self):
        self.coder.done_messages = []
        self.coder.cur_messages = []

    def quote_fname(self, fname):
        if " " in fname and '"' not in fname:
            fname = f'"{fname}"'
        return fname

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

    def glob_filtered_to_repo(self, pattern):

        def expand_subdir(file_path):
            if file_path.is_file():
                yield file_path
                return

            if file_path.is_dir():
                for file in file_path.rglob("*"):
                    if file.is_file():
                        yield file

        if not pattern.strip():
            return []
        try:
            if os.path.isabs(pattern):
                # Handle absolute paths
                raw_matched_files = [Path(pattern)]
            else:
                try:
                    raw_matched_files = list(Path(self.coder.root).glob(pattern))
                except (IndexError, AttributeError):
                    raw_matched_files = []
        except ValueError as err:
            self.io.print_error(f"Error matching {pattern}: {err}")
            raw_matched_files = []

        matched_files = []
        for fn in raw_matched_files:
            matched_files += expand_subdir(fn)

        matched_files = [
            fn.relative_to(self.coder.root)
            for fn in matched_files
            if fn.is_relative_to(self.coder.root)
        ]

        # if repo, filter against it
        if self.coder.repo:
            git_files = self.coder.repo.get_tracked_files()
            matched_files = [fn for fn in matched_files if str(fn) in git_files]

        res = list(map(str, matched_files))
        return res


    def cmd_run(self, args, add_on_nonzero_exit=False):
        "Run a shell command and optionally add the output to the chat (alias: !)"
        exit_status, combined_output = run_cmd(
            args, verbose=self.verbose, error_print=self.io.print_error, cwd=self.coder.root
        )

        if combined_output is None:
            return

        # Calculate token count of output
        token_count = self.coder.main_model.token_count(combined_output)
        k_tokens = token_count / 1000

        if add_on_nonzero_exit:
            add = exit_status != 0
        else:
            add = self.io.confirm_ask(f"Add {k_tokens:.1f}k tokens of command output to the chat?")

        if add:
            num_lines = len(combined_output.strip().splitlines())
            line_plural = "line" if num_lines == 1 else "lines"
            self.io.print_info(f"Added {num_lines} {line_plural} of output to the chat.")

            msg = prompts.run_output.format(
                command=args,
                output=combined_output,
            )

            self.coder.cur_messages += [
                dict(role="user", content=msg),
                dict(role="assistant", content="Ok."),
            ]

            if add_on_nonzero_exit and exit_status != 0:
                # Return the formatted output message for test failures
                return msg
            elif add and exit_status != 0:
                self.io.placeholder = "What's wrong? Fix"

        # Return None if output wasn't added or command succeeded
        return None

    def cmd_exit(self, args):
        "Exit the application"
        self.coder.event("exit", reason="/exit")
        sys.exit()

    def cmd_quit(self, args):
        "Exit the application"
        self.cmd_exit(args)

    def basic_help(self):
        commands = sorted(self.get_commands())
        pad = max(len(cmd) for cmd in commands)
        pad = "{cmd:" + str(pad) + "}"
        for cmd in commands:
            cmd_method_name = f"cmd_{cmd[1:]}".replace("-", "_")
            cmd_method = getattr(self, cmd_method_name, None)
            cmd = pad.format(cmd=cmd)
            if cmd_method:
                description = cmd_method.__doc__
                self.io.print_info(f"{cmd} {description}")
            else:
                self.io.print_info(f"{cmd} No description available.")
        self.io.print_info()
        self.io.print_info("Use `/help <question>` to ask questions about how to use aider.")

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

    def cmd_map(self, args):
        "Print out the current repository map"
        repo_map = self.coder.get_repo_map()
        if repo_map:
            self.io.print_info(repo_map)
        else:
            self.io.print_info("No repository map available.")

    def cmd_map_refresh(self, args):
        "Force a refresh of the repository map"
        repo_map = self.coder.get_repo_map(force_refresh=True)
        if repo_map:
            self.io.print_info("The repo map has been refreshed, use /map to view it.")

    def cmd_settings(self, args):
        "Print out the current settings"
        settings = SettingsUtils.format_settings(self.parser, self.args)
        announcements = "\n".join(self.coder.get_announcements())

        # Build metadata for the active models (main, editor, weak)
        model_sections = []
        active_models = [
            ("Main model", self.coder.main_model),
            ("Editor model", getattr(self.coder.main_model, "editor_model", None)),
            ("Weak model", getattr(self.coder.main_model, "weak_model", None)),
        ]
        for label, model in active_models:
            if not model:
                continue
            info = getattr(model, "info", {}) or {}
            if not info:
                continue
            model_sections.append(f"{label} ({model.name}):")
            for k, v in sorted(info.items()):
                model_sections.append(f"  {k}: {v}")
            model_sections.append("")  # blank line between models

        model_metadata = "\n".join(model_sections)

        output = f"{announcements}\n{settings}"
        if model_metadata:
            output += "\n" + model_metadata
        self.io.print_info(output)

    def completions_raw_load(self, document, complete_event):
        return self.completions_raw_read_only(document, complete_event)

    def cmd_load(self, args):
        "Load and execute commands from a file"
        if not args.strip():
            self.io.print_error("Please provide a filename containing commands to load.")
            return

        try:
            with open(args.strip(), "r", encoding=self.io.encoding, errors="replace") as f:
                commands = f.readlines()
        except FileNotFoundError:
            self.io.print_error(f"File not found: {args}")
            return
        except Exception as e:
            self.io.print_error(f"Error reading file: {e}")
            return

        for cmd in commands:
            cmd = cmd.strip()
            if not cmd or cmd.startswith("#"):
                continue

            self.io.print_info(f"\nExecuting: {cmd}")
            try:
                self.run(cmd)
            except SwitchEvent:
                self.io.print_error(
                    f"Command '{cmd}' is only supported in interactive mode, skipping."
                )

    def cmd_multiline_mode(self, args):
        "Toggle multiline mode (swaps behavior of Enter and Meta+Enter)"
        self.io.toggle_multiline_mode()


    def cmd_editor(self, initial_content=""):
        "Open an editor to write a prompt"

        user_input = pipe_editor(initial_content, suffix="md", editor=self.editor)
        if user_input.strip():
            self.io.set_placeholder(user_input.rstrip())

    def cmd_edit(self, args=""):
        "Siada for /editor: Open an editor to write a prompt"
        return self.cmd_editor(args)

    def cmd_think_tokens(self, args):
        # """Set the thinking token budget, eg: 8096, 8k, 10.5k, 0.5M, or 0 to disable."""
        # model = self.coder.main_model

        # if not args.strip():
        #     # Display current value if no args are provided
        #     formatted_budget = model.get_thinking_tokens()
        #     if formatted_budget is None:
        #         self.io.print_info("Thinking tokens are not currently set.")
        #     else:
        #         budget = model.get_raw_thinking_tokens()
        #         self.io.print_info(
        #             f"Current thinking token budget: {budget:,} tokens ({formatted_budget})."
        #         )
        #     return

        # value = args.strip()
        # model.set_thinking_tokens(value)

        # # Handle the special case of 0 to disable thinking tokens
        # if value == "0":
        #     self.io.print_info("Thinking tokens disabled.")
        # else:
        #     formatted_budget = model.get_thinking_tokens()
        #     budget = model.get_raw_thinking_tokens()
        #     self.io.print_info(
        #         f"Set thinking token budget to {budget:,} tokens ({formatted_budget})."
        #     )

        # self.io.print_info()

        # # Output announcements
        # announcements = "\n".join(self.coder.get_announcements())
        # self.io.print_info(announcements)
        pass

    def cmd_reasoning_effort(self, args):
        # "Set the reasoning effort level (values: number or low/medium/high depending on model)"
        # model = self.coder.main_model

        # if not args.strip():
        #     # Display current value if no args are provided
        #     reasoning_value = model.get_reasoning_effort()
        #     if reasoning_value is None:
        #         self.io.print_info("Reasoning effort is not currently set.")
        #     else:
        #         self.io.print_info(f"Current reasoning effort: {reasoning_value}")
        #     return

        # value = args.strip()
        # model.set_reasoning_effort(value)
        # reasoning_value = model.get_reasoning_effort()
        # self.io.print_info(f"Set reasoning effort to {reasoning_value}")
        # self.io.print_info()

        # # Output announcements
        # announcements = "\n".join(self.coder.get_announcements())
        # self.io.print_info(announcements)
        pass


def main():
    md = SlashCommands(None, None).get_help_md()
    print(md)


if __name__ == "__main__":
    status = main()
    sys.exit(status)
