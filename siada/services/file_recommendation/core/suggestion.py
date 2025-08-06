"""
Suggestion data structures for file recommendation.
"""

from typing import Dict, List, TypedDict, Tuple
import os


class Suggestion(TypedDict):
    """
    File suggestion data structure
    
    Attributes:
        label: Display label for the suggestion
        value: Actual value to be inserted when selected
    """
    label: str
    value: str


def create_suggestion(label: str, value: str = None) -> Suggestion:
    """
    Create a suggestion object
    
    Args:
        label: Display label
        value: Insertion value (defaults to label if not provided)
        
    Returns:
        Suggestion object
    """
    return Suggestion(
        label=label,
        value=value if value is not None else label
    )


def sort_suggestions(suggestions: List[Suggestion]) -> List[Suggestion]:
    """
    Sort suggestions by priority:
    1. Path depth (shallow first)
    2. Directory type (directories first)
    3. File name (without extension)
    4. Full label
    
    Args:
        suggestions: Original suggestion list
        
    Returns:
        Sorted suggestion list
    """
    def sort_key(suggestion: Suggestion) -> Tuple[int, bool, str, str]:
        label = suggestion['label']
        
        # 1. Calculate path depth
        depth = label.count('/')
        
        # 2. Check if it's a directory
        is_dir = label.endswith('/')
        dir_priority = 0 if is_dir else 1  # Directories first
        
        # 3. Get filename without extension
        basename = os.path.basename(label.rstrip('/'))
        name_without_ext = os.path.splitext(basename)[0]
        
        # 4. Full label name
        full_label = label
        
        return (depth, dir_priority, name_without_ext.lower(), full_label.lower())
    
    return sorted(suggestions, key=sort_key)


def filter_suggestions_by_prefix(suggestions: List[Suggestion], prefix: str) -> List[Suggestion]:
    """
    Filter suggestions by matching prefix
    
    Args:
        suggestions: List of suggestions to filter
        prefix: Prefix to match against
        
    Returns:
        Filtered suggestions
    """
    if not prefix:
        return suggestions
    
    prefix_lower = prefix.lower()
    filtered = []
    
    for suggestion in suggestions:
        label_lower = suggestion['label'].lower()
        if label_lower.startswith(prefix_lower):
            filtered.append(suggestion)
    
    return filtered


def limit_suggestions(suggestions: List[Suggestion], max_results: int) -> List[Suggestion]:
    """
    Limit the number of suggestions
    
    Args:
        suggestions: List of suggestions
        max_results: Maximum number of results to return
        
    Returns:
        Limited suggestion list
    """
    return suggestions[:max_results] if max_results > 0 else suggestions
