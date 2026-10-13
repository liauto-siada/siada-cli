"""Run a local release-chain acceptance with real HTTPS, proxy and Chromium.

Run with Poetry, passing a freshly built wheel and browser artifact directory.
Only ACP model behavior is simulated. All user state is isolated.
"""

import argparse
import functools
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shlex
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.request

from playwright.sync_api import sync_playwright


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chromium", type=Path, required=True)
    args = parser.parse_args()
    args.wheel = args.wheel.resolve()
    args.artifacts = args.artifacts.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    root = args.output.resolve()
    home = root / "home"
    home.mkdir(exist_ok=True)
    venv = root / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    python = venv / "bin/python"
    subprocess.run([str(python), "-m", "pip", "install", "--no-deps", "--force-reinstall", str(args.wheel)], check=True, stdout=subprocess.DEVNULL)
    cert, key = root / "cert.pem", root / "key.pem"
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(key), "-out", str(cert), "-days", "1",
        "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    requests = []

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, fmt, *values):
            requests.append(self.path)

    site = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(args.artifacts)))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    site.socket = context.wrap_socket(site.socket, server_side=True)
    thread = threading.Thread(target=site.serve_forever, daemon=True)
    thread.start()
    proxy_port = free_port()
    browser = home / ".siada-cli/browser"
    node = browser / "runtime/bin/node"
    entry = browser / "proxy/dist/cli/bin.js"
    agent = Path(__file__).parent / "fixtures/success-agent.mjs"
    env = dict(os.environ, HOME=str(home), SSL_CERT_FILE=str(cert),
               BASE_URL="http://127.0.0.1:9/v1", API_KEY="sk-test-public-build",
               LITELLM_LOCAL_MODEL_COST_MAP="True", NO_PROXY="127.0.0.1,localhost")
    env.pop("PYTHONPATH", None)
    env.pop("SIADA_BROWSER_HOME", None)
    env.pop("SIADA_BROWSER_NODE", None)
    env["SIADA_BROWSER_PROXY_CMD"] = shlex.join([str(node), str(entry), "--host", "127.0.0.1", "--port", str(proxy_port), str(node), str(agent)])
    setup_code = (
        "from siada.browser_addon import cli; "
        "cli._open_url=lambda u:None; cli._copy_clipboard=lambda t:False; "
        "raise SystemExit(cli.main())"
    )

    def cli(command):
        result = subprocess.run([str(python), "-c", setup_code, *command], env=env, cwd=root, capture_output=True, text=True, timeout=90)
        # Setup prints the synthetic connection credential; keep raw output private.
        (root / "cli-output.log").write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f"CLI failed: {command[0]} (see private cli-output.log)")
        return result.stdout

    def status():
        return json.loads(cli(["status"]))

    checks = []
    try:
        base = f"https://localhost:{site.server_port}"
        cli(["setup", "--base-url", base, "--port", str(proxy_port)])
        installed = json.loads((browser / "installed.json").read_text())
        assert requests and "/browser-manifest.json" in requests
        assert any(path.endswith(".zip") for path in requests)
        assert status()["status"] == "ok"
        checks += ["real_https_download", "manifest_and_sha256", "wheel_installer", "proxy_started"]
        token = json.loads((browser / "state.json").read_text())["token"]
        with sync_playwright() as p:
            chrome = p.chromium.launch_persistent_context(
                str(root / "chrome-profile"), executable_path=str(args.chromium), headless=True,
                args=[f"--disable-extensions-except={browser / 'extension'}", f"--load-extension={browser / 'extension'}"],
            )
            try:
                worker = chrome.service_workers[0] if chrome.service_workers else chrome.wait_for_event("serviceworker", timeout=20000)
                extension_id = worker.url.split("/")[2]
                settings_page = chrome.new_page()
                settings_page.goto(f"chrome-extension://{extension_id}/dist/sidepanel.html", wait_until="domcontentloaded")
                settings_page.evaluate("settings => chrome.storage.local.set({acp_settings: settings})", {"proxyUrl": f"ws://127.0.0.1:{proxy_port}/ws", "token": token})
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline and not status().get("extensionConnected"):
                    time.sleep(0.2)
                assert status()["extensionConnected"] is True
                checks.append("actual_extension_executor_connected")
                page = chrome.new_page()
                page.goto(f"http://127.0.0.1:{proxy_port}/app", wait_until="networkidle")
                # A real browser WebSocket client drives the ACP session deterministically.
                result = page.evaluate("""async ({url, cwd}) => {
                  const socket = new WebSocket(url);
                  const messages = [];
                  const wait = type => new Promise((resolve, reject) => {
                    const timer = setTimeout(() => reject(new Error('timeout '+type)), 15000);
                    const inspect = () => {
                      const index = messages.findIndex(m => m.type===type);
                      if(index>=0) {clearTimeout(timer); socket.removeEventListener('message', inspect); resolve(messages.splice(index,1)[0]);}
                    };
                    socket.addEventListener('message', inspect); inspect();
                  });
                  socket.addEventListener('message', e=>messages.push(JSON.parse(e.data)));
                  await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
                  socket.send(JSON.stringify({type:'connect'}));
                  const connected = await wait('status');
                  if(!connected.payload.connected) throw new Error('agent did not connect');
                  socket.send(JSON.stringify({type:'new_session',payload:{cwd}}));
                  await wait('session_created');
                  socket.send(JSON.stringify({type:'prompt',payload:{content:[{type:'text',text:'synthetic acceptance'}]}}));
                  const update = await wait('session_update');
                  const done = await wait('prompt_complete');
                  socket.close();
                  return {update,done};
                }""", {"url": f"ws://127.0.0.1:{proxy_port}/ws?token={token}", "cwd": str(root)})
                assert "OFFLINE_RELEASE_CHAIN_OK" in json.dumps(result)
                assert result["done"]["payload"]["stopReason"] == "end_turn"
                checks.append("acp_initialize_session_prompt_stream_completion")
                request = urllib.request.Request(
                    f"http://127.0.0.1:{proxy_port}/mcp?token={token}",
                    data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "browser_tabs", "arguments": {}}}).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(request, timeout=20) as response:
                    tools = json.load(response)
                assert not tools["result"].get("isError")
                assert str(proxy_port) in json.dumps(tools)
                checks.append("mcp_browser_tabs_real_extension")
                tab_id = settings_page.evaluate(
                    "url => chrome.tabs.query({}).then(tabs => tabs.find(tab => tab.url===url).id)",
                    page.url,
                )
                page.set_content("<title>Synthetic acceptance</title><h1>RELEASE_BROWSER_READ_OK</h1><p>Offline browser package verification.</p>")
                request = urllib.request.Request(
                    f"http://127.0.0.1:{proxy_port}/mcp?token={token}",
                    data=json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "browser_read", "arguments": {"tabId": tab_id}}}).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(request, timeout=20) as response:
                    read_result = json.load(response)
                assert not read_result["result"].get("isError")
                assert "RELEASE_BROWSER_READ_OK" in json.dumps(read_result)
                checks.append("mcp_browser_read_real_page")
                page.screenshot(path=str(root / "web-client.png"))
            finally:
                chrome.close()
        cli(["restart"])
        assert status()["status"] == "ok"
        checks.append("proxy_restart")
        cli(["setup", "--base-url", base, "--port", str(proxy_port)])
        assert json.loads((browser / "state.json").read_text())["token"] == token
        assert status()["status"] == "ok"
        checks.append("reinstall_preserves_token_and_restarts")
        cli(["stop"])
        assert status()["running"] is False
        checks.append("proxy_stop")
        report = {
            "checks": checks, "installed": installed,
            "wheel_sha256": hashlib.sha256(args.wheel.read_bytes()).hexdigest(),
            "limitations": ["local synthetic ACP peer; no live model", "isolated headless Chromium; no manual Chrome loading", "macOS ARM64 only"],
        }
        (root / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
    finally:
        try:
            cli(["stop"])
        finally:
            site.shutdown()
            site.server_close()


if __name__ == "__main__":
    main()