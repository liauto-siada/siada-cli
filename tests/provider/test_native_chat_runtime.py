"""Exercise native SDK concurrency and loop isolation against localhost only."""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from agents import ModelSettings
from agents.models.interface import ModelTracing
from openai import AsyncOpenAI

from siada.provider import provider_factory
from siada.provider.default import chat_completions as default_chat


@pytest.fixture
def completion_server():
    received = []
    blocked = threading.Event()
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def handle(self):
            try:
                super().handle()
            except ConnectionResetError:
                # Cancellation intentionally aborts a keepalive socket.
                pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            label = request["messages"][-1]["content"]
            received.append((label, self.headers.get("X-Synthetic-Caller")))
            if label == "cancel":
                blocked.set()
                release.wait(timeout=5)
            if request.get("stream"):
                choices = [
                    {"index": 0, "delta": {"role": "assistant", "content": label}, "finish_reason": None},
                    {"index": 0, "delta": {}, "finish_reason": "stop"},
                ]
                body = b"".join(
                    ("data: " + json.dumps({
                        "id": "chatcmpl-synthetic", "object": "chat.completion.chunk",
                        "created": 1, "model": "gpt-4o", "choices": [choice],
                    }) + "\n\n").encode()
                    for choice in choices
                ) + b"data: [DONE]\n\n"
                content_type = "text/event-stream"
            else:
                body = json.dumps({
                    "id": "chatcmpl-synthetic", "object": "chat.completion",
                    "created": 1, "model": "gpt-4o",
                    "choices": [{"index": 0, "message": {
                        "role": "assistant", "content": label,
                    }, "finish_reason": "stop"}],
                }).encode()
                content_type = "application/json"
            try:
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", received, blocked, release
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.fixture
def native_runtime(completion_server, monkeypatch):
    url, received, blocked, release = completion_server
    clients = []

    def make_client(**kwargs):
        client = AsyncOpenAI(
            **kwargs,
            http_client=httpx.AsyncClient(trust_env=False, limits=httpx.Limits(keepalive_expiry=30)),
        )
        clients.append(client)
        return client

    monkeypatch.setenv("BASE_URL", url)
    monkeypatch.setenv("API_KEY", "synthetic-key")
    monkeypatch.setattr(default_chat, "AsyncOpenAI", make_client)

    class Provider:
        def __init__(self):
            self.factory = default_chat.DefaultChatClientFactory()

        def get_model(self, model):
            return default_chat.DefaultOpenAIChatCompletionsModel(model, self.factory, False)

        async def aclose(self):
            await self.factory.aclose()

    monkeypatch.setattr(provider_factory, "_discover_providers", lambda: None)
    monkeypatch.setattr(provider_factory, "provider_map", {"synthetic": Provider()})
    yield clients, received, blocked, release
    assert all(client.is_closed() for client in clients)


async def fetch(label, streamed=False):
    model = provider_factory.get_provider("synthetic").get_model("gpt-4o")
    kwargs = dict(
        system_instructions="Synthetic offline test",
        input=[{"role": "user", "content": label}],
        model_settings=ModelSettings(extra_headers={"X-Synthetic-Caller": label}),
        tools=[], output_schema=None, handoffs=[], tracing=ModelTracing.DISABLED,
    )
    if streamed:
        events = [event async for event in model.stream_response(**kwargs)]
        assert events[-1].type == "response.completed"
        return events[-1].response.output[0].content[0].text
    response = await model.get_response(**kwargs)
    return response.output[0].content[0].text


@pytest.mark.asyncio
@pytest.mark.parametrize("streamed", [False, True])
async def test_main_and_six_children_share_one_client(native_runtime, streamed):
    clients, received, _, _ = native_runtime
    labels = ["main"] + [f"child-{i}" for i in range(6)]
    async with provider_factory.provider_runtime():
        assert await asyncio.gather(*(fetch(label, streamed) for label in labels)) == labels
        assert len(clients) == 1
        assert sorted(received) == sorted((label, label) for label in labels)


@pytest.mark.asyncio
@pytest.mark.parametrize("streamed", [False, True])
async def test_cancelling_one_request_preserves_siblings(native_runtime, streamed):
    clients, _, blocked, release = native_runtime
    async with provider_factory.provider_runtime():
        task = asyncio.create_task(fetch("cancel", streamed))
        try:
            assert await asyncio.to_thread(blocked.wait, 3)
            assert await fetch("sibling", streamed) == "sibling"
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert not clients[0].is_closed()
            assert await fetch("follow-up", streamed) == "follow-up"
            assert len(clients) == 1
        finally:
            release.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("streamed", [False, True])
async def test_shutdown_drains_inflight_native_request_before_client_close(native_runtime, streamed):
    clients, _, blocked, release = native_runtime
    try:
        async with provider_factory.provider_runtime():
            task = asyncio.create_task(fetch("cancel", streamed))
            assert await asyncio.to_thread(blocked.wait, 3)
            client = clients[0]
            original_close = client.close

            async def close():
                assert task.done()
                await original_close()

            client.close = close
        assert task.cancelled()
        assert client.is_closed()
    finally:
        release.set()


@pytest.mark.parametrize("owner_closed", [False, True])
def test_factory_lookup_isolates_native_clients_across_loops(native_runtime, owner_closed):
    clients, _, _, _ = native_runtime
    first = asyncio.Runner()
    second = asyncio.Runner()
    try:
        assert first.run(fetch("first")) == "first"
        if owner_closed:
            first.run(provider_factory.shutdown_provider_runtime())
            first.close()
        assert second.run(fetch("second")) == "second"
        assert len(clients) == 2
        assert clients[0] is not clients[1]
        if not owner_closed:
            assert first.run(fetch("first-again")) == "first-again"
            assert not clients[0].is_closed()
        second.run(provider_factory.shutdown_provider_runtime())
    finally:
        if not owner_closed:
            first.run(provider_factory.shutdown_provider_runtime())
        first.close()
        second.close()
