"""
Core search functionality using ripgrep binary.
"""

import json
import os
import platform
import re
import subprocess
import sys
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from agents import function_tool, RunContextWrapper

from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.coder.observation.observation import FunctionCallResult
from siada.tools.resolve_cwd import resolve_cwd
from siada.utils import DirectoryUtils
from siada.foundation.context import get_context_var

SEARCH_DOCS="""
    Perform high-performance regex search across files using ripgrep.
    
    This function provides a convenient interface to search for patterns in files
    within a specified directory. It uses ripgrep for fast searching and returns
    formatted results with context lines for better readability.
    
    Args:
        cwd (str): Current working directory used as the base for calculating
                  relative file paths in the output. This helps make the results
                  more readable by showing paths relative to the project root.
        directory_path (str): The target directory to search in. Can be an absolute
                             or relative path. All files matching the file_pattern
                             within this directory (and subdirectories) will be searched.
        regex (str): Regular expression pattern to search for. Uses Rust regex syntax
                    which is similar to PCRE. Supports advanced features like lookahead,
                    lookbehind, and Unicode character classes.
        file_pattern (str, optional): Glob pattern to filter which files to search.
                                     Defaults to "*" (all files). Examples:
                                     - "*.py" for Python files only
                                     - "*.{js,ts}" for JavaScript and TypeScript files
                                     - "test_*.py" for Python test files
        
    Returns:
        str: Formatted search results containing:
             - Summary line with total number of matches found
             - For each file with matches:
               - Relative file path
               - Each match with surrounding context lines
               - Line numbers and column positions
             - Results are limited to MAX_RESULTS (300) for performance
             - Returns "No results found" if no matches are discovered
        
    Raises:
        RuntimeError: If the ripgrep binary cannot be found or executed.
                     This can happen if ripgrep is not installed or the binary
                     path is not properly configured.
        
    Example:
        >>> results = regex_search_files(
        ...     cwd="/project/root",
        ...     directory_path="siada",
        ...     regex=r"def\\s+(\\w+)",
        ...     file_pattern="*.py"
        ... )
        >>> print(results)
        Found 15 results.
        
        siada/main.py
        │----
        │class MyClass:
        │    def my_function(self):
        │        pass
        │----
    """


# Try to import importlib.resources for packaged environments
try:
    from importlib import resources
except ImportError:
    try:
        import importlib_resources as resources
    except ImportError:
        resources = None


@dataclass
class SearchResult:
    """Represents a single search result with context."""
    file_path: str
    line: int
    column: int
    match: str
    before_context: List[str]
    after_context: List[str]


class RipgrepSearchResult(FunctionCallResult):
    """Represents a single search result with context."""
    search_results: List[SearchResult]
    cwd: str

    def __init__(self, search_results: List[SearchResult], cwd: str):
        self.search_results = search_results
        self.cwd = cwd
        # Stable id for persistence across multiple .content property reads
        self.call_id = str(uuid.uuid4())
        self._content_cache: Optional[str] = None
        # super().__init__(content=content)


    @property
    def content(self) -> str:
        """Generate content dynamically from search results."""
        if self._content_cache is not None:
            return self._content_cache

        if not self.search_results:
            self._content_cache = "No results found"
            return self._content_cache

        raw_content = RipgrepSearcher.format_results(self.search_results, self.cwd)

        # Apply tool output truncation strategy 
        self._content_cache = _truncate_tool_output_if_needed(
            content=raw_content,
            call_id=self.call_id,
            cwd=self.cwd,
        )
        return self._content_cache

    def format_for_display(self):
        if self.search_results:
            match_term = "match" if len(self.search_results) == 1 else "matches"
            return f"Found {len(self.search_results)} {match_term}."
        else:
            return "No results found"

    def __str__(self):
        return self.content


