"""
Tests for daily_summary.py – verifies that the timezone bug is fixed.

The original bug: get_daily_summary_file_path() used datetime.now(timezone.utc).date()
which could produce different dates for Phase 1 (generation) and Phase 2 (IM send)
when they straddle the UTC midnight boundary in UTC+8.

After the fix, local time is used consistently so both phases resolve the same path.
"""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MODULE = "siada.agent_hub.proactive.prompts.task_templates.daily_summary"


def _create_event_file(events_dir: Path, d: date, suffix: str = "test-event") -> None:
    """Create a dummy event file for the given date."""
    events_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{d.strftime('%Y-%m-%d')}-12-00-{suffix}.md"
    (events_dir / fname).write_text("test event content")


# ---------------------------------------------------------------------------
# Tests for the UTC-vs-local timezone bug
# ---------------------------------------------------------------------------


class TestTimezoneConsistency:
    """Verify that generation and IM-send phases always resolve the same file."""

    def test_same_path_across_utc_midnight_boundary(self, tmp_path: Path):
        """
        Simulate the original bug scenario:
        - Phase 1 runs at 07:09 Shanghai (23:09 UTC previous day)
        - Phase 2 runs at 08:54 Shanghai (00:54 UTC current day)
        Both should resolve to the same summary file path.
        """
        from siada.agent_hub.proactive.prompts.task_templates.daily_summary import (
            get_daily_summary_file_path,
            get_last_work_date_str,
        )

        events_dir = tmp_path / "workspace" / "memory" / "events"
        # Create events for Apr 15 and Apr 16
        _create_event_file(events_dir, date(2026, 4, 15))
        _create_event_file(events_dir, date(2026, 4, 16))

        # Phase 1: 07:09 Shanghai time on Apr 17 = local date is Apr 17
        phase1_local = datetime(2026, 4, 17, 7, 9, 0)
        # Phase 2: 08:54 Shanghai time on Apr 17 = local date is still Apr 17
        phase2_local = datetime(2026, 4, 17, 8, 54, 0)

        with patch(f"{MODULE}.SIADA_HOME", tmp_path):
            # Re-evaluate _MEMORY_DIR after patching SIADA_HOME
            with patch(f"{MODULE}._MEMORY_DIR", tmp_path / "workspace" / "memory"):
                with patch(f"{MODULE}.datetime") as mock_dt:
                    mock_dt.now.return_value = phase1_local
                    mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
                    path1 = get_daily_summary_file_path()
                    date_str1 = get_last_work_date_str()

                with patch(f"{MODULE}.datetime") as mock_dt:
                    mock_dt.now.return_value = phase2_local
                    mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
                    path2 = get_daily_summary_file_path()
                    date_str2 = get_last_work_date_str()

        assert path1 == path2, (
            f"Phase 1 and Phase 2 resolved different paths!\n"
            f"  Phase 1: {path1}\n"
            f"  Phase 2: {path2}"
        )
        assert date_str1 == date_str2
        # Both should pick Apr 16 as the last work date (latest event before Apr 17)
        assert date_str1 == "2026-04-16"

    def test_utc_would_have_produced_different_dates(self):
        """
        Demonstrate that the old UTC-based logic would have given different
        dates for the two phases, confirming the bug existed.
        """
        # Phase 1: 07:09 Shanghai = 23:09 UTC on Apr 16
        phase1_utc_date = datetime(2026, 4, 16, 23, 9, 0, tzinfo=timezone.utc).date()
        # Phase 2: 08:54 Shanghai = 00:54 UTC on Apr 17
        phase2_utc_date = datetime(2026, 4, 17, 0, 54, 0, tzinfo=timezone.utc).date()

        assert phase1_utc_date != phase2_utc_date, (
            "UTC dates should differ to confirm the bug scenario"
        )
        assert phase1_utc_date == date(2026, 4, 16)
        assert phase2_utc_date == date(2026, 4, 17)


# ---------------------------------------------------------------------------
# Tests for get_daily_summary_file_path with explicit work_date_str
# ---------------------------------------------------------------------------


class TestGetDailySummaryFilePath:
    """Verify that get_daily_summary_file_path works with explicit dates."""

    def test_explicit_work_date_str(self, tmp_path: Path):
        """When work_date_str is provided, it should be used directly."""
        from siada.agent_hub.proactive.prompts.task_templates.daily_summary import (
            get_daily_summary_file_path,
        )

        with patch(f"{MODULE}._MEMORY_DIR", tmp_path / "workspace" / "memory"):
            path = get_daily_summary_file_path("2026-04-16")

        assert path == tmp_path / "workspace" / "memory" / "summary" / "2026-04-16_summary.md"

    def test_none_falls_back_to_auto_detection(self, tmp_path: Path):
        """When work_date_str is None, the date is auto-detected."""
        from siada.agent_hub.proactive.prompts.task_templates.daily_summary import (
            get_daily_summary_file_path,
        )

        events_dir = tmp_path / "workspace" / "memory" / "events"
        _create_event_file(events_dir, date(2026, 4, 15))

        fake_now = datetime(2026, 4, 16, 10, 0, 0)

        with patch(f"{MODULE}._MEMORY_DIR", tmp_path / "workspace" / "memory"):
            with patch(f"{MODULE}.datetime") as mock_dt:
                mock_dt.now.return_value = fake_now
                mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
                path = get_daily_summary_file_path()

        assert "2026-04-15_summary.md" in str(path)


# ---------------------------------------------------------------------------
# Tests for _find_last_work_date
# ---------------------------------------------------------------------------


class TestFindLastWorkDate:
    """Verify edge cases for _find_last_work_date."""

    def test_no_events_dir(self, tmp_path: Path):
        """When events dir doesn't exist, fall back to yesterday."""
        from siada.agent_hub.proactive.prompts.task_templates.daily_summary import (
            _find_last_work_date,
        )

        non_existent = tmp_path / "no_events"
        result = _find_last_work_date(non_existent, date(2026, 4, 17))
        assert result == date(2026, 4, 16)

    def test_empty_events_dir(self, tmp_path: Path):
        """When events dir exists but is empty, fall back to yesterday."""
        from siada.agent_hub.proactive.prompts.task_templates.daily_summary import (
            _find_last_work_date,
        )

        events_dir = tmp_path / "events"
        events_dir.mkdir()
        result = _find_last_work_date(events_dir, date(2026, 4, 17))
        assert result == date(2026, 4, 16)

    def test_picks_most_recent_date_before_today(self, tmp_path: Path):
        """Should pick the most recent event date that is strictly before today."""
        from siada.agent_hub.proactive.prompts.task_templates.daily_summary import (
            _find_last_work_date,
        )

        events_dir = tmp_path / "events"
        _create_event_file(events_dir, date(2026, 4, 13))
        _create_event_file(events_dir, date(2026, 4, 15))
        _create_event_file(events_dir, date(2026, 4, 16))
        # Also create one for today – should be excluded
        _create_event_file(events_dir, date(2026, 4, 17))

        result = _find_last_work_date(events_dir, date(2026, 4, 17))
        assert result == date(2026, 4, 16)
