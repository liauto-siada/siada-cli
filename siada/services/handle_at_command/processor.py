"""
AtCommand Processor - Main processor that coordinates all components.
"""

import time
import re
from typing import List, Dict, Optional, Any, Tuple

from .models import (
    HandleAtCommandParams, 
    HandleAtCommandResult, 
    AtCommandPart,
    ResolverContext,
    ProcessingStats,
    IgnoredFileStats
)
from .parser import AtCommandParser
from .resolver import PathResolver
from .exceptions import AtCommandError

# Import ReadManyFiles tool
from siada.tools.read_many_files_tool import ReadManyFilesTool
from siada.tools.read_many_files.models import ReadManyFilesParams


class AtCommandProcessor:
    """Main processor for handling @ commands"""
    
    def __init__(self, config=None):
        self.config = config
        self.parser = AtCommandParser()
        self.stats = ProcessingStats()
        self.ignored_stats = IgnoredFileStats()
        
        # Regex to parse file content from read_many_files output
        self.file_content_regex = re.compile(r'^--- (.*?) ---\n\n([\s\S]*?)\n\n$')
    
    async def handle_at_command(self, params: HandleAtCommandParams) -> HandleAtCommandResult:
        """
        Main entry point for handling @ commands
        
        Args:
            params: HandleAtCommandParams with all necessary parameters
            
        Returns:
            HandleAtCommandResult with processed query and status
        """
        start_time = time.time()
        
        try:
            # 1. Parse user input
            command_parts = self.parser.parse_all_at_commands(params.query)
            at_path_parts = [part for part in command_parts if part.type == 'atPath']
            
            self.stats.total_at_commands = len(at_path_parts)
            
            # 2. Early exit if no @ commands
            if not at_path_parts:
                params.add_item({'type': 'user', 'text': params.query}, params.message_id)
                return HandleAtCommandResult([{'text': params.query}], True)
            
            params.add_item({'type': 'user', 'text': params.query}, params.message_id)
            
            # 3. Initialize resolver context
            resolver_context = self._create_resolver_context(params.config)
            resolver = PathResolver(resolver_context)
            
            # 4. Resolve paths
            paths_to_read = []
            at_path_to_resolved_map = {}
            content_labels = []
            
            for at_path_part in at_path_parts:
                try:
                    resolution_result = await resolver.resolve_path(
                        at_path_part.content, 
                        params.on_debug_message
                    )
                    
                    if resolution_result.resolved_path:
                        paths_to_read.append(resolution_result.resolved_path)
                        at_path_to_resolved_map[at_path_part.content] = resolution_result.resolved_path
                        content_labels.append(at_path_part.content[1:])  # Remove @
                        self.stats.resolved_paths += 1
                    else:
                        params.on_debug_message(f'Failed to resolve {at_path_part.content}: {resolution_result.reason}')
                        self.stats.failed_paths += 1
                        
                except AtCommandError as e:
                    params.on_debug_message(f'Error resolving {at_path_part.content}: {e}')
                    self.stats.failed_paths += 1
                    continue
            
            # 5. Handle case with no valid paths
            if not paths_to_read:
                params.on_debug_message('No valid file paths found in @ commands to read.')
                initial_query = self._rebuild_initial_query(command_parts, at_path_to_resolved_map)
                return HandleAtCommandResult([{'text': initial_query or params.query}], True)
            
            # 6. Read files using ReadManyFilesTool
            try:
                file_contents = await self._read_files(
                    paths_to_read, 
                    resolver_context.target_directory,
                    resolver_context.file_filtering_options,
                    params.signal
                )
                
                self.stats.files_read = len(file_contents) if file_contents else 0
                
                # 7. Build processed query
                processed_query = self._build_processed_query(
                    command_parts, 
                    at_path_to_resolved_map, 
                    file_contents
                )
                
                # 8. Record success
                self._record_tool_success(content_labels, params.add_item, params.message_id)
                
                # 9. Update processing time
                self.stats.processing_time = time.time() - start_time
                
                return HandleAtCommandResult(processed_query, True)
                
            except Exception as error:
                # 10. Handle file reading errors
                self._handle_read_error(error, content_labels, params.add_item, params.message_id)
                return HandleAtCommandResult(None, False)
                
        except Exception as error:
            # Handle unexpected errors
            params.on_debug_message(f'Unexpected error in handleAtCommand: {error}')
            params.add_item(
                {'type': 'error', 'text': f'Unexpected error processing @ commands: {str(error)}'},
                params.message_id
            )
            return HandleAtCommandResult(None, False)
    
    def _create_resolver_context(self, config) -> ResolverContext:
        """
        Create resolver context from config
        
        Args:
            config: Configuration object
            
        Returns:
            ResolverContext for path resolution
        """
        # Extract configuration values
        # This is a simplified implementation - in practice, you'd extract from actual config
        workspace_directories = [config.root_dir] if hasattr(config, 'root_dir') and config.root_dir else ['.']
        target_directory = config.root_dir if hasattr(config, 'root_dir') and config.root_dir else '.'
        
        return ResolverContext(
            workspace_directories=workspace_directories,
            target_directory=target_directory,
            enable_recursive_search=True,
            file_filtering_options={
                'respect_git_ignore': True
            }
        )
    
    async def _read_files(self, paths: List[str], target_dir: str, 
                         filtering_options: Dict[str, bool], signal=None) -> List[Any]:
        """
        Read files using ReadManyFilesTool
        
        Args:
            paths: List of file paths to read
            target_dir: Target directory
            filtering_options: File filtering options
            signal: Cancellation signal
            
        Returns:
            List of file contents
        """
        tool = ReadManyFilesTool(target_dir)
        
        params = ReadManyFilesParams(
            paths=paths,
            file_filtering_options=filtering_options
        )
        
        result = await tool.execute(params, signal)
        
        if result and hasattr(result, 'llmContent'):
            return result.llmContent
        
        return []
    
    def _rebuild_initial_query(self, command_parts: List[AtCommandPart], 
                              at_path_to_resolved_map: Dict[str, str]) -> str:
        """
        Rebuild the initial query text with resolved paths
        
        Args:
            command_parts: Parsed command parts
            at_path_to_resolved_map: Mapping of @ paths to resolved paths
            
        Returns:
            Rebuilt query string
        """
        initial_query_text = ""
        
        for i, part in enumerate(command_parts):
            if part.type == 'text':
                initial_query_text += part.content
            else:  # atPath
                resolved_spec = at_path_to_resolved_map.get(part.content)
                
                # Add appropriate spacing
                if (i > 0 and initial_query_text and 
                    not initial_query_text.endswith(' ') and
                    (resolved_spec or not part.content.startswith(' '))):
                    initial_query_text += ' '
                
                if resolved_spec:
                    initial_query_text += f'@{resolved_spec}'
                else:
                    initial_query_text += part.content
        
        return initial_query_text.strip()
    
    def _build_processed_query(self, command_parts: List[AtCommandPart], 
                              at_path_to_resolved_map: Dict[str, str],
                              file_contents: List[Any]) -> List[Dict]:
        """
        Build the processed query with file contents injected
        
        Args:
            command_parts: Parsed command parts
            at_path_to_resolved_map: Mapping of @ paths to resolved paths
            file_contents: File contents from ReadManyFilesTool
            
        Returns:
            List of processed query parts
        """
        # 1. Rebuild initial query text
        initial_query_text = self._rebuild_initial_query(command_parts, at_path_to_resolved_map)
        
        # 2. Start with the initial query
        processed_parts = [{'text': initial_query_text}]
        
        # 3. Add file contents if any
        if file_contents:
            processed_parts.append({'text': '\n--- Content from referenced files ---'})
            
            for file_content_part in file_contents:
                if isinstance(file_content_part, str):
                    # Parse file content format: "--- filepath ---\n\ncontent\n\n"
                    file_path, content = self.parser.extract_file_content_info(file_content_part)
                    
                    if file_path:
                        processed_parts.append({'text': f'\nContent from @{file_path}:\n'})
                        processed_parts.append({'text': content})
                    else:
                        processed_parts.append({'text': file_content_part})
                else:
                    # Non-string content (e.g., image Part objects)
                    processed_parts.append(file_content_part)
            
            processed_parts.append({'text': '\n--- End of content ---'})
        
        return processed_parts
    
    def _record_tool_success(self, content_labels: List[str], add_item: callable, message_id: int):
        """
        Record successful tool execution
        
        Args:
            content_labels: List of content labels
            add_item: Function to add items to history
            message_id: Message ID
        """
        if content_labels:
            success_message = f"Successfully read {len(content_labels)} file(s): {', '.join(content_labels)}"
            add_item(
                {'type': 'tool_success', 'text': success_message},
                message_id
            )
    
    def _handle_read_error(self, error: Exception, content_labels: List[str], 
                          add_item: callable, message_id: int):
        """
        Handle file reading errors
        
        Args:
            error: Exception that occurred
            content_labels: List of content labels that were being processed
            add_item: Function to add items to history
            message_id: Message ID
        """
        error_message = f"Error reading files {', '.join(content_labels)}: {str(error)}"
        add_item(
            {'type': 'error', 'text': error_message},
            message_id
        )
    
    def get_processing_stats(self) -> ProcessingStats:
        """
        Get processing statistics
        
        Returns:
            ProcessingStats object
        """
        return self.stats
    
    def get_ignored_stats(self) -> IgnoredFileStats:
        """
        Get ignored file statistics
        
        Returns:
            IgnoredFileStats object
        """
        return self.ignored_stats
    
    def reset_stats(self):
        """Reset processing statistics"""
        self.stats = ProcessingStats()
        self.ignored_stats = IgnoredFileStats()
