"""
Proactive Scheduler

Schedules and executes proactive agent tasks using APScheduler.

Two distinct scheduling layers:

Part 1 – Daily fixed jobs (cron-based, non-cancellable system tasks)
    All run at `daily_task_execution_time` (default 08:30).
    Default jobs (extensible via add_daily_job):
      • daily_summary        – ProactiveAgent summarises previous day's work
      • discover_tasks       – ProactiveAgent discovers pending tasks
      • update_personal_style – ProactiveAgent updates personal style memory
      • cleanup_memory       – Clean up old memory files

Part 2 – Crontab tasks (user-configured, persisted in CronTaskStorage)
    Loaded at startup; reloaded dynamically when the signal file appears.

Signal file: ~/.siada-cli/cron_tasks.reload
    Written by manage_cron_task after any create/update/delete operation.
    Polled every _RELOAD_CHECK_INTERVAL seconds.
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Awaitable, Callable, List, Optional, Set

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from siada.agent_hub.proactive.cron_task_storage import CronTaskStorage
from siada.agent_hub.proactive.models import CronTask
from siada.agent_hub.proactive.utils.time_utils import parse_time_str
from siada.config.config_loader import ProactiveConfig
from siada.foundation.constants import SIADA_HOME


logger = logging.getLogger(__name__)

_RELOAD_CHECK_INTERVAL = 30  # seconds between signal-file polls


# ---------------------------------------------------------------------------
# Job registry types
# ---------------------------------------------------------------------------

@dataclass
class DailyJob:
    """A daily fixed-time job entry."""
    name: str
    handler: Callable[[], Awaitable[None]]
    cancellable: bool = False  # False = system job, cannot be removed


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class ProactiveScheduler:
    """
    Two-layer proactive task scheduler.

    Args:
        config: ProactiveConfig (work hours, daily times).
        cron_storage: CronTaskStorage for Part 2 user-defined crontab tasks.
        signal_file: Path polled for dynamic crontab reload requests.
    """

    def __init__(
        self,
        config: ProactiveConfig,
        cron_storage: Optional[CronTaskStorage] = None,
        signal_file: Optional[Path] = None,
        workspace: Optional[str] = None,
    ):
        self.config = config
        self._workspace = workspace or os.getcwd()
        self._cron_storage = cron_storage or CronTaskStorage()
        self._signal_file = signal_file or (SIADA_HOME / "cron_tasks.reload")

        self._scheduler = BackgroundScheduler()
        self._cron_job_ids: Set[str] = set()
        self._discover_tasks_lock = Lock()

        # Job registry – populated by _setup_default_jobs(), extensible afterwards
        self._daily_jobs: List[DailyJob] = []
        self._setup_default_jobs()

    # ------------------------------------------------------------------
    # Default job registration
    # ------------------------------------------------------------------

    def _setup_default_jobs(self) -> None:
        """Register the built-in daily jobs."""
        # Part 1 – daily fixed (non-cancellable)
        self._daily_jobs = [
            DailyJob(name="daily_summary", handler=self._daily_summary, cancellable=False),
            DailyJob(name="update_personal_style", handler=self._update_personal_style, cancellable=False),
            DailyJob(name="discover_tasks", handler=self._discover_tasks, cancellable=False),
            DailyJob(name="cleanup_memory", handler=self._cleanup_memory, cancellable=False),
        ]

    # ------------------------------------------------------------------
    # Public extension API
    # ------------------------------------------------------------------

    def add_daily_job(self, job: DailyJob) -> None:
        """Add a custom daily job to the registry."""
        self._daily_jobs.append(job)
        logger.info("ProactiveScheduler -- Added daily job: %s", job.name)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the scheduler and register all jobs."""
        logger.info("ProactiveScheduler -- Starting...")

        if self.config.enabled:
            self._register_daily_job()
            self._scheduler.add_job(
                self._analyze_recent_sessions,
                "interval",
                minutes=30,
                id="analyze_recent_sessions",
                max_instances=1,
            )
        else:
            logger.info("ProactiveScheduler -- Proactive mode disabled; skipping fixed-schedule jobs")

        self._load_cron_tasks()

        self._scheduler.add_job(
            self._check_reload_signal,
            "interval",
            seconds=_RELOAD_CHECK_INTERVAL,
            id="check_reload_signal",
        )

        self._scheduler.start()
        logger.info("ProactiveScheduler -- Started")

    def stop(self) -> None:
        """Stop the scheduler gracefully."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("ProactiveScheduler -- Stopped")

    @property
    def running(self) -> bool:
        return self._scheduler.running

    # ------------------------------------------------------------------
    # Part 1 – Daily fixed-time registration
    # ------------------------------------------------------------------

    def _register_daily_job(self) -> None:
        """Register a single cron job at daily_task_execution_time for all daily handlers.

        misfire_grace_time=86400 ensures the job still fires after the machine
        wakes from sleep, as long as it wakes within 24 hours of the scheduled
        time.  coalesce=True (APScheduler default) guarantees at most one
        catch-up execution even if multiple firings were missed.
        """
        h, m = parse_time_str(self.config.daily_task_execution_time)
        self._scheduler.add_job(
            self._run_all_daily_jobs,
            "cron",
            hour=h,
            minute=m,
            id="daily_fixed",
            max_instances=1,
            misfire_grace_time=86400,  # fire any time within 24 h of the missed slot
        )
        logger.info(
            "ProactiveScheduler -- Registered daily fixed runner at %02d:%02d", h, m
        )

    def _run_all_daily_jobs(self) -> None:
        """APScheduler callback: run all daily fixed jobs in sequence."""
        if not self._has_recent_session(hours=36):
            logger.info(
                "ProactiveScheduler -- No session file created within 36h; skipping daily jobs"
            )
            return
        self._run_async(self._run_job_sequence(self._daily_jobs, "daily"))

    def _has_recent_session(self, hours: int = 36) -> bool:
        """Return True if any session file was created within the last `hours` hours."""
        session_dir = Path.home() / ".siada-cli" / "workspace" / "memory" / "session"
        if not session_dir.exists():
            return False
        cutoff = datetime.now().timestamp() - hours * 3600
        for f in session_dir.iterdir():
            if f.is_file() and not f.name.startswith("."):
                try:
                    stat = f.stat()
                    created = getattr(stat, "st_birthtime", stat.st_mtime)
                    if created >= cutoff:
                        return True
                except Exception:
                    continue
        return False

    # ------------------------------------------------------------------
    # Part 2 – Crontab task management
    # ------------------------------------------------------------------

    def _load_cron_tasks(self) -> None:
        """(Re-)register APScheduler jobs for all enabled CronTask records."""
        for job_id in list(self._cron_job_ids):
            try:
                self._scheduler.remove_job(job_id)
            except Exception:
                pass
        self._cron_job_ids.clear()

        tasks = self._cron_storage.get_enabled()
        for task in tasks:
            self._register_cron_task(task)

        logger.info("ProactiveScheduler -- Loaded %d crontab task(s)", len(tasks))

    def _register_cron_task(self, task: CronTask) -> None:
        """Register a single CronTask as an APScheduler job."""
        job_id = f"cron_{task.id}"
        try:
            trigger = CronTrigger.from_crontab(task.cron_expr)
            self._scheduler.add_job(
                self._execute_cron_task,
                trigger=trigger,
                args=[task.id, task.instruction],
                id=job_id,
                replace_existing=True,
                max_instances=1,
            )
            self._cron_job_ids.add(job_id)
            logger.info(
                "ProactiveScheduler -- Registered crontab task: %s (%s) expr=%s",
                task.id, task.name, task.cron_expr,
            )
        except Exception as e:
            logger.error("ProactiveScheduler -- Failed to register crontab task %s: %s", task.id, e)

    def _check_reload_signal(self) -> None:
        """Poll signal file; reload crontab tasks if it exists."""
        if self._signal_file.exists():
            try:
                self._signal_file.unlink()
                logger.info("ProactiveScheduler -- Reload signal detected; reloading crontab tasks")
                self._load_cron_tasks()
            except Exception as e:
                logger.warning("ProactiveScheduler -- Failed to process reload signal: %s", e)

    def _execute_cron_task(self, task_id: str, instruction: str) -> None:
        """APScheduler callback: execute a user-defined crontab task."""
        self._run_async(self._run_cron_task(task_id, instruction))

    async def _run_cron_task(self, task_id: str, instruction: str) -> None:
        """Run the coder agent for a crontab task, then update timestamps."""
        try:
            logger.info("_run_cron_task -- Executing crontab task , instruction : %s", instruction)
            await self._run_agent("coder", instruction)
        except Exception as e:
            logger.error("ProactiveScheduler -- Crontab task %s failed: %s", task_id, e, exc_info=True)
        finally:
            self._update_cron_task_run_time(task_id)

    def _update_cron_task_run_time(self, task_id: str) -> None:
        """Persist last_run and next_run for a crontab task after execution."""
        task = self._cron_storage.get(task_id)
        if task is None:
            return
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        try:
            trigger = CronTrigger.from_crontab(task.cron_expr)
            next_dt = trigger.get_next_fire_time(None, datetime.now(timezone.utc))
            next_iso = next_dt.isoformat().replace("+00:00", "Z") if next_dt else None
        except Exception:
            next_iso = None
        self._cron_storage.update(task_id, last_run=now_iso, next_run=next_iso)

    # ------------------------------------------------------------------
    # Built-in job handlers
    # ------------------------------------------------------------------

    async def _discover_tasks(self) -> None:
        """Run ProactiveAgent to discover pending tasks (writes today's task file).

        Uses a non-blocking mutex so that concurrent callers skip instead of
        queuing behind an already-running execution.
        """
        from siada.agent_hub.proactive.prompts.task_templates import get_discover_tasks_instruction

        acquired = self._discover_tasks_lock.acquire(blocking=False)
        if not acquired:
            logger.info("ProactiveScheduler -- discover_tasks already running; skipping this call")
            return

        try:
            logger.info("ProactiveScheduler -- Running discover_tasks")
            await self._run_agent("proactive", get_discover_tasks_instruction())
        except Exception as e:
            logger.error("ProactiveScheduler -- discover_tasks failed: %s", e, exc_info=True)
        finally:
            self._discover_tasks_lock.release()

    async def _update_personal_style(self) -> None:
        """Run ProactiveAgent to update the personal style memory from today's events."""
        from siada.agent_hub.proactive.prompts.task_templates import get_update_personal_style_instruction

        logger.info("ProactiveScheduler -- Running update_personal_style")
        try:
            await self._run_agent("proactive", get_update_personal_style_instruction())
        except Exception as e:
            logger.error("ProactiveScheduler -- update_personal_style failed: %s", e, exc_info=True)

    async def _daily_summary(self) -> None:
        """Run ProactiveAgent to generate a summary of the previous day's work."""
        from siada.agent_hub.proactive.prompts.task_templates import get_daily_summary_instruction

        logger.info("ProactiveScheduler -- Running daily_summary")
        try:
            await self._run_agent("proactive", get_daily_summary_instruction())
        except Exception as e:
            logger.error("ProactiveScheduler -- daily_summary failed: %s", e, exc_info=True)

    async def _cleanup_memory(self) -> None:
        """Clean up old memory files to maintain a manageable history size.
        
        Cleanup rules:
        - events: keep latest 20 files by modification time
        - experience: keep latest 10 files by modification time
        - session: keep files from last 30 days by modification time (sync DB)
        - summary: keep files from last 30 days by modification time
        - task: keep files from last 30 days by modification time
        - tmp: keep files from last 30 days by modification time (all file types)
        """
        logger.info("ProactiveScheduler -- Running cleanup_memory")
        try:
            workspace_dir = Path.home() / ".siada-cli" / "workspace"
            memory_dir = workspace_dir / "memory"
            task_dir = workspace_dir / "task"
            tmp_dir = workspace_dir / "tmp"
            
            if not memory_dir.exists():
                logger.warning("ProactiveScheduler -- Memory directory not found, skipping memory cleanup")
            
            total_deleted = 0
            
            # Clean memory directories
            if memory_dir.exists():
                # Clean events: keep latest 20
                total_deleted += await self._cleanup_by_count(memory_dir / "events", keep_count=30, file_ext=".md")
                
                # Clean experience: keep latest 10
                total_deleted += await self._cleanup_by_count(memory_dir / "experience", keep_count=15, file_ext=".md")
                
                # Clean session: keep files from last 30 days (sync DB)
                total_deleted += await self._cleanup_by_age(memory_dir / "session", days=30, file_ext=".md", sync_db=True)
                
                # Clean summary: keep files from last 30 days
                total_deleted += await self._cleanup_by_age(memory_dir / "summary", days=30, file_ext=".md")
            
            # Clean task directory: keep files from last 30 days
            if task_dir.exists():
                total_deleted += await self._cleanup_by_age(task_dir, days=30, file_ext=".json")
            
            # Clean tmp directory: keep files from last 30 days (all file types)
            if tmp_dir.exists():
                total_deleted += await self._cleanup_by_age(tmp_dir, days=30, file_ext=None)
            
            logger.info("ProactiveScheduler -- cleanup_memory completed: deleted %d file(s)", total_deleted)
        except Exception as e:
            logger.error("ProactiveScheduler -- cleanup_memory failed: %s", e, exc_info=True)
    
    async def _cleanup_by_count(self, directory: Path, keep_count: int, file_ext: str = ".md") -> int:
        """Delete old files keeping only the latest N files by modification time.
        
        Args:
            directory: Directory to clean
            keep_count: Number of files to keep
            file_ext: File extension to filter (default: ".md")
            
        Returns:
            Number of files deleted
        """
        if not directory.exists():
            logger.debug("ProactiveScheduler -- Directory %s does not exist, skipping", directory.name)
            return 0
        
        try:
            # Get all files with specified extension sorted by modification time (newest first)
            files = [
                f for f in directory.iterdir()
                if f.is_file() and f.suffix == file_ext and not f.name.startswith(".")
            ]
            files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            
            # Delete files beyond keep_count
            deleted = 0
            for file in files[keep_count:]:
                try:
                    file.unlink()
                    deleted += 1
                    logger.debug("ProactiveScheduler -- Deleted %s/%s", directory.name, file.name)
                except Exception as e:
                    logger.warning("ProactiveScheduler -- Failed to delete %s: %s", file, e)
            
            if deleted > 0:
                logger.info(
                    "ProactiveScheduler -- Cleaned %s: kept %d, deleted %d file(s)",
                    directory.name, min(len(files), keep_count), deleted
                )
            return deleted
        except Exception as e:
            logger.error("ProactiveScheduler -- Error cleaning %s: %s", directory.name, e)
            return 0
    
    async def _cleanup_by_age(self, directory: Path, days: int, file_ext: str = ".md", sync_db: bool = False) -> int:
        """Delete files older than specified days based on modification time.
        
        Args:
            directory: Directory to clean
            days: Number of days to keep
            file_ext: File extension to filter (default: ".md"). If None, all files are considered.
            sync_db: If True, also delete database records for deleted files (default: False)
            
        Returns:
            Number of files deleted
        """
        if not directory.exists():
            logger.debug("ProactiveScheduler -- Directory %s does not exist, skipping", directory.name)
            return 0
        
        try:
            cutoff_time = datetime.now().timestamp() - (days * 86400)  # days * seconds_per_day
            
            # Get all files with specified extension (or all files if file_ext is None)
            if file_ext is None:
                files = [
                    f for f in directory.iterdir()
                    if f.is_file() and not f.name.startswith(".")
                ]
            else:
                files = [
                    f for f in directory.iterdir()
                    if f.is_file() and f.suffix == file_ext and not f.name.startswith(".")
                ]
            
            # Initialize memory database if sync_db is enabled
            memory_db = None
            if sync_db:
                try:
                    from siada.services.memory.memory_db import MemoryDatabase
                    memory_db = MemoryDatabase()
                    logger.debug("ProactiveScheduler -- Memory database initialized for sync deletion")
                except Exception as e:
                    logger.warning("ProactiveScheduler -- Failed to initialize memory database: %s", e)
                    memory_db = None
            
            # Delete files older than cutoff
            deleted = 0
            for file in files:
                try:
                    if file.stat().st_mtime < cutoff_time:
                        # Delete from database first if sync_db is enabled
                        if sync_db and memory_db:
                            try:
                                memory_db.delete_file_records(str(file))
                                logger.debug("ProactiveScheduler -- Deleted DB records for %s", file.name)
                            except Exception as e:
                                logger.warning("ProactiveScheduler -- Failed to delete DB records for %s: %s", file.name, e)
                        
                        # Delete the file
                        file.unlink()
                        deleted += 1
                        logger.debug("ProactiveScheduler -- Deleted %s/%s", directory.name, file.name)
                except Exception as e:
                    logger.warning("ProactiveScheduler -- Failed to delete %s: %s", file, e)
            
            # Close database connection if opened
            if memory_db:
                try:
                    memory_db.close()
                except Exception:
                    pass
            
            if deleted > 0:
                logger.info(
                    "ProactiveScheduler -- Cleaned %s: deleted %d file(s) older than %d days%s",
                    directory.name, deleted, days, " (synced DB)" if sync_db else ""
                )
            return deleted
        except Exception as e:
            logger.error("ProactiveScheduler -- Error cleaning %s: %s", directory.name, e)
            return 0

    # ------------------------------------------------------------------
    # Session memory analysis (periodic)
    # ------------------------------------------------------------------

    def _analyze_recent_sessions(self) -> None:
        """APScheduler callback: analyze session files updated 30–65 minutes ago."""
        self._run_async(self._do_analyze_recent_sessions())

    async def _do_analyze_recent_sessions(self) -> None:
        """Scan session directory and run memory pipeline on qualifying files.

        Qualifying files: last-modified time is between 30 and 65 minutes ago.
        The 30-minute scheduler interval combined with this 35-minute window ensures
        each file is processed exactly once (with a 5-minute grace period for
        scheduler delays). No in-memory tracking is needed.
        """
        session_dir = Path.home() / ".siada-cli" / "workspace" / "memory" / "session"
        if not session_dir.exists():
            return

        now = datetime.now().timestamp()
        min_age = 30 * 60  # 30 minutes in seconds
        max_age = 65 * 60  # 65 minutes in seconds (30min interval + 5min grace)

        candidates = []
        for f in session_dir.iterdir():
            if not f.is_file() or not f.name.endswith(".md") or f.name.startswith("."):
                continue
            age = now - f.stat().st_mtime
            if min_age <= age <= max_age:
                candidates.append(f)

        if not candidates:
            return

        logger.info(
            "ProactiveScheduler -- analyze_recent_sessions: found %d qualifying file(s)", len(candidates)
        )

        from siada.models.model_run_config import ModelRunConfig
        from siada.foundation.context import set_context_var, LLM_CONFIG
        from siada.services.memory.memory_agent import analyze_and_update_memory

        llm_config = ModelRunConfig.get_default_config()
        set_context_var(LLM_CONFIG, llm_config)

        for f in candidates:
            logger.info("ProactiveScheduler -- Analyzing session file: %s", f.name)
            try:
                content = f.read_text(encoding="utf-8")
                result = await analyze_and_update_memory(session_content=content)
                if result.get("success"):
                    logger.info(
                        "ProactiveScheduler -- Session analysis done: %s, tasks=%s",
                        f.name, result.get("completed_tasks", []),
                    )
                else:
                    logger.error(
                        "ProactiveScheduler -- Session analysis failed: %s, error=%s",
                        f.name, result.get("error"),
                    )
            except Exception as e:
                logger.error(
                    "ProactiveScheduler -- Error analyzing session %s: %s", f.name, e, exc_info=True
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_agent(self, agent_name: str, instruction: str) -> None:
        """Execute an instruction via the named agent using SiadaRunner."""
        from siada.foundation.tools.user_info import get_username
        if not get_username():
            logger.warning(
                "ProactiveScheduler -- user_id not configured in conf.yaml; skipping agent '%s'",
                agent_name,
            )
            return

        from siada.services.siada_runner import SiadaRunner
        from siada.session.session_manager import RunningSessionManager
        from siada.entrypoint.interaction.running_config import RunningConfig
        from siada.io.io import InputOutput
        from siada.models.model_run_config import ModelRunConfig

        llm_config = ModelRunConfig.get_default_config()
        siada_config = RunningConfig(
            llm_config=llm_config,
            io=InputOutput(),
            workspace=self._workspace,
            agent_name=agent_name,
            console_output=False,
            interactive=False,
        )
        session = RunningSessionManager.create_session(siada_config)
        await SiadaRunner.run_agent(agent_name, instruction, workspace=self._workspace, session=session)

    async def _run_job_sequence(
        self, jobs: List, label: str
    ) -> None:
        """Run a list of DailyJob handlers in sequence."""
        succeeded, failed = 0, 0
        for job in jobs:
            logger.info("ProactiveScheduler -- Running %s job: %s", label, job.name)
            try:
                await job.handler()
                succeeded += 1
            except Exception as e:
                failed += 1
                logger.error(
                    "ProactiveScheduler -- %s job '%s' failed: %s",
                    label, job.name, e, exc_info=True,
                )
        logger.info(
            "ProactiveScheduler -- %s job sequence finished: total=%d, succeeded=%d, failed=%d",
            label, len(jobs), succeeded, failed,
        )

    @staticmethod
    def _run_async(coro: Awaitable) -> None:
        """Run a coroutine from a synchronous APScheduler thread."""
        try:
            asyncio.run(coro)
        except Exception as e:
            logger.error("ProactiveScheduler -- Async execution failed: %s", e, exc_info=True)



