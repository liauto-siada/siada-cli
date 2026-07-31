import json
import os
import subprocess
import sys


def test_module_entrypoint_serves_official_initialize_and_exits_on_eof():
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": 1,
            "clientCapabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
    }
    environment = os.environ | {"PYTHONPATH": "."}

    process = subprocess.run(
        [sys.executable, "-m", "siada.acp_server"],
        input=json.dumps(request) + "\n",
        text=True,
        capture_output=True,
        cwd=os.getcwd(),
        env=environment,
        timeout=20,
        check=True,
    )

    messages = [json.loads(line) for line in process.stdout.splitlines()]
    assert messages == [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": 1,
                "agentCapabilities": {"sessionCapabilities": {"list": {}}},
                "agentInfo": {"name": "siada", "title": "Siada", "version": "1.7.17"},
            },
        }
    ]
    assert process.stderr == ""
