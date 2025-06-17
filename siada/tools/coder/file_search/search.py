"""
Core search functionality using ripgrep binary.
"""

import json
import os
import platform
import subprocess
import sys
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from agents import function_tool

# 尝试导入 importlib.resources 用于打包环境
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
        
        # 1. 优先检查环境变量指定的路径
        env_path = os.environ.get('RIPGREP_BINARY_PATH')
        if env_path and os.path.exists(env_path) and os.access(env_path, os.X_OK):
            return env_path
        
        # 2. 尝试使用 importlib.resources (适用于打包环境)
        if resources:
            try:
                # 尝试获取包资源路径
                with resources.path('siada.tools.coder.file_search', 'bin') as bin_path:
                    for binary_name in binary_names:
                        binary_file = bin_path / binary_name
                        if binary_file.exists():
                            # 确保有执行权限
                            self._ensure_executable(binary_file)
                            if os.access(binary_file, os.X_OK):
                                return str(binary_file)
            except (ImportError, FileNotFoundError, AttributeError):
                pass
        
        # 3. 检查多个可能的搜索路径
        search_paths = [
            # 开发环境路径
            Path(__file__).parent / "bin",
            # 安装环境路径
            Path(sys.executable).parent / "ripgrep_bin",
            # 用户目录
            Path.home() / ".local" / "bin" / "ripgrep",
            # 系统路径
            Path("/usr/local/bin"),
            Path("/opt/homebrew/bin"),
            # Windows 常见路径
            Path("C:/Program Files/ripgrep/bin"),
            Path("C:/tools/ripgrep"),
        ]
        
        # 添加 PATH 环境变量中的路径
        path_env = os.environ.get('PATH', '')
        for path_str in path_env.split(os.pathsep):
            if path_str.strip():
                search_paths.append(Path(path_str.strip()))
        
        # 在所有路径中搜索二进制文件
        for search_path in search_paths:
            if not search_path.exists():
                continue
                
            for binary_name in binary_names:
                binary_path = search_path / binary_name
                if binary_path.exists():
                    # 确保有执行权限
                    self._ensure_executable(binary_path)
                    if os.access(binary_path, os.X_OK):
                        return str(binary_path)
        
        return None
    
    def _ensure_executable(self, binary_path: Path) -> None:
        """
        确保二进制文件有执行权限。
        在某些打包环境中，文件可能会失去执行权限。
        """
        try:
            current_mode = binary_path.stat().st_mode
            # 添加用户执行权限
            new_mode = current_mode | stat.S_IXUSR
            # 如果有读权限，也添加对应的执行权限
            if current_mode & stat.S_IRGRP:
                new_mode |= stat.S_IXGRP
            if current_mode & stat.S_IROTH:
                new_mode |= stat.S_IXOTH
            
            if new_mode != current_mode:
                os.chmod(binary_path, new_mode)
        except (OSError, PermissionError):
            # 如果无法修改权限，忽略错误
            pass
    
    def _execute_ripgrep(self, args: List[str]) -> str:
        """
        Execute ripgrep with given arguments and return output.
        Implements output limiting similar to the original TypeScript version.
        """
        try:
            # Start ripgrep process
            process = subprocess.Popen(
                [self.rg_path] + args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            output_lines = []
            max_lines = self.MAX_RESULTS * 5  # Limit output lines
            
            # Read output line by line with limit
            for line in process.stdout:
                if len(output_lines) < max_lines:
                    output_lines.append(line.rstrip('\n\r'))
                else:
                    process.terminate()
                    break
            
            # Wait for process to complete
            process.wait()
            
            # Check for errors
            if process.returncode != 0 and process.returncode != 1:  # 1 means no matches found
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
        """
        results = []
        current_result = None
        
        for line in output.split('\n'):
            if not line.strip():
                continue
                
            try:
                parsed = json.loads(line)
                
                if parsed.get('type') == 'match':
                    # Save previous result if exists
                    if current_result:
                        results.append(current_result)
                    
                    # Create new result
                    data = parsed.get('data', {})
                    path_info = data.get('path', {})
                    submatches = data.get('submatches', [{}])
                    lines_info = data.get('lines', {})
                    
                    current_result = SearchResult(
                        file_path=path_info.get('text', ''),
                        line=data.get('line_number', 0),
                        column=submatches[0].get('start', 0) if submatches else 0,
                        match=lines_info.get('text', ''),
                        before_context=[],
                        after_context=[]
                    )
                
                elif parsed.get('type') == 'context' and current_result:
                    # Add context lines
                    data = parsed.get('data', {})
                    context_line_number = data.get('line_number', 0)
                    context_text = data.get('lines', {}).get('text', '')
                    
                    if context_line_number < current_result.line:
                        current_result.before_context.append(context_text)
                    else:
                        current_result.after_context.append(context_text)
                        
            except json.JSONDecodeError:
                # Skip invalid JSON lines
                continue
            except Exception:
                # Skip problematic lines
                continue
        
        # Add the last result
        if current_result:
            results.append(current_result)
        
        return results

    def search_in_files(
        self, 
        directory_path: str, 
        regex: str, 
        file_pattern: str = "*",
        cwd: Optional[str] = None
    ) -> str:
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
            "--json",           # Output in JSON format
            "-e", regex,        # Regex pattern
            "--glob", file_pattern,  # File pattern filter
            "--context", "1",   # Include 1 line of context before/after
            directory_path      # Directory to search
        ]
        
        try:
            # Execute ripgrep
            output = self._execute_ripgrep(args)
            
            if not output.strip():
                return "No results found"
            
            # Parse results
            results = self._parse_ripgrep_output(output)
            
            if not results:
                return "No results found"
            
            # Format and return results
            return self._format_results(results, cwd or os.getcwd())
            
        except Exception:
            return "No results found"
    
    def _format_results(self, results: List[SearchResult], cwd: str) -> str:
        """
        Format search results into readable string output.
        Mimics the original TypeScript formatting.
        """
        # Group results by file
        grouped_results = {}
        
        for result in results[:self.MAX_RESULTS]:
            try:
                relative_path = os.path.relpath(result.file_path, cwd)
            except ValueError:
                # Handle case where paths are on different drives (Windows)
                relative_path = result.file_path
            
            # Convert backslashes to forward slashes for consistency
            relative_path = relative_path.replace('\\', '/')
            
            if relative_path not in grouped_results:
                grouped_results[relative_path] = []
            grouped_results[relative_path].append(result)
        
        # Build output string
        output_lines = []
        
        # Add header with result count
        total_results = len(results)
        if total_results >= self.MAX_RESULTS:
            output_lines.append(f"Showing first {self.MAX_RESULTS} of {self.MAX_RESULTS}+ results. Use a more specific search if necessary.")
        else:
            result_word = "result" if total_results == 1 else "results"
            output_lines.append(f"Found {total_results:,} {result_word}.")
        
        output_lines.append("")  # Empty line
        
        # Format each file's results
        for file_path, file_results in grouped_results.items():
            output_lines.append(file_path)
            output_lines.append("│----")
            
            for i, result in enumerate(file_results):
                # Combine all lines (before context + match + after context)
                all_lines = (
                    result.before_context + 
                    [result.match] + 
                    result.after_context
                )
                
                # Add each line with pipe prefix
                for line in all_lines:
                    # Remove trailing whitespace but preserve the line structure
                    formatted_line = line.rstrip() if line else ""
                    output_lines.append(f"│{formatted_line}")
                
                # Add separator between results in the same file
                if i < len(file_results) - 1:
                    output_lines.append("│----")
            
            output_lines.append("│----")
            output_lines.append("")  # Empty line between files
        
        return '\n'.join(output_lines).rstrip()


@function_tool(
    name_override="regex_search_files"
)
def regex_search_files(
    cwd: str,
    directory_path: str,
    regex: str,
    file_pattern: str = "*"
) -> str:
    """
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
        ...     regex=r"def\s+(\w+)",
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
    searcher = RipgrepSearcher()
    return searcher.search_in_files(directory_path, regex, file_pattern, cwd)
