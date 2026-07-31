"""
Proactive Scheduler

Schedules and executes proactive agent tasks using APScheduler.

Three scheduling concerns:

Part 1 – Daily LLM jobs (cron-based, non-cancellable system tasks)
    Triggered at `daily_task_execution_time` (default 06:00) with adaptive
    jitter to spread ~1000 users across a window ending at `daily_im_send_time`.

    Default jobs (extensible via add_daily_job):
      • daily_summary        – ProactiveAgent generates previous day's summary
      • update_personal_style – DISABLED: personal_style.md is deprecated; USER.md is canonical
      • discover_tasks       – ProactiveAgent discovers pending tasks
      • cleanup_memory       – Clean up old memory files (no LLM needed)

    Jitter calculation:
      max_jitter = min(_JITTER_MAX_MINUTES, daily_im_send_time - daily_task_execution_time)
      Examples:
        06:00 start, 08:30 IM → jitter 0~120min → tasks start in 06:00-08:00
        08:00 start, 08:30 IM → jitter 0~30min  → tasks start in 08:00-08:30
        09:00 start, 08:30 IM → jitter 0         → tasks start at exactly 09:00

Part 1b – IM send (Feishu/Lark daily summary delivery)
    After daily LLM jobs complete, if `send_daily_summary_to_im` is enabled:
      - Compute target = daily_im_send_time + random(0~30min) jitter
      - If target is in the future → schedule via APScheduler date trigger
      - If target already passed   → send immediately
    This guarantees: ordering (summary file exists) + staggering (30min window).

Part 2 – Crontab tasks (user-configured, persisted in CronTaskStorage)
    Loaded at startup; reloaded dynamically when the signal file appears.

Signal file: ~/.siada-cli/cron_tasks.reload
    Written by manage_cron_task after any create/update/delete operation.
    Polled every _RELOAD_CHECK_INTERVAL seconds.
"""

import asyncio
import logging
import os
import random
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
from siada.foundation.code_agent_context import RuntimeSource
from siada.foundation.constants import SIADA_HOME


logger = logging.getLogger(__name__)

_RELOAD_CHECK_INTERVAL = 30   # seconds between signal-file polls
_JITTER_MAX_MINUTES = 120     # upper bound for LLM task start jitter (actual may be smaller, see below)
_IM_SEND_JITTER_MAX_MINUTES = 5  # IM send staggering window after daily_im_send_time
_INTER_JOB_DELAY_SECONDS = 120    # cooldown between consecutive LLM jobs within a sequence
_CONSECUTIVE_FAIL_ABORT = 2       # abort remaining LLM jobs after N consecutive rate-limit failures

# Jobs that must still run when the "no recent events" short-circuit kicks in.
# This is an explicit allow-list (not derived from `requires_llm`) so that
# membership is obvious at the call site and new jobs are NOT silently pulled
# in just because they happen to not call an LLM.
_ALWAYS_RUN_DAILY_JOBS: frozenset = frozenset({"cleanup_memory"})


# NOTE on adaptive jitter:
# The actual LLM jitter is: min(_JITTER_MAX_MINUTES, daily_im_send_time - daily_task_execution_time)
# This ensures all LLM tasks START before daily_im_send_time.
# Example configs:
#   06:00 + IM 08:30 → jitter 0~120min (06:00–08:00)
#   08:00 + IM 08:30 → jitter 0~30min  (08:00–08:30)
#   09:00 + IM 08:30 → jitter 0        (exactly 09:00, no staggering)


# ---------------------------------------------------------------------------
# Job registry types
# ---------------------------------------------------------------------------

