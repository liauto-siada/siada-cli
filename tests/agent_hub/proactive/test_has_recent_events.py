"""
Unit tests for ProactiveScheduler._has_recent_events.

This is the gating check for the daily run – it must correctly identify
whether any event file has been written within a configurable time window.
The method is side-effect free (no self attributes, no scheduler state), so
we test it directly by patching ``SIADA_HOME`` to a temporary directory.
"""

from datetime import datetime, timedelta
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

MODULE = "siada.agent_hub.proactive.scheduler"


def _make_event_file(events_dir: Path, name: str, age_hours: float) -> Path:
    """Create an event file and back-date its mtime (and atime) by ``age_hours``."""
    events_dir.mkdir(parents=True, exist_ok=True)
    path = events_dir / name
    path.write_text("x")
    past = datetime.now() - timedelta(hours=age_hours)
    ts = past.timestamp()
    os.utime(path, (ts, ts))
    return path


def _call(hours: int = 36) -> bool:
    """Invoke the method under test without constructing a ProactiveScheduler."""
    from siada.agent_hub.proactive.scheduler import ProactiveScheduler

    # The method does not touch any ``self`` attribute; SimpleNamespace is enough.
    return ProactiveScheduler._has_recent_events(SimpleNamespace(), hours=hours)


class TestHasRecentEvents:
    def test_events_dir_missing(self, tmp_path: Path):
        """When the events directory doesn't exist, return False."""
        with patch(f"{MODULE}.SIADA_HOME", tmp_path):
            assert _call(hours=36) is False

    def test_empty_events_dir(self, tmp_path: Path):
        """An empty events dir yields False."""
        (tmp_path / "workspace" / "memory" / "events").mkdir(parents=True)
        with patch(f"{MODULE}.SIADA_HOME", tmp_path):
            assert _call(hours=36) is False

    def test_recent_file_within_window(self, tmp_path: Path):
        """A file modified 1h ago is within a 36h window → True."""
        events_dir = tmp_path / "workspace" / "memory" / "events"
        _make_event_file(events_dir, "2026-04-21-10-00-foo.md", age_hours=1)
        with patch(f"{MODULE}.SIADA_HOME", tmp_path):
            assert _call(hours=36) is True

    def test_old_file_outside_window(self, tmp_path: Path):
        """A file modified 100h ago is outside a 36h window → False."""
        events_dir = tmp_path / "workspace" / "memory" / "events"
        _make_event_file(events_dir, "2026-04-15-10-00-foo.md", age_hours=100)
        with patch(f"{MODULE}.SIADA_HOME", tmp_path):
            assert _call(hours=36) is False

    def test_mixed_old_and_recent(self, tmp_path: Path):
        """If at least one file is recent, True regardless of other old files."""
        events_dir = tmp_path / "workspace" / "memory" / "events"
        _make_event_file(events_dir, "stale.md", age_hours=500)
        _make_event_file(events_dir, "fresh.md", age_hours=2)
        with patch(f"{MODULE}.SIADA_HOME", tmp_path):
            assert _call(hours=36) is True

    def test_hidden_files_ignored(self, tmp_path: Path):
        """Dotfiles must be skipped even when fresh (e.g. editor swap files)."""
        events_dir = tmp_path / "workspace" / "memory" / "events"
        _make_event_file(events_dir, ".hidden.md", age_hours=1)
        with patch(f"{MODULE}.SIADA_HOME", tmp_path):
            assert _call(hours=36) is False

    def test_subdirectories_ignored(self, tmp_path: Path):
        """Only regular files count; a fresh *subdir* must not flip the result."""
        events_dir = tmp_path / "workspace" / "memory" / "events"
        events_dir.mkdir(parents=True)
        (events_dir / "nested").mkdir()
        with patch(f"{MODULE}.SIADA_HOME", tmp_path):
            assert _call(hours=36) is False

    def test_custom_window_hours(self, tmp_path: Path):
        """The ``hours`` parameter is respected: file 10h old with 1h window → False."""
        events_dir = tmp_path / "workspace" / "memory" / "events"
        _make_event_file(events_dir, "somewhat-old.md", age_hours=10)
        with patch(f"{MODULE}.SIADA_HOME", tmp_path):
            assert _call(hours=1) is False
            # same file becomes "recent" under a wider window
            assert _call(hours=24) is True
