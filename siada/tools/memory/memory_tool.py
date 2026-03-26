"""
Memory Tools for Agent

Provides search and retrieval tools for accessing historical conversation memory.
Compatible with OpenClaw's memory search approach.
"""

import logging
from pathlib import Path
from typing import Optional

from agents import function_tool, RunContextWrapper
from siada.foundation.code_agent_context import CodeAgentContext
from siada.services.memory import MemorySearch, SearchResult, DEFAULT_CHUNK_SIZE


logger = logging.getLogger(__name__)


# ---- Tool Documentation --------------------------------

SEARCH_MEMORY_DOCS = """Search through memory files for relevant information.

Mandatory recall step: semantically search memory files (conversation history
and saved sessions) before answering questions about prior work, decisions,
dates, people, preferences, or todos.

Use this tool when the user asks about:
- Previous conversations or tasks
- Past decisions or preferences  
- Historical context or project history
- Anything that might have been discussed before

Args:
    query (str): Search query string (supports both English and Chinese)
    max_results (int, optional): Maximum number of results to return. Defaults to 5.
    min_score (float, optional): Minimum relevance score threshold. Defaults to 0.0.

Returns:
    str: Formatted search results with file paths, line numbers, relevance scores,
         and text snippets. Returns empty results if search fails or finds nothing.

Examples:
    search_memory("API design decisions")
    search_memory("上次讨论的数据库方案")
    search_memory("bug fixes from last week", max_results=10)
"""


GET_MEMORY_DOCS = """Read specific content from a memory file.

Use this tool after search_memory to get more detailed context from
relevant memory files. Reads the entire file or a specific line range.

Args:
    path (str): Relative path to the memory file (e.g., "session/2024-01-15-14-30-api-design.md" or "personal_style.md")
    start_line (int, optional): Starting line number (1-indexed)
    line_count (int, optional): Number of lines to read from start_line

Returns:
    str: The requested file content, or an error message if file not found.

Examples:
    get_memory("session/2024-01-15-14-30-api-design.md")
    get_memory("personal_style.md")
    get_memory("session/2024-01-15-14-30-api-design.md", start_line=10, line_count=20)
"""


# ---- Implementation Functions --------------------------------

def search_memory_impl(
    query: str,
    max_results: int = 5,
    min_score: float = 0.0
) -> str:
    """
    Internal implementation of memory search.
    
    This function performs the actual search logic and is intended to be tested directly.
    The public search_memory function wraps this with the function_tool decorator.
    
    Args:
        query: Search query string (supports both English and Chinese)
        max_results: Maximum number of results to return (default: 5)
        min_score: Minimum relevance score threshold (default: 0.0)
    
    Returns:
        Formatted search results as string
    """
    memory_search = None
    try:
        # Validate inputs
        if not query or not query.strip():
            return "Error: Search query cannot be empty"
        
        if max_results <= 0:
            return "Error: max_results must be greater than 0"
        
        # Initialize memory search
        memory_search = MemorySearch()
        
        if not memory_search.fts_available:
            return "Memory search is not available. The memory database may not be initialized yet."
        
        # Perform search
        results = memory_search.search(
            query=query.strip(),
            limit=max_results,
            snippet_max_chars=DEFAULT_CHUNK_SIZE
        )
        
        # Filter by minimum score
        if min_score > 0:
            results = [r for r in results if r.score >= min_score]
        
        # Format results
        if not results:
            return f"No results found for query: {query}"
        
        formatted_output = []
        formatted_output.append(f"Found {len(results)} result(s) for query: {query}\n")
        
        for i, result in enumerate(results, 1):
            formatted_output.append(f"--- Result {i} ---")
            formatted_output.append(f"File: {result.path}")
            formatted_output.append(f"Lines: {result.start_line}-{result.end_line}")
            formatted_output.append(f"Score: {result.score:.3f}")
            formatted_output.append(f"Source: {result.source}")
            formatted_output.append(f"\nSnippet:")
            formatted_output.append(result.snippet)
            formatted_output.append("")  # Empty line between results
        
        return "\n".join(formatted_output)
        
    except Exception as e:
        error_msg = f"Error searching memory: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg
    finally:
        # Clean up connection
        if memory_search is not None:
            try:
                memory_search.close()
            except Exception:
                pass


