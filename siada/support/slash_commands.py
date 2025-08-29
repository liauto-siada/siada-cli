import inspect
import os
import sys

from prompt_toolkit.completion import Completion, PathCompleter
from prompt_toolkit.document import Document

import siada.io.io
from siada.services.model_info_service import ModelInfoService
from siada.support.editor import pipe_editor
from siada.tools.coder.cmd_runner import run_cmd_impl as run_cmd
from siada.support.checkpoint_tracker import CheckPointData
from siada.tools.read_many_files.models import ProcessingStats


class SwitchEvent:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


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

    def cmd_shell(self, args):
        "Open a shell"
        self.io.print_info("Switching to shell mode...")
        return SwitchEvent(shell=True)

    def completions_model(self):
        return ModelInfoService.get_model_names()

    def cmd_models(self, args):
        "Search the list of available models"

        args = args.strip()

        # models.print_matching_models(self.io, args)
        models = ModelInfoService.get_model_names()
        for model in models:
            self.io.print_info(f"- {model}")

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

    def do_run(self, session, cmd_name, args):
        cmd_name = cmd_name.replace("-", "_")
        cmd_method_name = f"cmd_{cmd_name}"
        cmd_method = getattr(self, cmd_method_name, None)
        if not cmd_method:
            self.io.print_info(f"Error: Command {cmd_name} not found.")
            return

        try:
            # 检查方法的参数签名
            sig = inspect.signature(cmd_method)
            params = list(sig.parameters.keys())

            # 如果方法有 session 参数，则传递 session 和 args
            if 'session' in params:
                return cmd_method(session, args)
            else:
                # 否则只传递 args
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

    def run(self, session, inp):
        """
        Run a command.
        any method called cmd_xxx becomes a command automatically.
        each one must take an args param.
        """
        if inp.startswith("!"):
            return self.do_run(session, "run", inp[1:])

        res = self.matching_commands(inp)
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

    def cmd_run(self, session, args, add_on_nonzero_exit=False):
        "Run a shell command (alias: !)"
        exit_status, combined_output = run_cmd(
            args,
            verbose=self.verbose,
            error_print=self.io.print_error,
            cwd=session.siada_config.workspace,
        )
        return combined_output

    def cmd_exit(self, args):
        "Exit the application"
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
        self.io.print_info("Use `/help <question>` to ask questions about how to use siadahub.")

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

    def cmd_init(self, session, args):
        """Analyze the project and create a tailored siada.md file"""
        try:
            # Get workspace directory from session
            workspace = session.siada_config.workspace
            siada_md_path = os.path.join(workspace, 'siada.md')

            # Parse command arguments
            force_overwrite = '--force' in args.strip()

            # Check if file already exists before any operations
            file_exists = os.path.exists(siada_md_path)

            # Check if siada.md already exists and user doesn't want to force overwrite
            if file_exists and not force_overwrite:
                self.io.print_info('A siada.md file already exists in this directory. No changes were made.')
                self.io.print_info('Use `/init --force` to overwrite the existing file.')
                return

            # Create/overwrite siada.md file
            with open(siada_md_path, 'w', encoding='utf-8') as f:
                f.write('')

            # Display appropriate message based on whether file existed
            if file_exists:
                self.io.print_info('Existing siada.md overwritten. Now analyzing the project...')
            else:
                self.io.print_info('Empty siada.md created. Now analyzing the project...')

            # Generate the analysis prompt
            init_prompt = self._create_init_analysis_prompt(workspace)

            # Return special event to trigger AI analysis with full streaming support
            return SwitchEvent(ai_analysis_prompt=init_prompt)

        except PermissionError:
            self.io.print_error('Permission denied: Unable to create siada.md file.')
        except Exception as e:
            self.io.print_error(f'Error during project analysis: {str(e)}')
            import traceback
            self.io.print_error(traceback.format_exc())

    def cmd_memory_refresh(self, session, args):
        """Refresh user memory content from siada.md file"""
        try:
            from siada.services.siada_memory import refresh_siada_memory
            
            workspace = session.siada_config.workspace
            user_memory, status_message = refresh_siada_memory(workspace)
            
            # Update the session config with new memory content
            if hasattr(session.siada_config, 'user_memory'):
                session.siada_config.user_memory = user_memory
            
            self.io.print_info(status_message)
            
        except Exception as e:
            self.io.print_error(f'Error refreshing memory: {str(e)}')
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())

    def cmd_memory_status(self, session, args):
        """Display current user memory status"""
        try:
            workspace = session.siada_config.workspace
            siada_md_path = os.path.join(workspace, 'siada.md')
            
            if os.path.exists(siada_md_path):
                # Get file size
                file_size = os.path.getsize(siada_md_path)
                if file_size > 0:
                    # Get content preview
                    with open(siada_md_path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        lines_count = len(content.split('\n')) if content else 0
                    
                    self.io.print_info(f"Memory file: {siada_md_path}")
                    self.io.print_info(f"File size: {file_size} bytes")
                    self.io.print_info(f"Lines: {lines_count}")
                    
                    # Check if memory is loaded in current session
                    has_memory = hasattr(session.siada_config, 'user_memory') and session.siada_config.user_memory
                    self.io.print_info(f"Loaded in current session: {'Yes' if has_memory else 'No'}")
                else:
                    self.io.print_info(f"Memory file exists but is empty: {siada_md_path}")
            else:
                self.io.print_info("No siada.md file found in current workspace")
                self.io.print_info("Use `/init` to create and analyze project structure")
                
        except Exception as e:
            self.io.print_error(f'Error checking memory status: {str(e)}')
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())

    def _create_init_analysis_prompt(self, workspace):
        """Create the analysis prompt for /init command"""

        init_prompt = """You are an AI agent that brings the power of Siada directly into the terminal. Your task is to analyze the current directory and generate a comprehensive siada.md file to be used as instructional context for future interactions.

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

**siada.md Content Generation:**

**For a Code Project:**

*   **Project Overview:** Write a clear and concise summary of the project's purpose, main technologies, and architecture.
*   **Building and Running:** Document the key commands for building, running, and testing the project. Infer these from the files you've read (e.g., `scripts` in `package.json`, `Makefile`, etc.). If you can't find explicit commands, provide a placeholder with a TODO.
*   **Development Conventions:** Describe any coding styles, testing practices, or contribution guidelines you can infer from the codebase.

**For a Non-Code Project:**

*   **Directory Overview:** Describe the purpose and contents of the directory. What is it for? What kind of information does it hold?
*   **Key Files:** List the most important files and briefly explain what they contain.
*   **Usage:** Explain how the contents of this directory are intended to be used.

**Final Output:**

Write the complete content to the `siada.md` file. The output must be well-formatted Markdown."""

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
            if self.io.pretty:
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
                self.io.print_info(f"Comparing with checkpoint: {checkpoint_filename}")
                self.io.print_info("")
                
                if diff_hunks.strip():
                    self.io.print_info("Differences between checkpoint and working directory:")
                    self.io.print_info("=" * 60)
                    self.io.print_info(diff_hunks)
                else:
                    self.io.print_info("No differences found between checkpoint and working directory")

        except Exception as e:
            self.io.print_error(f"Failed to compare with checkpoint: {str(e)}")
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())

    def cmd_restore(self, session, args: str):
        "Restore files from a checkpoint"

        # Parse checkpoint filename from args
        checkpoint_filename = args.strip()
        if not checkpoint_filename:
            self.io.print_error("Please provide a checkpoint filename. Usage: /restore <checkpoint_filename>")
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
                self.io.print_error(
                    f"Checkpoint file '{checkpoint_filename}' not found"
                )
                return

            # Display checkpoint information
            self.io.print_info(f"Restoring from checkpoint: {checkpoint_filename}")
            self.io.print_info(f"Last tool used: {checkpoint_data.use_tool_name}")
            self.io.print_info(f"Modified files: {', '.join(checkpoint_data.modified_file_names)}")

            # Create a copy of the history to avoid modifying checkpoint data
            import copy
            restored_history = copy.deepcopy(checkpoint_data.history)

            if restored_history:
                last_message = restored_history[-1]
                ## compute the edge case
                if "role" in last_message:
                    if last_message["role"] == "assistant":
                        # if the last message is from the assistant, need to add a use message
                        restored_history.append(
                            {
                                "role": "user",
                                "content": "Checkpoint restored. User has new instructions. Give a concise response asking for next steps.",
                                "type": "message",
                            }
                        )
                if "type" in last_message:
                    ## only process type: function_call
                    if last_message["type"] in ["function_call"]:
                        call_id = last_message["call_id"]
                        function = last_message.get("name", "unknown_function")
                        restored_history.append(
                            {
                                "call_id": call_id,
                                "output": f"{function} executed successfully. Checkpoint restored. Briefly ask user how to continue.",
                                "type": "function_call_output",
                            }
                        )

            # clear the openai session
            import asyncio
            asyncio.run(session.state.openai_session.clear_session())

            # Restore the file states using GitService
            session.checkpoint_tracker.git_service.restore_project_from_snapshot(
                checkpoint_data.last_commit_hash
            )

            self.io.print_info(f"Successfully restored from checkpoint '{checkpoint_filename}'")
            return SwitchEvent(restored=True, history=restored_history)

        except Exception as e:
            self.io.print_error(f"Failed to restore from checkpoint: {str(e)}")
            if self.verbose:
                import traceback
                self.io.print_error(traceback.format_exc())


def main():
    md = SlashCommands(None, None).get_help_md()
    print(md)


if __name__ == "__main__":
    status = main()
    sys.exit(status)
