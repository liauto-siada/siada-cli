"""
Search Memory by Date Tool

Provides functionality to search memory files within a specified time range.
"""

import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional

from agents import function_tool, RunContextWrapper
from siada.foundation.code_agent_context import CodeAgentContext
from siada.services.memory import MemorySearch


logger = logging.getLogger(__name__)


SEARCH_MEMORY_BY_DATE_DOCS = """Search memory files within a specific time range.

Use this tool to search for information in a specific date range, useful for:
- Finding recent TODO items or pending tasks
- Searching within last week's work
- Locating discussions from a specific time period

Args:
    query (str): Search query string (supports both English and Chinese)
    days (int, optional): Search in files from the last N days. Default is 7.
    start_date (str, optional): Start date in "YYYY-MM-DD" format (inclusive)
    end_date (str, optional): End date in "YYYY-MM-DD" format (inclusive)
    max_results (int, optional): Maximum number of results. Default is 5.
    min_score (float, optional): Minimum relevance score (0.0-1.0). Default is 0.0.

Note: Either use 'days' OR use 'start_date'/'end_date', not both.

Returns:
    str: Formatted search results with file paths, line numbers, relevance scores,
         and text snippets from files within the date range.

Examples:
    search_memory_by_date("TODO", days=7)
    search_memory_by_date("API design", start_date="2024-03-01", end_date="2024-03-05")
    search_memory_by_date("bug fix", days=3, max_results=10)
"""


# ---- Implementation Function --------------------------------

def search_memory_by_date_impl(
    query: str,
    days: Optional[int] = 7,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_results: int = 5,
    min_score: float = 0.0,
) -> str:
    """
    Internal implementation of search_memory_by_date.
    
    This function performs the actual search logic and is intended to be tested directly.
    The public search_memory_by_date function wraps this with the function_tool decorator.
    
    Args:
        query: Search query
        days: Number of recent days to search (default: 7)
        start_date: Start date "YYYY-MM-DD" (optional)
        end_date: End date "YYYY-MM-DD" (optional)
        max_results: Maximum results to return
        min_score: Minimum relevance score threshold
        
    Returns:
        Formatted string with search results
    """
    memory_search = None
    try:
        # Get memory directory path
        memory_dir = Path.home() / ".siada-cli" / "workspace" / "memory"
        
        if not memory_dir.exists():
            return "No memory directory found. No memories have been saved yet."
        
        # Determine date range
        if start_date or end_date:
            # Use explicit date range
            if start_date:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            else:
                start_dt = datetime.min.replace(tzinfo=timezone.utc)
            
            if end_date:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                end_dt = end_dt.replace(hour=23, minute=59, second=59)
            else:
                end_dt = datetime.now(timezone.utc)
        else:
            # Use days parameter
            end_dt = datetime.now(timezone.utc)
            start_dt = end_dt - timedelta(days=days)
        
        # Find all .md files recursively in subdirectories within date range
        all_files = list(memory_dir.glob("**/*.md"))
        files_in_range = []
        
        for file_path in all_files:
            try:
                filename = file_path.name
                # Extract date from filename (format: YYYY-MM-DD-HH-MM-slug.md or YYYY-MM-DD-slug.md)
                # Both formats use YYYY-MM-DD as the date prefix
                date_str = "-".join(filename.split("-")[:3])  # Extract YYYY-MM-DD
                file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                
                if start_dt <= file_date <= end_dt:
                    # Store relative path from memory directory
                    relative_path = str(file_path.relative_to(memory_dir))
                    files_in_range.append(relative_path)
            except (ValueError, IndexError):
                # Skip files that don't match the naming pattern
                logger.debug(f"Skipping file with invalid name format: {file_path.name}")
                continue
        
        if not files_in_range:
            date_range = f"{start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')}"
            return f"No memory files found in date range: {date_range}"
        
        # Perform search using MemorySearch
        searcher = MemorySearch()
        results = searcher.search(query, max_results=max_results * 2)  # Get more to filter
        
        # Filter results to only include files in date range
        filtered_results = []
        for result in results:
            if result.file_path in files_in_range and result.score >= min_score:
                filtered_results.append(result)
                if len(filtered_results) >= max_results:
                    break
        
        # Format output
        if not filtered_results:
            date_range = f"{start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')}"
            return f"No results found for \"{query}\" in date range: {date_range}"
        
        result_lines = []
        date_range = f"{start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')}"
        result_lines.append(f"Found {len(filtered_results)} result(s) for \"{query}\" in {date_range}:")
        result_lines.append("")
        
        for i, result in enumerate(filtered_results, 1):
            result_lines.append(
                f"{i}. {result.file_path}:{result.line_number}\n"
                f"   Score: {result.score:.3f}\n"
                f"   {result.text.strip()}"
            )
            result_lines.append("")
        
        return "\n".join(result_lines)
        
    except Exception as e:
        logger.error(f"Error searching memory by date: {e}", exc_info=True)
        return f"Error searching memory: {str(e)}"
    finally:
        # Clean up connection
        if memory_search is not None:
            try:
                memory_search.close()
            except Exception:
                pass


# ---- Public Tool Function --------------------------------

@function_tool(
    name_override="search_memory_by_date", description_override=SEARCH_MEMORY_BY_DATE_DOCS
)
def search_memory_by_date(
    context: RunContextWrapper[CodeAgentContext],
    query: str,
    days: Optional[int] = 7,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_results: int = 5,
    min_score: float = 0.0,
) -> str:
    return search_memory_by_date_impl(
        query=query,
        days=days,
        start_date=start_date,
        end_date=end_date,
        max_results=max_results,
        min_score=min_score
    )
