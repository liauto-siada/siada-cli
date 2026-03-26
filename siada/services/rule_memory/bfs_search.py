"""
Breadth-First Search for Context Files

Implements BFS-based file discovery for siada_rule.md files.
"""

import os
import logging
from collections import deque
from typing import List, Set, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class BFSFileSearch:
    """Breadth-first search for context files in directory tree"""
    
    # Directories to always ignore
    DEFAULT_IGNORE_DIRS = {
        '.git', '.svn', '.hg', '.bzr',
        'node_modules', '__pycache__', '.pytest_cache',
        'venv', 'env', '.env', '.venv',
        'dist', 'build', '.tox', '.mypy_cache',
        '.eggs', '*.egg-info', '.cache'
    }
    
    def __init__(
        self,
        respect_gitignore: bool = True,
        respect_siadaignore: bool = True,
        max_dirs: int = 200,
        debug: bool = False
    ):
        self.respect_gitignore = respect_gitignore
        self.respect_siadaignore = respect_siadaignore
        self.max_dirs = max_dirs
        self.debug = debug
        self._gitignore_patterns = set()
        self._siadaignore_patterns = set()
    
    def _load_ignore_patterns(self, directory: str) -> Set[str]:
        """Load patterns from .gitignore and .siadaignore files"""
        patterns = set()
        
        if self.respect_gitignore:
            gitignore_path = os.path.join(directory, '.gitignore')
            if os.path.exists(gitignore_path):
                try:
                    with open(gitignore_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#'):
                                patterns.add(line)
                except Exception as e:
                    logger.debug(f"Failed to load .gitignore: {e}")
        
        if self.respect_siadaignore:
            siadaignore_path = os.path.join(directory, '.siadaignore')
            if os.path.exists(siadaignore_path):
                try:
                    with open(siadaignore_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#'):
                                patterns.add(line)
                except Exception as e:
                    logger.debug(f"Failed to load .siadaignore: {e}")
        
        return patterns
    
    def _should_ignore_dir(self, dir_name: str, dir_path: str, root_dir: str) -> bool:
        """Check if directory should be ignored"""
        # Always ignore default directories
        if dir_name in self.DEFAULT_IGNORE_DIRS:
            return True
        
        # Check ignore patterns
        ignore_patterns = self._load_ignore_patterns(root_dir)
        for pattern in ignore_patterns:
            # Simple pattern matching (can be enhanced with fnmatch)
            if pattern.endswith('/'):
                if dir_name == pattern.rstrip('/'):
                    return True
            elif pattern == dir_name:
                return True
            elif pattern.startswith('*') and dir_name.endswith(pattern[1:]):
                return True
        
        return False
    
    def search(
        self,
        start_dir: str,
        file_name: str,
        additional_ignore: Optional[Set[str]] = None
    ) -> List[str]:
        """
        Search for files using breadth-first search
        
        Args:
            start_dir: Starting directory for search
            file_name: Name of file to search for
            additional_ignore: Additional directory names to ignore
            
        Returns:
            List of absolute file paths found
        """
        if not os.path.isdir(start_dir):
            return []
        
        found_files = []
        visited_dirs = set()
        queue = deque([start_dir])
        dirs_searched = 0
        
        ignore_dirs = self.DEFAULT_IGNORE_DIRS.copy()
        if additional_ignore:
            ignore_dirs.update(additional_ignore)
        
            logger.debug(f"[BFS] Starting search from: {start_dir}")
        logger.debug(f"[BFS] Looking for: {file_name}")
        logger.debug(f"[BFS] Max dirs: {self.max_dirs}")
        
        while queue and dirs_searched < self.max_dirs:
            current_dir = queue.popleft()
            
            # Skip if already visited
            if current_dir in visited_dirs:
                continue
            
            visited_dirs.add(current_dir)
            dirs_searched += 1
            
            try:
                # Check if target file exists in current directory
                target_file = os.path.join(current_dir, file_name)
                if os.path.isfile(target_file):
                    found_files.append(target_file)
                    logger.debug(f"[BFS] Found: {target_file}")
                
                # Add subdirectories to queue
                try:
                    entries = os.listdir(current_dir)
                except PermissionError:
                    logger.debug(f"[BFS] Permission denied: {current_dir}")
                    continue
                
                for entry in entries:
                    entry_path = os.path.join(current_dir, entry)
                    
                    if os.path.isdir(entry_path) and not os.path.islink(entry_path):
                        # Check if should ignore
                        if self._should_ignore_dir(entry, entry_path, start_dir):
                            logger.debug(f"[BFS] Ignoring: {entry_path}")
                            continue
                        
                        if entry_path not in visited_dirs:
                            queue.append(entry_path)
            
            except Exception as e:
                logger.debug(f"[BFS] Error processing {current_dir}: {e}")
                continue
        
        logger.debug(f"[BFS] Search complete. Dirs searched: {dirs_searched}, Files found: {len(found_files)}")
        
        return found_files
    
    def search_multiple_names(
        self,
        start_dir: str,
        file_names: List[str],
        additional_ignore: Optional[Set[str]] = None
    ) -> List[str]:
        """
        Search for multiple file names using single BFS pass
        
        Args:
            start_dir: Starting directory for search
            file_names: List of file names to search for
            additional_ignore: Additional directory names to ignore
            
        Returns:
            List of absolute file paths found
        """
        if not os.path.isdir(start_dir):
            return []
        
        found_files = []
        visited_dirs = set()
        queue = deque([start_dir])
        dirs_searched = 0
        file_names_set = set(file_names)
        
        ignore_dirs = self.DEFAULT_IGNORE_DIRS.copy()
        if additional_ignore:
            ignore_dirs.update(additional_ignore)
        
            logger.debug(f"[BFS] Starting multi-name search from: {start_dir}")
            logger.debug(f"[BFS] Looking for: {file_names}")
        
        while queue and dirs_searched < self.max_dirs:
            current_dir = queue.popleft()
            
            if current_dir in visited_dirs:
                continue
            
            visited_dirs.add(current_dir)
            dirs_searched += 1
            
            try:
                # Check for all target files in current directory
                for file_name in file_names_set:
                    target_file = os.path.join(current_dir, file_name)
                    if os.path.isfile(target_file):
                        found_files.append(target_file)
                        logger.debug(f"[BFS] Found: {target_file}")
                
                # Add subdirectories to queue
                try:
                    entries = os.listdir(current_dir)
                except PermissionError:
                    logger.debug(f"[BFS] Permission denied: {current_dir}")
                    continue
                
                for entry in entries:
                    entry_path = os.path.join(current_dir, entry)
                    
                    if os.path.isdir(entry_path) and not os.path.islink(entry_path):
                        if self._should_ignore_dir(entry, entry_path, start_dir):
                            logger.debug(f"[BFS] Ignoring: {entry_path}")
                            continue
                        
                        if entry_path not in visited_dirs:
                            queue.append(entry_path)
            
            except Exception as e:
                logger.debug(f"[BFS] Error processing {current_dir}: {e}")
                continue
        
        logger.debug(f"[BFS] Multi-name search complete. Files found: {len(found_files)}")
        
        return found_files