class RipgrepSearcher:
    """High-performance file search using ripgrep binary."""
    
    MAX_RESULTS = 300
    
    def __init__(self):
        """Initialize the searcher and locate ripgrep binary."""
        self.rg_path = self._find_ripgrep_binary()
        if not self.rg_path:
            raise RuntimeError("Could not find ripgrep binary")
    
    def _find_ripgrep_binary(self) -> Optional[str]:
        """
        Find ripgrep binary in multiple possible locations.
        Supports both development and packaged environments.
        """
        # Determine binary name based on platform
        system = platform.system().lower()
        machine = platform.machine().lower()
        
        # Map platform to binary names
        binary_names = []
        
        if system == "windows":
            binary_names = ["rg.exe", "rg-windows.exe"]
        elif system == "darwin":  # macOS
            if machine in ["arm64", "aarch64"]:
                binary_names = ["rg-macos-arm64", "rg-macos", "rg"]
            else:
                binary_names = ["rg-macos-x64", "rg-macos", "rg"]
        elif system == "linux":
            if machine in ["arm64", "aarch64"]:
                binary_names = ["rg-linux-arm64", "rg-linux", "rg"]
            else:
                binary_names = ["rg-linux-x64", "rg-linux", "rg"]
        else:
            binary_names = ["rg"]
        
        # Check environment variable path first
        env_path = os.environ.get('RIPGREP_BINARY_PATH')
        if env_path and os.path.exists(env_path) and os.access(env_path, os.X_OK):
            return env_path
        
        # Try using importlib.resources for packaged environments
        if resources:
            try:
                with resources.path('siada.tools.coder.file_search', 'bin') as bin_path:
                    for binary_name in binary_names:
                        binary_file = bin_path / binary_name
                        if binary_file.exists():
                            self._ensure_executable(binary_file)
                            if os.access(binary_file, os.X_OK):
                                return str(binary_file)
            except (ImportError, FileNotFoundError, AttributeError):
                pass
        
        # Check multiple possible search paths
        search_paths = [
            Path(__file__).parent / "bin",  # Development environment
            Path(sys.executable).parent / "ripgrep_bin",  # Installation environment
            Path.home() / ".local" / "bin" / "ripgrep",  # User directory
            Path("/usr/local/bin"),  # System paths
            Path("/opt/homebrew/bin"),
            Path("C:/Program Files/ripgrep/bin"),  # Windows common paths
            Path("C:/tools/ripgrep"),
        ]
        
        # Add paths from PATH environment variable
        path_env = os.environ.get('PATH', '')
        for path_str in path_env.split(os.pathsep):
            if path_str.strip():
                search_paths.append(Path(path_str.strip()))
        
        # Search for binary files in all paths
        for search_path in search_paths:
            if not search_path.exists():
                continue
                
            for binary_name in binary_names:
                binary_path = search_path / binary_name
                if binary_path.exists():
                    self._ensure_executable(binary_path)
                    if os.access(binary_path, os.X_OK):
                        return str(binary_path)
        
        return None
    
    def _ensure_executable(self, binary_path: Path) -> None:
        """
        Ensure binary file has execute permissions.
        In some packaged environments, files may lose execute permissions.
        """
        try:
            current_mode = binary_path.stat().st_mode
            new_mode = current_mode | stat.S_IXUSR  # Add user execute permission
            
            # Add execute permission if read permission exists
            if current_mode & stat.S_IRGRP:
                new_mode |= stat.S_IXGRP
            if current_mode & stat.S_IROTH:
                new_mode |= stat.S_IXOTH
            
            if new_mode != current_mode:
                os.chmod(binary_path, new_mode)
        except (OSError, PermissionError):
            # Ignore errors if unable to modify permissions
            pass
    
    def _execute_ripgrep(self, args: List[str]) -> str:
        """
        Execute ripgrep with given arguments and return output.
        Implements output limiting similar to the original TypeScript version.
        """
        try:
            process = subprocess.Popen(
                [self.rg_path] + args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            output_lines = []
            max_lines = self.MAX_RESULTS * 5
            
            for line in process.stdout:
                if len(output_lines) < max_lines:
                    output_lines.append(line.rstrip('\n\r'))
                else:
                    process.terminate()
                    break
            
            process.wait()
            
            # Return code 1 means no matches found, which is normal
            if process.returncode != 0 and process.returncode != 1:
                stderr_output = process.stderr.read() if process.stderr else ""
                if stderr_output.strip():
                    raise subprocess.CalledProcessError(
                        process.returncode, 
                        [self.rg_path] + args, 
                        stderr_output
                    )
            
            return '\n'.join(output_lines)
            
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"ripgrep process error: {e.stderr}")
        except Exception as e:
            raise RuntimeError(f"ripgrep execution failed: {str(e)}")
    
    def _parse_ripgrep_output(self, output: str) -> List[SearchResult]:
        """
        Parse ripgrep JSON output into SearchResult objects.
        Handles both match and context lines.

        Context attribution strategy
        ----------------------------
        ripgrep emits events in file order, so a context line that appears
        *after* the previous match but *before* the next match is ambiguous
        at the time it is read: we don't yet know whether a new match will
        follow.  We therefore buffer all context lines in ``pending_context``
        and resolve attribution lazily:

        * When a **match** event arrives the entire pending buffer becomes
          that match's ``before_context``, and the buffer is cleared.
        * When the previous match is **finalised** (i.e. the next match or
          end-of-stream is reached) any remaining pending lines are appended
          to its ``after_context``.

        This correctly handles three scenarios:
          1. Leading context before the very first match (previously lost
             because ``current_result`` was None).
          2. Context between two distant matches (previously misattributed to
             the previous match's ``after_context``).
          3. Shared / adjacent context that sits between two close matches.
        """
        results = []
        current_result = None
        prev_match_line: int = 0
        # Each entry is (line_number, text) so we can route lines to the
        # correct match when a new match arrives.
        pending_context: List[tuple] = []

        for line in output.split('\n'):
            if not line.strip():
                continue

            try:
                parsed = json.loads(line)

                if parsed.get('type') == 'match':
                    data = parsed.get('data', {})
                    match_line: int = data.get('line_number', 0)

                    if current_result is None:
                        # First match ever: every buffered context line is
                        # before-context (there is no previous match to
                        # attribute them to).
                        before_ctx = [txt for _, txt in pending_context]
                    else:
                        # Split buffered context between the two matches using
                        # the midpoint of their line numbers.  Lines closer to
                        # the previous match become its after_context; lines
                        # closer to the new match become its before_context.
                        midpoint = (prev_match_line + match_line) / 2
                        before_ctx = [
                            txt for ln, txt in pending_context if ln > midpoint
                        ]
                        current_result.after_context.extend(
                            txt for ln, txt in pending_context if ln <= midpoint
                        )
                        results.append(current_result)

                    path_info = data.get('path', {})
                    submatches = data.get('submatches', [{}])
                    lines_info = data.get('lines', {})

                    current_result = SearchResult(
                        file_path=path_info.get('text', ''),
                        line=match_line,
                        column=submatches[0].get('start', 0) if submatches else 0,
                        match=lines_info.get('text', ''),
                        before_context=before_ctx,
                        after_context=[]
                    )
                    prev_match_line = match_line
                    pending_context = []

                elif parsed.get('type') == 'context':
                    data = parsed.get('data', {})
                    context_line_number = data.get('line_number', 0)
                    context_text = data.get('lines', {}).get('text', '')
                    pending_context.append((context_line_number, context_text))

            except json.JSONDecodeError:
                continue
            except Exception:
                continue

        if current_result:
            current_result.after_context.extend(txt for _, txt in pending_context)
            results.append(current_result)

        return results

    def search_in_files(
        self, 
        directory_path: str, 
        regex: str, 
        file_pattern: str = "*",
        cwd: Optional[str] = None
    ) -> RipgrepSearchResult:
        """
        Perform regex search in files and return formatted results.
        
        Args:
            directory_path: Directory to search in
            regex: Regular expression pattern (Rust regex syntax)
            file_pattern: Glob pattern to filter files (default: "*")
            cwd: Current working directory for relative path calculation
            
        Returns:
            Formatted search results as string
        """
        # Build ripgrep arguments
        args = [
            "--json",
            "-e", regex,
            "--glob", file_pattern,
            "--context", "1",
            directory_path
        ]
        
        try:
            output = self._execute_ripgrep(args)
            
            if not output.strip():
                return "No results found"
            
            results = self._parse_ripgrep_output(output)
            
            return RipgrepSearchResult(search_results=results, cwd=cwd or os.getcwd())
        
        except Exception:
            return RipgrepSearchResult(search_results=[], cwd=cwd or os.getcwd())
    
    @staticmethod
    def format_results(results: List[SearchResult], cwd: str) -> str:
        """
        Format search results into readable string output.
        Mimics the original TypeScript formatting.
        """
        grouped_results = {}
        
        for result in results[:RipgrepSearcher.MAX_RESULTS]:
            try:
                relative_path = os.path.relpath(result.file_path, cwd)
            except ValueError:
                # Handle case where paths are on different drives (Windows)
                relative_path = result.file_path
            
            relative_path = relative_path.replace('\\', '/')
            
            if relative_path not in grouped_results:
                grouped_results[relative_path] = []
            grouped_results[relative_path].append(result)
        
        output_lines = []
        
        total_results = len(results)
        if total_results >= RipgrepSearcher.MAX_RESULTS:
            output_lines.append(f"Showing first {RipgrepSearcher.MAX_RESULTS} of {RipgrepSearcher.MAX_RESULTS}+ results. Use a more specific search if necessary.")
        else:
            result_word = "result" if total_results == 1 else "results"
            output_lines.append(f"Found {total_results:,} {result_word}.")
        
        output_lines.append("")
        
        for file_path, file_results in grouped_results.items():
            output_lines.append(file_path)
            output_lines.append("│----")
            
            for i, result in enumerate(file_results):
                all_lines = (
                    result.before_context + 
                    [result.match] + 
                    result.after_context
                )
                
                for line in all_lines:
                    formatted_line = line.rstrip() if line else ""
                    output_lines.append(f"│{formatted_line}")
                
                if i < len(file_results) - 1:
                    output_lines.append("│----")
            
            output_lines.append("│----")
            output_lines.append("")
        
        return '\n'.join(output_lines).rstrip()


