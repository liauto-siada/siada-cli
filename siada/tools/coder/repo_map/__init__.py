"""
Repository map generation tools.

Generate repository maps with:
- Code analysis and tag extraction.
- File ranking with PageRank.
- Code structure display.
- Token counting.
- Configurable input/output handling.

Main components:
- RepoMap: Repository map generator.
- IO: Standard input/output handler.
- TokenCounterModel: Token counting model.
- Tag: Code tag data structure.
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
    Create a RepoMap instance.
    
    Args:
        root_path (str): Repository root directory.
        model_name (str): Model name; defaults to Claude 3.5 Sonnet.
        verbose (bool): Whether to enable verbose output.
        map_tokens (int): Maximum map token count.
        **kwargs: Other RepoMap parameters.
        
    Returns:
        RepoMap: Configured RepoMap instance.
        
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
    Create an optimized RepoMap instance.
    
    Use an optimized token counter for large repositories.
    
    Args:
        root_path (str): Repository root directory.
        model_name (str): Model name.
        verbose (bool): Whether to enable verbose output.
        map_tokens (int): Maximum map token count; defaults to 8192.
        sampling_threshold (int): Sampling threshold.
        **kwargs: Other RepoMap parameters.
        
    Returns:
        RepoMap: Configured optimized RepoMap instance.
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
    Create a silent RepoMap instance.
    
    Use for tests or other scenarios requiring silent operation.
    
    Args:
        root_path (str): Repository root directory.
        model_name (str): Model name.
        map_tokens (int): Maximum map token count.
        **kwargs: Other RepoMap parameters.
        
    Returns:
        RepoMap: Configured silent RepoMap instance.
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
