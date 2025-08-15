"""
HandleAtCommand data models and structures.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Union, Any, Literal


@dataclass
class AtCommandPart:
    """Represents a part of the parsed @ command query"""
    type: Literal['text', 'atPath']  # Part type
    content: str                     # Content


@dataclass
class HandleAtCommandParams:
    """Input parameters for handleAtCommand function"""
    query: str                       # User's original query
    config: Any                      # Configuration object
    add_item: callable              # History addition function
    on_debug_message: callable      # Debug message callback
    message_id: int                 # Message ID
    signal: Optional[Any] = None    # Cancellation signal


@dataclass
class HandleAtCommandResult:
    """Output result from handleAtCommand function"""
    processed_query: Optional[List[Dict]]  # Processed query parts
    should_proceed: bool                   # Whether to continue processing


@dataclass
class ResolverContext:
    """Context for path resolution"""
    workspace_directories: List[str]
    target_directory: str
    enable_recursive_search: bool = True
    file_filtering_options: Optional[Dict[str, bool]] = None
    
    def __post_init__(self):
        if self.file_filtering_options is None:
            self.file_filtering_options = {
                'respect_git_ignore': True
            }


@dataclass
class PathResolutionResult:
    """Result of path resolution"""
    resolved_path: Optional[str]
    original_path: str
    resolution_type: Literal['direct', 'glob', 'directory', 'not_found']
    reason: Optional[str] = None


@dataclass
class ProcessingStats:
    """Statistics for @ command processing"""
    total_at_commands: int = 0
    resolved_paths: int = 0
    failed_paths: int = 0
    ignored_paths: int = 0
    files_read: int = 0
    processing_time: float = 0.0
    
    
@dataclass
class IgnoredFileStats:
    """Statistics for ignored files"""
    git_ignored: List[str]
    gemini_ignored: List[str]
    both_ignored: List[str]
    
    def __init__(self):
        self.git_ignored = []
        self.gemini_ignored = []
        self.both_ignored = []
    
    def add_ignored_file(self, file_path: str, reason: Literal['git', 'gemini', 'both']):
        """Add a file to the ignored list"""
        if reason == 'git':
            self.git_ignored.append(file_path)
        elif reason == 'gemini':
            self.gemini_ignored.append(file_path)
        elif reason == 'both':
            self.both_ignored.append(file_path)
    
    def get_total_ignored(self) -> int:
        """Get total number of ignored files"""
        return len(self.git_ignored) + len(self.gemini_ignored) + len(self.both_ignored)
