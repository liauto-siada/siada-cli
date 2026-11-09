"""
Standard input/output interface for repository maps.

Repository-map IO supports:
- Info, warning and error output.
- File reading.
- Configurable output streams.
"""

import os
import sys
from typing import Optional, TextIO
from pathlib import Path


class IO:
    """
    Standard IO class for file reading and log output.
    
    Provide a unified interface for repository maps:
    - Log output at multiple levels.
    - File content reading.
    - Configurable output targets.
    - Verbose mode control.
    """
    
    def __init__(
        self, 
        verbose: bool = False,
        output_stream: Optional[TextIO] = None,
        error_stream: Optional[TextIO] = None
    ):
        """
        Initialize an IO instance.
        
        Args:
            verbose (bool): Whether to enable verbose output.
            output_stream (TextIO, optional): Output stream; defaults to sys.stdout.
            error_stream (TextIO, optional): Error stream; defaults to sys.stderr.
        """
        self.verbose = verbose
        self.output_stream = output_stream or sys.stdout
        self.error_stream = error_stream or sys.stderr
        
        # Statistics
        self.outputs = []
        self.warnings = []
        self.errors = []
    
    def tool_output(self, message: str) -> None:
        """
        Output an info message.
        
        Args:
            message (str): Message to output.
        """
        self.outputs.append(message)
        if self.verbose:
            print(f"[INFO] {message}", file=self.output_stream)
    
    def tool_warning(self, message: str) -> None:
        """
        Output a warning message.
        
        Args:
            message (str): Warning message to output.
        """
        self.warnings.append(message)
        print(f"[WARNING] {message}", file=self.error_stream)
    
    def tool_error(self, message: str) -> None:
        """
        Output an error message.
        
        Args:
            message (str): Error message to output.
        """
        self.errors.append(message)
        print(f"[ERROR] {message}", file=self.error_stream)
    
    def read_text(self, filepath: str) -> str:
        """
        Read file contents.
        
        Args:
            filepath (str): File path.
            
        Returns:
            str: File contents, or an empty string if reading fails.
        """
        try:
            # Ensure the path is absolute or relative to the current working directory
            path = Path(filepath)
            
            # Try different encodings
            encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'latin1']
            
            for encoding in encodings:
                try:
                    with open(path, 'r', encoding=encoding) as f:
                        content = f.read()
                    return content
                except UnicodeDecodeError:
                    continue
            
            # If all encodings fail, try reading in binary mode and ignore errors
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            if self.verbose:
                self.tool_warning(f"Read {filepath} using fallback encoding")
            
            return content
            
        except FileNotFoundError:
            self.tool_error(f"File not found: {filepath}")
            return ""
        except PermissionError:
            self.tool_error(f"Permission denied reading: {filepath}")
            return ""
        except IsADirectoryError:
            self.tool_error(f"Path is a directory: {filepath}")
            return ""
        except Exception as e:
            self.tool_error(f"Failed to read {filepath}: {str(e)}")
            return ""
    
    def clear_stats(self) -> None:
        """Clear statistics."""
        self.outputs.clear()
        self.warnings.clear()
        self.errors.clear()
    
    def get_stats(self) -> dict:
        """
        Get statistics.
        
        Returns:
            dict: Output, warning and error counts.
        """
        return {
            'outputs': len(self.outputs),
            'warnings': len(self.warnings),
            'errors': len(self.errors)
        }
    
    def set_verbose(self, verbose: bool) -> None:
        """
        Set verbose mode.
        
        Args:
            verbose (bool): Whether to enable verbose output.
        """
        self.verbose = verbose


class SilentIO(IO):
    """
    Silent IO class that outputs nothing to the console.
    
    Use for tests or other scenarios requiring silent operation.
    """
    
    def __init__(self):
        """Initialize a silent IO instance."""
        super().__init__(verbose=False)
    
    def tool_output(self, message: str) -> None:
        """Silently record an output message."""
        self.outputs.append(message)
    
    def tool_warning(self, message: str) -> None:
        """Silently record a warning message."""
        self.warnings.append(message)
    
    def tool_error(self, message: str) -> None:
        """Silently record an error message."""
        self.errors.append(message)


class FileIO(IO):
    """
    File IO class that redirects output to a file.
    
    Use when logs need to be saved to a file.
    """
    
    def __init__(
        self, 
        log_file: str,
        verbose: bool = True,
        append: bool = True
    ):
        """
        Initialize a file IO instance.
        
        Args:
            log_file (str): Log file path.
            verbose (bool): Whether to enable verbose output.
            append (bool): Whether to append to an existing file.
        """
        self.log_file = Path(log_file)
        self.append = append
        
        # Ensure log directory exists
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Open log file
        mode = 'a' if append else 'w'
        self.log_stream = open(self.log_file, mode, encoding='utf-8')
        
        super().__init__(
            verbose=verbose,
            output_stream=self.log_stream,
            error_stream=self.log_stream
        )
    
    def __del__(self):
        """Ensure the log file is closed."""
        if hasattr(self, 'log_stream') and not self.log_stream.closed:
            self.log_stream.close()
    
    def close(self):
        """Close the log file explicitly."""
        if hasattr(self, 'log_stream') and not self.log_stream.closed:
            self.log_stream.close()
