"""Verify built sidepanel reopen against an isolated proxy and fake ACP agent."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright


def wait_for(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("Verification timed out")


def main():
    base = Path(__file__).resolve().parents[4]
    source = base / "packages/chrome-extension"
    node = shutil.which("node")
    browser = os.environ["SIADA_RETENTION_TEST_BROWSER"]
    with tempfile.TemporaryDirectory(prefix="siada-retention-browser-") as raw:
        home = Path(raw).resolve()
        extension = home / "extension"
        extension.mkdir()
        shutil.copytree(source / "dist", extension / "dist")
        shutil.copytree(source / "icons", extension / "icons")
        for name in ("manifest.json", "background.js"):
            shutil.copy2(Path(__file__).parent / name, extension / name)
        digest = hashlib.sha256(str(extension).encode()).hexdigest()[:32]
        extension_id = "".join(chr(97 + int(char, 16)) for char in digest)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        proxy = subprocess.Popen(
            [
                node, str(base / "packages/proxy-server/dist/cli/bin.js"),
                "--host", "127.0.0.1", "--port", str(port), node, "--",
                str(base / "packages/proxy-server/test/fixtures/fake-agent.mjs"),
                "--retention",
            ],
            cwd=home,
            env={
                **os.environ,
                "ACP_AUTH_TOKEN": "synthetic-browser-retention",
                "SIADA_BROWSER_EXTENSION_IDS": extension_id,
                "SIADA_PROXY_MANAGED": "1",
                "SIADA_PROXY_LOG_DIR": str(home / "logs"),
                "SIADA_RETENTION_TEST_LAUNCH_LOG": str(home / "launches.txt"),
            },
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        def status():
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=1) as response:
                    return json.load(response)
            except OSError:
                return None

        try:
            wait_for(status)
            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    str(home / "profile"), headless=True, executable_path=browser,
                    args=[
                        "--disable-extensions-except=" + str(extension),
                        "--load-extension=" + str(extension),
                    ],
                    viewport={"width": 600, "height": 850},
                )
                try:
                    worker = context.service_workers[0] if context.service_workers else context.wait_for_event("serviceworker")
                    worker.evaluate(
                        "(settings) => chrome.storage.local.set({acp_settings: settings})",
                        {"proxyUrl": f"ws://127.0.0.1:{port}/ws", "token": "synthetic-browser-retention"},
                    )
                    endpoint = f"chrome-extension://{extension_id}/dist/sidepanel.html"
                    read_session = """async () => {
                        const window = await chrome.windows.getCurrent();
                        const key = 'sidepanel_last_session:' + window.id;
                        const stored = await chrome.storage.local.get(key);
                        return stored[key]?.sessionId || null;
                    }"""
                    first = context.new_page()
                    started = time.monotonic()
                    first.goto(endpoint)
                    try:
                        session_id = wait_for(lambda: first.evaluate(read_session))
                    except AssertionError:
                        print("Sidepanel state:", first.locator("body").inner_text()[:800])
                        raise
                    cold = time.monotonic() - started
                    first.close()
                    wait_for(lambda: (status() or {}).get("retainedAgentSessions") == 1)
                    second = context.new_page()
                    started = time.monotonic()
                    second.goto(endpoint)
                    second.get_by_text("retained history", exact=False).wait_for(timeout=15000)
                    warm = time.monotonic() - started
                    assert second.evaluate(read_session) == session_id
                    assert len((home / "launches.txt").read_text().splitlines()) == 1
                    second.screenshot(path="/tmp/siada-retention-reopened.png")
                    print("PASS: built sidepanel close/reopen keeps one agent, one session, and visible history")
                    print(f"Fake-agent cold open: {cold:.3f}s; warm reopen: {warm:.3f}s")
                finally:
                    context.close()
        finally:
            proxy.terminate()
            proxy.wait(timeout=5)


if __name__ == "__main__":
    main()