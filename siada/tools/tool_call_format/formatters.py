import json
import logging
import os
from typing import Tuple
from siada.tools.tool_call_format.tool_call_formatter import ToolCallFormatter

logger = logging.getLogger("siada.tool_call_format")


from partial_json_parser import loads, MalformedJSON, ensure_json


class DefaultFormatter(ToolCallFormatter):


    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, bool]:
        return arguments, True

    @property
    def supported_function(self) -> str:
        return "default"


class FileEditFormatter(ToolCallFormatter):
    """
    File operation formatter
    """

    def format_input(
        self, call_id: str, function_name: str, arguments: str
    ) -> Tuple[str, str, bool]:

        # Valid command enumeration
        VALID_COMMANDS = {"view", "create", "str_replace", "insert", "undo_edit"}
        complete = False
        content = ""
        try:
            # Use partial JSON parser to handle incomplete arguments
            args = loads(arguments)
            if arguments == ensure_json(arguments):
                complete = True

            # Safely extract values, handling potential None/missing keys
            path = args.get("path", None) if args else ""
            raw_command = args.get("command", None) if args else ""
            file_text = args.get("file_text", None) if args else ""
            old_str = args.get("old_str", None) if args else ""
            new_str = args.get("new_str", None) if args else ""
            view_range = args.get("view_range", None) if args else None
            insert_line = args.get("insert_line", None) if args else None

            # Validate command - only return valid commands, otherwise empty string
            command = raw_command if raw_command in VALID_COMMANDS else ""
            cwd = args.get("cwd", None) if args else None

            # If command is not valid, return empty string regardless of other parameters
            if not command:
                return "", False
            
            # if path is a valid path, get the fence
            fence = ""
            if path:
                from .file_to_language import get_language_from_file_extension
                fence = get_language_from_file_extension(path)

            if command == "view":
                if complete:
                    if path:
                        # Safely check if path has file extension
                        try:
                            is_file = bool(os.path.splitext(str(path))[1])  # Has extension = likely a file
                        except Exception:
                            is_file = False  # Default to directory if path is invalid
                        if is_file:
                            content = f"Read the file `{path}`"
                            if view_range and len(view_range) == 2:
                                content += f" from line {view_range[0]} to line {view_range[1]}."
                            else:
                                content += "."
                        else:
                            content = f"View the directory `{path}`."
            elif command == "create":

                if path:
                    content = f"Create the file `{path}`"
                    if file_text and complete:
                        if fence.lower() in ['md', 'markdown']:
                            content += f"` with the following content:\n{file_text}"
                        else:
                            content += f"` with the following content:\n```{fence}\n{file_text}\n```"
            elif command == "str_replace":
                if path:
                    content = f"In the file `{path}`"
                    if old_str is not None:
                        if new_str is not None:
                            if fence.lower() in ['md', 'markdown']:
                                old_str = old_str if old_str else f"```\n{old_str}\n```"
                                content += f"`, replace the string:\n{old_str}"
                                if complete:
                                    content += f"\nwith:\n{new_str}"
                            else:
                                content += f"`, replace the string:\n```{fence}\n{old_str}\n```"
                                if complete:
                                    content += f"\nwith:\n```{fence}\n{new_str}\n```"
            elif command == "insert":

                if path:
                    content = f"In the file `{path}`"
                    if insert_line is not None and new_str and complete:
                        if fence.lower() in ['md', 'markdown']:
                            content += f"`, insert the following text after line {insert_line}:\n{new_str}"
                        else:
                            content += f"`, insert the following text after line {insert_line}:\n```{fence}\n{new_str}\n```"
            elif command == "undo_edit":
                if path:
                    content = f"Undo the last edit for the file `{path}`"
                    if complete:
                        content += "`"
            else:
                # If command is not valid or empty, return empty content
                content = ""

            return content, complete
        except Exception as e:
            # Handle any parsing errors gracefully
            return content + f"failed to parse arguments: {arguments}", False

    def format_input_im(
        self, call_id: str, function_name: str, arguments: str,
        default_workspace: str = ""
    ) -> Tuple[str, bool]:
        """IM-friendly format for Lark cards: compact output with relative paths."""
        IM_MAX_LINES = 1000  # max lines per code block in IM mode
        IM_MAX_CHARS = 50000  # max chars per code block in IM mode

        complete = False
        content = ""
        try:
            args = loads(arguments)
            if arguments == ensure_json(arguments):
                complete = True

            path = args.get("path", None) if args else ""
            raw_command = args.get("command", None) if args else ""
            file_text = args.get("file_text", None) if args else ""
            old_str = args.get("old_str", None) if args else ""
            new_str = args.get("new_str", None) if args else ""
            view_range = args.get("view_range", None) if args else None
            insert_line = args.get("insert_line", None) if args else None
            cwd = args.get("cwd", None) if args else None

            VALID_COMMANDS = {"view", "create", "str_replace", "insert", "undo_edit"}
            command = raw_command if raw_command in VALID_COMMANDS else ""
            if not command:
                return "", False

            fence = ""
            if path:
                from .file_to_language import get_language_from_file_extension
                fence = get_language_from_file_extension(path)

            def _truncate(s: str) -> str:
                """Truncate string by lines and chars for IM display.
                Ensures clean line boundaries to avoid breaking markdown."""
                if not s:
                    return ""
                lines = s.split("\n")
                if len(lines) <= IM_MAX_LINES and len(s) <= IM_MAX_CHARS:
                    return s
                # Truncate by lines first
                truncated_lines = lines[:IM_MAX_LINES]
                result = "\n".join(truncated_lines)
                # Then truncate by chars if still too long
                if len(result) > IM_MAX_CHARS:
                    cut_pos = result.rfind("\n", 0, IM_MAX_CHARS)
                    if cut_pos > 0:
                        result = result[:cut_pos]
                    else:
                        result = result[:IM_MAX_CHARS]
                return result + "\n... (truncated)"

            def _code_block(s: str, lang: str) -> str:
                """Wrap string in a code block, using enough backticks to avoid
                conflicts with backticks inside the content."""
                # Find the longest run of backticks in content
                ticks = "```"
                while ticks in s:
                    ticks += "`"
                return f"{ticks}{lang}\n{s}\n{ticks}"

            # Compute relative path based on cwd or default_workspace
            def _rel_path(p: str) -> str:
                """Strip workspace prefix from path. Fallback to original."""
                if not p:
                    return p
                base = cwd or default_workspace
                if base:
                    # Normalize both paths for reliable prefix stripping
                    norm_p = os.path.normpath(str(p))
                    norm_base = os.path.normpath(str(base))
                    if not norm_base.endswith(os.sep):
                        norm_base += os.sep
                    if norm_p.startswith(norm_base):
                        return norm_p[len(norm_base):]
                return p

            if command == "view":
                if complete and path:
                    try:
                        is_file = bool(os.path.splitext(str(path))[1])
                    except Exception:
                        is_file = False
                    if is_file:
                        rel = _rel_path(path)
                        content = f"Read file **{rel}**"
                        if view_range and len(view_range) == 2:
                            content += f" L{view_range[0]}-{view_range[1]}"
                    else:
                        rel = _rel_path(path)
                        content = f"View directory **{rel}**"

            elif command == "create":
                if path:
                    rel = _rel_path(path)
                    content = f"Create file **{rel}**"

            elif command == "str_replace":
                if path:
                    rel = _rel_path(path)
                    content = f"Edit **{rel}**"

            elif command == "insert":
                if path:
                    rel = _rel_path(path)
                    content = f"Insert in **{rel}**"
                    if insert_line is not None and complete:
                        content += f" after line {insert_line}"

            elif command == "undo_edit":
                if path and complete:
                    rel = _rel_path(path)
                    content = f"Undo last edit for **{rel}**"

            return content, complete
        except Exception:
            return content + f"failed to parse arguments: {arguments}", False

    def supports_streaming(self) -> bool:
        """FileEditFormatter supports streaming rendering"""
        return True

    @property
    def supported_function(self) -> str:
        return "edit_file"
    

    def get_style(self) -> str:
        return "markdown"


