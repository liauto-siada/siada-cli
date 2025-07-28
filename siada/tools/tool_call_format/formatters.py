import json
from typing import Tuple
from siada.tools.tool_call_format.tool_call_formatter import ToolCallFormatter


class DefaultFormatter(ToolCallFormatter):


    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, str]:
        return "text", arguments

    @property
    def supported_function(self) -> str:
        return ""


class FileOperationFormatter(ToolCallFormatter):
    """
    文件操作格式化程序
    """

    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, str]:
        return "text", ""

    @property
    def supported_function(self) -> str:
        return "file_operation"


class SearchFormatter(ToolCallFormatter):
    """
    搜索格式化程序
    """

    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, str]:
        try:
            args = json.loads(arguments)
            query = args.get("query", "")
            return "text", f"Searching for: {query}"
        except json.JSONDecodeError:
            return "text", f"Invalid search arguments: {arguments}"

    @property
    def supported_function(self) -> str:
        return "search"


class CommandFormatter(ToolCallFormatter):
    """
    命令格式化程序
    """

    def format_input(self, call_id: str, function_name: str, arguments: str) -> Tuple[str, str]:
        try:
            args = json.loads(arguments)
            command = args.get("command", "")
            return "text", f"Running command: {command}"
        except json.JSONDecodeError:
            return "text", f"Invalid command arguments: {arguments}"

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
            content = f"### Bug Fix Attempt Summary\n\n**Result:**\n{result}"
            return "markdown", content
        except json.JSONDecodeError:
            return "markdown", f"### Bug Fix Attempt Summary\n\n**Error:** Invalid arguments provided: `{arguments}`"

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
            content = f"### Issue Reproduction Summary\n\n**Test Case:**\n`{test_case}`\n\n**Bug Analysis:**\n{bug_analysis}"
            return "markdown", content
        except json.JSONDecodeError:
            return "markdown", f"### Issue Reproduction Summary\n\n**Error:** Invalid arguments provided: `{arguments}`"

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
            return "text", f"Crawling {url} with format {crawl_format}"
        except json.JSONDecodeError:
            return "text", f"Invalid crawl arguments: {arguments}"

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
            return "text", f"Asking question: {question}"
        except json.JSONDecodeError:
            return "text", f"Invalid question arguments: {arguments}"

    @property
    def supported_function(self) -> str:
        return "ask_followup_question" 