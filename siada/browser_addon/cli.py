"""siada-browser — quick install of the chrome-acp sidepanel + proxy server.

    siada-browser setup <chrome-acp-repo> [--port N]
    siada-browser start | stop | restart | status

The same commands are reachable from siada-cli without a separate entry:

    siada-cli --browser-setup <chrome-acp-repo> [--browser-port N]
    siada-cli --browser-start | --browser-stop | --browser-restart | --browser-status
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from siada.browser_addon import installer, manager, paths


def _print(msg: str = "") -> None:
    print(msg, flush=True)


def _open_url(url: str) -> None:
    try:
        if sys.platform == "darwin":
            # `open` alone can't handle chrome:// URLs — target Chrome explicitly.
            if url.startswith("chrome://"):
                subprocess.Popen(["open", "-a", "Google Chrome", url])
            else:
                subprocess.Popen(["open", url])
        elif sys.platform.startswith("win"):
            os.startfile(url)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", url])
    except OSError:
        pass


def _copy_clipboard(text: str) -> bool:
    try:
        if sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text.encode(), check=True, timeout=5)
        elif sys.platform.startswith("win"):
            subprocess.run(["clip"], input=text.encode(), check=True, timeout=5)
        else:
            subprocess.run(["wl-copy", text], check=True, timeout=5)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def cmd_setup(args: argparse.Namespace) -> int:
    if args.repo:
        _print(f"==> Installing proxy server (from {args.repo})...")
        installer.install_proxy(Path(args.repo))
        _print(f"    ✓ {paths.proxy_dir()}")
        _print("==> Installing the Chrome extension ...")
        installer.install_extension(Path(args.repo))
        _print(f"    ✓ {paths.extension_dir()}")
    else:
        base = args.base_url or installer.DEFAULT_BOS_BASE
        installer.install_proxy_from_bos(base)
        installer.install_extension_from_bos(base)

    state = manager.init_state(args.port, args.host)

    _print("==> Launch proxy ...")
    _print(f"    {manager.restart()}")

    # ---- Guided extension loading (manual user action, done once) ----
    _print()
    _print("==> Load the extension in Chrome (manual steps):")
    _print("    1. Open chrome://extensions and turn on \"Developer mode\" (top right)")
    ext_dir = str(paths.extension_dir())
    _copy_clipboard(ext_dir)
    _print(f"    2. Click \"Load unpacked\" → select the directory: {ext_dir} (path already copied to clipboard)")
    _print("    3. Open the siada extension side panel → Settings → paste the token (this token is the credential that lets Chrome connect to your local siada-cli; keep it safe):")
    _copy_clipboard(str(state["token"]))
    _print(f"       {state['token']}")
    _open_url("chrome://extensions")

    # ---- Remote access guide (only when host is not loopback) ----
    if not manager._is_loopback(args.host):
        ip = manager.lan_ip()
        _print()
        _print("==> Remote access guide (for other LAN devices reaching this proxy):")
        _print("    1. Find this machine's LAN IP:")
        if ip:
            _print(f"       {ip} (confirm with ifconfig / ipconfig if it does not match)")
        else:
            _print("       Could not detect it; run ifconfig (macOS/Linux) or ipconfig (Windows) locally to check")
        _print("    2. In the side panel settings, set the address to:")
        _print(f"       wss://{ip or '<LAN-IP>'}:{args.port}/ws  (wss is required: the proxy allows plain ws on loopback only)")
        _print("    3. Paste the token copied in step 3 above")
        _print("    4. Trust the self-signed certificate — this step must come first: the extension page has no certificate-warning entry,")
        _print("       and the wss handshake fails outright until the certificate is trusted. Open in a normal tab:")
        _print(f"       https://{ip or '<LAN-IP>'}:{args.port}/app?token={state['token']}")
        _print("       accept the warning via \"Advanced → Proceed\"; or import ~/.acp-proxy/cert.pem into the system trust store")
        _print(f"    (the local Chrome extension is unaffected: it still uses ws://localhost:{args.port}/ws and needs no trusted certificate)")

    # if args.no_wait:
    #     _print("\n✅ Setup complete. After loading the extension as described above, check the connection with `siada-browser status`.")
    #     return 0

    # _print("\n==> Waiting for the extension to connect ...")
    # for _ in range(30):
    #     st = manager.status()
    #     if st.get("extensionConnected"):
    #         _print(f"✅ Extension connected: {json.dumps(st.get('executor'), ensure_ascii=False)}")
    #         _print("   Click the extension icon in the Chrome toolbar to start using it.")
    #         return 0
    #     time.sleep(2)
    # _print("⏳ No extension connection within 60s. Once the steps above are done, check anytime with `siada-browser status`.")
    return 0


def _run_manager(fn: str) -> int:
    """Run a manager lifecycle function and map 'error: ...' results to exit 1."""
    result = getattr(manager, fn)()
    _print(result)
    return 1 if str(result).startswith("error") else 0


def cmd_status(args: argparse.Namespace) -> int:
    print(json.dumps(manager.status(), indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="siada-browser",
        description="Quick install and start/stop for the chrome-acp sidepanel + proxy server",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("setup", help="Install the proxy + extension and start them (no argument = download from BOS)")
    p.add_argument("repo", nargs="?", default=None, help="Path to the chrome-acp repo (must be built); omit to download from BOS")
    p.add_argument("--port", type=int, default=paths.DEFAULT_PORT)
    p.add_argument("--host", default="127.0.0.1",
                   help="Proxy listen address; set to 0.0.0.0 to let other LAN devices connect remotely (enables wss/https)")
    p.add_argument("--base-url", default=None, help=f"Override the BOS base URL (default {installer.DEFAULT_BOS_BASE})")
    p.add_argument("--no-wait", action="store_true", help="Do not poll for the extension connection (used by installer scripts)")
    p.set_defaults(func=cmd_setup)

    for name, fn, help_ in (
        ("start", "start", "Start the proxy (idempotent)"),
        ("stop", "stop", "Stop the proxy"),
        ("restart", "restart", "Restart the proxy (stop + start)"),
        ("status", None, "Query the proxy /status endpoint"),
    ):
        sp = sub.add_parser(name, help=help_)
        if fn:
            sp.set_defaults(func=lambda a, f=fn: _run_manager(f))
        else:
            sp.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
