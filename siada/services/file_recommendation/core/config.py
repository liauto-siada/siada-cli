"""
Configuration classes for file recommendation system.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class FilterOptions:
    """File filtering configuration options"""
    respect_git_ignore: bool = True


@dataclass
class CompletionConfig:
    """Auto-completion configuration"""
    
    # Search configuration
    enable_recursive_search: bool = True
    max_search_depth: int = 10
    max_results: int = 50
    debounce_delay_ms: int = 100
    
    # Display configuration
    max_visible_suggestions: int = 8
    suggestion_width: int = 60
    
    # Filtering configuration
    respect_git_ignore: bool = True
    
    # Performance configuration
    search_timeout_ms: int = 5000
    
    # User experience configuration
    show_loading_indicator: bool = True
    auto_select_first: bool = True
    
    def get_filter_options(self) -> FilterOptions:
        """Get filter options from config"""
        return FilterOptions(
            respect_git_ignore=self.respect_git_ignore
        )


@dataclass
class WorkspaceConfig:
    """Workspace configuration"""
    directories: List[str]
    current_directory: str
    project_root: str
    
    def get_search_directories(self) -> List[str]:
        """Get search directory list"""
        return self.directories if self.directories else [self.current_directory]


# Default configuration instance
DEFAULT_COMPLETION_CONFIG = CompletionConfig()

# Default filter options
DEFAULT_FILTER_OPTIONS = FilterOptions()
