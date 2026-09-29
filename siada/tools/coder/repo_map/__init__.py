"""
Repo Map module - a code repository map generation tool.

This module provides the full functionality for generating a code repository map, including:
- Code file analysis and tag extraction
- File importance ranking based on the PageRank algorithm
- Intelligent code structure display
- High-performance token counting
- Flexible IO handling

Main components:
- RepoMap: the core repository map generator
- IO: standard input/output handler
- TokenCounterModel: token counting model
- Tag: code tag data structure
"""

from .repo_map import RepoMap, Tag
from .io import IO, SilentIO, FileIO
from .token_counter import TokenCounterModel, OptimizedTokenCounterModel
from .dump import dump
from .special import filter_important_files, is_important
from .waiting import Spinner, WaitingSpinner

__all__ = [
    # Core classes
    'RepoMap',
    'Tag',
    
    # IO classes
    'IO',
    'SilentIO', 
    'FileIO',
    
    # Token counter classes
    'TokenCounterModel',
    'OptimizedTokenCounterModel',
    
    # Utility functions
    'dump',
    'filter_important_files',
    'is_important',
    
    # Wait/progress indicators
    'Spinner',
    'WaitingSpinner',
]

# Version info
__version__ = '1.0.0'

# Module-level convenience functions
def create_repo_map(
    root_path: str,
    model_name: str = "claude-3-5-sonnet-20241022",
    verbose: bool = False,
    map_tokens: int = 1024,
    **kwargs
) -> RepoMap:
    """
    Convenience function for creating a RepoMap instance.
    
    Args:
        root_path (str): The repository root directory path.
        model_name (str): The language model name, defaults to Claude 3.5 Sonnet.
        verbose (bool): Whether to enable verbose output.
        map_tokens (int): The maximum number of map tokens.
        **kwargs: Other RepoMap parameters.
        
    Returns:
        RepoMap: A configured RepoMap instance.
        
    Example:
        >>> repo_map = create_repo_map("/path/to/repo", verbose=True)
        >>> result = repo_map.get_repo_map(chat_files=[], other_files=python_files)
    """
    io = IO(verbose=verbose)
    model = TokenCounterModel(model_name)
    
    return RepoMap(
        root=root_path,
        main_model=model,
        io=io,
        verbose=verbose,
        map_tokens=map_tokens,
        **kwargs
    )


def create_optimized_repo_map(
    root_path: str,
    model_name: str = "claude-3-5-sonnet-20241022",
    verbose: bool = False,
    map_tokens: int = 8192,
    sampling_threshold: int = 10000,
    **kwargs
) -> RepoMap:
    """
    Convenience function for creating an optimized RepoMap instance.
    
    Suitable for large code repositories; uses an optimized token counter.
    
    Args:
        root_path (str): The repository root directory path.
        model_name (str): The language model name.
        verbose (bool): Whether to enable verbose output.
        map_tokens (int): The maximum number of map tokens, defaults to 8192.
        sampling_threshold (int): The sampling threshold.
        **kwargs: Other RepoMap parameters.
        
    Returns:
        RepoMap: A configured optimized RepoMap instance.
    """
    io = IO(verbose=verbose)
    model = OptimizedTokenCounterModel(model_name, sampling_threshold)
    
    return RepoMap(
        root=root_path,
        main_model=model,
        io=io,
        verbose=verbose,
        map_tokens=map_tokens,
        **kwargs
    )


def create_silent_repo_map(
    root_path: str,
    model_name: str = "claude-3-5-sonnet-20241022",
    map_tokens: int = 1024,
    **kwargs
) -> RepoMap:
    """
    Convenience function for creating a silent RepoMap instance.
    
    Suitable for tests or scenarios requiring silent operation.
    
    Args:
        root_path (str): The repository root directory path.
        model_name (str): The language model name.
        map_tokens (int): The maximum number of map tokens.
        **kwargs: Other RepoMap parameters.
        
    Returns:
        RepoMap: A configured silent RepoMap instance.
    """
    io = SilentIO()
    model = TokenCounterModel(model_name)
    
    return RepoMap(
        root=root_path,
        main_model=model,
        io=io,
        verbose=False,
        map_tokens=map_tokens,
        **kwargs
    )
