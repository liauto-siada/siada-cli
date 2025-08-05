import json
import os
from typing import Tuple
from siada.tools.tool_call_format.tool_call_formatter import ToolCallFormatter


from partial_json_parser import loads, MalformedJSON, ensure_json


class DefaultFormatter(ToolCallFormatter):


    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, str, bool]:
        return "text", arguments, True

    @property
    def supported_function(self) -> str:
        return "default"


class FileEditFormatter(ToolCallFormatter):
    """
    File operation formatter
    """

    def format_input(
        self, call_id: str, function_name: str, arguments: str
    ) -> Tuple[str, str]:
        style = "text"
        # Valid command enumeration
        VALID_COMMANDS = {"view", "create", "str_replace", "insert", "undo_edit"}
        complete = False
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

            # If command is not valid, return empty string regardless of other parameters
            if not command:
                return "text", ""

            content = ""
            if command == "view":
                if path:
                    content = f"I will read the file `{path}"
                    if view_range and len(view_range) == 2:
                        content += f"` from line {view_range[0]} to line {view_range[1]}"
                        if complete:
                            content += "."
                    elif complete:
                        content += "`"
            elif command == "create":
                style = "markdown"
                if path:
                    content = f"I will create the file `{path}"
                    if file_text:
                        content += "` with the following content:\n```\n{file_text}"
                        if complete:
                            content += "\n```"
            elif command == "str_replace":
                style = "markdown"
                if path:
                    content = f"In the file `{path}"
                    if old_str is not None:
                        content += "`, I will replace the string:\n```\n{old_str}"
                        if new_str is not None:
                            content += "\n```\nwith:\n```\n{new_str}"
                            if complete:
                                content += "\n```"
            elif command == "insert":
                style = "markdown"
                if path:
                    content = f"In the file `{path}"
                    if insert_line is not None and new_str:
                        content += f"`, I will insert the following text after line {insert_line}:\n```\n{new_str}"
                        if complete:
                            content += "\n```"
            elif command == "undo_edit":
                if path:
                    content = f"I will undo the last edit for the file `{path}"
                    if complete:
                        content += "`"
            else:
                # If command is not valid or empty, return empty content
                content = ""

            return style, content, complete
        except Exception as e:
            # Handle any parsing errors gracefully
            return "text", "", False

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

    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, str, bool]:
        try:
            args = json.loads(arguments)
            cwd = args.get("cwd", os.getcwd())
            directory_path = args.get("directory_path", "")
            regex = args.get("regex", "")
            file_pattern = args.get("file_pattern", "*")
            content = f"I will search for: {regex} in {directory_path} with file pattern {file_pattern} in {cwd}"
            return "text", content, True
        except json.JSONDecodeError:
            return "text", f"failed to parse arguments: {arguments}", False

    @property
    def supported_function(self) -> str:
        return "search"


class CommandFormatter(ToolCallFormatter):
    """
    Command formatter
    """

    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, str, bool]:
        try:
            args = json.loads(arguments)
            command = args.get("command", "")
            return "text", f"siada wants to run the following command: ```{command}```", True
        except json.JSONDecodeError:
            return "text", f"failed to parse arguments: {arguments}", False

    @property
    def supported_function(self) -> str:
        return "run_cmd"
    
    def get_style(self) -> str:
        return "markdown"


class FixAttemptCompletionFormatter(ToolCallFormatter):
    """
    Formatter for the fix_attempt_completion function.
    """

    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, str]:
        style = "markdown"
        complete = False
        try:
            # Use partial JSON parser to handle incomplete arguments
            args = loads(arguments)
            if arguments == ensure_json(arguments):
                complete = True

            # Safely extract values, handling potential None/missing keys
            result = args.get("result", "") if args else ""

            content = ""
            if result:
                content = f"The bug fix task has been successfully completed:\n\n```\n{result}"
                if complete:
                    content += "\n```"

            return style, content
        except Exception as e:
            return "text", ""

    @property
    def supported_function(self) -> str:
        return "fix_attempt_completion"
    
    def get_style(self) -> str:
        return "markdown"


class ReproduceCompletionFormatter(ToolCallFormatter):
    """
    Formatter for the reproduce_completion function.
    """

    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, str]:
        try:
            args = json.loads(arguments)
            test_case = args.get("test_case", "")
            bug_analysis = args.get("bug_analysis", "")
            content = f"This issue can be reproduced using test case : {test_case}.\n Analysis of the issue: {bug_analysis}"
            return "text", content
        except json.JSONDecodeError:
            return "text", f"failed to parse arguments: {arguments}"

    @property
    def supported_function(self) -> str:
        return "reproduce_completion"


class WebCrawlFormatter(ToolCallFormatter):
    """
    Formatter for the web_crawl function.
    """

    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, str]:
        try:
            args = json.loads(arguments)
            url = args.get("url", "")
            crawl_format = args.get("format", "text")
            return "text", f"siada wants to crawl the url: {url} with format {crawl_format}"
        except json.JSONDecodeError:
            return "text", f"failed to parse arguments: {arguments}"

    @property
    def supported_function(self) -> str:
        return "web_crawl"


class AskFollowupQuestionFormatter(ToolCallFormatter):
    """
    Formatter for the ask_followup_question function.
    """

    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, str]:
        try:
            args = json.loads(arguments)
            question = args.get("question", "")
            return "text", f"{question}"
        except json.JSONDecodeError:
            return "text", f"failed to parse arguments: {arguments}"

    @property
    def supported_function(self) -> str:
        return "ask_followup_question" 


class ListCodeDefinitionNamesFormatter(ToolCallFormatter):
    """
    Formatter for the list_code_definition_names function.
    """

    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, str]:
        try:
            args = json.loads(arguments)
            file_name = args.get("file_name", "Unknown file")
            return "text", f"siada wants to analyze definitions in `{file_name}`"
        except json.JSONDecodeError:
            return "text", "failed to parse arguments: {arguments}"

    @property
    def supported_function(self) -> str:
        return "list_code_definition_names"
