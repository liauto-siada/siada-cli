"""
Completion engine for file recommendation system.
"""

import asyncio
import time
from typing import List, Optional

from .config import CompletionConfig, FilterOptions
from .file_discovery import FileDiscoveryService
from .suggestion import Suggestion, sort_suggestions, limit_suggestions
from ..utils.text_utils import parse_at_command_path, extract_at_path_from_text
from ..utils.path_utils import escape_path


class CompletionEngine:
    """
    Main completion engine that coordinates all components
    """
    
    def __init__(self, search_directories: List[str], config: CompletionConfig):
        """
        Initialize completion engine
        
        Args:
            search_directories: List of directories to search in
            config: Completion configuration
        """
        self.search_directories = search_directories
        self.config = config
        self.file_discovery_services = {}
        
        # Initialize file discovery services for each directory
        for directory in search_directories:
            self.file_discovery_services[directory] = FileDiscoveryService(directory)
    
    async def get_suggestions(self, text: str) -> List[Suggestion]:
        """
        Get file suggestions for the given text
        
        Args:
            text: Input text containing @ command
            
        Returns:
            List of file suggestions
        """
        start_time = time.time()
        
        try:
            # Extract @ path from text
            at_path = extract_at_path_from_text(text)
            if not at_path:
                return []
            
            # Parse the @ command path
            base_dir, prefix, partial_path = parse_at_command_path(text)
            
            # If no prefix, return directory listing
            if not prefix and base_dir == ".":
                return await self._get_directory_listing()
            
            # Search for matching files
            suggestions = await self._search_files(base_dir, prefix)
            
            # Sort and limit results
            sorted_suggestions = sort_suggestions(suggestions)
            limited_suggestions = limit_suggestions(sorted_suggestions, self.config.max_results)
            
            return limited_suggestions
            
        except Exception as e:
            # Return empty list on error, with optional logging
            print(f"Error in completion engine: {e}")
            return []
        
        finally:
            # Optional: track performance
            elapsed_time = time.time() - start_time
            if elapsed_time > self.config.search_timeout_ms / 1000:
                print(f"Warning: Search took {elapsed_time:.2f}s, exceeding timeout")
    
    async def _get_directory_listing(self) -> List[Suggestion]:
        """
        Get listing of current directory files
        
        Returns:
            List of suggestions for current directory
        """
        all_suggestions = []
        filter_options = self.config.get_filter_options()
        
        for directory in self.search_directories:
            if directory in self.file_discovery_services:
                service = self.file_discovery_services[directory]
                suggestions = service.find_files_in_directory(
                    directory, 
                    "", 
                    filter_options,
                    self.config.max_results
                )
                all_suggestions.extend(suggestions)
        
        return all_suggestions
    
    async def _search_files(self, base_dir: str, prefix: str) -> List[Suggestion]:
        """
        Search for files matching the prefix
        
        Args:
            base_dir: Base directory to search in
            prefix: Search prefix
            
        Returns:
            List of matching suggestions
        """
        all_suggestions = []
        filter_options = self.config.get_filter_options()
        
        # Create search tasks for all directories
        search_tasks = []
        
        for directory in self.search_directories:
            if directory in self.file_discovery_services:
                service = self.file_discovery_services[directory]
                
                # Determine actual search directory
                if base_dir == ".":
                    search_dir = directory
                else:
                    search_dir = self._resolve_search_directory(directory, base_dir)
                    if not search_dir:
                        continue
                
                # Create search task
                if self.config.enable_recursive_search:
                    task = service.find_files_recursively(
                        search_dir,
                        prefix,
                        filter_options,
                        "",
                        0,
                        self.config.max_search_depth,
                        self.config.max_results
                    )
                else:
                    # Use synchronous method wrapped in async
                    task = asyncio.create_task(
                        asyncio.to_thread(
                            service.find_files_in_directory,
                            search_dir,
                            prefix,
                            filter_options,
                            self.config.max_results
                        )
                    )
                
                search_tasks.append(task)
        
        # Execute search tasks with timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*search_tasks, return_exceptions=True),
                timeout=self.config.search_timeout_ms / 1000
            )
            
            # Collect results from successful tasks
            for result in results:
                if isinstance(result, list):
                    all_suggestions.extend(result)
                elif isinstance(result, Exception):
                    # Log exception but continue
                    print(f"Search task failed: {result}")
                    
        except asyncio.TimeoutError:
            # Handle timeout - return partial results
            print(f"Search timeout after {self.config.search_timeout_ms}ms")
            
            # Cancel remaining tasks
            for task in search_tasks:
                if not task.done():
                    task.cancel()
            
            # Collect results from completed tasks
            for task in search_tasks:
                if task.done() and not task.cancelled():
                    try:
                        result = task.result()
                        if isinstance(result, list):
                            all_suggestions.extend(result)
                    except Exception:
                        pass
        
        return all_suggestions
    
    def _resolve_search_directory(self, base_directory: str, relative_path: str) -> Optional[str]:
        """
        Resolve search directory from base directory and relative path
        
        Args:
            base_directory: Base directory
            relative_path: Relative path from @ command
            
        Returns:
            Resolved directory path or None if invalid
        """
        import os
        
        try:
            # Remove trailing slash from relative_path if present
            relative_path = relative_path.rstrip('/')
            
            # Join paths
            resolved_path = os.path.join(base_directory, relative_path)
            resolved_path = os.path.abspath(resolved_path)
            
            # Security check - ensure resolved path is within base directory
            base_abs = os.path.abspath(base_directory)
            if not resolved_path.startswith(base_abs):
                return None
            
            # Check if directory exists
            if os.path.exists(resolved_path) and os.path.isdir(resolved_path):
                return resolved_path
            
            return None
            
        except Exception:
            return None
    
    def get_suggestions_sync(self, text: str) -> List[Suggestion]:
        """
        Synchronous version of get_suggestions
        
        Args:
            text: Input text containing @ command
            
        Returns:
            List of file suggestions
        """
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.get_suggestions(text))
        except RuntimeError:
            # No event loop running, create a new one
            return asyncio.run(self.get_suggestions(text))
    
    def should_show_suggestions(self, text: str) -> bool:
        """
        Check if suggestions should be shown for the given text
        
        Args:
            text: Input text
            
        Returns:
            bool: True if suggestions should be shown
        """
        # Basic check - look for @ character
        at_path = extract_at_path_from_text(text)
        if at_path is None:
            return False
        
        # Don't show suggestions for lone @ symbol
        if at_path == '@':
            return False
        
        # Check if the path corresponds to a complete existing file
        path_content = at_path[1:]  # Remove @ prefix
        if self._is_complete_file_path(path_content):
            return False
            
        # Show suggestions for @ with content
        return True
    
    def _is_complete_file_path(self, path: str) -> bool:
        """
        Check if path corresponds to a complete existing file
        
        Args:
            path: Path to check (without @ prefix)
            
        Returns:
            bool: True if path points to an existing file
        """
        import os
        
        if not path:
            return False
        
        # Check in all search directories
        for search_dir in self.search_directories:
            full_path = os.path.join(search_dir, path)
            if os.path.isfile(full_path):
                return True
        
        return False
    
    def update_config(self, config: CompletionConfig):
        """
        Update completion configuration
        
        Args:
            config: New configuration
        """
        self.config = config
    
    def add_search_directory(self, directory: str):
        """
        Add a new search directory
        
        Args:
            directory: Directory to add
        """
        if directory not in self.search_directories:
            self.search_directories.append(directory)
            self.file_discovery_services[directory] = FileDiscoveryService(directory)
    
    def remove_search_directory(self, directory: str):
        """
        Remove a search directory
        
        Args:
            directory: Directory to remove
        """
        if directory in self.search_directories:
            self.search_directories.remove(directory)
            if directory in self.file_discovery_services:
                del self.file_discovery_services[directory]
    
    def clear_cache(self):
        """
        Clear any cached data (for future cache implementation)
        """
        # Placeholder for cache clearing functionality
        pass
    
    def get_stats(self) -> dict:
        """
        Get performance and usage statistics
        
        Returns:
            Dictionary containing stats
        """
        return {
            'search_directories': len(self.search_directories),
            'config': {
                'max_results': self.config.max_results,
                'max_depth': self.config.max_search_depth,
                'recursive_search': self.config.enable_recursive_search,
                'git_ignore': self.config.respect_git_ignore
            }
        }