class SearchFormatter(ToolCallFormatter):
    """
    Search formatter
    """

    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, bool]:
        try:
            args = json.loads(arguments)
            cwd = args.get("cwd", os.getcwd())
            directory_path = args.get("directory_path", "")
            regex = args.get("regex", "")
            file_pattern = args.get("file_pattern", "*")
            content = f"Search for: {regex} in {directory_path} with file pattern {file_pattern} in {cwd}"
            return content, True
        except json.JSONDecodeError:
            return f"failed to parse arguments: {arguments}", False

    @property
    def supported_function(self) -> str:
        return "regex_search_files"


class CommandFormatter(ToolCallFormatter):
    """
    Command formatter
    """

    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, bool]:
        try:
            args = json.loads(arguments)
            command = args.get("command", "")
            cwd = args.get("cwd", None)
            content = f"Run the following command: \n```bash \n{command}\n```"
            if cwd:
                content += f"\cwd: `{cwd}`"
            return content, True
        except json.JSONDecodeError:
            return f"failed to parse arguments: {arguments}", False

    def format_input_im(self, call_id: str, function_name: str, arguments: str,
                        default_workspace: str = "") -> Tuple[str, bool]:
        """IM-friendly format for Lark cards: inline code command (workspace handled by batcher)."""
        try:
            args = json.loads(arguments)
            command = args.get("command", "")
            # Use inline code for single-line commands, code block for multi-line
            if "\n" not in command.strip():
                content = f"`{command}`"
            else:
                content = f"```bash\n{command}\n```"
            return content, True
        except json.JSONDecodeError:
            return f"failed to parse arguments: {arguments}", False

    @property
    def supported_function(self) -> str:
        return "run_cmd"
    
    def get_style(self) -> str:
        return "markdown"


