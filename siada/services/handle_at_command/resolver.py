"""
Path Resolver - Resolves @ command paths to actual file paths.
"""

import os
import glob
from pathlib import Path
from typing import List, Optional, Tuple

from .models import ResolverContext, PathResolutionResult
from .exceptions import (
    PathNotFoundError, 
    WorkspaceSecurityError, 
    PathIgnoredError,
    InvalidPathError
)


class PathResolver:
    """Resolves @ command paths to actual file paths"""
    
    def __init__(self, context: ResolverContext):
        self.context = context
        self.target_dir = Path(context.target_directory).resolve()
    
    async def resolve_path(self, at_path: str, on_debug_message: callable = None) -> PathResolutionResult:
        """
        Resolve an @ path to an actual file path
        
        Args:
            at_path: @ path string (e.g., "@file.py", "@directory/")
            on_debug_message: Optional debug message callback
            
        Returns:
            PathResolutionResult with resolution details
        """
        if not on_debug_message:
            on_debug_message = lambda msg: None
        
        # Handle lone '@' symbol
        if at_path == '@':
            on_debug_message('Lone @ detected, treating as text')
            return PathResolutionResult(
                resolved_path=None,
                original_path=at_path,
                resolution_type='not_found',
                reason='Lone @ symbol treated as text'
            )
        
        # Extract path without '@' prefix
        if not at_path.startswith('@'):
            raise InvalidPathError(f"Invalid @ path format: {at_path}")
        
        path_name = at_path[1:]  # Remove '@' prefix
        
        if not path_name:
            return PathResolutionResult(
                resolved_path=None,
                original_path=at_path,
                resolution_type='not_found',
                reason='Empty path after @'
            )
        
        # Security validation
        if not self._is_path_safe(path_name):
            raise WorkspaceSecurityError(f"Path contains unsafe elements: {path_name}")
        
        # Try to resolve path in each workspace directory
        for workspace_dir in self.context.workspace_directories:
            result = await self._try_resolve_in_workspace(path_name, workspace_dir, on_debug_message)
            if result.resolved_path:
                return result
        
        # If not found, return not_found result
        on_debug_message(f'Path {path_name} not found in any workspace directory')
        return PathResolutionResult(
            resolved_path=None,
            original_path=at_path,
            resolution_type='not_found',
            reason=f'Path not found in workspace directories: {self.context.workspace_directories}'
        )
    
    async def _try_resolve_in_workspace(self, path_name: str, workspace_dir: str, 
                                      on_debug_message: callable) -> PathResolutionResult:
        """
        Try to resolve path within a specific workspace directory
        
        Args:
            path_name: Path name without '@' prefix
            workspace_dir: Workspace directory to search in
            on_debug_message: Debug message callback
            
        Returns:
            PathResolutionResult
        """
        workspace_path = Path(workspace_dir).resolve()
        
        # Check if workspace directory is within target directory
        if not self._is_workspace_within_target(workspace_path):
            on_debug_message(f'Workspace {workspace_dir} is not within target directory {self.target_dir}')
            return PathResolutionResult(
                resolved_path=None,
                original_path=f"@{path_name}",
                resolution_type='not_found',
                reason='Workspace not within target directory'
            )
        
        # Try direct path resolution
        direct_result = self._try_direct_resolution(path_name, workspace_path, on_debug_message)
        if direct_result.resolved_path:
            return direct_result
        
        # Try glob search if enabled
        if self.context.enable_recursive_search:
            glob_result = await self._try_glob_search(path_name, workspace_path, on_debug_message)
            if glob_result.resolved_path:
                return glob_result
        
        return PathResolutionResult(
            resolved_path=None,
            original_path=f"@{path_name}",
            resolution_type='not_found',
            reason=f'Not found in workspace: {workspace_dir}'
        )
    
    def _try_direct_resolution(self, path_name: str, workspace_path: Path, 
                             on_debug_message: callable) -> PathResolutionResult:
        """
        Try direct path resolution (exact match)
        
        Args:
            path_name: Path name to resolve
            workspace_path: Workspace directory path
            on_debug_message: Debug message callback
            
        Returns:
            PathResolutionResult
        """
        try:
            absolute_path = workspace_path / path_name
            resolved_path = absolute_path.resolve()
            
            # Security check - ensure resolved path is within workspace
            if not self._is_path_within_workspace(resolved_path, workspace_path):
                raise WorkspaceSecurityError(f"Resolved path is outside workspace: {resolved_path}")
            
            if resolved_path.exists():
                if resolved_path.is_dir():
                    # Directory - convert to glob pattern
                    glob_pattern = path_name + ('**' if path_name.endswith('/') else '/**')
                    on_debug_message(f'Path {path_name} resolved to directory, using glob: {glob_pattern}')
                    return PathResolutionResult(
                        resolved_path=glob_pattern,
                        original_path=f"@{path_name}",
                        resolution_type='directory',
                        reason=f'Directory converted to glob pattern: {glob_pattern}'
                    )
                else:
                    # File - return relative path
                    relative_path = os.path.relpath(str(resolved_path), str(workspace_path))
                    on_debug_message(f'Path {path_name} resolved to file: {resolved_path}')
                    return PathResolutionResult(
                        resolved_path=relative_path,
                        original_path=f"@{path_name}",
                        resolution_type='direct',
                        reason=f'Direct file match: {resolved_path}'
                    )
        
        except (OSError, ValueError) as e:
            on_debug_message(f'Error resolving path {path_name}: {e}')
        
        return PathResolutionResult(
            resolved_path=None,
            original_path=f"@{path_name}",
            resolution_type='not_found',
            reason='Direct resolution failed'
        )
    
    async def _try_glob_search(self, path_name: str, workspace_path: Path, 
                             on_debug_message: callable) -> PathResolutionResult:
        """
        Try glob search for fuzzy matching
        
        Args:
            path_name: Path name to search for
            workspace_path: Workspace directory path
            on_debug_message: Debug message callback
            
        Returns:
            PathResolutionResult
        """
        on_debug_message(f'Path {path_name} not found directly, attempting glob search')
        
        try:
            # Create glob pattern for fuzzy search
            glob_pattern = f"**/*{path_name}*"
            search_path = workspace_path / glob_pattern
            
            # Use glob to find matching files
            matches = list(workspace_path.glob(glob_pattern))
            
            if matches:
                # Take the first match
                first_match = matches[0].resolve()
                
                # Security check
                if not self._is_path_within_workspace(first_match, workspace_path):
                    raise WorkspaceSecurityError(f"Glob match is outside workspace: {first_match}")
                
                relative_path = os.path.relpath(str(first_match), str(workspace_path))
                on_debug_message(f'Glob search for {path_name} found {first_match}, using relative path: {relative_path}')
                
                return PathResolutionResult(
                    resolved_path=relative_path,
                    original_path=f"@{path_name}",
                    resolution_type='glob',
                    reason=f'Glob search found: {first_match} (first of {len(matches)} matches)'
                )
            else:
                on_debug_message(f'Glob search for "**/*{path_name}*" found no files')
                
        except Exception as e:
            on_debug_message(f'Error during glob search for {path_name}: {e}')
        
        return PathResolutionResult(
            resolved_path=None,
            original_path=f"@{path_name}",
            resolution_type='not_found',
            reason='Glob search found no matches'
        )
    
    def _is_path_safe(self, path_name: str) -> bool:
        """
        Check if path is safe (no path traversal attempts)
        
        Args:
            path_name: Path to check
            
        Returns:
            True if path is safe, False otherwise
        """
        # Check for path traversal patterns
        dangerous_patterns = ['../', '..\\', '../', '..\\']
        for pattern in dangerous_patterns:
            if pattern in path_name:
                return False
        
        # Check for absolute paths
        if os.path.isabs(path_name):
            return False
        
        # Check for null bytes
        if '\x00' in path_name:
            return False
        
        return True
    
    def _is_workspace_within_target(self, workspace_path: Path) -> bool:
        """
        Check if workspace directory is within target directory
        
        Args:
            workspace_path: Workspace directory path
            
        Returns:
            True if workspace is within target, False otherwise
        """
        try:
            workspace_path.relative_to(self.target_dir)
            return True
        except ValueError:
            return False
    
    def _is_path_within_workspace(self, file_path: Path, workspace_path: Path) -> bool:
        """
        Check if file path is within workspace directory
        
        Args:
            file_path: File path to check
            workspace_path: Workspace directory path
            
        Returns:
            True if file is within workspace, False otherwise
        """
        try:
            file_path.relative_to(workspace_path)
            return True
        except ValueError:
            return False
    
    def should_ignore_file(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        Check if file should be ignored based on filtering options
        
        Args:
            file_path: File path to check
            
        Returns:
            Tuple of (should_ignore, reason)
        """
        # This is a simplified implementation
        # In a full implementation, this would integrate with .gitignore parsing
        # For now, we'll use basic patterns
        
        ignore_patterns = [
            '__pycache__',
            '.git',
            '.vscode',
            '.idea',
            'node_modules',
            '.env'
        ]
        
        for pattern in ignore_patterns:
            if pattern in file_path:
                return True, f"Matches ignore pattern: {pattern}"
        
        return False, None
