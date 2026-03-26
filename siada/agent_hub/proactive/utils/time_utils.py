"""
Time utilities for ProactiveScheduler.

Provides work hours judgment and time parsing helpers.
"""

from datetime import datetime, timezone
from typing import Tuple, Optional


def parse_time_str(time_str: str) -> Tuple[int, int]:
    """
    Parse a "HH:MM" time string into (hour, minute).

    Args:
        time_str: Time string in "HH:MM" format

    Returns:
        Tuple of (hour, minute) as integers

    Raises:
        ValueError: If format is invalid
    """
    parts = time_str.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time format '{time_str}'. Expected 'HH:MM'")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        raise ValueError(f"Invalid time format '{time_str}'. Expected 'HH:MM'")
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Time out of range in '{time_str}'")
    return hour, minute


def parse_work_hours(work_hours_str: str) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """
    Parse a "HH:MM-HH:MM" work hours string.

    Args:
        work_hours_str: Work hours string in "HH:MM-HH:MM" format

    Returns:
        Tuple of ((start_hour, start_minute), (end_hour, end_minute))

    Raises:
        ValueError: If format is invalid
    """
    parts = work_hours_str.strip().split("-")
    if len(parts) != 2:
        raise ValueError(f"Invalid work_hours format '{work_hours_str}'. Expected 'HH:MM-HH:MM'")
    start = parse_time_str(parts[0])
    end = parse_time_str(parts[1])
    return start, end


def is_work_hours(work_hours_str: str, now: Optional[datetime] = None) -> bool:
    """
    Check whether the given (or current) time falls within work hours.

    Args:
        work_hours_str: Work hours range in "HH:MM-HH:MM" format
        now: Datetime to check (defaults to current local time)

    Returns:
        True if within work hours, False otherwise
    """
    if now is None:
        now = datetime.now()

    try:
        (start_h, start_m), (end_h, end_m) = parse_work_hours(work_hours_str)
    except ValueError:
        return False

    current_minutes = now.hour * 60 + now.minute
    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m

    return start_minutes <= current_minutes < end_minutes