class FixAttemptCompletionFormatter(ToolCallFormatter):
    """
    Formatter for the fix_attempt_completion function.
    """

    def format_input(
        self, call_id: str, function_name: str, arguments: str
    ) -> Tuple[str, bool]:

        complete = False
        content = ""
        try:
            # Use partial JSON parser to handle incomplete arguments
            args = loads(arguments)
            # Check if JSON is complete by comparing with ensured version
            ensured_json = ensure_json(arguments)
            if arguments == ensured_json:
                complete = True

            # Safely extract values, handling potential None/missing keys
            result = args.get("result", "") if args else ""

            if result:
                content = f"The bug fix task has been successfully completed:\n{result}"
                if complete:
                    content += ""

            return content, complete
        except Exception as e:
            return content + f"failed to parse arguments: {arguments}", False

    @property
    def supports_streaming(self) -> bool:
        return False

    @property
    def supported_function(self) -> str:
        return "fix_attempt_completion"

    def get_style(self) -> str:
        return "markdown"


class ReproduceCompletionFormatter(ToolCallFormatter):
    """
    Formatter for the reproduce_completion function.
    """

    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, bool]:
        try:
            args = json.loads(arguments)
            test_case = args.get("test_case", "")
            bug_analysis = args.get("bug_analysis", "")
            content = f"This issue can be reproduced using test case : {test_case}.\n Analysis of the issue: {bug_analysis}"
            return content, True
        except json.JSONDecodeError:
            return f"failed to parse arguments: {arguments}", False

    @property
    def supported_function(self) -> str:
        return "reproduce_completion"


class WebCrawlFormatter(ToolCallFormatter):
    """
    Formatter for the web_crawl function.
    """

    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, bool]:
        try:
            args = json.loads(arguments)
            url = args.get("url", "")
            crawl_format = args.get("format", "text")
            return f"Crawl the url: {url} with format {crawl_format}", True
        except json.JSONDecodeError:
            return f"failed to parse arguments: {arguments}", False

    @property
    def supported_function(self) -> str:
        return "web_crawl"


class AskFollowupQuestionFormatter(ToolCallFormatter):
    """
    Formatter for the ask_followup_question function.
    """

    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, bool]:
        try:
            args = json.loads(arguments)
            question = args.get("question", "")
            return f"{question}", True
        except json.JSONDecodeError:
            return f"failed to parse arguments: {arguments}", False

    @property
    def supported_function(self) -> str:
        return "ask_followup_question" 


class ListCodeDefinitionNamesFormatter(ToolCallFormatter):
    """
    Formatter for the list_code_definition_names function.
    """

    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, bool]:
        try:
            args = json.loads(arguments)
            file_name = args.get("file_name", "Unknown file")
            return f"Analyze definitions in `{file_name}`", True
        except json.JSONDecodeError:
            return "failed to parse arguments: {arguments}", False

    @property
    def supported_function(self) -> str:
        return "list_code_definition_names"


