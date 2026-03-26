"""
Context File Discovery

Implements 3-tier hierarchical discovery: global, project root, subdirectories.
"""

import os
import asyncio
import logging
from typing import List, Tuple, Optional, Set
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import get_rule_config
from .bfs_search import BFSFileSearch
from .import_processor import ImportProcessor

logger = logging.getLogger(__name__)


class ContextDiscovery:
    """Discover and load context files from hierarchical locations"""
    
    # Concurrency limits
    FILE_READ_CONCURRENCY = 20
    DIR_SEARCH_CONCURRENCY = 10
    
    def __init__(self, workspace: str, debug: bool = False):
        """
        Initialize context discovery
        
        Args:
            workspace: Current working directory
            debug: Enable debug output
        """
        self.workspace = os.path.abspath(workspace)
        self.debug = debug
        self.config = get_rule_config()
    
    def _find_project_root(self) -> Optional[str]:
        """
        Find project root by looking for .git directory
        
        Returns:
            Absolute path to project root, or None if not found
        """
        current = self.workspace
        
        while True:
            git_dir = os.path.join(current, '.git')
            if os.path.isdir(git_dir):
                logger.debug(f"[Discovery] Found project root: {current}")
                return current
            
            parent = os.path.dirname(current)
            if parent == current:  # Reached filesystem root
                break
            current = parent
        
            logger.debug("[Discovery] No project root found (no .git directory)")
        return None
    
    def _find_global_files(self) -> List[str]:
        """
        Find global context files in ~/.siada-cli/
        
        Returns:
            List of absolute paths to global context files
        """
        files = []
        file_names = self.config.get_file_names()
        
        for file_name in file_names:
            global_path = os.path.join(self.config.config_dir, file_name)
            if os.path.isfile(global_path):
                files.append(global_path)
                logger.debug(f"[Discovery] Found global file: {global_path}")
        
        return files
    
    def _find_project_root_files(self, project_root: str) -> List[str]:
        """
        Find context files in project root directory
        
        Args:
            project_root: Path to project root
            
        Returns:
            List of absolute paths to context files in project root
        """
        files = []
        file_names = self.config.get_file_names()
        
        for file_name in file_names:
            root_file = os.path.join(project_root, file_name)
            if os.path.isfile(root_file):
                files.append(root_file)
                logger.debug(f"[Discovery] Found project root file: {root_file}")
        
        return files
    
    def _find_subdirectory_files(self) -> List[str]:
        """
        Find context files in subdirectories using BFS
        
        Returns:
            List of absolute paths to context files in subdirectories
        """
        file_names = self.config.get_file_names()
        max_dirs = self.config.get_max_dirs()
        respect_gitignore = self.config.get_respect_gitignore()
        respect_siadaignore = self.config.get_respect_siadaignore()
        
        searcher = BFSFileSearch(
            respect_gitignore=respect_gitignore,
            respect_siadaignore=respect_siadaignore,
            max_dirs=max_dirs,
            debug=self.debug
        )
        
        logger.debug(f"[Discovery] Searching subdirectories from: {self.workspace}")
        
        # Search for all file names in one pass
        found_files = searcher.search_multiple_names(
            self.workspace,
            file_names
        )
        
        logger.debug(f"[Discovery] Found {len(found_files)} files in subdirectories")
        
        return found_files
    
    def discover_all_files(self) -> Tuple[List[str], List[str], List[str]]:
        """
        Discover all context files in hierarchical order
        
        Returns:
            Tuple of (global_files, project_root_files, subdirectory_files)
        """
        logger.debug("[Discovery] Starting hierarchical file discovery...")
        
        # Tier 1: Global files
        global_files = self._find_global_files()
        
        # Tier 2: Project root files
        project_root = self._find_project_root()
        project_root_files = []
        if project_root:
            project_root_files = self._find_project_root_files(project_root)
        
        # Tier 3: Subdirectory files (only if enabled)
        subdirectory_files = []
        if self.config.get_enable_subdirectories():
            subdirectory_files = self._find_subdirectory_files()
            logger.debug("[Discovery] Subdirectory discovery enabled")
        else:
            logger.debug("[Discovery] Subdirectory discovery disabled")
        
        total = len(global_files) + len(project_root_files) + len(subdirectory_files)
        logger.debug(f"[Discovery] Total files found: {total}")
        logger.debug(f"  - Global: {len(global_files)}")
        logger.debug(f"  - Project root: {len(project_root_files)}")
        logger.debug(f"  - Subdirectories: {len(subdirectory_files)}")
        
        return global_files, project_root_files, subdirectory_files
    
    def _read_file_content(self, file_path: str) -> Tuple[str, str]:
        """
        Read content from a single file
        
        Args:
            file_path: Path to file to read
            
        Returns:
            Tuple of (file_path, content)
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
                logger.debug(f"[Discovery] Read {len(content)} bytes from: {file_path}")
            
            return file_path, content
        except Exception as e:
            logger.debug(f"[Discovery] Failed to read {file_path}: {e}")
            return file_path, ""
    
    def _read_files_concurrent(self, file_paths: List[str]) -> List[Tuple[str, str]]:
        """
        Read multiple files concurrently with batching
        
        Args:
            file_paths: List of file paths to read
            
        Returns:
            List of (file_path, content) tuples
        """
        results = []
        
        # Process in batches to control concurrency
        batch_size = self.FILE_READ_CONCURRENCY
        for i in range(0, len(file_paths), batch_size):
            batch = file_paths[i:i + batch_size]
            
            with ThreadPoolExecutor(max_workers=self.FILE_READ_CONCURRENCY) as executor:
                futures = {executor.submit(self._read_file_content, fp): fp for fp in batch}
                
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        file_path = futures[future]
                        logger.debug(f"[Discovery] Error reading {file_path}: {e}")
                        results.append((file_path, ""))
        
        return results
    
    def load_and_process_files(
        self,
        process_imports: bool = True
    ) -> Tuple[str, int, List[str]]:
        """
        Discover, load, and process all context files
        
        Args:
            process_imports: Whether to process @ import statements
            
        Returns:
            Tuple of (combined_content, file_count, file_paths)
        """
        # Discover files
        global_files, root_files, subdir_files = self.discover_all_files()
        
        # Combine in hierarchical order
        all_files = global_files + root_files + subdir_files
        all_files_set = set(all_files)
        all_files=list(all_files_set)
        
        if not all_files:
            logger.debug("[Discovery] No context files found")
            return "", 0, []
        
        # Read all files concurrently
        logger.debug(f"[Discovery] Reading {len(all_files)} files...")
        
        file_contents = self._read_files_concurrent(all_files)
        
        # Process imports if enabled
        if process_imports:
            import_format = self.config.get_import_format()
            
            logger.debug(f"[Discovery] Processing imports with format: {import_format}")
            
            # Get allowed directories for import validation
            project_root = self._find_project_root()
            allowed_dirs = [self.config.config_dir, self.workspace]
            if project_root:
                allowed_dirs.append(project_root)
            
            processor = ImportProcessor(
                format_type=import_format,
                allowed_directories=allowed_dirs,
                debug=self.debug
            )
            
            # Process each file through import processor
            processed_contents = []
            processed_paths = []
            
            for file_path, content in file_contents:
                if content:  # Only process non-empty files
                    try:
                        # Process this file's imports
                        processed = processor.process_file(file_path)
                        processed_contents.append((file_path, processed))
                        processed_paths.append(file_path)
                    except Exception as e:
                        logger.debug(f"[Discovery] Error processing imports for {file_path}: {e}")
                        # Fall back to original content
                        processed_contents.append((file_path, content))
                        processed_paths.append(file_path)
        else:
            processed_contents = [(fp, c) for fp, c in file_contents if c]
            processed_paths = [fp for fp, c in file_contents if c]
        
        # Concatenate all content with clear separators
        combined = self._concatenate_contents(processed_contents)
        
        logger.debug(f"[Discovery] Combined content length: {len(combined)} characters")
        
        return combined, len(processed_paths), processed_paths
    
    def _concatenate_contents(self, file_contents: List[Tuple[str, str]]) -> str:
        """
        Concatenate file contents with clear separators
        
        Args:
            file_contents: List of (file_path, content) tuples
            
        Returns:
            Combined content string
        """
        result = []
        
        for file_path, content in file_contents:
            # Create relative path for display
            try:
                rel_path = os.path.relpath(file_path, self.workspace)
            except ValueError:
                # If files are on different drives (Windows), use absolute path
                rel_path = file_path
            
            result.append(f"--- Context from: {rel_path} ---")
            result.append(content.rstrip())
            result.append(f"--- End of Context from: {rel_path} ---")
            result.append("")  # Empty line between files
        
        return '\n'.join(result)


def load_hierarchical_context(
    workspace: str,
    debug: bool = False,
    process_imports: bool = True
) -> Tuple[str, int, List[str]]:
    """
    Main entry point for loading hierarchical context
    
    Args:
        workspace: Current working directory
        debug: Enable debug output
        process_imports: Whether to process @ import statements
        
    Returns:
        Tuple of (combined_content, file_count, file_paths)
    """
    discovery = ContextDiscovery(workspace, debug=debug)
    return discovery.load_and_process_files(process_imports=process_imports)