@dataclass
class DailyJob:
    """A daily fixed-time job entry."""
    name: str
    handler: Callable[[], Awaitable[None]]
    cancellable: bool = False  # False = system job, cannot be removed
    requires_llm: bool = True  # True = needs LLM API calls, subject to rate-limit protection


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
            # Disabled: personal_style.md is deprecated; USER.md (managed by MemoryReviewAgent) is canonical now.
            # The handler `_update_personal_style` is preserved below for easy re-enabling if needed.
            # DailyJob(name="update_personal_style", handler=self._update_personal_style, cancellable=False, requires_llm=True),
            # DailyJob(name="discover_tasks", handler=self._discover_tasks, cancellable=False, requires_llm=True),
            DailyJob(
                name="cleanup_memory",
                handler=self._cleanup_memory,
                cancellable=False,
                requires_llm=False,
            ),
        ]
        # daily_summary only runs when send_daily_summary_to_im is enabled;
        # without IM delivery the summary file serves no purpose.
        if self.config.send_daily_summary_to_im:
            self._daily_jobs.insert(
                0,
                DailyJob(
                    name="daily_summary",
                    handler=self._daily_summary,
                    cancellable=False,
                    requires_llm=True,
                ),
            )
        else:
            logger.info("ProactiveScheduler -- daily_summary skipped: send_daily_summary_to_im is disabled")

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

        # DEBUG: run daily_summary + IM send once on startup.
        # Activate by setting env var: SIADA_DEBUG_DAILY_SUMMARY=1
        if self.config.enabled and os.environ.get("SIADA_DEBUG_DAILY_SUMMARY") == "1":
            from datetime import timedelta
            delay_seconds = 15  # allow IM controllers to finish initialization
            run_at = datetime.now() + timedelta(seconds=delay_seconds)
            self._scheduler.add_job(
                self._debug_daily_summary_on_startup,
                "date",
                run_date=run_at,
                id="debug_daily_summary_startup",
                max_instances=1,
            )
            logger.info(
                "ProactiveScheduler -- [DEBUG] daily_summary + IM send scheduled in %ds at %s",
                delay_seconds, run_at,
            )

    def stop(self) -> None:
        """Stop the scheduler gracefully."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("ProactiveScheduler -- Stopped")

    @property
    def running(self) -> bool:
        return self._scheduler.running

    # ------------------------------------------------------------------
    # Debug: on-startup daily summary + IM send
    # ------------------------------------------------------------------

    def _debug_daily_summary_on_startup(self) -> None:
        """Run daily_summary generation then immediately send to IM.

        Activated by env var SIADA_DEBUG_DAILY_SUMMARY=1.
        Executes Phase 1 (LLM generation) then Phase 2 (IM send) sequentially,
        bypassing the normal jitter / scheduling logic for fast iteration.
        """
        from siada.agent_hub.proactive.prompts.task_templates.daily_summary import (
            get_daily_summary_file_path,
            get_last_work_date_str,
        )

        work_date_str = get_last_work_date_str()
        summary_file = get_daily_summary_file_path(work_date_str)
        logger.info(
            "ProactiveScheduler -- [DEBUG] Starting daily_summary for %s", work_date_str,
        )

        # Phase 1: generate summary file via LLM
        try:
            self._run_async(self._daily_summary(work_date_str))
        except Exception as e:
            logger.error("ProactiveScheduler -- [DEBUG] daily_summary generation failed: %s", e, exc_info=True)

        # Phase 2: send to IM immediately (no jitter)
        try:
            self._send_daily_summary_to_im(summary_file, work_date_str)
        except Exception as e:
            logger.error("ProactiveScheduler -- [DEBUG] IM send failed: %s", e, exc_info=True)

        logger.info("ProactiveScheduler -- [DEBUG] daily_summary + IM send completed")

    # ------------------------------------------------------------------
    # Part 1 – Daily fixed-time registration
    # ------------------------------------------------------------------

    def _register_daily_job(self) -> None:
        """Register a daily cron job for LLM tasks + IM send.

        A random jitter of 0~_JITTER_MAX_MINUTES (default 120min) is added to
        stagger execution across ~1000 users sharing the same LLM gateway.
        Default window: 06:00-08:00.

        After the LLM job sequence completes, the daily summary is sent to IM
        (if send_daily_summary_to_im is enabled). This guarantees IM send always
        happens after the summary file has been generated.

        misfire_grace_time=86400 ensures the job still fires after the machine
        wakes from sleep.  coalesce=True (APScheduler default) guarantees at most
        one catch-up execution even if multiple firings were missed.
        """
        h, m = parse_time_str(self.config.daily_task_execution_time)

        # Adaptive jitter: cap at the gap between task start and IM send time.
        # If task start >= IM send time, jitter=0 (execute on time, no delay).
        im_h, im_m = parse_time_str(self.config.daily_im_send_time)
        available_window = (im_h * 60 + im_m) - (h * 60 + m)
        max_jitter = max(0, min(_JITTER_MAX_MINUTES, available_window))
        jitter = random.randint(0, max_jitter) if max_jitter > 0 else 0

        total_minutes = h * 60 + m + jitter
        h, m = divmod(total_minutes, 60)
        h = h % 24

        self._scheduler.add_job(
            self._run_all_daily_jobs,
            "cron",
            hour=h,
            minute=m,
            id="daily_fixed",
            max_instances=1,
            misfire_grace_time=86400,
        )
        logger.info(
            "ProactiveScheduler -- Registered daily runner at %02d:%02d (jitter=%dmin)",
            h, m, jitter,
        )

    def _run_all_daily_jobs(self) -> None:
        """APScheduler callback: run all daily fixed jobs, then send IM if enabled.

        Computes the summary file path once here so both Phase 1 (generation)
        and Phase 2 (IM send) use the exact same path — no re-computation.

        Behavior when no recent events exist (last 36h):
          - Skip jobs that are NOT in ``_ALWAYS_RUN_DAILY_JOBS`` — on quiet
            days there is nothing meaningful to summarize or report.
          - Still run jobs explicitly listed in ``_ALWAYS_RUN_DAILY_JOBS``
            (e.g. ``cleanup_memory``) so long-term disk usage stays bounded.

        The allow-list is driven by job *name*, not by ``requires_llm``,
        so the decision is explicit and new jobs don't slip in by accident.
        """
        has_events = self._has_recent_events(hours=36)

        if not has_events:
            logger.info(
                "ProactiveScheduler -- No event file created within 36h; "
                "only running always-run jobs: %s",
                sorted(_ALWAYS_RUN_DAILY_JOBS),
            )
            always_run_jobs = [
                j for j in self._daily_jobs if j.name in _ALWAYS_RUN_DAILY_JOBS
            ]
            if always_run_jobs:
                self._run_async(
                    self._run_job_sequence(always_run_jobs, "daily-housekeeping")
                )
            return

        # Resolve the work date ONCE for this daily run – both Phase 1
        # (generation) and Phase 2 (IM send) use this same value.
        from siada.agent_hub.proactive.prompts.task_templates.daily_summary import (
            get_daily_summary_file_path,
            get_last_work_date_str,
        )
        work_date_str = get_last_work_date_str()
        summary_file = get_daily_summary_file_path(work_date_str)

        # Build a per-run job list that binds work_date_str to _daily_summary
        # so the instruction and IM send share the exact same date.
        jobs = [
            DailyJob(
                name=j.name,
                handler=lambda: self._daily_summary(work_date_str),
                cancellable=j.cancellable,
                requires_llm=j.requires_llm,
            ) if j.name == "daily_summary" else j
            for j in self._daily_jobs
        ]
        self._run_async(self._run_job_sequence(jobs, "daily"))

        # After all LLM tasks complete, schedule IM send if configured
        if self.config.send_daily_summary_to_im:
            self._schedule_im_send(summary_file, work_date_str)

    def _has_recent_events(self, hours: int = 36) -> bool:
        """Return True if any event file was created within the last ``hours`` hours.

        Scans the events memory directory (``~/.siada-cli/workspace/memory/events``)
        and returns True as soon as one file whose creation time falls inside
        the window is found. Uses ``st_birthtime`` when the platform exposes it
        (macOS, Windows) and falls back to ``st_mtime`` otherwise (Linux).

        This is the gating check for the daily run: if nothing has been
        recorded recently, there is nothing to summarize and we skip the
        whole LLM sequence to avoid burning tokens on an empty report.

        Args:
            hours: Size of the lookback window in hours. Default 36h so that
                a missed fire (e.g. overnight suspend) can still catch
                yesterday's events on the next run.

        Returns:
            True when at least one qualifying event file exists.
        """
        events_dir = SIADA_HOME / "workspace" / "memory" / "events"
        if not events_dir.exists():
            return False

        cutoff = datetime.now().timestamp() - hours * 3600
        try:
            for f in events_dir.iterdir():
                if not f.is_file() or f.name.startswith("."):
                    continue
                try:
                    stat = f.stat()
                    # Prefer creation time; fall back to mtime on Linux.
                    created = getattr(stat, "st_birthtime", stat.st_mtime)
                    if created >= cutoff:
                        return True
                except OSError:
                    # Per-file stat failure should not abort the scan.
                    continue
        except OSError as e:
            # Defensive: a transient filesystem issue must not crash the
            # scheduler thread; log and treat as "no recent events".
            logger.warning(
                "ProactiveScheduler -- Failed to scan events dir %s: %s",
                events_dir, e,
            )
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

    def _resolve_cron_model(self):
        """Resolve the ModelRunConfig for a cron task.

        Priority:
          1. conf.yaml proactive.llm_config.model
          2. ModelRunConfig.get_default_config() (original behaviour)
        """
        from siada.config.config_loader import load_conf
        from siada.models.model_run_config import ModelRunConfig
        from siada.provider.provider_factory import resolve_provider_by_model

        try:
            conf = load_conf()
            proactive_llm = conf.proactive_config.llm_config
            if proactive_llm and proactive_llm.model:
                mrc = ModelRunConfig(proactive_llm.model)
                mrc.provider = resolve_provider_by_model(proactive_llm.model, proactive_llm.provider)
                return mrc
        except Exception as e:
            logger.warning("_resolve_cron_model -- failed to load conf: %s", e)

        return ModelRunConfig.get_default_config()

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
            from agents import RunConfig
            from siada.models.model_setting_converter import ModelSettingsConverter
            from siada.provider.provider_factory import get_provider
            from siada.services.input_processor import process_input
            from siada.services.model_wrapper import ModelProviderWrapper
            mrc = self._resolve_cron_model()
            model_settings = ModelSettingsConverter.convert_model_settings(mrc)
            provider_wrapper = ModelProviderWrapper(
                base_provider=get_provider(mrc.provider),
                input_processor=process_input,
            )
            run_config = RunConfig(
                tracing_disabled=False,
                model=mrc.model_name,
                model_provider=provider_wrapper,
                model_settings=model_settings,
            )
            await self._run_agent_with_config("coder", instruction, run_config)
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
            raise  # propagate to _run_job_sequence for correct failure counting
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
            raise  # propagate to _run_job_sequence for correct failure counting

    async def _daily_summary(self, work_date_str: Optional[str] = None) -> None:
        """Run ProactiveAgent to generate a summary file (Phase 1 only).

        Args:
            work_date_str: Pre-computed work date (YYYY-MM-DD), passed from
                _run_all_daily_jobs to ensure consistency with the IM send phase.
                When *None*, the date is auto-detected (standalone usage).

        IM sending is handled separately by Phase 2 (_run_im_send) on its own schedule.
        """
        from siada.agent_hub.proactive.prompts.task_templates import get_daily_summary_instruction
        from siada.provider.fast_llm import build_fast_run_config

        logger.info("ProactiveScheduler -- Running daily_summary (Phase 1: generate only)")
        try:
            await self._run_agent(
                "proactive",
                get_daily_summary_instruction(work_date_str=work_date_str),
                run_config=build_fast_run_config(),
            )
        except Exception as e:
            logger.error("ProactiveScheduler -- daily_summary failed: %s", e, exc_info=True)
            raise  # propagate to _run_job_sequence for correct failure counting

    def _schedule_im_send(
        self, summary_file: Path, work_date_str: str | None = None,
    ) -> None:
        """Schedule IM send via APScheduler at daily_im_send_time + jitter.

        Args:
            summary_file: Pre-computed summary file path (resolved once in
                _run_all_daily_jobs to guarantee consistency with Phase 1).
            work_date_str: Pre-computed work date (YYYY-MM-DD) forwarded to
                _send_daily_summary_to_im for header title assembly.

        Called after LLM tasks complete. Computes a target time (daily_im_send_time
        + random 0~30min jitter). If target is in the future, schedules a one-shot
        APScheduler job; if already passed, executes immediately.

        This ensures:
        1. IM send always happens after daily_summary generates the file (ordering).
        2. IM sends are staggered across users within a 30-min window (load spreading).
        3. No thread blocking — APScheduler handles the delayed execution.
        """
        im_h, im_m = parse_time_str(self.config.daily_im_send_time)
        im_jitter = random.randint(0, _IM_SEND_JITTER_MAX_MINUTES)
        im_total = im_h * 60 + im_m + im_jitter
        target_h, target_m = divmod(im_total, 60)
        target_h = target_h % 24

        now = datetime.now()
        target = now.replace(hour=target_h, minute=target_m, second=0, microsecond=0)

        if target > now:
            # Schedule for the future via APScheduler date trigger
            # Use lambda to capture summary_file and work_date_str for the delayed callback
            self._scheduler.add_job(
                lambda: self._execute_im_send(summary_file, work_date_str),
                "date",
                run_date=target,
                id="daily_im_send",
                replace_existing=True,
                max_instances=1,
            )
            logger.info(
                "ProactiveScheduler -- IM send scheduled at %02d:%02d (jitter=%dmin, wait=%ds)",
                target_h, target_m, im_jitter, int((target - now).total_seconds()),
            )
        else:
            # Target already passed (LLM tasks took longer than expected), send now
            logger.info(
                "ProactiveScheduler -- IM send target %02d:%02d already passed (jitter=%dmin); sending now",
                target_h, target_m, im_jitter,
            )
            self._execute_im_send(summary_file, work_date_str)

    def _execute_im_send(
        self, summary_file: Path, work_date_str: str | None = None,
    ) -> None:
        """APScheduler callback: actually send the daily summary to IM."""
        logger.info("ProactiveScheduler -- Executing IM send")
        try:
            self._send_daily_summary_to_im(summary_file, work_date_str)
        except Exception as e:
            logger.error("ProactiveScheduler -- IM send failed: %s", e, exc_info=True)

    def _send_daily_summary_to_im(
        self, summary_file: Path, work_date_str: str | None = None,
    ) -> None:
        """Read the daily summary file and send it to all active IM controllers.

        Args:
            summary_file: Path to the summary file, pre-computed in
                _run_all_daily_jobs to ensure consistency with Phase 1.
            work_date_str: Pre-computed work date (YYYY-MM-DD). When provided,
                the card is sent with a localized header title.
        """
        if not summary_file.exists():
            logger.warning("ProactiveScheduler -- Summary file not found: %s", summary_file)
            return

        content = summary_file.read_text(encoding="utf-8")
        if not content.strip():
            logger.warning("ProactiveScheduler -- Summary file is empty: %s", summary_file)
            return

        # Build header_title from localized template when work_date_str is available
        header_title: str | None = None
        if work_date_str:
            try:
                from siada.config.config_loader import load_conf
                from siada.im.feishu.notification_templates import (
                    get_daily_summary_notification_template,
                )

                conf = load_conf()
                language = conf.preferred_language if conf else None
            except Exception:
                language = None
            template = get_daily_summary_notification_template(language)
            header_title = template.header_title

        # Get daemon instance and send to all active IM controllers
        try:
            from siada.agent_hub.proactive.ipc_server import get_daemon_instance
        except ImportError:
            logger.warning("ProactiveScheduler -- ipc_server not available, skipping IM send")
            return

        daemon = get_daemon_instance()
        if daemon is None or not getattr(daemon, "im_controllers", None):
            logger.info("ProactiveScheduler -- No IM controllers available, skipping IM send")
            return

        import asyncio

        sent_count = 0
        for ctrl, ctrl_loop in zip(daemon.im_controllers, daemon._im_loops):
            if not hasattr(ctrl, "enqueue_ipc_message"):
                continue
            try:
                future = asyncio.run_coroutine_threadsafe(
                    ctrl.enqueue_ipc_message(
                        content=content.strip(),
                        content_type="markdown",
                        header_title=header_title,
                    ),
                    ctrl_loop,
                )
                future.result(timeout=30)
                sent_count += 1
                logger.info(
                    "ProactiveScheduler -- Daily summary sent via %s",
                    ctrl.__class__.__name__,
                )
            except Exception as e:
                logger.error(
                    "ProactiveScheduler -- Failed to send daily summary via %s: %s",
                    ctrl.__class__.__name__, e,
                )

        if sent_count == 0:
            logger.warning("ProactiveScheduler -- No active IM controller could send the daily summary")
        else:
            logger.info("ProactiveScheduler -- Daily summary sent to %d IM controller(s)", sent_count)

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

        The entire pipeline is skipped when the memory master switch is OFF so
        that ``/memory disable`` stops background writes immediately.
        """
        # Re-read conf.yaml each invocation so runtime toggles (e.g. /memory
        # disable) take effect without restarting the scheduler.
        try:
            from siada.config.config_loader import load_conf
            if not load_conf().memory_config.enabled:
                logger.info(
                    "ProactiveScheduler -- analyze_recent_sessions skipped: memory disabled"
                )
                return
        except Exception as _e:
            logger.warning(
                "ProactiveScheduler -- Could not read memory config, proceeding: %s", _e
            )

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

        llm_config = ModelRunConfig.get_default_config()
        set_context_var(LLM_CONFIG, llm_config)

        for f in candidates:
            await self._analyze_session_file(f)

    async def _analyze_session_file(self, f: Path) -> None:
        """Analyze a single session file and update memory.

        Args:
            f: Path to the session file to analyze.
        """
        from siada.services.memory.memory_agent import analyze_and_update_memory
        from siada.services.memory.memory_review_agent import review_and_update_inline_memory

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
            # Serial: inline memory review runs after MemoryAgent pipeline completes
            review_result = await review_and_update_inline_memory(content)
            if review_result.get("success"):
                logger.info(
                    "ProactiveScheduler -- Inline memory review done: %s, skipped=%s",
                    f.name, review_result.get("skipped"),
                )
            else:
                logger.error(
                    "ProactiveScheduler -- Inline memory review failed: %s, error=%s",
                    f.name, review_result.get("error"),
                )
        except Exception as e:
            logger.error(
                "ProactiveScheduler -- Error analyzing session %s: %s", f.name, e, exc_info=True
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_agent_with_config(self, agent_name: str, instruction: str, run_config) -> None:
        """Run an agent with a pre-built RunConfig via the full SiadaRunner path.

        Delegates to SiadaRunner.run_agent() with run_config override so that
        FileSession.on_items_added (telemetry hook) fires correctly.
        """
        from siada.entrypoint.interaction.running_config import RunningConfig
        from siada.io.io import InputOutput
        from siada.models.model_run_config import ModelRunConfig
        from siada.services.siada_runner import SiadaRunner
        from siada.session.session_manager import RunningSessionManager

        siada_config = RunningConfig(
            llm_config=ModelRunConfig.get_default_config(),
            io=InputOutput(),
            workspace=self._workspace,
            agent_name=agent_name,
            console_output=False,
            interactive=False,
        )
        session = RunningSessionManager.create_session(siada_config)
        await SiadaRunner.run_agent(
            agent_name,
            instruction,
            workspace=self._workspace,
            session=session,
            runtime_source=RuntimeSource.DAEMON,
            run_config=run_config,
        )

    async def _run_agent(self, agent_name: str, instruction: str, run_config=None) -> None:
        """Execute an instruction via the named agent.

        Args:
            agent_name: Name of the agent to run.
            instruction: Task instruction to pass to the agent.
            run_config: Optional ``RunConfig``. When provided, bypasses
                SiadaRunner's session-based model resolution and calls
                ``Runner.run()`` directly — the same lightweight pattern used
                by MemoryAgent. Pass ``build_fast_run_config()`` here to pin
                the execution to the fast model.
        """
        from siada.foundation.tools.user_info import get_username
        if not get_username():
            logger.warning(
                "ProactiveScheduler -- user_id not configured in conf.yaml; skipping agent '%s'",
                agent_name,
            )
            return

        if run_config is not None:
            await self._run_agent_with_config(agent_name, instruction, run_config)
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
        await SiadaRunner.run_agent(
            agent_name,
            instruction,
            workspace=self._workspace,
            session=session,
            runtime_source=RuntimeSource.DAEMON,
        )

    async def _run_job_sequence(
        self, jobs: List[DailyJob], label: str
    ) -> None:
        """Run a list of DailyJob handlers in sequence.

        Rate-limit protection:
        - Insert _INTER_JOB_DELAY_SECONDS cooldown between consecutive LLM jobs
        - Abort remaining LLM jobs after _CONSECUTIVE_FAIL_ABORT consecutive failures
        - Non-LLM jobs (e.g. cleanup_memory) always run regardless of failures
        """
        succeeded, failed, skipped = 0, 0, 0
        consecutive_llm_failures = 0
        prev_was_llm = False

        for job in jobs:
            # Abort LLM jobs after consecutive failures (likely gateway-wide rate limit)
            if job.requires_llm and consecutive_llm_failures >= _CONSECUTIVE_FAIL_ABORT:
                skipped += 1
                logger.warning(
                    "ProactiveScheduler -- Skipping %s job '%s': %d consecutive LLM failures",
                    label, job.name, consecutive_llm_failures,
                )
                continue

            # Cooldown between consecutive LLM jobs to reduce burst pressure
            if job.requires_llm and prev_was_llm:
                logger.info(
                    "ProactiveScheduler -- Waiting %ds before next LLM job",
                    _INTER_JOB_DELAY_SECONDS,
                )
                await asyncio.sleep(_INTER_JOB_DELAY_SECONDS)

            logger.info("ProactiveScheduler -- Running %s job: %s", label, job.name)
            try:
                await job.handler()
                succeeded += 1
                if job.requires_llm:
                    consecutive_llm_failures = 0  # reset on success
            except Exception as e:
                failed += 1
                if job.requires_llm:
                    consecutive_llm_failures += 1
                logger.error(
                    "ProactiveScheduler -- %s job '%s' failed: %s",
                    label, job.name, e, exc_info=True,
                )

            prev_was_llm = job.requires_llm

        logger.info(
            "ProactiveScheduler -- %s job sequence finished: total=%d, succeeded=%d, failed=%d, skipped=%d",
            label, len(jobs), succeeded, failed, skipped,
        )

    @staticmethod
    def _run_async(coro: Awaitable) -> None:
        """Run a coroutine from a synchronous APScheduler thread."""
        try:
            asyncio.run(coro)
        except Exception as e:
            logger.error("ProactiveScheduler -- Async execution failed: %s", e, exc_info=True)