class BrowserOperateFormatter(ToolCallFormatter):
    """
    Formatter for the browser_operate function (BrowserGym).
    Formats browser automation actions for user display.
    """

    # Map action types to human-readable descriptions
    ACTION_DESCRIPTIONS = {
        "launch": "open browser and navigate to",
        "click": "click on element",
        "fill": "enter text into",
        "select_option": "select option in",
        "scroll": "scroll the page",
        "press": "press key on",
        "hover": "hover over element",
        "focus": "focus on element",
        "clear": "clear content of",
        "dblclick": "double-click on element",
        "drag_and_drop": "drag element to target",
        "upload_file": "upload file to",
        "close": "close browser",
    }

    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, bool]:
        try:
            args = json.loads(arguments)
            action = args.get("action", "")

            if not action:
                return "Siada wants to perform a browser operation", False

            # Build description based on action type
            content = self._format_action(action, args)
            return content, True

        except json.JSONDecodeError:
            return f"failed to parse arguments: {arguments}", False

    def _format_action(self, action: str, args: dict) -> str:
        """Format action description based on action type and parameters."""
        url = args.get("url", "")
        bid = args.get("bid", "")
        value = args.get("value", "")
        target_bid = args.get("target_bid", "")
        file_path = args.get("file_path", "")
        delta_x = args.get("delta_x", 0)
        delta_y = args.get("delta_y", 0)
        key = args.get("key", "")

        if action == "launch":
            return f"> Siada will open browser and navigate to: `{url}`"

        elif action == "click":
            return f"> Siada will click on element `{bid}`"

        elif action == "fill":
            display_value = value[:50] + "..." if len(value) > 50 else value
            return f"> Siada will enter text into element `{bid}`: \"{display_value}\""

        elif action == "select_option":
            return f"> Siada will select option `{value}` in element `{bid}`"

        elif action == "scroll":
            direction_parts = []
            if delta_y > 0:
                direction_parts.append(f"down {delta_y}px")
            elif delta_y < 0:
                direction_parts.append(f"up {abs(delta_y)}px")
            if delta_x > 0:
                direction_parts.append(f"right {delta_x}px")
            elif delta_x < 0:
                direction_parts.append(f"left {abs(delta_x)}px")
            direction = " and ".join(direction_parts) if direction_parts else "by 0px"
            return f"> Siada will scroll the page {direction}"

        elif action == "press":
            return f"> Siada will press key `{key}` on element `{bid}`"

        elif action == "hover":
            return f"> Siada will hover over element `{bid}`"

        elif action == "focus":
            return f"> Siada will focus on element `{bid}`"

        elif action == "clear":
            return f"> Siada will clear content of element `{bid}`"

        elif action == "dblclick":
            return f"> Siada will double-click on element `{bid}`"

        elif action == "drag_and_drop":
            return f"> Siada will drag element `{bid}` to target `{target_bid}`"

        elif action == "upload_file":
            return f"> Siada will upload file `{file_path}` to element `{bid}`"

        elif action == "close":
            return "> Siada will close the browser"

        else:
            return f"> Siada will perform browser action: {action}"

    @property
    def supported_function(self) -> str:
        return "browser_operate"


class RunSubtaskFormatter(ToolCallFormatter):
    """
    Formatter for the run_subtask function.
    Shows a concise task summary instead of the full instruction JSON.
    """

    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, bool]:
        try:
            args = json.loads(arguments)
            instruction = args.get("instruction", "")
            lines = instruction.splitlines()
            # "Your task:" is its own line; the description follows on the next non-empty line
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped == "Your task:":
                    for j in range(i + 1, len(lines)):
                        next_line = lines[j].strip()
                        if next_line:
                            return f"Sub-agent task: {next_line}", True
                elif stripped.startswith("Your task:"):
                    task = stripped[len("Your task:"):].strip()
                    if task:
                        return f"Sub-agent task: {task}", True
            # Fallback: first non-empty line, truncated
            for line in lines:
                stripped = line.strip()
                if stripped:
                    return f"Sub-agent task: {stripped[:120]}", True
            return "Sub-agent task", True
        except (json.JSONDecodeError, Exception):
            return "Sub-agent task", True

    @property
    def supported_function(self) -> str:
        return "run_subtask"


class SmartSearchMemoryFormatter(ToolCallFormatter):
    """
    Formatter for the smart_search_memory function.
    Renders memory search queries for both standard and IM modes.
    """

    def format_input(
        self, call_id: str, function_name: str, arguments: str
    ) -> Tuple[str, bool]:
        return arguments, True

    def format_input_im(
        self,
        call_id: str,
        function_name: str,
        arguments: str,
        default_workspace: str = "",
    ) -> Tuple[str, bool]:
        """IM-friendly format: compact memory search display."""
        try:
            args = json.loads(arguments)
            query = args.get("query", "")
            # Truncate long queries for IM display
            display_query = query[:80] + "..." if len(query) > 80 else query
            content = f"Search memory: **{display_query}**"
            return content, True
        except json.JSONDecodeError:
            return f"failed to parse arguments: {arguments}", False

    @property
    def supported_function(self) -> str:
        return "smart_search_memory"