def read_memory_content(
    path: str,
    start_line: Optional[int] = None,
    line_count: Optional[int] = None
) -> str:
    """
    Read memory file content without header.
    
    This is a helper function that returns only the file content without any header information.
    Used internally by get_memory_impl to separate content reading from formatting.
    
    Args:
        path: Relative path to the memory file
        start_line: Starting line number (1-indexed, optional)
        line_count: Number of lines to read from start_line (optional)
    
    Returns:
        File content as string (without header)
    """
    # Validate path
    if not path or not path.strip():
        return "Error: File path cannot be empty"
    
    # Construct full path
    memory_dir = Path.home() / ".siada-cli" / "workspace" / "memory"
    file_path = memory_dir / path.strip()
    
    # Security check: ensure path is within memory directory
    try:
        file_path = file_path.resolve()
        memory_dir = memory_dir.resolve()
        if not str(file_path).startswith(str(memory_dir)):
            return f"Error: Access denied. Path must be within memory directory: {path}"
    except Exception:
        return f"Error: Invalid file path: {path}"
    
    # Check if file exists
    if not file_path.exists():
        return f"Error: File not found: {path}"
    
    if not file_path.is_file():
        return f"Error: Path is not a file: {path}"
    
    # Read file content
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        return f"Error: File is not a valid text file: {path}"
    
    # Handle line range selection
    if start_line is not None:
        if start_line < 1:
            return "Error: start_line must be >= 1"
        
        # Convert to 0-indexed
        start_idx = start_line - 1
        
        if start_idx >= len(lines):
            return f"Error: start_line {start_line} exceeds file length ({len(lines)} lines)"
        
        if line_count is not None:
            if line_count < 1:
                return "Error: line_count must be >= 1"
            end_idx = start_idx + line_count
            selected_lines = lines[start_idx:end_idx]
        else:
            # Read from start_line to end
            selected_lines = lines[start_idx:]
        
        return "".join(selected_lines)
    else:
        # Read entire file
        return "".join(lines)


def get_memory_impl(
    path: str,
    start_line: Optional[int] = None,
    line_count: Optional[int] = None
) -> str:
    """
    Internal implementation of memory file reading.
    
    This function performs the actual file reading logic and is intended to be tested directly.
    The public get_memory function wraps this with the function_tool decorator.
    
    Args:
        path: Relative path to the memory file
        start_line: Starting line number (1-indexed, optional)
        line_count: Number of lines to read from start_line (optional)
    
    Returns:
        File content with header as string
    """
    try:
        # Get the content without header
        content = read_memory_content(path=path, start_line=start_line, line_count=line_count)
        
        # If content is an error message, return it directly
        if content.startswith("Error:"):
            return content
        
        # Construct full path to get line count for header
        memory_dir = Path.home() / ".siada-cli" / "workspace" / "memory"
        file_path = memory_dir / path.strip()
        
        with open(file_path, 'r', encoding='utf-8') as f:
            total_lines = len(f.readlines())
        
        # Generate appropriate header
        if start_line is not None:
            actual_lines = len(content.splitlines())
            if not content.endswith('\n') and actual_lines > 0:
                # Adjust if last line doesn't have newline
                actual_lines = len(content.split('\n'))
            header = f"File: {path} (lines {start_line}-{start_line + actual_lines - 1} of {total_lines})\n\n"
        else:
            header = f"File: {path} ({total_lines} lines)\n\n"
        
        return header + content
        
    except Exception as e:
        error_msg = f"Error reading memory file: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


# ---- Public Tool Functions --------------------------------

@function_tool(
    name_override="search_memory", description_override=SEARCH_MEMORY_DOCS
)
def search_memory(
    context: RunContextWrapper[CodeAgentContext],
    query: str,
    max_results: int = 5,
    min_score: float = 0.0
) -> str:

    return search_memory_impl(query=query, max_results=max_results, min_score=min_score)


@function_tool(
    name_override="get_memory", description_override=GET_MEMORY_DOCS
)
def get_memory(
    context: RunContextWrapper[CodeAgentContext],
    path: str,
    start_line: Optional[int] = None,
    line_count: Optional[int] = None
) -> str:

    return get_memory_impl(path=path, start_line=start_line, line_count=line_count)
