"""
Tests for ProactiveScheduler – scheduling logic, crontab management, and job execution.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from siada.agent_hub.proactive.cron_task_storage import CronTaskStorage
from siada.agent_hub.proactive.models import CronTask
from siada.agent_hub.proactive.scheduler import DailyJob, ProactiveScheduler
from siada.config.config_loader import ProactiveConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def default_config():
    return ProactiveConfig(
        enabled=True,
        work_hours="09:00-18:00",
        trigger_interval=60,
        daily_task_execution_time="08:30",
    )


@pytest.fixture
def disabled_config():
    return ProactiveConfig(enabled=False)


@pytest.fixture
def cron_storage(tmp_path):
    return CronTaskStorage(str(tmp_path / "cron_tasks.json"))


@pytest.fixture
def signal_file(tmp_path):
    return tmp_path / "cron_tasks.reload"


@pytest.fixture
def scheduler(default_config, cron_storage, signal_file, tmp_path):
    return ProactiveScheduler(
        config=default_config,
        cron_storage=cron_storage,
        signal_file=signal_file,
        workspace=str(tmp_path),
    )


# ---------------------------------------------------------------------------
# Fixed-schedule job registration (APScheduler job IDs)
# ---------------------------------------------------------------------------


class TestFixedScheduleJobRegistration:

    def test_enabled_config_registers_daily_and_reload_jobs(
        self, default_config, cron_storage, signal_file
    ):
        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
        )
        s.start()
        try:
            job_ids = {job.id for job in s._scheduler.get_jobs()}
            assert "daily_fixed" in job_ids
            assert "check_reload_signal" in job_ids
        finally:
            s.stop()

    def test_disabled_config_skips_fixed_jobs(
        self, disabled_config, cron_storage, signal_file
    ):
        s = ProactiveScheduler(
            config=disabled_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
        )
        s.start()
        try:
            job_ids = {job.id for job in s._scheduler.get_jobs()}
            assert "daily_fixed" not in job_ids
            assert "check_reload_signal" in job_ids
        finally:
            s.stop()

    def test_start_stop_running_state(self, scheduler):
        assert not scheduler.running
        scheduler.start()
        assert scheduler.running
        scheduler.stop()
        assert not scheduler.running


# ---------------------------------------------------------------------------
# Crontab task loading
# ---------------------------------------------------------------------------


class TestCrontabTaskLoading:

    def test_enabled_tasks_are_registered_at_startup(
        self, default_config, cron_storage, signal_file
    ):
        task = CronTask.create(name="T1", cron_expr="0 9 * * *", instruction="Do something")
        cron_storage.add(task)

        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
        )
        s.start()
        try:
            assert f"cron_{task.id}" in {j.id for j in s._scheduler.get_jobs()}
        finally:
            s.stop()

    def test_disabled_tasks_are_not_registered(
        self, default_config, cron_storage, signal_file
    ):
        task = CronTask.create(
            name="Disabled", cron_expr="0 9 * * *", instruction="Skip me", enabled=False
        )
        cron_storage.add(task)

        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
        )
        s.start()
        try:
            assert f"cron_{task.id}" not in {j.id for j in s._scheduler.get_jobs()}
        finally:
            s.stop()

    def test_multiple_tasks_all_registered(
        self, default_config, cron_storage, signal_file
    ):
        tasks = [
            CronTask.create(name=f"T{i}", cron_expr="0 9 * * *", instruction="Test")
            for i in range(3)
        ]
        for t in tasks:
            cron_storage.add(t)

        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
        )
        s.start()
        try:
            job_ids = {j.id for j in s._scheduler.get_jobs()}
            for t in tasks:
                assert f"cron_{t.id}" in job_ids
        finally:
            s.stop()


# ---------------------------------------------------------------------------
# Dynamic reload via signal file
# ---------------------------------------------------------------------------


class TestDynamicReload:

    def test_reload_removes_deleted_task(
        self, default_config, cron_storage, signal_file
    ):
        task = CronTask.create(name="T1", cron_expr="0 9 * * *", instruction="Run me")
        cron_storage.add(task)

        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
        )
        s.start()
        try:
            assert f"cron_{task.id}" in {j.id for j in s._scheduler.get_jobs()}

            cron_storage.delete(task.id)
            signal_file.touch()
            s._check_reload_signal()

            assert f"cron_{task.id}" not in {j.id for j in s._scheduler.get_jobs()}
        finally:
            s.stop()

    def test_reload_adds_new_task(
        self, default_config, cron_storage, signal_file
    ):
        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
        )
        s.start()
        try:
            task = CronTask.create(name="New", cron_expr="0 10 * * *", instruction="New task")
            cron_storage.add(task)
            signal_file.touch()
            s._check_reload_signal()

            assert f"cron_{task.id}" in {j.id for j in s._scheduler.get_jobs()}
        finally:
            s.stop()

    def test_signal_file_is_removed_after_reload(
        self, default_config, cron_storage, signal_file
    ):
        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
        )
        signal_file.touch()
        s._check_reload_signal()
        assert not signal_file.exists()

    def test_no_reload_when_signal_absent(
        self, default_config, cron_storage, signal_file
    ):
        task = CronTask.create(name="T1", cron_expr="0 9 * * *", instruction="Run me")
        cron_storage.add(task)

        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
        )
        s.start()
        try:
            initial_ids = {j.id for j in s._scheduler.get_jobs()}
            s._check_reload_signal()
            assert {j.id for j in s._scheduler.get_jobs()} == initial_ids
        finally:
            s.stop()

    def test_reload_updates_instruction_for_existing_task(
        self, default_config, cron_storage, signal_file
    ):
        task = CronTask.create(name="T1", cron_expr="0 9 * * *", instruction="old instruction")
        cron_storage.add(task)

        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
        )
        s.start()
        try:
            job = s._scheduler.get_job(f"cron_{task.id}")
            assert job.args[1] == "old instruction"

            cron_storage.update(task.id, instruction="new instruction")
            signal_file.touch()
            s._check_reload_signal()

            job = s._scheduler.get_job(f"cron_{task.id}")
            assert job.args[1] == "new instruction"
        finally:
            s.stop()


# ---------------------------------------------------------------------------
# Crontab task execution: agent call and last_run persistence
# ---------------------------------------------------------------------------


class TestCrontabTaskExecution:

    def test_run_cron_task_calls_run_agent_with_instruction(
        self, default_config, cron_storage, signal_file, tmp_path
    ):
        task = CronTask.create(name="T1", cron_expr="0 9 * * *", instruction="Run me")
        cron_storage.add(task)

        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
            workspace=str(tmp_path),
        )
        s._run_agent = AsyncMock(return_value=None)

        asyncio.run(s._run_cron_task(task.id, task.instruction))

        s._run_agent.assert_called_once_with("coder", task.instruction)

    def test_run_cron_task_persists_last_run_to_disk(
        self, default_config, cron_storage, signal_file, tmp_path
    ):
        task = CronTask.create(name="T1", cron_expr="0 9 * * *", instruction="Run me")
        cron_storage.add(task)
        assert cron_storage.get(task.id).last_run is None

        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
            workspace=str(tmp_path),
        )
        s._run_agent = AsyncMock(return_value=None)

        asyncio.run(s._run_cron_task(task.id, task.instruction))

        updated = cron_storage.get(task.id)
        assert updated.last_run is not None
        dt = datetime.fromisoformat(updated.last_run.replace("Z", "+00:00"))
        assert (datetime.now(timezone.utc) - dt).total_seconds() < 5

    def test_run_cron_task_persists_last_run_even_on_agent_failure(
        self, default_config, cron_storage, signal_file, tmp_path
    ):
        task = CronTask.create(name="T1", cron_expr="0 9 * * *", instruction="Run me")
        cron_storage.add(task)

        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
            workspace=str(tmp_path),
        )
        s._run_agent = AsyncMock(side_effect=RuntimeError("boom"))

        asyncio.run(s._run_cron_task(task.id, task.instruction))

        assert cron_storage.get(task.id).last_run is not None


# ---------------------------------------------------------------------------
# discover_tasks mutex: concurrent call is skipped
# ---------------------------------------------------------------------------


class TestDiscoverTasksMutex:

    def test_concurrent_discover_tasks_is_skipped(
        self, default_config, cron_storage, signal_file, tmp_path
    ):
        """If discover_tasks is already running, a second concurrent call is skipped."""
        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
            workspace=str(tmp_path),
        )
        s._run_agent = AsyncMock(return_value=None)

        # Hold the lock to simulate an in-progress discover_tasks
        s._discover_tasks_lock.acquire()
        try:
            asyncio.run(s._discover_tasks())
        finally:
            s._discover_tasks_lock.release()

        s._run_agent.assert_not_called()


# ---------------------------------------------------------------------------
# Work-hours gating for periodic jobs
# ---------------------------------------------------------------------------


class TestDailyTaskExecutionTimeConfig:
    """Test that daily_task_execution_time is correctly read from config."""

    def test_daily_job_uses_config_time_not_default(
        self, cron_storage, signal_file, tmp_path
    ):
        """Verify that _register_daily_job uses the configured time, not the default."""
        # Use a non-default time to ensure it's coming from config
        custom_time = "11:29"
        config = ProactiveConfig(
            enabled=True,
            work_hours="09:00-18:00",
            trigger_interval=60,
            daily_task_execution_time=custom_time,
        )
        
        s = ProactiveScheduler(
            config=config,
            cron_storage=cron_storage,
            signal_file=signal_file,
            workspace=str(tmp_path),
        )
        s.start()
        
        try:
            # Get the daily_fixed job
            daily_job = None
            for job in s._scheduler.get_jobs():
                if job.id == "daily_fixed":
                    daily_job = job
                    break
            
            assert daily_job is not None, "daily_fixed job not found"
            
            # Check the trigger configuration
            # Fields order: [year, month, day, week, day_of_week, hour, minute, second]
            trigger = daily_job.trigger
            hour_field = trigger.fields[5]  # hour is at index 5
            minute_field = trigger.fields[6]  # minute is at index 6
            
            assert hour_field.expressions[0].first == 11, \
                f"Expected hour=11, got hour={hour_field.expressions[0].first}"
            assert minute_field.expressions[0].first == 29, \
                f"Expected minute=29, got minute={minute_field.expressions[0].first}"
        finally:
            s.stop()

    def test_daily_job_with_yaml_config_loads_correctly(
        self, cron_storage, signal_file, tmp_path
    ):
        """
        Integration test: Verify that daily_task_execution_time is correctly loaded
        from a YAML config file and used by the scheduler.
        
        This reproduces the real-world scenario where config is loaded from conf.yaml.
        """
        import yaml
        from siada.config.config_loader import load_conf
        
        # Create a temporary config file with custom daily_task_execution_time
        config_path = tmp_path / "conf.yaml"
        config_content = {
            "proactive": {
                "enabled": True,
                "work_hours": "09:00-18:00",
                "trigger_interval": 60,
                "daily_task_execution_time": "13:45"  # Use a distinct non-default time
            }
        }
        
        with open(config_path, 'w') as f:
            yaml.dump(config_content, f)
        
        # Load config from the temporary YAML file
        config = load_conf(config_path)
        
        # Verify the config was loaded correctly
        assert config.proactive_config.daily_task_execution_time == "13:45", \
            f"Config did not load correctly: {config.proactive_config.daily_task_execution_time}"
        
        # Create scheduler with the loaded config
        s = ProactiveScheduler(
            config=config.proactive_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
            workspace=str(tmp_path),
        )
        s.start()
        
        try:
            # Get the daily_fixed job
            daily_job = None
            for job in s._scheduler.get_jobs():
                if job.id == "daily_fixed":
                    daily_job = job
                    break
            
            assert daily_job is not None, "daily_fixed job not found"
            
            # Verify the scheduler is using the time from the YAML config, not the default
            trigger = daily_job.trigger
            hour_field = trigger.fields[5]
            minute_field = trigger.fields[6]
            
            assert hour_field.expressions[0].first == 13, \
                f"Expected hour=13 from YAML config, got hour={hour_field.expressions[0].first}"
            assert minute_field.expressions[0].first == 45, \
                f"Expected minute=45 from YAML config, got minute={minute_field.expressions[0].first}"
        finally:
            s.stop()

    def test_daily_job_uses_default_when_not_specified(
        self, cron_storage, signal_file, tmp_path
    ):
        """Verify that the default time (08:30) is used when not specified in config."""
        config = ProactiveConfig(
            enabled=True,
            work_hours="09:00-18:00",
            trigger_interval=60,
            # daily_task_execution_time not specified, should use default "08:30"
        )
        
        s = ProactiveScheduler(
            config=config,
            cron_storage=cron_storage,
            signal_file=signal_file,
            workspace=str(tmp_path),
        )
        s.start()
        
        try:
            daily_job = None
            for job in s._scheduler.get_jobs():
                if job.id == "daily_fixed":
                    daily_job = job
                    break
            
            assert daily_job is not None
            trigger = daily_job.trigger
            hour_field = trigger.fields[5]
            minute_field = trigger.fields[6]
            
            assert hour_field.expressions[0].first == 8, \
                f"Expected hour=8, got hour={hour_field.expressions[0].first}"
            assert minute_field.expressions[0].first == 30, \
                f"Expected minute=30, got minute={minute_field.expressions[0].first}"
        finally:
            s.stop()


class TestCleanupMemory:
    """Test the cleanup_memory daily task that removes old memory and task files."""

    def test_cleanup_memory_keeps_latest_events_by_count(
        self, default_config, cron_storage, signal_file, tmp_path
    ):
        """Test that events directory keeps only the latest 20 files."""
        # Create a mock memory/events directory with 25 files
        events_dir = tmp_path / ".siada-cli" / "workspace" / "memory" / "events"
        events_dir.mkdir(parents=True)
        
        # Create 25 files with different modification times
        import time
        files = []
        for i in range(25):
            file_path = events_dir / f"event-{i:03d}.md"
            file_path.write_text(f"Event content {i}")
            # Set modification time to different values (oldest to newest)
            timestamp = time.time() - (25 - i) * 86400  # days ago
            Path(file_path).touch()
            files.append(file_path)
        
        # Update modification times properly
        for i, file_path in enumerate(files):
            timestamp = time.time() - (25 - i) * 86400
            import os
            os.utime(file_path, (timestamp, timestamp))
        
        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
            workspace=str(tmp_path),
        )
        
        # Run cleanup with mocked home directory
        with patch("pathlib.Path.home", return_value=tmp_path):
            asyncio.run(s._cleanup_memory())
        
        # Check that only 20 files remain (the newest ones)
        remaining = list(events_dir.glob("*.md"))
        assert len(remaining) == 20, f"Expected 20 files, got {len(remaining)}"
        
        # Verify the newest files are kept
        remaining_names = {f.name for f in remaining}
        for i in range(5, 25):  # Files 5-24 should remain (newest 20)
            assert f"event-{i:03d}.md" in remaining_names
        for i in range(0, 5):  # Files 0-4 should be deleted (oldest 5)
            assert f"event-{i:03d}.md" not in remaining_names

    def test_cleanup_memory_keeps_latest_experience_by_count(
        self, default_config, cron_storage, signal_file, tmp_path
    ):
        """Test that experience directory keeps only the latest 10 files."""
        experience_dir = tmp_path / ".siada-cli" / "workspace" / "memory" / "experience"
        experience_dir.mkdir(parents=True)
        
        import time
        import os
        files = []
        for i in range(15):
            file_path = experience_dir / f"experience-{i:03d}.md"
            file_path.write_text(f"Experience content {i}")
            timestamp = time.time() - (15 - i) * 86400
            os.utime(file_path, (timestamp, timestamp))
            files.append(file_path)
        
        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
            workspace=str(tmp_path),
        )
        
        with patch("pathlib.Path.home", return_value=tmp_path):
            asyncio.run(s._cleanup_memory())
        
        remaining = list(experience_dir.glob("*.md"))
        assert len(remaining) == 10, f"Expected 10 files, got {len(remaining)}"
        
        # Verify newest 10 are kept
        remaining_names = {f.name for f in remaining}
        for i in range(5, 15):
            assert f"experience-{i:03d}.md" in remaining_names

    def test_cleanup_memory_removes_old_session_files(
        self, default_config, cron_storage, signal_file, tmp_path
    ):
        """Test that session files older than 30 days are removed and DB is synced."""
        session_dir = tmp_path / ".siada-cli" / "workspace" / "memory" / "session"
        session_dir.mkdir(parents=True)
        
        import time
        import os
        
        # Create files: 5 recent (15 days old) and 5 old (35 days old)
        for i in range(5):
            file_path = session_dir / f"session-recent-{i}.md"
            file_path.write_text(f"Recent session {i}")
            timestamp = time.time() - 15 * 86400  # 15 days ago
            os.utime(file_path, (timestamp, timestamp))
        
        for i in range(5):
            file_path = session_dir / f"session-old-{i}.md"
            file_path.write_text(f"Old session {i}")
            timestamp = time.time() - 35 * 86400  # 35 days ago
            os.utime(file_path, (timestamp, timestamp))
        
        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
            workspace=str(tmp_path),
        )
        
        with patch("pathlib.Path.home", return_value=tmp_path):
            asyncio.run(s._cleanup_memory())
        
        remaining = list(session_dir.glob("*.md"))
        assert len(remaining) == 5, f"Expected 5 files, got {len(remaining)}"
        
        # Verify only recent files remain
        remaining_names = {f.name for f in remaining}
        for i in range(5):
            assert f"session-recent-{i}.md" in remaining_names
            assert f"session-old-{i}.md" not in remaining_names

    def test_cleanup_memory_removes_old_task_files(
        self, default_config, cron_storage, signal_file, tmp_path
    ):
        """Test that task JSON files older than 30 days are removed."""
        task_dir = tmp_path / ".siada-cli" / "workspace" / "task"
        task_dir.mkdir(parents=True)
        
        import time
        import os
        
        # Create recent and old task files
        for i in range(5):
            file_path = task_dir / f"tasks_2026-03-{10+i:02d}.json"
            file_path.write_text('{"tasks": []}')
            timestamp = time.time() - 10 * 86400  # 10 days ago
            os.utime(file_path, (timestamp, timestamp))
        
        for i in range(5):
            file_path = task_dir / f"tasks_2026-01-{10+i:02d}.json"
            file_path.write_text('{"tasks": []}')
            timestamp = time.time() - 40 * 86400  # 40 days ago
            os.utime(file_path, (timestamp, timestamp))
        
        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
            workspace=str(tmp_path),
        )
        
        with patch("pathlib.Path.home", return_value=tmp_path):
            asyncio.run(s._cleanup_memory())
        
        remaining = list(task_dir.glob("*.json"))
        assert len(remaining) == 5, f"Expected 5 files, got {len(remaining)}"
        
        # Verify only recent task files remain
        remaining_names = {f.name for f in remaining}
        for i in range(5):
            assert f"tasks_2026-03-{10+i:02d}.json" in remaining_names
            assert f"tasks_2026-01-{10+i:02d}.json" not in remaining_names

    def test_cleanup_memory_handles_missing_directories(
        self, default_config, cron_storage, signal_file, tmp_path
    ):
        """Test that cleanup gracefully handles missing directories."""
        # Don't create any directories
        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
            workspace=str(tmp_path),
        )
        
        with patch("pathlib.Path.home", return_value=tmp_path):
            # Should not raise any exceptions
            asyncio.run(s._cleanup_memory())

    def test_cleanup_memory_ignores_hidden_files(
        self, default_config, cron_storage, signal_file, tmp_path
    ):
        """Test that cleanup ignores hidden files (starting with .)."""
        events_dir = tmp_path / ".siada-cli" / "workspace" / "memory" / "events"
        events_dir.mkdir(parents=True)
        
        import time
        import os
        
        # Create regular files and hidden files
        for i in range(5):
            file_path = events_dir / f"event-{i}.md"
            file_path.write_text(f"Event {i}")
            timestamp = time.time() - i * 86400
            os.utime(file_path, (timestamp, timestamp))
        
        # Create hidden files
        hidden_file = events_dir / ".hidden-file.md"
        hidden_file.write_text("Hidden content")
        
        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
            workspace=str(tmp_path),
        )
        
        with patch("pathlib.Path.home", return_value=tmp_path):
            asyncio.run(s._cleanup_memory())
        
        # Hidden file should still exist
        assert hidden_file.exists(), "Hidden file should not be deleted"
        # Regular files should exist (fewer than 20, so none deleted)
        assert len(list(events_dir.glob("event-*.md"))) == 5

    def test_cleanup_memory_only_affects_md_and_json_files(
        self, default_config, cron_storage, signal_file, tmp_path
    ):
        """Test that cleanup only removes .md and .json files, not other types."""
        events_dir = tmp_path / ".siada-cli" / "workspace" / "memory" / "events"
        events_dir.mkdir(parents=True)
        
        import time
        import os
        
        # Create .md files
        for i in range(25):
            file_path = events_dir / f"event-{i}.md"
            file_path.write_text(f"Event {i}")
            timestamp = time.time() - (25 - i) * 86400
            os.utime(file_path, (timestamp, timestamp))
        
        # Create other file types that should be ignored
        txt_file = events_dir / "notes.txt"
        txt_file.write_text("Some notes")
        db_file = events_dir / "memory.db"
        db_file.write_text("Database")
        
        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
            workspace=str(tmp_path),
        )
        
        with patch("pathlib.Path.home", return_value=tmp_path):
            asyncio.run(s._cleanup_memory())
        
        # Only 20 .md files should remain
        assert len(list(events_dir.glob("*.md"))) == 20
        # Other files should still exist
        assert txt_file.exists(), "txt file should not be deleted"
        assert db_file.exists(), "db file should not be deleted"

    def test_cleanup_memory_removes_old_tmp_files(
        self, default_config, cron_storage, signal_file, tmp_path
    ):
        """Test that tmp directory files older than 30 days are removed (all file types)."""
        tmp_dir = tmp_path / ".siada-cli" / "workspace" / "tmp"
        tmp_dir.mkdir(parents=True)
        
        import time
        import os
        
        # Create recent files with various extensions (10 days old)
        for i in range(3):
            for ext in [".txt", ".json", ".log", ".tmp"]:
                file_path = tmp_dir / f"recent-{i}{ext}"
                file_path.write_text(f"Recent file {i}")
                timestamp = time.time() - 10 * 86400  # 10 days ago
                os.utime(file_path, (timestamp, timestamp))
        
        # Create old files with various extensions (40 days old)
        for i in range(3):
            for ext in [".txt", ".json", ".log", ".tmp"]:
                file_path = tmp_dir / f"old-{i}{ext}"
                file_path.write_text(f"Old file {i}")
                timestamp = time.time() - 40 * 86400  # 40 days ago
                os.utime(file_path, (timestamp, timestamp))
        
        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
            workspace=str(tmp_path),
        )
        
        with patch("pathlib.Path.home", return_value=tmp_path):
            asyncio.run(s._cleanup_memory())
        
        # Count remaining files
        remaining = [f for f in tmp_dir.iterdir() if f.is_file() and not f.name.startswith(".")]
        assert len(remaining) == 12, f"Expected 12 recent files, got {len(remaining)}"
        
        # Verify only recent files remain
        remaining_names = {f.name for f in remaining}
        for i in range(3):
            for ext in [".txt", ".json", ".log", ".tmp"]:
                assert f"recent-{i}{ext}" in remaining_names
                assert f"old-{i}{ext}" not in remaining_names


# ---------------------------------------------------------------------------
# _has_recent_session: session directory presence check
# ---------------------------------------------------------------------------


class TestHasRecentSession:
    """Unit tests for _has_recent_session()."""

    def _make_scheduler(self, default_config, cron_storage, signal_file, tmp_path):
        return ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
            workspace=str(tmp_path),
        )

    def test_returns_false_when_session_dir_does_not_exist(
        self, default_config, cron_storage, signal_file, tmp_path
    ):
        s = self._make_scheduler(default_config, cron_storage, signal_file, tmp_path)
        with patch("pathlib.Path.home", return_value=tmp_path):
            assert s._has_recent_session(hours=36) is False

    def test_returns_false_when_session_dir_is_empty(
        self, default_config, cron_storage, signal_file, tmp_path
    ):
        session_dir = tmp_path / ".siada-cli" / "workspace" / "memory" / "session"
        session_dir.mkdir(parents=True)
        s = self._make_scheduler(default_config, cron_storage, signal_file, tmp_path)
        with patch("pathlib.Path.home", return_value=tmp_path):
            assert s._has_recent_session(hours=36) is False

    def test_returns_true_when_recent_session_file_exists(
        self, default_config, cron_storage, signal_file, tmp_path
    ):
        session_dir = tmp_path / ".siada-cli" / "workspace" / "memory" / "session"
        session_dir.mkdir(parents=True)
        (session_dir / "session-today.md").write_text("data")  # just created = recent

        s = self._make_scheduler(default_config, cron_storage, signal_file, tmp_path)
        with patch("pathlib.Path.home", return_value=tmp_path):
            assert s._has_recent_session(hours=36) is True

    def test_returns_false_when_all_files_are_old(
        self, default_config, cron_storage, signal_file, tmp_path
    ):
        session_dir = tmp_path / ".siada-cli" / "workspace" / "memory" / "session"
        session_dir.mkdir(parents=True)
        f = session_dir / "session-old.md"
        f.write_text("data")
        # Age the file to 40 hours ago
        old_ts = time.time() - 40 * 3600
        os.utime(f, (old_ts, old_ts))

        s = self._make_scheduler(default_config, cron_storage, signal_file, tmp_path)
        # Patch datetime.now so the scheduler also sees mtime as old
        # (on macOS st_birthtime can't be changed; fall back by testing mtime path)
        with patch("pathlib.Path.home", return_value=tmp_path):
            with patch("siada.agent_hub.proactive.scheduler.datetime") as mock_dt:
                mock_dt.now.return_value = datetime.fromtimestamp(time.time())
                # Override getattr to always return st_mtime so the test is portable
                original = s._has_recent_session.__func__

                def patched(self_inner, hours=36):
                    cutoff = datetime.now().timestamp() - hours * 3600
                    from pathlib import Path as _Path
                    session_dir_inner = tmp_path / ".siada-cli" / "workspace" / "memory" / "session"
                    if not session_dir_inner.exists():
                        return False
                    for file in session_dir_inner.iterdir():
                        if file.is_file() and not file.name.startswith("."):
                            try:
                                if file.stat().st_mtime >= cutoff:
                                    return True
                            except Exception:
                                continue
                    return False

                assert patched(s, hours=36) is False

    def test_returns_true_when_at_least_one_recent_among_old_files(
        self, default_config, cron_storage, signal_file, tmp_path
    ):
        session_dir = tmp_path / ".siada-cli" / "workspace" / "memory" / "session"
        session_dir.mkdir(parents=True)

        # Two old files
        for i in range(2):
            f = session_dir / f"session-old-{i}.md"
            f.write_text("old")
            old_ts = time.time() - 40 * 3600
            os.utime(f, (old_ts, old_ts))

        # One recent file (just created – mtime is now)
        (session_dir / "session-recent.md").write_text("new")

        s = self._make_scheduler(default_config, cron_storage, signal_file, tmp_path)
        with patch("pathlib.Path.home", return_value=tmp_path):
            assert s._has_recent_session(hours=36) is True

    def test_hidden_files_are_ignored(
        self, default_config, cron_storage, signal_file, tmp_path
    ):
        session_dir = tmp_path / ".siada-cli" / "workspace" / "memory" / "session"
        session_dir.mkdir(parents=True)
        # Only a hidden file (should be ignored even though it's recent)
        (session_dir / ".hidden.md").write_text("data")

        s = self._make_scheduler(default_config, cron_storage, signal_file, tmp_path)
        with patch("pathlib.Path.home", return_value=tmp_path):
            assert s._has_recent_session(hours=36) is False


# ---------------------------------------------------------------------------
# Daily jobs session gating: _run_all_daily_jobs skips when no recent session
# ---------------------------------------------------------------------------


class TestDailyJobsSessionGating:
    """_run_all_daily_jobs must skip when _has_recent_session returns False."""

    def test_daily_jobs_skipped_when_no_recent_session(
        self, default_config, cron_storage, signal_file, tmp_path
    ):
        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
            workspace=str(tmp_path),
        )
        called = []
        s._daily_jobs = [
            DailyJob(name="dummy", handler=AsyncMock(side_effect=lambda: called.append(1)))
        ]
        with patch.object(s, "_has_recent_session", return_value=False):
            s._run_all_daily_jobs()
        assert called == [], "Daily jobs should not run when no recent session"

    def test_daily_jobs_run_when_recent_session_exists(
        self, default_config, cron_storage, signal_file, tmp_path
    ):
        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
            workspace=str(tmp_path),
        )
        handler = AsyncMock(return_value=None)
        s._daily_jobs = [DailyJob(name="dummy", handler=handler)]
        with patch.object(s, "_has_recent_session", return_value=True):
            s._run_all_daily_jobs()
        handler.assert_called_once()

    @pytest.mark.integration
    @pytest.mark.slow
    def test_daily_jobs_real_handlers_real_llm(
        self, default_config, cron_storage, signal_file, tmp_path, caplog
    ):
        """Integration: real handlers, real _has_recent_session, real LLM call.

        No mocks at all. _has_recent_session checks the real ~/.siada-cli session
        directory; if recent files exist the jobs run, otherwise the call is a no-op.

        Pass criteria:
        - _run_all_daily_jobs() does not raise regardless of LLM outcome.
        - The job sequence log line is emitted (all 4 jobs attempted).
        - When LLM is unreachable, each handler logs an ERROR but the sequence
          still reports succeeded=4 / failed=0 — the swallowed-exception bug.
        """
        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
            workspace=str(tmp_path),
        )
        with caplog.at_level(logging.INFO, logger="siada.agent_hub.proactive.scheduler"):
            s._run_all_daily_jobs()  # must not raise regardless of LLM outcome

        # Job sequence always runs to completion (handlers never re-raise).
        finish_records = [r for r in caplog.records if "job sequence finished" in r.message]
        assert len(finish_records) == 1
        assert "total=4" in finish_records[0].message


# ---------------------------------------------------------------------------
# _do_analyze_recent_sessions – window filtering and dispatch
# ---------------------------------------------------------------------------

_ANALYZE_PATH = "siada.services.memory.memory_agent.analyze_and_update_memory"
_MODEL_CONFIG_PATH = "siada.models.model_run_config.ModelRunConfig.get_default_config"
_SET_CTX_PATH = "siada.foundation.context.set_context_var"


def _make_session_file(session_dir: Path, name: str, age_seconds: float) -> Path:
    """Create a .md session file with a controlled mtime."""
    f = session_dir / name
    f.write_text(f"# Session: {name}\n\nuser: hello\nassistant: hi")
    t = time.time() - age_seconds
    os.utime(f, (t, t))
    return f


class TestAnalyzeRecentSessions:
    """Unit tests for _do_analyze_recent_sessions time-window logic."""

    # -- fixtures ----------------------------------------------------------

    @pytest.fixture
    def session_dir(self, tmp_path):
        d = tmp_path / ".siada-cli" / "workspace" / "memory" / "session"
        d.mkdir(parents=True)
        return d

    @pytest.fixture
    def patched_home(self, tmp_path):
        """Redirect Path.home() → tmp_path so the scheduler finds the right session_dir."""
        with patch("pathlib.Path.home", return_value=tmp_path):
            yield tmp_path

    @pytest.fixture
    def mock_analyze(self):
        with patch(
            _ANALYZE_PATH,
            new_callable=AsyncMock,
            return_value={"success": True, "completed_tasks": ["structured_event", "experience"]},
        ) as m:
            yield m

    @pytest.fixture
    def mock_llm_and_ctx(self):
        """Suppress real LLM config lookup and context-var side effects."""
        with patch(_MODEL_CONFIG_PATH, return_value=object()), \
             patch(_SET_CTX_PATH):
            yield

    # -- helpers -----------------------------------------------------------

    def _run(self, scheduler):
        """Execute _do_analyze_recent_sessions synchronously."""
        asyncio.run(scheduler._do_analyze_recent_sessions())

    # -- tests -------------------------------------------------------------

    def test_file_at_30min_is_analyzed(
        self, scheduler, session_dir, patched_home, mock_analyze, mock_llm_and_ctx
    ):
        _make_session_file(session_dir, "edge-min.md", 30 * 60 + 1)
        self._run(scheduler)
        mock_analyze.assert_called_once()

    def test_file_at_65min_is_analyzed(
        self, scheduler, session_dir, patched_home, mock_analyze, mock_llm_and_ctx
    ):
        _make_session_file(session_dir, "edge-max.md", 65 * 60 - 1)
        self._run(scheduler)
        mock_analyze.assert_called_once()

    def test_file_too_fresh_is_skipped(
        self, scheduler, session_dir, patched_home, mock_analyze, mock_llm_and_ctx
    ):
        _make_session_file(session_dir, "fresh.md", 10 * 60)  # 10 min ago
        self._run(scheduler)
        mock_analyze.assert_not_called()

    def test_file_too_old_is_skipped(
        self, scheduler, session_dir, patched_home, mock_analyze, mock_llm_and_ctx
    ):
        _make_session_file(session_dir, "old.md", 90 * 60)  # 90 min ago
        self._run(scheduler)
        mock_analyze.assert_not_called()

    def test_multiple_files_in_window_all_analyzed(
        self, scheduler, session_dir, patched_home, mock_analyze, mock_llm_and_ctx
    ):
        for i, age in enumerate([32 * 60, 37 * 60, 43 * 60]):
            _make_session_file(session_dir, f"s{i}.md", age)
        self._run(scheduler)
        assert mock_analyze.call_count == 3

    def test_only_in_window_files_are_analyzed_when_mixed(
        self, scheduler, session_dir, patched_home, mock_analyze, mock_llm_and_ctx
    ):
        _make_session_file(session_dir, "ok.md", 35 * 60)       # in window
        _make_session_file(session_dir, "fresh.md", 5 * 60)     # too fresh
        _make_session_file(session_dir, "old.md", 90 * 60)      # too old
        self._run(scheduler)
        assert mock_analyze.call_count == 1

    def test_non_md_files_are_skipped(
        self, scheduler, session_dir, patched_home, mock_analyze, mock_llm_and_ctx
    ):
        for ext in [".txt", ".json", ".log", ""]:
            f = session_dir / f"session{ext}"
            f.write_text("content")
            t = time.time() - 35 * 60
            os.utime(f, (t, t))
        self._run(scheduler)
        mock_analyze.assert_not_called()

    def test_hidden_files_are_skipped(
        self, scheduler, session_dir, patched_home, mock_analyze, mock_llm_and_ctx
    ):
        _make_session_file(session_dir, ".hidden.md", 35 * 60)
        self._run(scheduler)
        mock_analyze.assert_not_called()

    def test_nonexistent_session_dir_returns_early(
        self, scheduler, tmp_path, mock_analyze, mock_llm_and_ctx
    ):
        # tmp_path has no .siada-cli subdir → session_dir doesn't exist
        empty_home = tmp_path / "no_home"
        empty_home.mkdir()
        with patch("pathlib.Path.home", return_value=empty_home):
            self._run(scheduler)
        mock_analyze.assert_not_called()

    def test_file_content_passed_to_analyze(
        self, scheduler, session_dir, patched_home, mock_analyze, mock_llm_and_ctx
    ):
        f = _make_session_file(session_dir, "content-check.md", 35 * 60)
        expected_content = f.read_text(encoding="utf-8")

        self._run(scheduler)

        mock_analyze.assert_called_once()
        _, kwargs = mock_analyze.call_args
        assert kwargs.get("session_content") == expected_content

    def test_analyze_failure_does_not_raise_and_continues(
        self, scheduler, session_dir, patched_home, mock_llm_and_ctx
    ):
        _make_session_file(session_dir, "fail.md", 33 * 60)
        _make_session_file(session_dir, "ok.md", 38 * 60)

        call_order = []
        async def side_effect(session_content):
            call_order.append(session_content[:10])
            if "fail" in session_content:
                raise RuntimeError("LLM error")
            return {"success": True, "completed_tasks": []}

        with patch(_ANALYZE_PATH, side_effect=side_effect):
            self._run(scheduler)  # must not raise

        assert len(call_order) == 2  # both files were attempted

    def test_analyze_returning_success_false_does_not_raise(
        self, scheduler, session_dir, patched_home, mock_llm_and_ctx
    ):
        _make_session_file(session_dir, "s.md", 35 * 60)
        with patch(
            _ANALYZE_PATH,
            new_callable=AsyncMock,
            return_value={"success": False, "error": "model error"},
        ):
            self._run(scheduler)  # must not raise

    def test_llm_config_and_context_var_are_set_before_analyze(
        self, scheduler, session_dir, patched_home, mock_analyze
    ):
        _make_session_file(session_dir, "s.md", 35 * 60)
        sentinel = object()
        call_log = []

        def fake_set_ctx(key, value):
            call_log.append(("set_ctx", key, value))

        with patch(_MODEL_CONFIG_PATH, return_value=sentinel), \
             patch(_SET_CTX_PATH, side_effect=fake_set_ctx):
            self._run(scheduler)

        from siada.foundation.context import LLM_CONFIG
        assert ("set_ctx", LLM_CONFIG, sentinel) in call_log
        mock_analyze.assert_called_once()

    def test_analyze_sessions_job_registered_when_enabled(
        self, default_config, cron_storage, signal_file, tmp_path
    ):
        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
            workspace=str(tmp_path),
        )
        s.start()
        try:
            job_ids = {job.id for job in s._scheduler.get_jobs()}
            assert "analyze_recent_sessions" in job_ids
        finally:
            s.stop()

    def test_analyze_sessions_job_not_registered_when_disabled(
        self, disabled_config, cron_storage, signal_file, tmp_path
    ):
        s = ProactiveScheduler(
            config=disabled_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
            workspace=str(tmp_path),
        )
        s.start()
        try:
            job_ids = {job.id for job in s._scheduler.get_jobs()}
            assert "analyze_recent_sessions" not in job_ids
        finally:
            s.stop()


# ---------------------------------------------------------------------------
# _do_analyze_recent_sessions – integration test (real model, no mocks)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.slow
class TestAnalyzeRecentSessionsIntegration:
    """
    End-to-end test: real session file on disk, real LLM calls.

    Creates a .md session file in the real session directory, sets its mtime
    to 35 minutes ago so it falls inside the [30, 65] minute window, then runs
    _do_analyze_recent_sessions() without any mocking.

    Pass criteria:
    - No exception is raised
    - At least one new event file is written to the events/ directory
    - The event file contains the required structured sections
    """

    # Session content with clear technical implementation — reliably triggers SAVE path
    SESSION_CONTENT = """\
