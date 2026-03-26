"""
List Memory Files Tool

Provides functionality to list memory files within a specified time range.
"""

import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional

from agents import function_tool, RunContextWrapper
from siada.foundation.code_agent_context import CodeAgentContext


logger = logging.getLogger(__name__)


LIST_MEMORY_FILES_DOCS = """List memory files within a specified time range.

Use this tool to discover what memory files exist in a time period, useful for:
- Getting an overview of recent work activity
- Finding files to read with get_memory
- Understanding the scope of work in a date range

Args:
    days (int, optional): List files from the last N days. Default is 7.
    start_date (str, optional): Start date in "YYYY-MM-DD" format (inclusive)
    end_date (str, optional): End date in "YYYY-MM-DD" format (inclusive)

Note: Either use 'days' OR use 'start_date'/'end_date', not both.

Returns:
    str: Formatted list of memory files with metadata (filename, size, line count, date)

Examples:
    list_memory_files()  # Last 7 days
    list_memory_files(days=3)  # Last 3 days
    list_memory_files(start_date="2024-03-01", end_date="2024-03-05")
"""


# ---- Implementation Function --------------------------------

def list_memory_files_impl(
    days: Optional[int] = 7,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """
    Internal implementation of list_memory_files.
    
    This function performs the actual file listing logic and is intended to be tested directly.
    The public list_memory_files function wraps this with the function_tool decorator.
    
    Args:
        days: Number of recent days to list (default: 7)
        start_date: Start date "YYYY-MM-DD" (optional)
        end_date: End date "YYYY-MM-DD" (optional)
        
    Returns:
        Formatted string with file listing
    """
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
        
        # Find all .md files recursively in subdirectories
        all_files = list(memory_dir.glob("**/*.md"))
        
        # Filter files by date
        filtered_files = []
        for file_path in all_files:
            # Extract date from filename (format: YYYY-MM-DD-HH-MM-slug.md or YYYY-MM-DD-slug.md)
            try:
                filename = file_path.name
                # Try new format first (YYYY-MM-DD-HH-MM), then fall back to old format (YYYY-MM-DD)
                parts = filename.split("-")
                if len(parts) >= 5 and parts[3].isdigit() and parts[4].split(".")[0].isdigit():
                    # New format: YYYY-MM-DD-HH-MM-slug.md
                    date_str = "-".join(parts[:3])  # Extract YYYY-MM-DD
                else:
                    # Old format: YYYY-MM-DD-slug.md
                    date_str = "-".join(parts[:3])  # Extract YYYY-MM-DD
                file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                
                if start_dt <= file_date <= end_dt:
                    # Get file stats
                    stat = file_path.stat()
                    line_count = len(file_path.read_text(encoding='utf-8').splitlines())
                    
                    # Get relative path from memory directory
                    relative_path = file_path.relative_to(memory_dir)
                    
                    filtered_files.append({
                        'name': str(relative_path),
                        'date': file_date,
                        'size': stat.st_size,
                        'lines': line_count,
                    })
            except (ValueError, IndexError):
                # Skip files that don't match the naming pattern
                logger.debug(f"Skipping file with invalid name format: {file_path.name}")
                continue
        
        # Sort by date (newest first)
        filtered_files.sort(key=lambda x: x['date'], reverse=True)
        
        # Format output
        if not filtered_files:
            date_range = f"{start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')}"
            return f"No memory files found in date range: {date_range}"
        
        # Build result string
        result_lines = []
        result_lines.append(f"Found {len(filtered_files)} memory file(s):")
        result_lines.append("")
        
        for i, file_info in enumerate(filtered_files, 1):
            size_kb = file_info['size'] / 1024
            result_lines.append(
                f"{i}. {file_info['name']}\n"
                f"   Date: {file_info['date'].strftime('%Y-%m-%d')}\n"
                f"   Size: {size_kb:.1f} KB, Lines: {file_info['lines']}"
            )
        
        return "\n".join(result_lines)
        
    except Exception as e:
        logger.error(f"Error listing memory files: {e}", exc_info=True)
        return f"Error listing memory files: {str(e)}"


# ---- Public Tool Function --------------------------------

@function_tool(
    name_override="list_memory_files", description_override=LIST_MEMORY_FILES_DOCS
)
def list_memory_files(
    context: RunContextWrapper[CodeAgentContext],
    days: Optional[int] = 7,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    return list_memory_files_impl(days=days, start_date=start_date, end_date=end_date)
