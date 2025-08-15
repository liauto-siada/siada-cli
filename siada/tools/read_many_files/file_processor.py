"""
File processing utilities for ReadManyFiles tool.
"""

import os
import glob
import asyncio
import mimetypes
import base64
from pathlib import Path
from typing import List, Set, Dict, Tuple, Optional, Any, Union
import time

from .models import (
    FileProcessResult, 
    ProcessingStats,
    TEXT_FILE_EXTENSIONS,
    IMAGE_FILE_EXTENSIONS,
    PDF_FILE_EXTENSIONS
)
from .filters import FileFilter


class FileProcessor:
    """File processing utility class"""
    
    # Configuration constants
    MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20MB
    MAX_TEXT_LINES = 2000
    MAX_CONTENT_CHARS = 100000
    MAX_CONCURRENT_FILES = 10
    DEFAULT_OUTPUT_SEPARATOR_FORMAT = "--- {filePath} ---"
    
    def __init__(self, target_dir: str):
        self.target_dir = Path(target_dir).resolve()
        self.file_filter = FileFilter(str(self.target_dir))
        self.stats = ProcessingStats()
    
    async def search_files_with_glob(self, search_patterns: List[str], 
                                   exclusion_patterns: List[str],
                                   signal=None) -> Set[str]:
        """
        Search files using glob patterns
        
        Args:
            search_patterns: List of glob search patterns
            exclusion_patterns: List of exclusion patterns
            signal: Cancellation signal (optional)
            
        Returns:
            Set of absolute file paths
        """
        all_entries = set()
        
        # Use target_dir as the single workspace directory
        workspace_dir = str(self.target_dir)
        
        for pattern in search_patterns:
            # Check cancellation signal
            if signal and signal.is_cancelled():
                break
                
            try:
                # Normalize path separators (Windows compatibility)
                normalized_pattern = pattern.replace('\\', '/')
                
                # Build full path pattern
                if os.path.isabs(normalized_pattern):
                    full_pattern = normalized_pattern
                else:
                    full_pattern = os.path.join(workspace_dir, normalized_pattern)
                
                # Execute glob search in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                matches = await loop.run_in_executor(
                    None, 
                    lambda: glob.glob(full_pattern, recursive=True)
                )
                
                # Filter directories, keep only files
                file_matches = [f for f in matches if os.path.isfile(f)]
                
                # Apply exclusion patterns
                for file_path in file_matches:
                    if not self.file_filter.should_exclude_file(
                        file_path, workspace_dir, exclusion_patterns
                    ):
                        all_entries.add(file_path)
                        
            except Exception as error:
                # Log error but continue processing other patterns
                print(f"Glob pattern '{pattern}' failed: {error}")
        
        self.stats.total_files_found = len(all_entries)
        return all_entries
    
    async def process_files(self, file_paths: List[str], 
                          input_patterns: List[str]) -> Tuple[List[Any], List[str], List[Dict]]:
        """
        Process multiple files concurrently
        
        Args:
            file_paths: List of absolute file paths to process
            input_patterns: Original input patterns for explicit request checking
            
        Returns:
            Tuple of (content_parts, processed_files, skipped_files)
        """
        content_parts = []
        processed_files = []
        skipped_files = []
        
        # Sort file paths for consistent output order
        sorted_files = sorted(file_paths)
        
        # Process files concurrently with semaphore to control concurrency
        semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_FILES)
        
        async def process_single_file_wrapper(file_path: str):
            async with semaphore:
                return await self.process_single_file(file_path, input_patterns)
        
        # Create tasks for all files
        tasks = [process_single_file_wrapper(fp) for fp in sorted_files]
        
        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for i, result in enumerate(results):
            file_path = sorted_files[i]
            relative_path = os.path.relpath(file_path, self.target_dir).replace('\\', '/')
            
            if isinstance(result, Exception):
                skipped_files.append({
                    'path': relative_path,
                    'reason': f'Processing error: {str(result)}'
                })
                self.stats.error_files += 1
            elif result.success:
                content_parts.append(result.content)
                processed_files.append(relative_path)
                self.stats.processed_files += 1
                
                # Update file type statistics
                if result.file_type == 'text':
                    self.stats.text_files += 1
                elif result.file_type == 'image':
                    self.stats.image_files += 1
                elif result.file_type == 'pdf':
                    self.stats.pdf_files += 1
                else:
                    self.stats.binary_files += 1
                    
                if result.size:
                    self.stats.total_size += result.size
            else:
                skipped_files.append({
                    'path': relative_path,
                    'reason': result.reason
                })
                self.stats.skipped_files += 1
        
        return content_parts, processed_files, skipped_files
    
    async def process_single_file(self, file_path: str, 
                                input_patterns: List[str]) -> FileProcessResult:
        """
        Process a single file
        
        Args:
            file_path: Absolute path to the file
            input_patterns: Original input patterns for explicit request checking
            
        Returns:
            FileProcessResult object
        """
        try:
            # Detect file type
            file_type = await self.detect_file_type(file_path)
            
            # Check if resource files are explicitly requested
            if file_type in ['image', 'pdf']:
                if not self.is_explicitly_requested(file_path, input_patterns):
                    return FileProcessResult(
                        success=False,
                        path=file_path,
                        reason=f'{file_type} file was not explicitly requested by name or extension',
                        file_type=file_type
                    )
            
            # Check file size
            file_size = os.path.getsize(file_path)
            if file_size > self.MAX_FILE_SIZE_BYTES:
                return FileProcessResult(
                    success=False,
                    path=file_path,
                    reason=f'File too large ({file_size / 1024 / 1024:.1f}MB > {self.MAX_FILE_SIZE_BYTES / 1024 / 1024}MB)',
                    file_type=file_type,
                    size=file_size
                )
            
            # Read file content
            file_content = await self.read_file_content_by_type(file_path, file_type)
            
            if file_content.get('error'):
                return FileProcessResult(
                    success=False,
                    path=file_path,
                    reason=f"Read error: {file_content['error']}",
                    file_type=file_type,
                    size=file_size
                )
            
            # Format content
            formatted_content = self.format_file_content(file_path, file_content['content'])
            
            return FileProcessResult(
                success=True,
                path=file_path,
                content=formatted_content,
                file_type=file_type,
                size=file_size
            )
            
        except Exception as error:
            return FileProcessResult(
                success=False,
                path=file_path,
                reason=f'Unexpected error: {str(error)}'
            )
    
    async def detect_file_type(self, file_path: str) -> str:
        """
        Detect file type based on extension and MIME type
        
        Args:
            file_path: Path to the file
            
        Returns:
            File type: 'text', 'image', 'pdf', or 'binary'
        """
        file_extension = Path(file_path).suffix.lower()
        
        # Check by extension first
        if file_extension in TEXT_FILE_EXTENSIONS:
            return 'text'
        elif file_extension in IMAGE_FILE_EXTENSIONS:
            return 'image'
        elif file_extension in PDF_FILE_EXTENSIONS:
            return 'pdf'
        
        # Check MIME type as fallback
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type:
            if mime_type.startswith('text/'):
                return 'text'
            elif mime_type.startswith('image/'):
                return 'image'
            elif mime_type == 'application/pdf':
                return 'pdf'
        
        return 'binary'
    
    def is_explicitly_requested(self, file_path: str, input_patterns: List[str]) -> bool:
        """
        Check if image/PDF file is explicitly requested
        
        Args:
            file_path: Path to the file
            input_patterns: Original input patterns
            
        Returns:
            True if file is explicitly requested, False otherwise
        """
        file_extension = Path(file_path).suffix.lower()
        file_name = Path(file_path).name.lower()
        
        for pattern in input_patterns:
            pattern_lower = pattern.lower()
            
            # Check if extension is mentioned in pattern
            if file_extension in pattern_lower:
                return True
            
            # Check if filename is mentioned in pattern
            if file_name in pattern_lower:
                return True
        
        return False
    
    async def read_file_content_by_type(self, file_path: str, file_type: str) -> Dict[str, Any]:
        """
        Read file content based on file type
        
        Args:
            file_path: Path to the file
            file_type: Type of the file
            
        Returns:
            Dictionary with content and error information
        """
        try:
            if file_type == 'text':
                return await self.read_text_file(file_path)
            elif file_type == 'image':
                return await self.read_image_file(file_path)
            elif file_type == 'pdf':
                return await self.read_pdf_file(file_path)
            else:
                return {'content': None, 'error': f'Unsupported file type: {file_type}'}
                
        except Exception as error:
            return {'content': None, 'error': str(error)}
    
    async def read_text_file(self, file_path: str) -> Dict[str, Any]:
        """
        Read text file with encoding detection and content truncation
        
        Args:
            file_path: Path to the text file
            
        Returns:
            Dictionary with content, error, and encoding information
        """
        loop = asyncio.get_event_loop()
        
        def read_sync():
            encodings_to_try = ['utf-8', 'utf-16', 'latin-1', 'cp1252']
            
            for encoding in encodings_to_try:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    
                    # Limit line count
                    lines = content.split('\n')
                    if len(lines) > self.MAX_TEXT_LINES:
                        content = '\n'.join(lines[:self.MAX_TEXT_LINES])
                        content += f"\n\n[Content truncated: showing first {self.MAX_TEXT_LINES} of {len(lines)} lines]"
                    
                    # Limit total character count
                    if len(content) > self.MAX_CONTENT_CHARS:
                        content = content[:self.MAX_CONTENT_CHARS]
                        content += "\n\n[Content truncated due to size limit]"
                    
                    return {'content': content, 'error': None, 'encoding': encoding}
                    
                except UnicodeDecodeError:
                    continue
                except Exception as error:
                    return {'content': None, 'error': str(error)}
            
            return {'content': None, 'error': 'Unable to decode file with any supported encoding'}
        
        return await loop.run_in_executor(None, read_sync)
    
    async def read_image_file(self, file_path: str) -> Dict[str, Any]:
        """
        Read image file and return Part object for LLM processing
        
        Args:
            file_path: Path to the image file
            
        Returns:
            Dictionary with Part object content or error
        """
        try:
            loop = asyncio.get_event_loop()
            
            def read_sync():
                with open(file_path, 'rb') as f:
                    return f.read()
            
            binary_data = await loop.run_in_executor(None, read_sync)
            
            # Detect MIME type
            mime_type = self.get_mime_type(file_path)
            
            # Create Part object (format compatible with LLM APIs)
            part_object = {
                'type': 'image',
                'mime_type': mime_type,
                'data': base64.b64encode(binary_data).decode('utf-8'),
                'source': 'file',
                'file_path': file_path
            }
            
            return {'content': part_object, 'error': None}
            
        except Exception as error:
            return {'content': None, 'error': str(error)}
    
    async def read_pdf_file(self, file_path: str) -> Dict[str, Any]:
        """
        Read PDF file and return Part object for LLM processing
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Dictionary with Part object content or error
        """
        try:
            loop = asyncio.get_event_loop()
            
            def read_sync():
                with open(file_path, 'rb') as f:
                    return f.read()
            
            binary_data = await loop.run_in_executor(None, read_sync)
            
            # Create Part object for PDF
            part_object = {
                'type': 'pdf',
                'mime_type': 'application/pdf',
                'data': base64.b64encode(binary_data).decode('utf-8'),
                'source': 'file',
                'file_path': file_path
            }
            
            return {'content': part_object, 'error': None}
            
        except Exception as error:
            return {'content': None, 'error': str(error)}
    
    def get_mime_type(self, file_path: str) -> str:
        """
        Get MIME type for file
        
        Args:
            file_path: Path to the file
            
        Returns:
            MIME type string
        """
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type:
            return mime_type
        
        # Fallback based on extension
        extension = Path(file_path).suffix.lower()
        mime_map = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
            '.webp': 'image/webp',
            '.svg': 'image/svg+xml',
            '.pdf': 'application/pdf'
        }
        
        return mime_map.get(extension, 'application/octet-stream')
    
    def format_file_content(self, file_path: str, content: Any) -> Any:
        """
        Format file content for output
        
        Args:
            file_path: Path to the file
            content: File content
            
        Returns:
            Formatted content
        """
        if isinstance(content, str):
            # Text file: add standard separator
            separator = self.DEFAULT_OUTPUT_SEPARATOR_FORMAT.format(filePath=file_path)
            return f"{separator}\n\n{content}\n\n"
        else:
            # Non-text file (image, PDF): return Part object directly
            return content
    
    def get_stats(self) -> ProcessingStats:
        """
        Get processing statistics
        
        Returns:
            ProcessingStats object
        """
        return self.stats
    
    def reset_stats(self):
        """Reset processing statistics"""
        self.stats = ProcessingStats()
