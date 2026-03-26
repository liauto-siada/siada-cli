"""
Proactive daemon CLI command handlers.
"""
import sys
import threading
from pathlib import Path
from typing import Optional

from siada.foundation.logging import logger


def ensure_daemon_running(conf, verbose: bool = False) -> None:
    """Ensure proactive daemon is running in a background thread."""
    def _run():
        try:
            from siada.foundation.constants import SIADA_HOME
            from siada.agent_hub.proactive.daemon_manager import DaemonManager

            pid_file = SIADA_HOME / "siada-daemon.pid"
            daemon_script = Path(__file__).parent.parent.parent / "agent_hub/proactive/daemon.py"

            manager = DaemonManager(pid_file, daemon_script)
            manager.ensure_daemon()
        except Exception as e:
            logger.error(f"Failed to ensure daemon running: {e}")

    threading.Thread(target=_run, daemon=True).start()


def handle_stop_daemon() -> int:
    """Stop proactive daemon. Returns exit code."""
    try:
        from siada.foundation.constants import SIADA_HOME
        from siada.agent_hub.proactive.daemon_manager import DaemonManager

        pid_file = SIADA_HOME / "siada-daemon.pid"
        daemon_script = Path(__file__).parent.parent.parent / "agent_hub/proactive/daemon.py"

        manager = DaemonManager(pid_file, daemon_script)

        if not manager.is_running():
            print("Proactive daemon is not running")
            return 0

        if manager.stop_daemon():
            print("✓ Proactive daemon stopped")
            return 0
        else:
            print("✗ Failed to stop daemon", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"✗ Error stopping daemon: {e}", file=sys.stderr)
        logger.error(f"Error stopping daemon: {e}", exc_info=True)
        return 1


def handle_daemon_status() -> int:
    """Show daemon status. Returns 0 if running, 1 if not."""
    try:
        from siada.foundation.constants import SIADA_HOME
        from siada.agent_hub.proactive.daemon_manager import DaemonManager

        pid_file = SIADA_HOME / "siada-daemon.pid"
        daemon_script = Path(__file__).parent.parent.parent / "agent_hub/proactive/daemon.py"

        manager = DaemonManager(pid_file, daemon_script)
        pid = manager.get_pid()

        if pid:
            print(f"✓ Proactive daemon is running (PID: {pid})")
            try:
                import psutil
                import datetime
                proc = psutil.Process(pid)
                start_time = datetime.datetime.fromtimestamp(proc.create_time())
                print(f"  Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
            except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                pass

            from siada.foundation.logging import get_log_directory
            log_file = Path(get_log_directory()) / "siada_cli.log"
            if log_file.exists():
                print(f"  Log: {log_file}")
            return 0
        else:
            print("✗ Proactive daemon is not running")
            return 1
    except Exception as e:
        print(f"✗ Error checking daemon status: {e}", file=sys.stderr)
        logger.error(f"Error checking daemon status: {e}", exc_info=True)
        return 1


def handle_task_list() -> int:
    """Show discovered pending tasks from proactive agent. Returns exit code."""
    try:
        from siada.agent_hub.proactive.task_storage import TaskStorage

        storage = TaskStorage()
        task_list = storage.load()
        if task_list is None or len(task_list) == 0:
            task_files = sorted(storage.storage_dir.glob("tasks_*.json"), reverse=True)
            for task_file in task_files:
                date_str = task_file.stem.replace("tasks_", "")
                task_list = storage.load(date=date_str)
                if task_list and len(task_list) > 0:
                    break

        if task_list is None or len(task_list) == 0:
            print("No tasks found. Run the proactive daemon to discover tasks.")
            return 0

        priority_order = {"high": 0, "medium": 1, "low": 2}
        tasks = sorted(task_list.tasks, key=lambda t: priority_order.get(t.priority, 3))

        priority_icons = {"high": "!!!", "medium": "!", "low": " "}
        status_icons = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]", "cancelled": "[-]"}
        category_colors = {"feature": "feat", "bug": "bug", "refactor": "rfct", "doc": "doc", "test": "test", "other": "other"}

        print(f"\nPending Tasks ({len(tasks)} total)  [updated: {task_list.last_updated[:10]}]\n")
        print(f"{'#':<3} {'P':<4} {'Status':<5} {'Cat':<6} {'Conf':<6} {'Title'}")
        print("-" * 72)

        for i, task in enumerate(tasks, 1):
            prio = priority_icons.get(task.priority, " ")
            status = status_icons.get(task.status, "[ ]")
            cat = category_colors.get(task.category, task.category)[:5]
            conf = f"{task.confidence:.2f}"
            confirm = " [confirm]" if task.needs_confirmation else ""
            print(f"{i:<3} {prio:<4} {status:<5} {cat:<6} {conf:<6} {task.title}{confirm}")

        print()
        return 0
    except Exception as e:
        print(f"Error reading task list: {e}", file=sys.stderr)
        logger.error(f"Error reading task list: {e}", exc_info=True)
        return 1
