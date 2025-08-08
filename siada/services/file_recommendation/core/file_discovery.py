"""
File discovery and filtering service.
"""

import os
import glob
import fnmatch
from pathlib import Path
from typing import List, Optional, Tuple

from .config import FilterOptions
from .suggestion import Suggestion, create_suggestion
from ..utils.path_utils import escape_path, is_hidden_file, normalize_path_separators


class GitIgnoreParser:
    """Simple .gitignore parser"""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root).resolve()
        self.patterns = []
        
    def load_git_repo_patterns(self):
        """Load patterns from .gitignore file"""
        gitignore_path = self.project_root / '.gitignore'
        if gitignore_path.exists():
            self.load_patterns_from_file(gitignore_path)
    
    def load_patterns_from_file(self, file_path: Path):
        """Load patterns from a specific file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        self.patterns.append(line)
        except (IOError, UnicodeDecodeError):
            pass  # Ignore errors
    
    def is_ignored(self, file_path: str) -> bool:
        """Check if file path is ignored"""
        normalized_path = normalize_path_separators(file_path)
        
        for pattern in self.patterns:
            if self._match_pattern(normalized_path, pattern):
                return True
        
        return False
    
    def _match_pattern(self, file_path: str, pattern: str) -> bool:
        """Check if file path matches gitignore pattern"""
        # Simple pattern matching - this could be enhanced
        if pattern.endswith('/'):
            # Directory pattern
            pattern = pattern.rstrip('/')
            return fnmatch.fnmatch(file_path, pattern) or fnmatch.fnmatch(os.path.dirname(file_path), pattern)
        else:
            # File pattern
            return fnmatch.fnmatch(file_path, pattern) or fnmatch.fnmatch(os.path.basename(file_path), pattern)


class FileDiscoveryService:
    """File discovery and filtering service"""
    
    def __init__(self, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.git_ignore_filter = None
        
        # Initialize Git ignore filter
        if self._is_git_repository(self.project_root):
            self.git_ignore_filter = GitIgnoreParser(self.project_root)
            try:
                self.git_ignore_filter.load_git_repo_patterns()
            except Exception:
                pass  # Ignore errors
    
    def _is_git_repository(self, path: str) -> bool:
        """Check if directory is a git repository"""
        git_dir = os.path.join(path, '.git')
        return os.path.exists(git_dir)
    
    def should_ignore_file(self, file_path: str, filter_options: FilterOptions) -> bool:
        """
        Check if file should be ignored
        
        Args:
            file_path: File path to check
            filter_options: Filter options
        
        Returns:
            bool: True if should ignore
        """
        if filter_options.respect_git_ignore and self._should_git_ignore_file(file_path):
            return True
        
        return False
    
    def _should_git_ignore_file(self, file_path: str) -> bool:
        """Check if file is ignored by git"""
        if self.git_ignore_filter:
            return self.git_ignore_filter.is_ignored(file_path)
        return False
    
    async def find_files_recursively(
        self,
        start_dir: str,
        search_prefix: str,
        filter_options: FilterOptions,
        current_relative_path: str = "",
        depth: int = 0,
        max_depth: int = 10,
        max_results: int = 50
    ) -> List[Suggestion]:
        """
        Recursively search for files and directories
        
        Args:
            start_dir: Starting search directory
            search_prefix: Search prefix
            filter_options: Filter options
            current_relative_path: Current relative path
            depth: Current recursion depth
            max_depth: Maximum recursion depth
            max_results: Maximum number of results
        
        Returns:
            List[Suggestion]: Suggestion list
        """
        if depth > max_depth:
            return []
        
        lower_search_prefix = search_prefix.lower()
        found_suggestions = []
        
        try:
            entries = os.listdir(start_dir)
            
            for entry in entries:
                if len(found_suggestions) >= max_results:
                    break
                
                entry_path_relative = os.path.join(current_relative_path, entry) if current_relative_path else entry
                entry_path_from_root = os.path.relpath(
                    os.path.join(start_dir, entry), 
                    self.project_root
                )
                
                # Skip hidden files unless search prefix starts with .
                if not search_prefix.startswith('.') and entry.startswith('.'):
                    continue
                
                # Check file filtering rules
                if self.should_ignore_file(entry_path_from_root, filter_options):
                    continue
                
                # Enhanced matching: prefix match OR fuzzy match
                entry_matches = False
                
                # Check prefix matching (original logic)
                if entry.lower().startswith(lower_search_prefix):
                    entry_matches = True
                
                # Check fuzzy matching (contains match)
                elif self._is_fuzzy_match(entry_path_from_root, search_prefix):
                    entry_matches = True
                
                if entry_matches:
                    full_entry_path = os.path.join(start_dir, entry)
                    is_dir = os.path.isdir(full_entry_path)
                    suffix = '/' if is_dir else ''
                    
                    # Use full path from project root for suggestion
                    suggestion = create_suggestion(
                        label=entry_path_from_root + suffix,
                        value=escape_path(entry_path_from_root + suffix)
                    )
                    found_suggestions.append(suggestion)
                
                # Recursively search subdirectories
                full_entry_path = os.path.join(start_dir, entry)
                if (os.path.isdir(full_entry_path) and 
                    entry != 'node_modules' and 
                    not entry.startswith('.') and
                    len(found_suggestions) < max_results):
                    
                    sub_suggestions = await self.find_files_recursively(
                        full_entry_path,
                        search_prefix,
                        filter_options,
                        entry_path_relative,
                        depth + 1,
                        max_depth,
                        max_results - len(found_suggestions)
                    )
                    found_suggestions.extend(sub_suggestions)
        
        except (OSError, PermissionError):
            # Ignore permission errors and other OS errors
            pass
        
        return found_suggestions[:max_results]
    
    async def find_files_with_glob(
        self,
        search_prefix: str,
        filter_options: FilterOptions,
        search_dir: str,
        max_results: int = 50
    ) -> List[Suggestion]:
        """
        Use glob pattern to search files
        
        Args:
            search_prefix: Search prefix
            filter_options: Filter options
            search_dir: Search directory
            max_results: Maximum number of results
        
        Returns:
            List[Suggestion]: Suggestion list
        """
        glob_pattern = f"**/{search_prefix}*"
        
        try:
            search_path = os.path.join(search_dir, glob_pattern)
            files = glob.glob(search_path, recursive=True)
            
            suggestions = []
            for file in files[:max_results]:
                if self.should_ignore_file(file, filter_options):
                    continue
                
                absolute_path = os.path.abspath(file)
                label = os.path.relpath(absolute_path, search_dir)
                
                # Add directory suffix
                if os.path.isdir(absolute_path):
                    label += '/'
                
                suggestion = create_suggestion(
                    label=label,
                    value=escape_path(label)
                )
                suggestions.append(suggestion)
            
            return suggestions
        
        except Exception:
            # Return empty list on error
            return []
    
    def find_files_in_directory(
        self,
        directory: str,
        search_prefix: str,
        filter_options: FilterOptions,
        max_results: int = 50
    ) -> List[Suggestion]:
        """
        Find files in a specific directory (non-recursive)
        
        Args:
            directory: Directory to search
            search_prefix: Search prefix
            filter_options: Filter options
            max_results: Maximum number of results
        
        Returns:
            List[Suggestion]: Suggestion list
        """
        suggestions = []
        
        try:
            if not os.path.exists(directory) or not os.path.isdir(directory):
                return suggestions
            
            lower_search_prefix = search_prefix.lower()
            entries = os.listdir(directory)
            
            for entry in entries:
                if len(suggestions) >= max_results:
                    break
                
                # Skip hidden files unless search prefix starts with .
                if not search_prefix.startswith('.') and entry.startswith('.'):
                    continue
                
                # Check file filtering rules
                entry_path = os.path.relpath(os.path.join(directory, entry), self.project_root)
                if self.should_ignore_file(entry_path, filter_options):
                    continue
                
                # Check name matching
                if entry.lower().startswith(lower_search_prefix):
                    full_path = os.path.join(directory, entry)
                    is_dir = os.path.isdir(full_path)
                    suffix = '/' if is_dir else ''
                    
                    suggestion = create_suggestion(
                        label=entry + suffix,
                        value=escape_path(entry + suffix)
                    )
                    suggestions.append(suggestion)
        
        except (OSError, PermissionError):
            # Ignore errors
            pass
        
        return suggestions
    
    def _is_fuzzy_match(self, file_path: str, search_term: str) -> bool:
        """
        Check if file path fuzzy matches the search term
        
        Args:
            file_path: File path to check
            search_term: Search term
            
        Returns:
            bool: True if it's a fuzzy match
        """
        if not search_term:
            return False
        
        search_term_lower = search_term.lower()
        file_path_lower = file_path.lower()
        
        # Check if search term is contained in file name (not full path for better UX)
        file_name = os.path.basename(file_path_lower)
        if search_term_lower in file_name:
            return True
        
        # Check if search term is contained in full path
        if search_term_lower in file_path_lower:
            return True
        
        return False
    
    def get_default_ignore_patterns(self) -> List[str]:
        """Get default ignore patterns"""
        return [
            '__pycache__',
            '.git',
            '.vscode',
            '.idea',
            'node_modules',
            '.env',
            '*.pyc',
            '*.pyo',
            '*.log',
            '.DS_Store',
            'Thumbs.db'
        ]