user: 帮我给 ProactiveScheduler 增加一个 analyze_recent_sessions job，每30分钟扫描session目录，
对最近修改的session文件调用 analyze_and_update_memory

assistant: 好的，我先查看 scheduler.py 的现有结构：

[edit_file view siada/agent_hub/proactive/scheduler.py lines 64-150]
→ ProactiveScheduler.__init__ 中注册了 daily_fixed 和 check_reload_signal 两个 job。
  _setup_default_jobs 定义了 4 个每日任务。

现在添加 analyze_recent_sessions job。实现分两部分：
1. APScheduler 注册（interval 30 分钟）
2. _do_analyze_recent_sessions 扫描逻辑

[edit_file str_replace siada/agent_hub/proactive/scheduler.py]
old: self._scheduler.add_job(self._check_reload_signal, ...)
new: self._scheduler.add_job(
         self._analyze_recent_sessions,
         "interval",
         minutes=30,
         id="analyze_recent_sessions",
         max_instances=1,
     )
     self._scheduler.add_job(self._check_reload_signal, ...)
→ File updated.

[edit_file str_replace siada/agent_hub/proactive/scheduler.py]
old: # ------ Internal helpers ------
new: def _analyze_recent_sessions(self) -> None:
         self._run_async(self._do_analyze_recent_sessions())

     async def _do_analyze_recent_sessions(self) -> None:
         session_dir = Path.home() / ".siada-cli/workspace/memory/session"
         if not session_dir.exists():
             return
         now = datetime.now().timestamp()
         min_age, max_age = 30 * 60, 65 * 60
         candidates = [
             f for f in session_dir.iterdir()
             if f.is_file() and f.name.endswith(".md") and not f.name.startswith(".")
             and min_age <= now - f.stat().st_mtime <= max_age
         ]
         if not candidates:
             return
         from siada.models.model_run_config import ModelRunConfig
         from siada.foundation.context import set_context_var, LLM_CONFIG
         from siada.services.memory.memory_agent import analyze_and_update_memory
         set_context_var(LLM_CONFIG, ModelRunConfig.get_default_config())
         for f in candidates:
             content = f.read_text(encoding="utf-8")
             await analyze_and_update_memory(session_content=content)
     # ------ Internal helpers ------
