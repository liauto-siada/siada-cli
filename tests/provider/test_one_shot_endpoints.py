"""Mock-HTTP coverage for independent endpoints and provider-owned clients."""

import asyncio
import json
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from openai import AsyncOpenAI

from siada.provider import one_shot, provider_factory
from siada.provider.default import chat_completions, responses_transport
from siada.provider.default.default_provider import DefaultProvider
from siada.provider.request_config import default_credentials_scope, get_default_credentials


class SyntheticSSEStream(httpx.AsyncByteStream):
    """Track request-body cleanup independently from HTTP-client ownership."""

    def __init__(self, events):
        self.events = events
        self.closed = False

    async def __aiter__(self):
        for event in self.events:
            await asyncio.sleep(0)
            event_name = f"event: {event['type']}\n" if "type" in event else ""
            yield f"{event_name}data: {json.dumps(event)}\n\n".encode()

    async def aclose(self):
        self.closed = True


@pytest.fixture
def runtime(monkeypatch):
    requests = []
    clients = []

    async def handler(request):
        body = json.loads(request.content)
        requests.append(request)
        await asyncio.sleep(0)
        if request.url.path.endswith("/responses"):
            payload = {
                "id": "resp-synthetic", "object": "response", "created_at": 1,
                "status": "completed", "model": body["model"],
                "output": [{"id": "msg-synthetic", "type": "message", "role": "assistant",
                            "status": "completed", "content": [{"type": "output_text", "text": "ok", "annotations": []}]}],
                "usage": {"input_tokens": 3, "output_tokens": 1, "total_tokens": 4,
                          "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}},
            }
        else:
            payload = {
                "id": "chatcmpl-synthetic", "object": "chat.completion", "created": 1, "model": body["model"],
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
            }
        if body.get("stream"):
            if request.url.path.endswith("/responses"):
                events = [{"type": "response.completed", "sequence_number": 1, "response": payload}]
            else:
                common = {"id": "chatcmpl-synthetic", "object": "chat.completion.chunk",
                          "created": 1, "model": body["model"]}
                events = [
                    {**common, "choices": [{"index": 0, "delta": {"role": "assistant", "content": "o"}, "finish_reason": None}]},
                    {**common, "choices": [{"index": 0, "delta": {"content": "k"}, "finish_reason": "stop"}]},
                    {**common, "choices": [], "usage": payload["usage"]},
                ]
            stream = SyntheticSSEStream(events)
            request.extensions["synthetic_stream"] = stream
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream, request=request)
        return httpx.Response(200, json=payload, request=request)

    def make_client(**kwargs):
        client = AsyncOpenAI(
            **kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        clients.append(client)
        return client

    monkeypatch.setattr(chat_completions, "AsyncOpenAI", make_client)
    monkeypatch.setattr(responses_transport, "AsyncOpenAI", make_client)
    monkeypatch.setenv("BASE_URL", "https://main.test/v1")
    monkeypatch.setenv("API_KEY", "synthetic-main-key")
    monkeypatch.setattr(provider_factory, "_discover_providers", lambda: None)
    monkeypatch.setattr(provider_factory, "provider_map", {"default": DefaultProvider()})
    return requests, clients


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["gpt-4o", "gpt-5.4"])
@pytest.mark.parametrize("stream", [None, False, True])
async def test_concurrent_main_and_independent_endpoints_share_owned_caches(runtime, model, stream):
    requests, clients = runtime

    async def fetch(label, **options):
        response = await one_shot.one_shot_completion(
            label, model=model, provider="default", timeout=1,
            extra_headers={"X-Synthetic-Caller": label}, **options,
            **({"stream": stream} if stream is not None else {}),
        )
        assert one_shot.extract_response_text(response) == "ok"
        assert (response.usage.input_tokens, response.usage.output_tokens, response.usage.total_tokens) == (3, 1, 4)

    async with provider_factory.provider_runtime():
        await asyncio.gather(
            fetch("main"),
            fetch("aux-one", api_base="https://aux.test/v1", api_key="synthetic-aux-key"),
            fetch("aux-two", api_base="https://aux.test/v1", api_key="synthetic-aux-key"),
            fetch("other", base_url="https://other.test/v1", api_key="synthetic-other-key"),
        )
        await fetch("main-again")
        assert len(clients) == 3
        assert all(not client.is_closed() for client in clients)
        assert get_default_credentials() == ("https://main.test/v1", "synthetic-main-key")
    assert all(client.is_closed() for client in clients)
    assert len(requests) == 5
    sent = {request.headers["X-Synthetic-Caller"]: request for request in requests}
    assert sent["main"].url.host == sent["main-again"].url.host == "main.test"
    assert sent["aux-one"].url.host == sent["aux-two"].url.host == "aux.test"
    assert sent["other"].url.host == "other.test"
    assert sent["aux-one"].headers["authorization"] == "Bearer synthetic-aux-key"
    assert sent["main-again"].headers["authorization"] == "Bearer synthetic-main-key"
    for request in requests:
        body = json.loads(request.content)
        assert body.get("stream", False) is (stream is not False)
        if stream is not False:
            assert request.extensions["synthetic_stream"].closed
        assert not body.get("tools")
        assert "api_key" not in body and "api_base" not in body


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["gpt-4o", "gpt-5.4"])
async def test_independent_endpoint_does_not_require_main_credentials(runtime, monkeypatch, model):
    requests, clients = runtime
    monkeypatch.delenv("API_KEY")
    async with provider_factory.provider_runtime():
        response = await one_shot.one_shot_completion(
            "hello", model=model, provider="default",
            api_base="https://aux.test/v1", api_key="synthetic-aux-key",
        )
        assert one_shot.extract_response_text(response) == "ok"
    assert len(requests) == 1
    assert clients[0].is_closed()


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["gpt-4o", "gpt-5.4"])
async def test_missing_credentials_fail_without_http_request(runtime, monkeypatch, model):
    requests, _ = runtime
    monkeypatch.delenv("API_KEY")
    async with provider_factory.provider_runtime():
        with pytest.raises(ValueError, match="API_KEY is required"):
            await one_shot.one_shot_completion("hello", model=model, provider="default")
    assert requests == []


