import io
import json

from siada.acp_server.stdio import serve


def test_stdio_serves_ndjson_requests_and_notifications():
    stdin = io.StringIO(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": 1, "clientInfo": {"name": "test", "version": "1"}, "capabilities": {}},
            }
        )
        + "\n"
    )
    stdout = io.StringIO()

    serve(stdin, stdout)

    response = json.loads(stdout.getvalue())
    assert response["result"]["agentInfo"]["name"] == "Siada"


def test_stdio_reports_parse_errors_and_continues_to_next_request():
    stdin = io.StringIO("not-json\n" + json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": 1}}) + "\n")
    stdout = io.StringIO()

    serve(stdin, stdout)

    messages = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert messages[0]["error"]["code"] == -32700
    assert messages[1]["result"]["protocolVersion"] == 1
