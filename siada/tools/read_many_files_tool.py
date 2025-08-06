"""
ReadManyFiles tool - Batch read multiple files with intelligent filtering.

This tool provides functionality to read multiple files based on glob patterns,
with support for text files, images, and PDFs. It includes intelligent filtering
using .gitignore rules and default exclusion patterns.
"""

import os
import time
import asyncio
from typing import Dict, Any, Optional

from .read_many_files.models import ReadManyFilesParams, ToolResult
from .read_many_files.file_processor import FileProcessor
from .read_many_files.filters import FileFilter
from .read_many_files.formatters import ResultFormatter


class ReadManyFilesTool:
    """ReadManyFiles tool implementation"""
    
    def __init__(self, target_dir: Optional[str] = None):
        """
        Initialize ReadManyFiles tool
        
        Args:
            target_dir: Target directory for file operations (defaults to current working directory)
        """
        self.target_dir = target_dir or os.getcwd()
        self.file_processor = FileProcessor(self.target_dir)
        self.file_filter = FileFilter(self.target_dir)
        self.formatter = ResultFormatter(self.target_dir)
    
    def validate_params(self, params: ReadManyFilesParams) -> Optional[str]:
        """
        Validate input parameters
        
        Args:
            params: ReadManyFilesParams object
            
        Returns:
            Error message if validation fails, None if valid
        """
        if not params.paths:
            return "Parameter 'paths' is required and cannot be empty"
        
        if not isinstance(params.paths, list):
            return "Parameter 'paths' must be a list"
        
        if any(not isinstance(path, str) for path in params.paths):
            return "All items in 'paths' must be strings"
        
        if params.include and not isinstance(params.include, list):
            return "Parameter 'include' must be a list if provided"
        
        if params.exclude and not isinstance(params.exclude, list):
            return "Parameter 'exclude' must be a list if provided"
        
        return None
    
    def merge_filtering_options(self, params: ReadManyFilesParams) -> Dict[str, bool]:
        """
        Merge filtering options with defaults
        
        Args:
            params: ReadManyFilesParams object
            
        Returns:
            Dictionary of filtering options
        """
        default_options = {
            'respect_git_ignore': True
        }
        
        if params.file_filtering_options:
            default_options.update(params.file_filtering_options)
        
        return default_options
    
    async def execute(self, params: ReadManyFilesParams, signal=None) -> ToolResult:
        """
        Execute the ReadManyFiles tool
        
        Args:
            params: ReadManyFilesParams object with tool parameters
            signal: Cancellation signal (optional)
            
        Returns:
            ToolResult object with processing results
        """
        start_time = time.time()
        
        try:
            # 1. Parameter validation
            validation_error = self.validate_params(params)
            if validation_error:
                return ToolResult(**self.formatter.create_error_result(validation_error))
            
            # 2. Configuration initialization
            file_filtering_options = self.merge_filtering_options(params)
            
            # 3. Build search patterns
            search_patterns = params.paths + (params.include or [])
            if not search_patterns:
                return ToolResult(**self.formatter.create_info_result("No search patterns provided"))
            
            exclusion_patterns = self.file_filter.build_exclusion_patterns(params)
            
            # 4. Execute file search
            all_files = await self.file_processor.search_files_with_glob(
                search_patterns, exclusion_patterns, signal
            )
            
            if not all_files:
                return ToolResult(**self.formatter.create_info_result(
                    "No files found matching the specified patterns"
                ))
            
            # 5. Apply ignore filters
            filtered_files, filter_counts = self.file_filter.apply_gitignore_filters(
                all_files, file_filtering_options
            )
            
            # 6. Security validation
            validated_files = self.file_filter.validate_workspace_security(filtered_files)
            
            if not validated_files:
                return ToolResult(**self.formatter.create_info_result(
                    "No files remain after filtering and security validation"
                ))
            
            # 7. Read file contents
            content_parts, processed_files, skipped_files = await self.file_processor.process_files(
                validated_files, params.paths
            )
            
            # 8. Add filter statistics to skipped files
            filter_skip_info = self.formatter.build_filter_skip_info(filter_counts)
            skipped_files.extend(filter_skip_info)
            
            # 9. Update processing time
            end_time = time.time()
            self.file_processor.stats.processing_time = end_time - start_time
            
            # 10. Build and return result
            result_dict = self.formatter.build_result(
                content_parts, processed_files, skipped_files, self.file_processor.stats
            )
            
            return ToolResult(**result_dict)
            
        except Exception as error:
            return ToolResult(**self.formatter.create_error_result(
                f"Unexpected error during file processing: {str(error)}"
            ))


# Main function for tool execution
async def read_many_files(params: ReadManyFilesParams, 
                         target_dir: Optional[str] = None,
                         signal=None) -> ToolResult:
    """
    Read multiple files based on glob patterns
    
    Args:
        params: ReadManyFilesParams object with tool parameters
        target_dir: Target directory for file operations (optional)
        signal: Cancellation signal (optional)
        
    Returns:
        ToolResult object with processing results
    """
    tool = ReadManyFilesTool(target_dir)
    return await tool.execute(params, signal)


# Convenience function for direct usage
async def read_files_by_patterns(paths: list, 
                                include: Optional[list] = None,
                                exclude: Optional[list] = None,
                                target_dir: Optional[str] = None,
                                use_default_excludes: bool = True,
                                respect_git_ignore: bool = True) -> ToolResult:
    """
    Convenience function to read files by patterns
    
    Args:
        paths: List of file paths or glob patterns
        include: Additional include patterns (optional)
        exclude: Exclude patterns (optional)
        target_dir: Target directory (optional)
        use_default_excludes: Whether to use default exclusion patterns
        respect_git_ignore: Whether to respect .gitignore rules
        
    Returns:
        ToolResult object with processing results
    """
    params = ReadManyFilesParams(
        paths=paths,
        include=include,
        exclude=exclude,
        useDefaultExcludes=use_default_excludes,
        file_filtering_options={
            'respect_git_ignore': respect_git_ignore
        }
    )
    
    return await read_many_files(params, target_dir)


if __name__ == "__main__":
    # Example usage
    import asyncio
    
    async def main():
        # Example: Read all Python files in current directory
        result = await read_files_by_patterns(
            paths=["**/*.py"],
            exclude=["**/test_*.py", "**/__pycache__/**"]
        )
        
        print("LLM Content:")
        for content in result.llmContent:
            if isinstance(content, str):
                print(content[:200] + "..." if len(content) > 200 else content)
            else:
                print(f"[Binary content: {content.get('type', 'unknown')}]")
        
        print("\nDisplay Message:")
        print(result.returnDisplay)
    
    asyncio.run(main())
