"""Background auto-update support for Siada.

The daemon uses this module to check for newer releases in the background,
install them silently, and persist state so the next CLI launch can pick up
any applied update without interrupting the current session.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import packaging.version
import requests

import siada
from siada.config.config_loader import AutoUpdateConfig
from siada.foundation.constants import SIADA_HOME

logger = logging.getLogger("siada.auto_update")

_AUTO_UPDATE_STATE_FILE = SIADA_HOME / "auto_update" / "state.json"
_AUTO_UPDATE_LOCK_FILE = SIADA_HOME / "locks" / "auto_update.lock"
_AUTO_UPDATE_INSTALL_LOG = SIADA_HOME / "logs" / "auto_update_install.log"
_INTERNAL_BASE_URL = "https://bj.bcebos.com/prod-cnhb01-siada/cli-install"
_INTERNAL_SCRIPT_NAMES = {
    "prod": "prod_install_from_tarball.sh",
    "beta": "beta_install_from_tarball.sh",
    "test": "test_install_from_tarball.sh",
}
_INTERNAL_SCRIPT_NAMES_WIN = {
    "prod": "prod_install_from_tarball.ps1",
    "beta": "beta_install_from_tarball.ps1",
    "test": "test_install_from_tarball.ps1",
}


def _detect_platform() -> str:
    """Detect the current platform string used in tarball filenames."""
    os_name = platform.system().lower()
    if os_name == "darwin":
        os_name = "macos"
    arch = platform.machine().lower()
    if arch in ("x86_64", "amd64"):
        arch = "x64"
    elif arch in ("aarch64", "arm64"):
        arch = "arm64"
    # macOS x86_64 under Rosetta -> use arm64
    if os_name == "macos" and arch == "x64":
        try:
            result = subprocess.run(
                ["sysctl", "-n", "sysctl.proc_translated"],
                capture_output=True, text=True, timeout=2,
            )
            if result.stdout.strip() == "1":
                arch = "arm64"
        except Exception:
            pass
    return f"{os_name}-{arch}"


def _is_windows() -> bool:
    """Detect Windows regardless of the shell (cmd / PowerShell / Git Bash).

    We intentionally do NOT use ``platform.system() == 'Windows'`` alone,
    because on MSYS2/Cygwin Python builds that returns ``MSYS_NT-*`` /
    ``CYGWIN_NT-*`` and would miss those environments.  ``os.name == 'nt'``
    covers Windows-native Python (the common case, including Git Bash
    calling the Windows-installed Python), while ``sys.platform`` prefix
    check catches the rarer MSYS/Cygwin Python builds — in both cases the
    ``curl`` binary in use is the Schannel-based Windows build that needs
    ``--ssl-no-revoke``.
    """
    return os.name == "nt" or sys.platform.startswith(("win", "msys", "cygwin"))


def get_curl_install_flags() -> str:
    """Return the curl flags used to download the install script.

    On Windows, curl ships with Schannel and enforces CRL/OCSP revocation
    checks by default.  In restricted/offline networks this often fails
    with ``CRYPT_E_NO_REVOCATION_CHECK`` because the CRL server is
    unreachable, so we add ``--ssl-no-revoke`` to skip the revocation
    check.  On macOS/Linux curl uses OpenSSL which does not do revocation
    checks by default, so the extra flag is unnecessary.
    """
    if _is_windows():
        return "--ssl-no-revoke -s"
    return "-s"




@dataclass(frozen=True)
class ReleaseInfo:
    """Description of the newest release for the current install mode."""

    version: str
    version_source: str
    install_mode: str
    channel: str


@dataclass
class AutoUpdateState:
    """Persisted daemon auto-update status."""

    enabled: bool = True
    status: str = "idle"
    install_mode: str = "unknown"
    channel: str = "prod"
    current_version: str = "unknown"
    latest_version: Optional[str] = None
    last_installed_version: Optional[str] = None
    version_source: Optional[str] = None
    restart_required: bool = False
    last_checked_at: Optional[str] = None
    last_install_attempt_at: Optional[str] = None
    last_install_succeeded_at: Optional[str] = None
    last_error: Optional[str] = None
    last_check_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "AutoUpdateState":
        if not isinstance(data, dict):
            return cls()
        valid = {field.name for field in cls.__dataclass_fields__.values()}
        filtered = {key: value for key, value in data.items() if key in valid}
        return cls(**filtered)


class AutoUpdateStateStore:
    """Persist auto-update state to disk."""

    def __init__(self, state_file: Path = _AUTO_UPDATE_STATE_FILE):
        self.state_file = state_file

    def load(self) -> AutoUpdateState:
        state = AutoUpdateState()
        if self.state_file.exists():
            try:
                state = AutoUpdateState.from_dict(
                    json.loads(self.state_file.read_text(encoding="utf-8"))
                )
            except Exception as exc:
                logger.warning("Failed to read auto-update state %s: %s", self.state_file, exc)
        normalized, changed = self._normalize_for_current_version(state)
        if changed:
            self.save(normalized)
        return normalized

    def save(self, state: AutoUpdateState) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.state_file.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(state.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(tmp_path, self.state_file)

    def update(self, **changes) -> AutoUpdateState:
        state = self.load()
        for key, value in changes.items():
            if hasattr(state, key):
                setattr(state, key, value)
        self.save(state)
        return state

    def _normalize_for_current_version(self, state: AutoUpdateState) -> tuple[AutoUpdateState, bool]:
        current_version = siada.__version__
        changed = False
        if state.current_version != current_version:
            state.current_version = current_version
            changed = True
        if state.restart_required and state.last_installed_version == current_version:
            state.restart_required = False
            if state.status == "installed":
                state.status = "up_to_date"
            changed = True
        # Always re-detect install_mode from the current process.  The value on
        # disk may have been written by older code (when install_mode could be
        # "external" for a venv-based install), but the authoritative source is
        # the current runtime's detection logic, not the persisted state.
        try:
            detected_mode = detect_install_mode()
            if detected_mode and state.install_mode != detected_mode:
                state.install_mode = detected_mode
                changed = True
        except Exception:
            pass
        return state, changed



class CrossProcessFileLock:
    """Best-effort cross-process lock using OS file locking."""

    def __init__(self, lock_file: Path):
        self.lock_file = lock_file
        self._handle = None

    def acquire(self, timeout: float = 0.0, poll_interval: float = 0.1) -> bool:
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + max(timeout, 0.0)
        while True:
            handle = open(self.lock_file, "a+", encoding="utf-8")
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    handle.write("0")
                    handle.flush()
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                handle.seek(0)
                handle.truncate()
                handle.write(f"{os.getpid()}\n")
                handle.flush()
                self._handle = handle
                return True
            except OSError:
                handle.close()
                if time.time() >= deadline:
                    return False
                time.sleep(poll_interval)

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            self._handle.close()
        finally:
            self._handle = None

    def __enter__(self) -> "CrossProcessFileLock":
        if not self.acquire():
            raise RuntimeError(f"Failed to acquire lock: {self.lock_file}")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


class BaseUpdateStrategy:
    """Release query and install implementation for one install mode."""

    install_mode = "unknown"

    def __init__(self, channel: str = "prod"):
        self.channel = _normalize_channel(channel)

    def get_latest_release(self) -> ReleaseInfo:
        raise NotImplementedError

    def install_release(self, release: ReleaseInfo) -> tuple[bool, str]:
        raise NotImplementedError

    def get_manual_upgrade_hint(self) -> str:
        raise NotImplementedError


class InternalUpdateStrategy(BaseUpdateStrategy):
    """Auto-update via prebuilt venv tarball install script.

    Spawns a detached helper process that downloads and runs
    install_from_tarball.sh.  The install script kills the running
    daemon, downloads base/app tarballs, extracts, fixes shebangs,
    atomically swaps the venv symlink, and cleans up.  After the
    install script finishes, the helper starts a new daemon from
    the (now swapped) venv symlink path.
    """

    install_mode = "internal"

    def get_latest_release(self) -> ReleaseInfo:
        plat = _detect_platform()
        base = f"{_INTERNAL_BASE_URL}/{self.channel}"
        version_url = f"{base}/latest_version-{plat}"
        resp = requests.get(version_url, timeout=10)
        resp.raise_for_status()
        version = resp.text.strip()
        if not version:
            raise RuntimeError(f"Empty version from {version_url}")
        return ReleaseInfo(
            version=version,
            version_source=version_url,
            install_mode=self.install_mode,
            channel=self.channel,
        )

    def install_release(self, release: ReleaseInfo) -> tuple[bool, str]:
        plat = _detect_platform()
        if _is_windows():
            script_name = _INTERNAL_SCRIPT_NAMES_WIN[self.channel]
            script_url = f"{_INTERNAL_BASE_URL}/{self.channel}/{script_name}"
            # Set SIADA_AUTO_UPDATE env var so the install script knows to
            # restart the daemon after installation.  The script uses
            # Start-Process to launch the daemon as an independent top-level
            # process, avoiding parent-child relationship with the old daemon.
            # -WindowStyle Hidden + CREATE_NO_WINDOW prevents any black console
            # window from appearing.
            ps_command = (
                f"$env:SIADA_AUTO_UPDATE = '1'; "
                f"irm '{script_url}' | iex 5>&1"
            )
            _AUTO_UPDATE_INSTALL_LOG.parent.mkdir(parents=True, exist_ok=True)
            _log_fd = open(_AUTO_UPDATE_INSTALL_LOG, "a", encoding="utf-8")  # noqa: WPS515
            subprocess.Popen(
                [
                    "powershell",
                    "-WindowStyle", "Hidden",
                    "-ExecutionPolicy", "Bypass",
                    "-Command", ps_command,
                ],
                stdout=_log_fd,
                stderr=_log_fd,
                stdin=subprocess.DEVNULL,
                # DETACHED_PROCESS disconnects the PSHost, causing Write-Host output to be
                # silently discarded even when stdout is redirected to a file.
                # CREATE_NO_WINDOW alone is sufficient: it hides any console window and
                # the child process will survive when the install script kills this daemon
                # (Windows does not tie child lifetime to parent unless a Job Object is used).
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            logger.info(
                "Auto-update: spawned PowerShell install helper (script=%s, log=%s)",
                script_url, _AUTO_UPDATE_INSTALL_LOG,
            )
            return True, "Install helper spawned; daemon will be restarted by helper"

        script_name = _INTERNAL_SCRIPT_NAMES[self.channel]
        script_url = f"{_INTERNAL_BASE_URL}/{self.channel}/{script_name}"
        # Set SIADA_AUTO_UPDATE env var so the install script knows to restart
        # the daemon after installation.  The script uses nohup to launch the
        # daemon as an independent background process.
        # start_new_session=True ensures the helper survives when the install
        # script's kill_proactive_processes kills this daemon process.
        helper_script = (
            f"set -e\n"
            f"export SIADA_AUTO_UPDATE=1\n"
            f"curl -fsSL '{script_url}' | sh -s -- --no-modify-path\n"
        )
        _AUTO_UPDATE_INSTALL_LOG.parent.mkdir(parents=True, exist_ok=True)
        _log_fd = open(_AUTO_UPDATE_INSTALL_LOG, "a")  # noqa: WPS515
        subprocess.Popen(
            ["sh", "-c", helper_script],
            stdout=_log_fd,
            stderr=_log_fd,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
        logger.info(
            "Auto-update: spawned install helper (script=%s, log=%s)",
            script_url, _AUTO_UPDATE_INSTALL_LOG,
        )
        return True, "Install helper spawned; daemon will be restarted by helper"

    def get_manual_upgrade_hint(self) -> str:
        script_name = _INTERNAL_SCRIPT_NAMES[self.channel]
        script_url = f"{_INTERNAL_BASE_URL}/{self.channel}/{script_name}"
        return f"curl {get_curl_install_flags()} {script_url} | sh"


class ExternalUpdateStrategy(BaseUpdateStrategy):
    """Auto-update using PyPI for externally installed builds."""

    install_mode = "external"

    def get_latest_release(self) -> ReleaseInfo:
        pypi_url = "https://pypi.org/pypi/siada-cli/json"
        response = requests.get(pypi_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        version = data["info"]["version"]
        return ReleaseInfo(
            version=version,
            version_source=pypi_url,
            install_mode=self.install_mode,
            channel=self.channel,
        )

    def install_release(self, release: ReleaseInfo) -> tuple[bool, str]:
        docker_image = os.environ.get("SIADA_DOCKER_IMAGE")
        if docker_image:
            return False, f"Docker-based installs are not auto-updated. Run: docker pull {docker_image}"

        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--upgrade-strategy",
            "only-if-needed",
            "siada-cli",
        ]
        return _run_command(command)

    def get_manual_upgrade_hint(self) -> str:
        return " ".join(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "--upgrade-strategy",
                "only-if-needed",
                "siada-cli",
            ]
        )


class DaemonAutoUpdater:
    """Background auto-update loop owned by the proactive daemon."""

    def __init__(
        self,
        config: AutoUpdateConfig,
        stop_event: threading.Event,
        state_store: Optional[AutoUpdateStateStore] = None,
        strategy_factory: Optional[Callable[[str], BaseUpdateStrategy]] = None,
        log: Optional[logging.Logger] = None,
    ):
        self.config = config
        self._stop_event = stop_event
        self._state_store = state_store or AutoUpdateStateStore()
        self._strategy_factory = strategy_factory or build_update_strategy
        self._logger = log or logger
        self._thread: Optional[threading.Thread] = None
        self._singleflight_lock = threading.Lock()
        # Timestamp (monotonic) set when an install helper is spawned.
        # _run_loop uses this to extend the next sleep to _POST_INSTALL_BACKOFF_SECONDS
        # so the old daemon keeps serving users while the helper runs in the background,
        # and avoids duplicate spawns without shutting down the daemon.
        self._install_triggered_at: Optional[float] = None

    def _complete_pending_install(self) -> None:
        """If a previous install helper finished and launched us, mark it complete now.

        install_release() only spawns the helper and leaves status="installing".
        The helper's last step is `exec <new_python> -m siada.agent_hub.proactive`,
        so when we reach start() we ARE the new daemon.  If state says "installing"
        and our version matches latest_version, the install succeeded.
        """
        state = self._state_store.load()
        if state.status != "installing":
            return
        if not state.latest_version:
            return
        if state.latest_version != siada.__version__:
            # Version mismatch — install may have failed or is still running.
            return
        self._state_store.update(
            status="installed",
            last_installed_version=siada.__version__,
            last_install_succeeded_at=_now_iso(),
            restart_required=True,
            last_error=None,
        )
        self._logger.info(
            "Auto-update: install of v%s confirmed on daemon startup", siada.__version__
        )

    def start(self) -> None:
        self._complete_pending_install()
        if self._thread and self._thread.is_alive():
            return
        if not self.config.enabled:
            self._state_store.update(
                enabled=False,
                status="disabled",
                channel=self.config.channel,
                current_version=siada.__version__,
                install_mode=detect_install_mode(),
            )
            self._logger.info("Auto-update disabled by configuration")
            return

        self._thread = threading.Thread(
            target=self._run_loop,
            name="siada-auto-update",
            daemon=True,
        )
        self._thread.start()
        self._logger.info(
            "Auto-update background loop started (channel=%s, interval=%s min)",
            self.config.channel,
            self.config.check_interval_minutes,
        )

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def get_status(self) -> AutoUpdateState:
        return self._state_store.load()

    def check_now(self, reason: str = "manual") -> bool:
        if not self.config.enabled:
            self._state_store.update(
                enabled=False,
                status="disabled",
                channel=self.config.channel,
                current_version=siada.__version__,
                install_mode=detect_install_mode(),
                last_check_reason=reason,
            )
            return False

        if not self._singleflight_lock.acquire(blocking=False):
            self._logger.debug("Auto-update check skipped because another check is already running")
            return False

        try:
            state = self._state_store.load()
            if state.restart_required and state.last_installed_version != siada.__version__:
                self._logger.info(
                    "Auto-update check skipped because version %s is already installed "
                    "and waiting for restart",
                    state.last_installed_version,
                )
                return False

            file_lock = CrossProcessFileLock(_AUTO_UPDATE_LOCK_FILE)
            if not file_lock.acquire(timeout=0):
                self._logger.debug("Auto-update check skipped because update lock is busy")
                return False

            try:
                return self._check_with_lock(reason=reason)
            finally:
                file_lock.release()
        finally:
            self._singleflight_lock.release()

    # After spawning an install helper, sleep this long before the next check
    # to prevent duplicate spawns while the install runs in the background.
    # The install script will kill this daemon when it's ready; we just need
    # to stay alive (serving users) and not re-trigger.
    _POST_INSTALL_BACKOFF_SECONDS = 60 * 60  # 30 minutes

    def _run_loop(self) -> None:
        self.check_now(reason="startup")
        interval_seconds = max(1, self.config.check_interval_minutes) * 60
        while not self._stop_event.wait(interval_seconds):
            # If an install helper was already spawned, back off to avoid
            # duplicate installs while the helper is still running.
            if self._install_triggered_at is not None:
                elapsed = time.monotonic() - self._install_triggered_at
                remaining = self._POST_INSTALL_BACKOFF_SECONDS - elapsed
                if remaining > 0:
                    self._logger.info(
                        "Auto-update: install already triggered %.0fs ago, "
                        "skipping check (backoff for %.0fs more)",
                        elapsed, remaining,
                    )
                    interval_seconds = remaining
                    continue
                # Backoff expired (very unlikely — install should have killed us
                # by now).  Reset and allow one more check.
                self._logger.info(
                    "Auto-update: post-install backoff expired, resuming normal checks"
                )
                self._install_triggered_at = None
                interval_seconds = max(1, self.config.check_interval_minutes) * 60
            self.check_now(reason="interval")

    def _check_with_lock(self, reason: str) -> bool:
        install_mode = detect_install_mode()
        self._state_store.update(
            enabled=self.config.enabled,
            status="checking",
            channel=self.config.channel,
            current_version=siada.__version__,
            install_mode=install_mode,
            last_checked_at=_now_iso(),
            last_check_reason=reason,
            last_error=None,
        )

        try:
            release = self._strategy_factory(self.config.channel).get_latest_release()
        except Exception as exc:
            self._logger.warning("Failed to query latest version: %s", exc)
            self._state_store.update(
                status="check_failed",
                install_mode=install_mode,
                channel=self.config.channel,
                last_error=str(exc),
            )
            return False

        self._state_store.update(
            latest_version=release.version,
            version_source=release.version_source,
            install_mode=release.install_mode,
            channel=release.channel,
        )

        if not _is_newer_version(release.version, siada.__version__):
            self._state_store.update(status="up_to_date", last_error=None)
            self._logger.debug("Auto-update check found no newer version")
            return False

        self._logger.info(
            "Auto-update found newer version %s (current=%s, mode=%s)",
            release.version,
            siada.__version__,
            release.install_mode,
        )
        self._state_store.update(
            status="installing",
            last_install_attempt_at=_now_iso(),
            last_error=None,
        )

        try:
            strategy = self._strategy_factory(self.config.channel)
            success, output = strategy.install_release(release)
        except Exception as exc:
            success = False
            output = str(exc)

        if success:
            # Keep status="installing" — the helper subprocess is still running.
            # _complete_pending_install() on the new daemon's start() will flip it
            # to "installed" + restart_required=True once the install truly finishes.
            self._state_store.update(
                latest_version=release.version,
                last_error=None,
                version_source=release.version_source,
                install_mode=release.install_mode,
                channel=release.channel,
            )
            self._logger.info(
                "Auto-update spawned install helper for version %s; daemon will be restarted",
                release.version,
            )
            # Record the install trigger time so _run_loop backs off for
            # _POST_INSTALL_BACKOFF_SECONDS (30 min) before the next check.
            # This keeps the old daemon alive and serving users while the
            # install helper runs in the background, while still preventing
            # duplicate spawns.  The install script will kill this daemon
            # (Stop-ProactiveDaemon / kill_proactive_processes) when ready.
            self._install_triggered_at = time.monotonic()
            self._logger.info(
                "Auto-update: install helper spawned, entering 30-min backoff "
                "(daemon continues serving; install script will replace it)"
            )
            return True

        self._state_store.update(
            status="failed",
            last_error=output or f"Failed to install version {release.version}",
            latest_version=release.version,
            version_source=release.version_source,
            install_mode=release.install_mode,
            channel=release.channel,
        )
        self._logger.warning("Auto-update install failed: %s", output)
        return False


def detect_install_mode() -> str:
    """Return the current Siada install mode."""
    forced_mode = (os.environ.get("SIADA_AUTO_UPDATE_MODE") or os.environ.get("SIADA_UPDATE_SOURCE") or "").strip().lower()
    if forced_mode in {"internal", "external"}:
        return forced_mode

    candidates = {
        str(sys.executable),
        str(Path(sys.executable).resolve()),
        str(sys.prefix),
        str(Path(sys.prefix).resolve()),
        str(getattr(siada, "__file__", "")),
    }
    normalized = [item.replace("\\", "/") for item in candidates if item]
    if any("siada_cli_venv_" in item or "siada_cli_versions" in item for item in normalized):
        return "internal"
    return "external"
    # return "internal"


def build_update_strategy(channel: str = "prod") -> BaseUpdateStrategy:
    if detect_install_mode() == "internal":
        return InternalUpdateStrategy(channel=channel)
    return ExternalUpdateStrategy(channel=channel)


def get_runtime_auto_update_config() -> AutoUpdateConfig:
    try:
        from siada.config.config_loader import load_conf

        return load_conf().auto_update_config
    except Exception as exc:
        logger.debug("Falling back to default auto-update config: %s", exc)
        return AutoUpdateConfig()


def get_latest_release_info(config: Optional[AutoUpdateConfig] = None) -> ReleaseInfo:
    cfg = config or get_runtime_auto_update_config()
    return build_update_strategy(cfg.channel).get_latest_release()


def install_latest_update(
    config: Optional[AutoUpdateConfig] = None,
    state_store: Optional[AutoUpdateStateStore] = None,
    force: bool = False,
) -> tuple[bool, Optional[ReleaseInfo], str]:
    cfg = config or get_runtime_auto_update_config()
    store = state_store or AutoUpdateStateStore()
    lock = CrossProcessFileLock(_AUTO_UPDATE_LOCK_FILE)
    if not lock.acquire(timeout=0):
        return False, None, "Another update is already in progress"

    try:
        release = build_update_strategy(cfg.channel).get_latest_release()
        if not force and not _is_newer_version(release.version, siada.__version__):
            store.update(
                enabled=cfg.enabled,
                status="up_to_date",
                channel=release.channel,
                install_mode=release.install_mode,
                current_version=siada.__version__,
                latest_version=release.version,
                version_source=release.version_source,
                last_checked_at=_now_iso(),
                last_error=None,
            )
            return True, release, "Already up to date"

        store.update(
            enabled=cfg.enabled,
            status="installing",
            channel=release.channel,
            install_mode=release.install_mode,
            current_version=siada.__version__,
            latest_version=release.version,
            version_source=release.version_source,
            last_checked_at=_now_iso(),
            last_install_attempt_at=_now_iso(),
            last_error=None,
        )
        success, output = build_update_strategy(cfg.channel).install_release(release)
        if success:
            store.update(
                status="installed",
                channel=release.channel,
                install_mode=release.install_mode,
                latest_version=release.version,
                last_installed_version=release.version,
                last_install_succeeded_at=_now_iso(),
                restart_required=True,
                last_error=None,
                version_source=release.version_source,
            )
            return True, release, output or "Update installed"

        store.update(
            status="failed",
            channel=release.channel,
            install_mode=release.install_mode,
            latest_version=release.version,
            version_source=release.version_source,
            last_error=output or "Install failed",
        )
        return False, release, output or "Install failed"
    finally:
        lock.release()


def read_auto_update_state(state_file: Path = _AUTO_UPDATE_STATE_FILE) -> AutoUpdateState:
    return AutoUpdateStateStore(state_file=state_file).load()


def get_restart_required_message(state: Optional[AutoUpdateState] = None) -> Optional[str]:
    current_state = state or read_auto_update_state()
    if not current_state.restart_required:
        return None
    if not current_state.last_installed_version:
        return None
    if current_state.last_installed_version == siada.__version__:
        return None
    return (
        f"Background update installed v{current_state.last_installed_version}. "
        "Restart siada-cli to use the new version."
    )


def format_status_lines(state: Optional[AutoUpdateState] = None) -> list[str]:
    current_state = state or read_auto_update_state()
    lines = [
        f"Auto-update: {current_state.status}",
        f"  Mode: {current_state.install_mode}",
        f"  Channel: {current_state.channel}",
        f"  Current version: {current_state.current_version}",
    ]
    if current_state.latest_version:
        lines.append(f"  Latest version: {current_state.latest_version}")
    if current_state.last_installed_version:
        lines.append(f"  Last installed version: {current_state.last_installed_version}")
    if current_state.last_checked_at:
        lines.append(f"  Last checked: {current_state.last_checked_at}")
    if current_state.last_install_succeeded_at:
        lines.append(f"  Last install success: {current_state.last_install_succeeded_at}")
    if current_state.restart_required:
        lines.append("  Restart required: yes")
    if current_state.last_error:
        lines.append(f"  Last error: {current_state.last_error}")
    return lines



def _run_command(command: list[str], env: Optional[dict] = None) -> tuple[bool, str]:
    try:
        run_kwargs: dict = {
            "capture_output": True,
            "text": True,
            "check": False,
            "env": env,
        }
        if sys.platform == "win32":
            # Prevent console windows from popping up for each install command.
            run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        completed = subprocess.run(command, **run_kwargs)
    except Exception as exc:
        return False, str(exc)

    output = "\n".join(part for part in [completed.stdout, completed.stderr] if part).strip()
    if completed.returncode == 0:
        return True, output
    return False, output or f"Command exited with code {completed.returncode}"


def _is_newer_version(candidate: str, current: str) -> bool:
    try:
        return packaging.version.parse(candidate) > packaging.version.parse(current)
    except Exception:
        return False


def _normalize_channel(channel: Optional[str]) -> str:
    normalized = (channel or "prod").strip().lower()
    if normalized in _INTERNAL_SCRIPT_NAMES:
        return normalized
    return "prod"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "AutoUpdateState",
    "AutoUpdateStateStore",
    "BaseUpdateStrategy",
    "CrossProcessFileLock",
    "DaemonAutoUpdater",
    "ExternalUpdateStrategy",
    "InternalUpdateStrategy",
    "ReleaseInfo",
    "build_update_strategy",
    "detect_install_mode",
    "format_status_lines",
    "get_latest_release_info",
    "get_restart_required_message",
    "get_runtime_auto_update_config",
    "install_latest_update",
    "read_auto_update_state",
]