def test_nested_endpoint_scopes_restore_credentials_after_failure(monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://main.test/v1")
    monkeypatch.setenv("API_KEY", "synthetic-main-key")
    with default_credentials_scope(base_url="https://aux.test/v1", api_key="synthetic-aux-key"):
        with pytest.raises(RuntimeError):
            with default_credentials_scope(base_url="https://other.test/v1", api_key="synthetic-other-key"):
                assert get_default_credentials() == ("https://other.test/v1", "synthetic-other-key")
                raise RuntimeError("synthetic failure")
        assert get_default_credentials() == ("https://aux.test/v1", "synthetic-aux-key")
    assert get_default_credentials() == ("https://main.test/v1", "synthetic-main-key")


@pytest.mark.asyncio
async def test_endpoint_scope_does_not_change_provider_configuration(runtime):
    async with provider_factory.provider_runtime():
        provider = provider_factory.get_provider("default")
        with provider.request_scope(base_url="https://aux.test/v1", api_key="synthetic-aux-key"):
            provider.get_model("gpt-4o")
            assert provider.base_url == "https://main.test/v1"
            assert provider.api_key == "synthetic-main-key"
        assert get_default_credentials() == ("https://main.test/v1", "synthetic-main-key")


@pytest.mark.asyncio
async def test_openrouter_endpoint_override_selects_correct_wire_model(runtime):
    requests, _ = runtime
    async with provider_factory.provider_runtime():
        await one_shot.one_shot_completion(
            "hello", model="gpt-4o", provider="default",
            base_url="https://openrouter.ai/api/v1", api_key="synthetic-openrouter-key",
        )
    assert requests[0].url.host == "openrouter.ai"
    assert json.loads(requests[0].content)["model"] == "openai/gpt-4o"


@pytest.mark.asyncio
async def test_native_chat_wire_preserves_history_images_and_settings(runtime):
    requests, _ = runtime
    history = [
        {"role": "user", "content": "update a.py"},
        {"type": "apply_patch_call", "id": "apc", "call_id": "call-synthetic", "status": "completed",
         "operation": {"type": "update_file", "path": "a.py", "diff": "@@"}},
        {"role": "assistant", "content": "interleaved"},
        {"type": "apply_patch_call_output", "id": "apco", "call_id": "call-synthetic", "status": "completed", "output": "done"},
        {"role": "user", "content": [
            {"type": "input_text", "text": "read this image"},
            {"type": "input_image", "image_url": "data:image/png;base64,c3ludGhldGlj", "detail": "low"},
        ]},
    ]
    async with provider_factory.provider_runtime():
        await one_shot.one_shot_completion(
            history, model="gpt-4o", provider="default", temperature=0.2,
            max_tokens=256, extra_body={"reasoning_effort": "low"},
        )
    body = json.loads(requests[0].content)
    assert body["temperature"] == 0.2 and body["max_tokens"] == 256
    assert body["reasoning_effort"] == "low"
    assert body["messages"][1]["tool_calls"][0]["id"] == "call-synthetic"
    assert body["messages"][2]["role"] == "tool"
    assert body["messages"][-1]["content"][1]["image_url"]["detail"] == "low"


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [None, False, True])
async def test_native_claude_wire_returns_final_response_and_preserves_input(runtime, monkeypatch, stream):
    import litellm
    import siada.entrypoint

    requests, _ = runtime
    responses = []
    monkeypatch.setattr(siada.entrypoint, "_configure_litellm", lambda: None)
    monkeypatch.setattr(litellm, "drop_params", True)
    monkeypatch.setattr(litellm, "num_retries", 0)
    for name in ("callbacks", "success_callback", "failure_callback", "input_callback",
                 "_async_success_callback", "_async_failure_callback"):
        monkeypatch.setattr(litellm, name, [])

    async def send(client, request, **kwargs):
        assert request.url.host == "aux.test" and request.url.path == "/v1/messages"
        requests.append(request)
        body = json.loads(request.content)
        message = {
            "id": "msg-synthetic", "type": "message", "role": "assistant", "model": body["model"],
            "content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 3, "output_tokens": 1},
        }
        if body.get("stream"):
            events = [
                {"type": "message_start", "message": {**message, "content": [], "stop_reason": None,
                                                     "usage": {"input_tokens": 3, "output_tokens": 0}}},
                {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "ok"}},
                {"type": "content_block_stop", "index": 0},
                {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                 "usage": {"output_tokens": 1}},
                {"type": "message_stop"},
            ]
            request_stream = SyntheticSSEStream(events)
            request.extensions["synthetic_stream"] = request_stream
            response = httpx.Response(200, headers={"content-type": "text/event-stream"},
                                      stream=request_stream, request=request)
            responses.append(response)
            return response
        return httpx.Response(200, json=message, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    history = [
        {"type": "reasoning", "id": "reasoning-synthetic", "summary": []},
        {"role": "user", "content": "synthetic prompt"},
    ]
    original = deepcopy(history)
    async with provider_factory.provider_runtime():
        response = await one_shot.one_shot_completion(
            history, model="claude-sonnet-4.6", provider="default",
            base_url="https://aux.test", api_key="synthetic-key", max_tokens=64,
            extra_args={"num_retries": 0},
            **({"stream": stream} if stream is not None else {}),
        )
        assert one_shot.extract_response_text(response) == "ok"
    assert len(requests) == 1 and history == original
    body = json.loads(requests[0].content)
    assert body.get("stream", False) is (stream is not False)
    assert body["model"] == "claude-sonnet-4.6" and body["max_tokens"] == 64
    assert not body.get("tools")
    assert body["messages"][0]["content"][0]["text"] == "synthetic prompt"
    # The pinned vendor iterator does not expose its raw HTTP response to the
    # SDK's closer. The test owns these synthetic responses and releases them.
    for response in responses:
        await response.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", ["chat", "responses"])
async def test_shutdown_closes_independent_clients_even_after_close_failure(monkeypatch, protocol):
    clients = []

    def make_client(**kwargs):
        client = MagicMock()
        client.close = AsyncMock(side_effect=OSError("synthetic close failure") if not clients else None)
        clients.append(client)
        return client

    monkeypatch.setenv("BASE_URL", "https://main.test/v1")
    monkeypatch.setenv("API_KEY", "synthetic-main-key")
    if protocol == "chat":
        monkeypatch.setattr(chat_completions, "AsyncOpenAI", make_client)
        factory = chat_completions.DefaultChatClientFactory()
        lookup = factory.get_client
    else:
        monkeypatch.setattr(responses_transport, "AsyncOpenAI", make_client)
        factory = responses_transport.DefaultResponsesTransport()
        lookup = factory._get_client
    lookup()
    with default_credentials_scope(base_url="https://aux.test/v1", api_key="synthetic-aux-key"):
        lookup()
        assert lookup() is clients[1]
    with pytest.raises(OSError, match="synthetic close failure"):
        await factory.aclose()
    assert len(clients) == 2
    for client in clients:
        client.close.assert_awaited_once()
    await factory.aclose()