"""
Import Processor for Context Files

Handles @ import statements in context files with two formats: tree and flat.
"""

import os
import re
import logging
from typing import List, Set, Tuple, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class ImportProcessor:
    """Process @ import statements in context files"""
    
    MAX_IMPORT_DEPTH = 5
    
    def __init__(
        self,
        format_type: str = "tree",
        allowed_directories: Optional[List[str]] = None,
        debug: bool = False
    ):
        """
        Initialize import processor
        
        Args:
            format_type: "tree" (nested) or "flat" (linear)
            allowed_directories: List of allowed base directories for imports
            debug: Enable debug output
        """
        self.format_type = format_type
        self.allowed_directories = allowed_directories or []
        self.debug = debug
        self.processed_files: Set[str] = set()
    
    def _validate_import_path(self, import_path: str, base_path: str) -> bool:
        """
        Validate that import path is safe and within allowed directories
        
        Args:
            import_path: Path from @ import statement
            base_path: Base directory of the importing file
            
        Returns:
            True if path is valid and safe
        """
        # Reject URL imports
        if re.match(r'^(file|https?|ftp)://', import_path):
            logger.debug(f"[Import] Rejected URL import: {import_path}")
            return False
        
        # Resolve to absolute path
        if os.path.isabs(import_path):
            resolved_path = os.path.normpath(import_path)
        else:
            resolved_path = os.path.normpath(os.path.join(base_path, import_path))
        
        # Check if file exists
        if not os.path.isfile(resolved_path):
            logger.debug(f"[Import] File not found: {resolved_path}")
            return False
        
        # If allowed directories specified, check if path is within them
        if self.allowed_directories:
            path_is_allowed = False
            for allowed_dir in self.allowed_directories:
                try:
                    # Check if resolved path is relative to allowed directory
                    Path(resolved_path).relative_to(Path(allowed_dir))
                    path_is_allowed = True
                    break
                except ValueError:
                    continue
            
            if not path_is_allowed:
                logger.debug(f"[Import] Path outside allowed directories: {resolved_path}")
                return False
        
        return True
    
    def _extract_imports(self, content: str) -> List[str]:
        """
        Extract @ import paths from content, ignoring those in code blocks
        
        Args:
            content: File content to search
            
        Returns:
            List of import paths found
        """
        imports = []
        
        # Simple regex to find @ imports (at start of line or after whitespace)
        # This is a simplified version - Gemini uses marked parser for proper detection
        pattern = r'^\s*@(.+)$'
        
        lines = content.split('\n')
        in_code_block = False
        
        for line in lines:
            # Track code blocks
            if line.strip().startswith('```'):
                in_code_block = not in_code_block
                continue
            
            # Skip lines in code blocks
            if in_code_block:
                continue
            
            # Skip inline code (simple check)
            if '`' in line:
                # Very basic check - just skip lines with backticks
                # A full implementation would parse properly
                continue
            
            # Check for import
            match = re.match(pattern, line)
            if match:
                import_path = match.group(1).strip()
                imports.append(import_path)
        
        return imports
    
    def _process_tree_format(
        self,
        file_path: str,
        depth: int = 0,
        processed: Optional[Set[str]] = None
    ) -> str:
        """
        Process file with tree (nested) format
        
        Args:
            file_path: Path to file to process
            depth: Current import depth
            processed: Set of already processed files
            
        Returns:
            Processed content with imports inlined
        """
        if processed is None:
            processed = set()
        
        # Prevent circular imports and depth limit
        normalized_path = os.path.normpath(os.path.abspath(file_path))
        if normalized_path in processed:
            logger.debug(f"[Import] Circular import detected: {file_path}")
            return f"<!-- Circular import detected: {file_path} -->\n"
        
        if depth > self.MAX_IMPORT_DEPTH:
            logger.debug(f"[Import] Max depth reached at: {file_path}")
            return f"<!-- Max import depth reached: {file_path} -->\n"
        
        processed.add(normalized_path)
        
        # Read file content
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            logger.debug(f"[Import] Failed to read {file_path}: {e}")
            return f"<!-- Failed to read: {file_path} -->\n"
        
        # Extract imports
        imports = self._extract_imports(content)
        
        if not imports:
            return content
        
        # Process each import
        base_dir = os.path.dirname(file_path)
        result = []
        
        for line in content.split('\n'):
            # Check if this line is an import
            match = re.match(r'^\s*@(.+)$', line)
            if match:
                import_path = match.group(1).strip()
                
                # Resolve import path
                if os.path.isabs(import_path):
                    resolved_path = import_path
                else:
                    resolved_path = os.path.join(base_dir, import_path)
                
                # Validate path
                if not self._validate_import_path(import_path, base_dir):
                    result.append(f"<!-- Invalid import: {import_path} -->")
                    continue
                
                # Process imported file recursively
                logger.debug(f"[Import] {'  ' * depth}Importing: {resolved_path}")
                
                result.append(f"<!-- Imported from: {resolved_path} -->")
                imported_content = self._process_tree_format(
                    resolved_path,
                    depth + 1,
                    processed.copy()
                )
                result.append(imported_content)
                result.append(f"<!-- End of import from: {resolved_path} -->")
            else:
                result.append(line)
        
        return '\n'.join(result)
    
    def _process_flat_format(
        self,
        file_path: str,
        collected_files: Optional[List[Tuple[str, str]]] = None,
        processed: Optional[Set[str]] = None
    ) -> List[Tuple[str, str]]:
        """
        Process file with flat (linear) format using BFS
        
        Args:
            file_path: Path to file to process
            collected_files: List of (path, content) tuples
            processed: Set of already processed files
            
        Returns:
            List of (file_path, content) tuples in BFS order
        """
        if collected_files is None:
            collected_files = []
        
        if processed is None:
            processed = set()
        
        # Prevent circular imports
        normalized_path = os.path.normpath(os.path.abspath(file_path))
        if normalized_path in processed:
            return collected_files
        
        processed.add(normalized_path)
        
        # Read file content
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            logger.debug(f"[Import] Failed to read {file_path}: {e}")
            return collected_files
        
        # Add current file
        collected_files.append((normalized_path, content))
        
        # Extract imports
        imports = self._extract_imports(content)
        base_dir = os.path.dirname(file_path)
        
        # Process imports (BFS - add to queue)
        for import_path in imports:
            # Resolve import path
            if os.path.isabs(import_path):
                resolved_path = import_path
            else:
                resolved_path = os.path.join(base_dir, import_path)
            
            # Validate and process
            if self._validate_import_path(import_path, base_dir):
                logger.debug(f"[Import] Collecting: {resolved_path}")
                self._process_flat_format(resolved_path, collected_files, processed)
        
        return collected_files
    
    def process_file(self, file_path: str) -> str:
        """
        Process a file and return content with imports resolved
        
        Args:
            file_path: Path to file to process
            
        Returns:
            Processed content string
        """
        if self.format_type == "tree":
            return self._process_tree_format(file_path)
        else:  # flat
            files = self._process_flat_format(file_path)
            
            # Concatenate all files with markers
            result = []
            for path, content in files:
                result.append(f"--- File: {path} ---")
                result.append(content)
                result.append(f"--- End of File: {path} ---")
                result.append("")  # Empty line between files
            
            return '\n'.join(result)
    
    def process_multiple_files(self, file_paths: List[str]) -> str:
        """
        Process multiple root files and combine their content
        
        Args:
            file_paths: List of file paths to process
            
        Returns:
            Combined processed content
        """
        results = []
        
        for file_path in file_paths:
            logger.debug(f"[Import] Processing root file: {file_path}")
            
            # Reset processed files for each root file in tree mode
            if self.format_type == "tree":
                self.processed_files = set()
            
            processed_content = self.process_file(file_path)
            results.append(processed_content)
        
        return '\n\n'.join(results)
