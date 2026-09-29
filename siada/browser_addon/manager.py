"""Start/stop/status for the chrome-acp proxy.

Spawn is detached from the spawning shell so the proxy outlives it:

- POSIX: ``start_new_session=True`` → ``setsid()``; the proxy survives the
  siada session (shell backgrounds die to SIGHUP when the spawning PTY exits).
- Windows: ``start_new_session`` is POSIX-only and silently ignored — the
  child would inherit the PowerShell console and die when the user closes the
  window (CTRL_CLOSE_EVENT) or presses Ctrl+C. ``DETACHED_PROCESS`` gives it
  no console at all (stdio is fully redirected), and
  ``CREATE_NEW_PROCESS_GROUP`` keeps console signals away.

The token is persisted in state.json and passed via ACP_AUTH_TOKEN — the
proxy generates a random token per launch otherwise, which silently
disconnects extensions holding the previous one. The bind host is persisted
alongside (default 127.0.0.1); a non-loopback bind (e.g. 0.0.0.0 for LAN
access) adds ``--https``. The proxy's dual-protocol port then serves TLS to
remote peers while loopback clients keep plaintext ws/http on the same
port, so local setups need no certificate trust.
"""

from __future__ import annotations

import json
import os
import secrets
import shlex
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from siada.browser_addon import paths

_START_TIMEOUT = 30.0  # first launch after install can take ~10s: macOS scans
                       # the freshly-extracted node_modules before loading it

# subprocess exposes the Windows creation flags only on Windows; fall back to
# the documented Win32 values so this module imports (and is testable) on
# every platform.
_DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
_CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)


def _popen_detach_kwargs() -> dict[str, Any]:
    """Popen kwargs that detach the child from the spawning shell/console.

    POSIX: start_new_session (setsid). Windows: DETACHED_PROCESS (no console,
    so no CTRL_CLOSE_EVENT / Ctrl+C can reach it) + CREATE_NEW_PROCESS_GROUP.
    """
    if sys.platform.startswith("win"):
        return {
            "creationflags": _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP,
        }
    return {"start_new_session": True}


_DEFAULT_HOST = "127.0.0.1"
_LOOPBACK_HOSTS = {"", "localhost", "127.0.0.1", "::1"}


def _is_loopback(host: str) -> bool:
    """True if host is reachable only on this machine (no --https needed)."""
    return host in _LOOPBACK_HOSTS


