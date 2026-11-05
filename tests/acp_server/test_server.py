from siada.acp_server.server import AcpServer


def initialize_request(request_id=1):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "initialize",
        "params": {
            "protocolVersion": 1,
            "clientInfo": {"name": "test-client", "version": "1.0"},
            "capabilities": {},
        },
    }


def test_initialize_then_create_session_returns_agent_and_session_ids():
    server = AcpServer(turn_runner=lambda *_: ())

    initialize = server.handle(initialize_request())
    session = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/new",
            "params": {"cwd": "/tmp", "mcpServers": []},
        }
    )

    assert initialize["result"]["protocolVersion"] == 1
    assert initialize["result"]["agentInfo"]["name"] == "Siada"
    assert session["result"]["sessionId"]


def test_prompt_for_unknown_session_returns_invalid_params_error():
    server = AcpServer(turn_runner=lambda *_: ())
    server.handle(initialize_request())

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "session/prompt",
            "params": {"sessionId": "missing", "prompt": [{"type": "text", "text": "hello"}]},
        }
    )

    assert response["error"]["code"] == -32602


def test_prompt_returns_response_and_emits_standard_session_updates():
    server = AcpServer(
        turn_runner=lambda _session_id, _prompt: (
            {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "hello"}},
            {"sessionUpdate": "end_turn"},
        )
    )
    server.handle(initialize_request())
    session_id = server.handle(
        {"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {}}
    )["result"]["sessionId"]

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "session/prompt",
            "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "hello"}]},
        }
    )

    assert response == {"jsonrpc": "2.0", "id": 3, "result": {}}
    assert server.drain_notifications() == [
        {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": session_id,
                "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "hello"}},
            },
        },
        {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {"sessionId": session_id, "update": {"sessionUpdate": "end_turn"}},
        },
    ]


def test_cancel_marks_known_session_and_returns_success():
    server = AcpServer(turn_runner=lambda *_: ())
    server.handle(initialize_request())
    session_id = server.handle(
        {"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {}}
    )["result"]["sessionId"]

    response = server.handle(
        {"jsonrpc": "2.0", "id": 3, "method": "session/cancel", "params": {"sessionId": session_id}}
    )

    assert response == {"jsonrpc": "2.0", "id": 3, "result": {}}
    assert server.is_cancelled(session_id)