# ---- Tool output truncation --------------------------------

# Default threshold: 200KB ( 4 chars~= 1 token in english)
DEFAULT_TRUNCATE_TOOL_OUTPUT_THRESHOLD = 200_000
# Default lines to keep after truncation
DEFAULT_TRUNCATE_TOOL_OUTPUT_LINES = 1000
# Force wrap width for ultra-long single line outputs
WRAP_WIDTH = 120


def _safe_output_file_name(call_id: str) -> str:
    """Create a safe file name from call_id."""
    base = os.path.basename(call_id)
    base = re.sub(r"[^a-zA-Z0-9._-]+", "_", base)
    if not base:
        base = "tool_call"
    return f"{base}.output"


def _get_dynamic_truncation_threshold(static_threshold: int) -> int:
    """Compute a dynamic threshold if context info is available.

    Mirrors gemini-cli logic:
      threshold = min(4 * (tokenLimit - usedTokens), staticThreshold)

    Here we try to read from global contextvars set by the interaction loop.
    """
    try:
        # set by conversation_turn._print_context_usage (best-effort)
        used_tokens = int(get_context_var("last_prompt_token_count", 0) or 0)
        token_limit = int(get_context_var("model_context_window", 0) or 0)
    except Exception:
        return static_threshold

    if token_limit <= 0:
        return static_threshold

    remaining = max(0, token_limit - used_tokens)
    dynamic = 4 * remaining
    return min(dynamic, static_threshold)