def lan_ip() -> str | None:
    """Best-effort LAN IPv4: UDP-connect (no packets sent) and read the local
    address. Returns None when the address cannot be determined."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return None


# ---------------------------------------------------------------------------
# state.json
# ---------------------------------------------------------------------------

def load_state() -> dict[str, Any]:
    try:
        return json.loads(paths.state_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict[str, Any]) -> None:
    path = paths.state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)  # holds the auth token
    except OSError:
        pass


def init_state(port: int, host: str = _DEFAULT_HOST) -> dict[str, Any]:
    """Load or create {port, token, host}, keeping an existing token stable."""
    state = load_state()
    state.setdefault("token", secrets.token_hex(32))
    state["port"] = port
    state["host"] = host
    save_state(state)
    return state


def effective_host() -> str:
    return str(load_state().get("host") or _DEFAULT_HOST)


def effective_port() -> int:
    return int(load_state().get("port") or paths.DEFAULT_PORT)


# ---------------------------------------------------------------------------
# HTTP (stdlib only)
# ---------------------------------------------------------------------------

# Health probes target localhost and must NEVER go through an HTTP proxy:
# on macOS urllib picks up the *system* proxy (e.g. Proxyman), which drops
# the probe loop with RemoteDisconnected even while the proxy is healthy.
# When the proxy binds a non-loopback host it serves --https with a
# self-signed cert (SANs cover the LAN IPs), so probes use an unverified SSL
# context: the cert is locally generated, /health carries no sensitive data,
# and access is already gated by ACP_AUTH_TOKEN at the application layer.
_opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    urllib.request.HTTPSHandler(context=ssl._create_unverified_context()),
)


def _probe_scheme() -> str:
    """Scheme for localhost probes: https iff the proxy binds non-loopback.

    With --https every endpoint (including /health) is served over TLS, so
    the probe must follow the scheme even though it still targets localhost.
    """
    return "http" if _is_loopback(effective_host()) else "https"


def _fetch(path_query: str, timeout: float = 1.5) -> str | None:
    url = f"{_probe_scheme()}://localhost:{effective_port()}{path_query}"
    try:
        with _opener.open(url, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except OSError:
        return None


def is_running() -> bool:
    return _fetch("/health") is not None


def status() -> dict[str, Any]:
    body = _fetch("/status")
    if body is None:
        return {"running": False}
    try:
        st = json.loads(body)
    except json.JSONDecodeError:
        return {"running": True}
    st.setdefault("running", True)
    return st


# ---------------------------------------------------------------------------
# process control
# ---------------------------------------------------------------------------

def _kill(pid: int) -> None:
    try:
        if sys.platform.startswith("win"):
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5)
        else:
            os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


def stop() -> str:
    """Kill the proxy: by pidfile if we spawned it, else by port."""
    pid: int | None = None
    try:
        pid = int(paths.browser_home().joinpath("proxy.pid").read_text().strip())
    except (OSError, ValueError):
        pass
    if pid is not None:
        _kill(pid)
        paths.browser_home().joinpath("proxy.pid").unlink(missing_ok=True)
    elif _fetch("/health") is not None:
        try:
            out = subprocess.run(
                ["lsof", "-ti", f"tcp:{effective_port()}"], capture_output=True, text=True, timeout=5
            ).stdout
            for p in out.split():
                if p.isdigit():
                    _kill(int(p))
        except (OSError, subprocess.SubprocessError):
            pass
    time.sleep(0.5)
    return "stopped" if not is_running() else "error: proxy still running"


def _proxy_argv(entry: Path, port: int, host: str, agent: str) -> list[str]:
    """Spawn argv for the chrome-acp proxy bound to host.

    Flags MUST precede the agent command (acp-proxy CLI parsing); agent flags
    go after ``--`` (argument escape sequence). Non-loopback hosts add
    ``--https`` so remote peers get self-signed TLS; the dual-protocol port
    keeps plaintext ws/http available to loopback clients.
    """
    argv = [paths.node_binary(), str(entry), "--host", host, "--port", str(port)]
    if not _is_loopback(host):
        argv.append("--https")
    argv += [agent, "--", "--acp"]
    return argv


def start() -> str:
    """Idempotent start. Returns 'running' | 'started' | 'error: ...'."""
    if is_running():
        return "running"

    entry = paths.proxy_entry()
    if entry is None:
        return "error: proxy not installed (run `siada-cli --browser-setup` or `siada-browser setup` first)"

    state = load_state()
    port = effective_port()
    host = effective_host()
    override = os.environ.get("SIADA_BROWSER_PROXY_CMD")
    if override:  # test hook
        cmd = shlex.split(override)
    else:
        agent = shutil.which("siada-cli") or "siada-cli"
        cmd = _proxy_argv(entry, port, host, agent)

    env = dict(os.environ)
    if state.get("token"):
        env["ACP_AUTH_TOKEN"] = str(state["token"])
    # Mark the agent subprocess as browser-launched (the proxy spawns
    # `siada-cli --acp` for every sidepanel connection). The agent stays
    # "coder"; only its X-Siada-Event-Type analytics header is remapped
    # (CodeGenAgent -> BrowserCodeGenAgent) so browser traffic is separable.
    env["SIADA_BROWSER_LAUNCH"] = "1"

    # The proxy's cwd becomes the sidepanel's default workspace (file tree +
    # agent sessions). NEVER use $HOME: ~/Library contains TCC-protected
    # directories (Spotlight metadata, Shortcuts) whose readdir fails with
    # EPERM and floods the sidepanel with "list_dir failed" errors.
    proxy_cwd = str(Path.home() / ".siada-cli" / "workspace")
    os.makedirs(proxy_cwd, exist_ok=True)

    paths.browser_home().mkdir(parents=True, exist_ok=True)
    log = open(paths.log_path(), "ab")
    try:
        proc = subprocess.Popen(
            cmd, cwd=proxy_cwd, env=env,
            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            **_popen_detach_kwargs(),
        )
    except OSError as e:
        log.close()
        return f"error: failed to spawn proxy: {e}"
    log.close()  # Popen dup'd the fd into the child

    paths.browser_home().joinpath("proxy.pid").write_text(str(proc.pid), encoding="utf-8")

    deadline = time.monotonic() + _START_TIMEOUT
    while time.monotonic() < deadline:
        if is_running():
            return "started"
        if proc.poll() is not None:
            return f"error: proxy exited with code {proc.returncode} (see {paths.log_path()})"
        time.sleep(0.3)
    return f"error: proxy not healthy within {_START_TIMEOUT}s (see {paths.log_path()})"


def restart() -> str:
    stop()
    return start()
