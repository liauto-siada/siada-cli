import json
import os
from typing import Tuple
from siada.tools.tool_call_format.tool_call_formatter import ToolCallFormatter


class DefaultFormatter(ToolCallFormatter):


    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, str]:
        return "text", arguments

    @property
    def supported_function(self) -> str:
        return "default"
    

class FileEditFormatter(ToolCallFormatter):
    """
    File operation formatter
    """

    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, str]:
        style = "text"
        try:
            args = json.loads(arguments)
            path = args.get("path", "")
            command = args.get("command", "")
            file_text = args.get("file_text", "")
            old_str = args.get("old_str", "")
            new_str = args.get("new_str", "")
            view_range = args.get("view_range", None)
            insert_line = args.get("insert_line", None)

            content = ""
            if command == "view":
                if view_range and len(view_range) == 2:
                    content = f"I will read the file `{path}` from line {view_range[0]} to line {view_range[1]}."
                else:
                    content = f"I will read the file `{path}`."
            elif command == 'create':
                content = f'I will create the file `{path}` with the following content:\n```\n{file_text}\n```'
            elif command == 'str_replace':
                style = "markdown"
                content = f'In the file `{path}`, I will replace the string:\n```\n{old_str}\n```\nwith:\n```\n{new_str}\n```'
            elif command == 'insert':
                style = "markdown"
                content = f'In the file `{path}`, I will insert the following text after line {insert_line}:\n```\n{new_str}\n```'
            elif command == 'undo_edit':
                content = f'I will undo the last edit for the file `{path}`.'
            else:
                content = f"I will perform the command `{command}` with the arguments: {arguments}"

            return style, content
        except json.JSONDecodeError:
            return "text", f"failed to parse arguments: {arguments}"

    @property
    def supported_function(self) -> str:
        return "edit_file"
    
    
    
    


class SearchFormatter(ToolCallFormatter):
    """
    Search formatter
    """

    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, str]:
        try:
            args = json.loads(arguments)
            cwd = args.get("cwd", os.getcwd())
            directory_path = args.get("directory_path", "")
            regex = args.get("regex", "")
            file_pattern = args.get("file_pattern", "*")
            content = f"I will search for: {regex} in {directory_path} with file pattern {file_pattern} in {cwd}"
            return "text", content
        except json.JSONDecodeError:
            return "text", f"failed to parse arguments: {arguments}"

    @property
    def supported_function(self) -> str:
        return "search"


class CommandFormatter(ToolCallFormatter):
    """
    Command formatter
    """

    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, str]:
        try:
            args = json.loads(arguments)
            command = args.get("command", "")
            return "text", f"siada wants to run the following command: {command}"
        except json.JSONDecodeError:
            return "text", f"failed to parse arguments: {arguments}"

    @property
    def supported_function(self) -> str:
        return "run_cmd"


class FixAttemptCompletionFormatter(ToolCallFormatter):
    """
    Formatter for the fix_attempt_completion function.
    """

    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, str]:
        try:
            args = json.loads(arguments)
            result = args.get("result", "")
            content = f"The bug fix task has been successfully completed. see the result below\n {result}"
            return "text", content
        except json.JSONDecodeError:
            return "text", f"failed to parse arguments: {arguments}"

    @property
    def supported_function(self) -> str:
        return "fix_attempt_completion"


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