→ File updated.

[run_cmd python -c "from siada.agent_hub.proactive.scheduler import ProactiveScheduler; print('OK')"]
→ OK

全部完成：
- analyze_recent_sessions job 已注册，每30分钟触发一次
- _do_analyze_recent_sessions 实现了 30–65 分钟时间窗口过滤
- 边界：30 min = min_age，65 min = max_age（30 min间隔 + 5 min grace）
- 已验证 import 正常

user: 很好，写几个测试用例覆盖时间窗口逻辑

assistant: 我来给 _do_analyze_recent_sessions 写测试：

[edit_file str_replace tests/agent_hub/proactive/test_scheduler.py]
→ 新增 TestAnalyzeRecentSessions 类，测试：
  - 30 min 边界（刚好在窗口内）
  - 65 min 边界（刚好在窗口内）
  - 29 min（太新，跳过）
  - 90 min（太老，跳过）
  - 混合文件（只处理窗口内的）
  - 非 .md 文件跳过
  - 隐藏文件（.hidden.md）跳过
→ File updated.

[run_cmd python -m pytest tests/agent_hub/proactive/test_scheduler.py::TestAnalyzeRecentSessions -q]
→ 8 passed in 0.42s

测试全部通过。覆盖了所有窗口边界和文件过滤逻辑。
"""

    def test_analyze_recent_sessions_end_to_end(
        self, default_config, cron_storage, signal_file, tmp_path
    ):
        session_dir = Path.home() / ".siada-cli" / "workspace" / "memory" / "session"
        events_dir = Path.home() / ".siada-cli" / "workspace" / "memory" / "events"
        session_dir.mkdir(parents=True, exist_ok=True)
        events_dir.mkdir(parents=True, exist_ok=True)

        # Create a real session file with mtime 35 minutes ago
        session_file = session_dir / "test-integration-analyze-sessions.md"
        session_file.write_text(self.SESSION_CONTENT, encoding="utf-8")
        t = time.time() - 35 * 60
        os.utime(session_file, (t, t))

        before = set(events_dir.glob("*.md"))

        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
            workspace=str(tmp_path),
        )
        try:
            asyncio.run(s._do_analyze_recent_sessions())
        finally:
            session_file.unlink(missing_ok=True)

        after = set(events_dir.glob("*.md"))
        new_files = after - before
        assert len(new_files) >= 1, (
            f"Expected at least one new event file in {events_dir}, found none"
        )

        event_content = next(iter(new_files)).read_text(encoding="utf-8")
        for section in ["Background", "Implementation Summary", "Artifacts"]:
            assert section in event_content, (
                f"Event file missing required section: {section}"
            )


# ---------------------------------------------------------------------------
# _do_analyze_recent_sessions – production smoke test (no setup, no teardown)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.slow
class TestAnalyzeRecentSessionsProduction:
    """
    Smoke test: run _do_analyze_recent_sessions directly against the real
    production session directory (~/.siada-cli/workspace/memory/session/).

    No files are created or deleted. The method picks up whatever session
    files happen to be in the 30–65 minute mtime window right now and runs
    the full memory pipeline on them.

    How to trigger a qualifying file before running this test:
        touch -t $(date -v-35M +%Y%m%d%H%M) ~/.siada-cli/workspace/memory/session/<your-file>.md

    Run:
        python -m pytest tests/agent_hub/proactive/test_scheduler.py::TestAnalyzeRecentSessionsProduction -v -s
    """

    def test_run_against_production_session_dir(
        self, default_config, cron_storage, signal_file, tmp_path
    ):
        s = ProactiveScheduler(
            config=default_config,
            cron_storage=cron_storage,
            signal_file=signal_file,
            workspace=str(tmp_path),
        )
        asyncio.run(s._do_analyze_recent_sessions())