def _wrap_long_lines_if_needed(lines: List[str], truncate_lines: int) -> List[str]:
    """If the output has too few lines to truncate by lines, force-wrap long lines."""
    # if len(lines) > truncate_lines:
    #     return lines
    
    has_long_line = any(len(line) > WRAP_WIDTH for line in lines)
    if not has_long_line:
        return lines
    
    wrapped: List[str] = []
    for line in lines:
        if len(line) > WRAP_WIDTH:
            for i in range(0, len(line), WRAP_WIDTH):
                wrapped.append(line[i : i + WRAP_WIDTH])
        else:
            wrapped.append(line)
    return wrapped


def _truncate_tool_output_if_needed(content: str, call_id: str, cwd: str) -> str:
    """Truncate oversized tool output while preserving head+tail and persisting full output."""
    # Allow env overrides for testing / tuning
    static_threshold = int(
        os.environ.get(
            "SIADA_TRUNCATE_TOOL_OUTPUT_THRESHOLD",
            DEFAULT_TRUNCATE_TOOL_OUTPUT_THRESHOLD,
        )
    )
    truncate_lines = int(
        os.environ.get(
            "SIADA_TRUNCATE_TOOL_OUTPUT_LINES",
            DEFAULT_TRUNCATE_TOOL_OUTPUT_LINES,
        )
    )

    # layer 2 (dynamic threshold) - best effort
    threshold = _get_dynamic_truncation_threshold(static_threshold)

    if static_threshold <= 0 or truncate_lines <= 0:
        return content

    if len(content) <= threshold:
        return content

    # Step 2: split and optionally wrap long lines (when too few lines to truncate)
    lines = content.splitlines()
    lines = _wrap_long_lines_if_needed(lines, truncate_lines)

    # Step 3: keep head 20% + tail 80%
    head = max(1, truncate_lines // 5)  # 20%
    beginning = lines[:head]
    end = lines[-(truncate_lines - head) :] if len(lines) > head else []

    truncated_content = (
        "\n".join(beginning)
        + "\n... [CONTENT TRUNCATED] ...\n"
        + "\n".join(end)
    ).rstrip()

    # Step 4: persist full content
    project_temp_dir = DirectoryUtils.get_project_temp_dir(cwd)
    output_file = os.path.join(project_temp_dir, _safe_output_file_name(call_id))
    try:
        Path(project_temp_dir).mkdir(parents=True, exist_ok=True)
        Path(output_file).write_text(content, encoding="utf-8", errors="replace")
    except Exception:
        # If persistence fails, still return truncated content
        output_file = ""

    # Step 5: build return message
    file_hint = (
        f"The full output has been saved to: {output_file}\n\n"
        if output_file
        else ""
    )

    return (
        "Tool output was too large and has been truncated.\n"
        + file_hint
        + "To read the complete output, use the edit_file tool with command=\"view\" and the absolute file path above.\n"
        + "For large files, you can use the view_range parameter to read specific line ranges:\n"
        + "- edit_file with command=\"view\", view_range=[1, 100] to see lines 1-100\n"
        + "- edit_file with command=\"view\", view_range=[N, M] to read lines N through M\n"
        + "- edit_file with command=\"view\", view_range=[N, -1] to read from line N to the end of the file\n"
        + "You may also use regex_search_files or run_cmd (e.g. grep/head/tail) to locate specific content within the saved file.\n\n"
        + "The truncated output below shows the beginning and end of the content.\n"
        + "The marker '... [CONTENT TRUNCATED] ...' indicates where content was removed.\n\n"
        + "Truncated part of the output:\n"
        + truncated_content
    )


@function_tool(
    name_override="regex_search_files", description_override=SEARCH_DOCS
)
def regex_search_files(
    context: RunContextWrapper[CodeAgentContext],
    cwd: str,
    directory_path: str,
    regex: str,
    file_pattern: str = "*"
) -> FunctionCallResult:

    effective_cwd = resolve_cwd(context, cwd)
    searcher = RipgrepSearcher()
    return searcher.search_in_files(directory_path, regex, file_pattern, effective_cwd)
