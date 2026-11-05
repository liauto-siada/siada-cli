from __future__ import annotations

import asyncio
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from agents import Agent, ModelSettings, RunConfig, Runner
from agents.decorators import function_tool
from agents.exceptions import ModelBehaviorError, UserError
from agents.models.interface import ModelTracing
from google import genai
from google.genai import types

from siada.provider.gemini import GeminiModel
from siada.provider.gemini.replay import decode_replay
from siada.provider.gemini.stream_handler import GeminiResponseAssembly
from siada.provider.gemini.transport import GeminiRequestError
from siada.provider.retry import MissingFinalResponseError
from siada.services.file_session import FileSession
from siada.services.model_wrapper import ModelWrapper


def native_response(parts, *, finish="STOP", usage=True):
    response = {"candidates": [{"content": {"role": "model", "parts": parts}}]}
    if finish:
        response["candidates"][0]["finishReason"] = finish
    if usage:
        response["usageMetadata"] = {"promptTokenCount": 11, "candidatesTokenCount": 3, "thoughtsTokenCount": 2, "totalTokenCount": 16}
    return response


@pytest.fixture
def endpoint():
    state = SimpleNamespace(requests=[], responses=[])

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state.requests.append((self.path, body, dict(self.headers)))
            status, response = state.responses.pop(0)
            payload = response if isinstance(response, bytes) else json.dumps(response).encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/event-stream" if isinstance(response, bytes) else "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.url = f"http://127.0.0.1:{server.server_port}"
    yield state
    server.shutdown()
    server.server_close()
    thread.join()


@pytest_asyncio.fixture
async def client(endpoint):
    client = genai.Client(vertexai=False, api_key="synthetic-api-key", http_options=types.HttpOptions(
        base_url=endpoint.url, retry_options=types.HttpRetryOptions(attempts=1),
        httpx_async_client=httpx.AsyncClient(trust_env=False),
    ))
    yield client
    await client.aio.aclose()
    client.close()


def request_args(input="hello", *, settings=None):
    return dict(system_instructions=None, input=input, model_settings=settings or ModelSettings(), tools=[],
                output_schema=None, handoffs=[], tracing=ModelTracing.DISABLED,
                previous_response_id=None, conversation_id=None, prompt=None)


def sse(*responses):
    return b"".join(b"data: " + json.dumps(response).encode() + b"\n\n" for response in responses)


def test_response_assembly_detaches_parts_and_keeps_empty_content_positions():
    origin = {"provider": "google", "model": "gemini-3.5-flash", "backend": "gemini_api"}
    assembly = GeminiResponseAssembly(origin)
    assembly.add(types.GenerateContentResponse.model_validate(native_response([], finish=None)))
    response = types.GenerateContentResponse.model_validate(native_response([
        {"text": "answer", "thoughtSignature": "c2ln"},
    ]))
    assembly.add(response)
    response.candidates[0].content.parts[0].thought_signature = b"changed"
    items = assembly.finalize()
    assert items[0].content[0].text == "answer"
    assert decode_replay(items[0])["parts"] == [{
        "content_index": 1, "part_index": 0,
        "part": {"text": "answer", "thought_signature": "c2ln"},
    }]


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_cached_usage_is_preserved_in_normalized_and_raw_responses(endpoint, client, stream):
    final_response = native_response([{"text": "answer", "thoughtSignature": "c2ln"}])
    final_response["usageMetadata"]["cachedContentTokenCount"] = 9
    if stream:
        earlier_response = native_response([{"text": "first"}], finish=None)
        earlier_response["usageMetadata"]["cachedContentTokenCount"] = 4
        endpoint.responses = [(200, sse(earlier_response, final_response))]
    else:
        endpoint.responses = [(200, final_response)]
    model = ModelWrapper(GeminiModel("gemini-3.5-flash", client=client))
    arguments = request_args(settings=ModelSettings(preserve_raw_usage=True))
    if stream:
        events = [event async for event in model.stream_response(**arguments)]
        assert events[-1].type == "response.completed"
        response = events[-1].response
    else:
        response = await model.get_response(**arguments)
    assert response.usage.input_tokens == 2
    assert response.usage.input_tokens_details.cached_tokens == 9
    assert response.usage.output_tokens == 5
    assert response.usage.output_tokens_details.reasoning_tokens == 2
    assert response.usage.total_tokens == 16
    assert response.raw_usage["prompt_token_count"] == 11
    assert response.raw_usage["cached_content_token_count"] == 9


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_native_parallel_calls_reject_duplicate_call_ids(endpoint, client, stream):
    endpoint.responses = [(200, native_response([
        {"functionCall": {"name": "lookup", "args": {"value": 1}}, "thoughtSignature": "Zmlyc3Q="},
        {"functionCall": {"name": "lookup", "args": {"value": 2}}},
    ]))]
    model = GeminiModel("gemini-3.5-flash", client=client)
    items = (await model.get_response(**request_args())).to_input_items()
    items[1]["call_id"] = items[0]["call_id"]
    with pytest.raises(UserError, match="unique nonempty call IDs"):
        if stream:
            async for _event in model.stream_response(**request_args(items)):
                pass
        else:
            await model.get_response(**request_args(items))
    assert len(endpoint.requests) == 1


@pytest.mark.asyncio
async def test_text_parts_signatures_survive_storage_and_new_model(endpoint, client, tmp_path):
    parts = [{"text": "first", "thoughtSignature": "Zmlyc3Q="}, {"text": "second", "thoughtSignature": "c2Vjb25k"}, {"text": "", "thoughtSignature": "dGFpbA=="}]
    endpoint.responses = [(200, native_response(parts)), (200, native_response([{"text": "done"}]))]
    model = ModelWrapper(GeminiModel("gemini-3.5-flash", client=client))
    response = await model.get_response(**request_args())
    assert response.usage.input_tokens == 11
    assert response.usage.output_tokens == 5
    assert response.output[0].content[0].text == "firstsecond"
    session = FileSession("synthetic-session", sessions_dir=tmp_path)
    await session.add_items(response.to_input_items())
    restored = await FileSession("synthetic-session", sessions_dir=tmp_path).get_items()
    await ModelWrapper(GeminiModel("gemini-3.5-flash", client=client)).get_response(**request_args([*restored, {"role": "user", "content": "next"}]))
    body = endpoint.requests[1][1]
    assert body["contents"][0] == {"role": "model", "parts": parts}
    assert body["contents"][1]["parts"] == [{"text": "next"}]
    assert "provider_data" not in json.dumps(body)


@pytest.mark.asyncio
async def test_stream_preserves_raw_fragments_and_waits_for_tail_signature(endpoint, client):
    chunks = [native_response([{"text": "first"}], finish=None),
              native_response([{"text": "second"}], finish=None),
              native_response([{"text": "", "thoughtSignature": "dGFpbA=="}])]
    endpoint.responses = [(200, sse(*chunks)), (200, native_response([{"text": "done"}]))]
    model = GeminiModel("gemini-3.5-flash", client=client)
    events = [event async for event in model.stream_response(**request_args())]
    assert [event.delta for event in events if event.type == "response.output_text.delta"] == ["first", "second"]
    final = events[-1].response
    assert events[-1].type == "response.completed"
    assert events[0].response.status == "in_progress"
    assert events[0].response.id == final.id
    done = [event.item for event in events if event.type == "response.output_item.done"]
    assert done == final.output
    assert decode_replay(final.output[0])["parts"][-1]["part"]["thought_signature"] == "dGFpbA=="
    replay = [item.model_dump(mode="json", exclude_unset=True) for item in final.output]
    await model.get_response(**request_args([*replay, {"role": "user", "content": "next"}]))
    assert endpoint.requests[1][1]["contents"] == [
        {"role": "model", "parts": [part for chunk in chunks for part in chunk["candidates"][0]["content"]["parts"]]},
        {"role": "user", "parts": [{"text": "next"}]},
    ]


@pytest.mark.asyncio
async def test_stop_chunk_does_not_discard_later_signature(endpoint, client):
    chunks = [native_response([{"text": "done"}]), native_response([{"text": "", "thoughtSignature": "dGFpbA=="}], finish=None)]
    endpoint.responses = [(200, sse(*chunks))]
    events = [event async for event in GeminiModel("gemini-3.5-flash", client=client).stream_response(**request_args())]
    assert decode_replay(events[-1].response.output[0])["parts"][-1]["part"]["thought_signature"] == "dGFpbA=="


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("mime_type", ["image/png", "audio/wav"])
async def test_signed_unsupported_media_does_not_publish_completed_output(endpoint, client, stream, mime_type):
    response = native_response([
        {"inlineData": {"mimeType": mime_type, "data": "c3ludGhldGlj"}, "thoughtSignature": "c2ln"},
    ])
    endpoint.responses = [(200, sse(response) if stream else response)]
    model = GeminiModel("gemini-3.5-flash", client=client)
    events = []
    with pytest.raises(ModelBehaviorError, match="unsupported output Part"):
        if stream:
            async for event in model.stream_response(**request_args()):
                events.append(event)
        else:
            await model.get_response(**request_args())
    assert len(endpoint.requests) == 1
    assert not any(event.type in {"response.completed", "response.output_item.done"} for event in events)


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_signature_only_part_remains_replayable(endpoint, client, stream):
    parts = [{"thoughtSignature": "dGFpbA=="}]
    response = native_response(parts)
    endpoint.responses = [
        (200, sse(response) if stream else response),
        (200, native_response([{"text": "next"}])),
    ]
    model = GeminiModel("gemini-3.5-flash", client=client)
    if stream:
        events = [event async for event in model.stream_response(**request_args())]
        items = [item.model_dump(mode="json", exclude_unset=True) for item in events[-1].response.output]
    else:
        items = (await model.get_response(**request_args())).to_input_items()
    await model.get_response(**request_args([*items, {"role": "user", "content": "next user"}]))
    assert endpoint.requests[-1][1]["contents"][0] == {"role": "model", "parts": parts}


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_runner_parallel_tools_replay_as_a_group_without_dummy(endpoint, client, tmp_path, stream):
    executed = []

    @function_tool
    async def lookup(value: int) -> str:
        executed.append(value)
        await asyncio.sleep(0)
        return str(value)

    parts = [{"functionCall": {"name": "lookup", "args": {"value": 1}}, "thoughtSignature": "dG9vbA=="},
             {"functionCall": {"name": "lookup", "args": {"value": 2}}}]
    responses = [native_response(parts), native_response([{"text": "done", "thoughtSignature": "ZmluYWw="}])]
    endpoint.responses = [(200, sse(response) if stream else response) for response in responses]
    agent = Agent(name="synthetic", model=ModelWrapper(GeminiModel("gemini-3.5-flash", client=client)), tools=[lookup])
    session = FileSession("runner-session", sessions_dir=tmp_path)
    config = RunConfig(tracing_disabled=True)
    if stream:
        result = Runner.run_streamed(agent, "hello", session=session, run_config=config)
        async for event in result.stream_events():
            pass
    else:
        result = await Runner.run(agent, "hello", session=session, run_config=config)
    assert result.final_output == "done"
    assert sorted(executed) == [1, 2]
    body = endpoint.requests[1][1]
    assert body["contents"][1] == {"role": "model", "parts": parts}
    assert [part["functionResponse"]["name"] for part in body["contents"][2]["parts"]] == ["lookup", "lookup"]
    assert [part["functionResponse"]["response"] for part in body["contents"][2]["parts"]] == [{"output": "1"}, {"output": "2"}]
    assert "id" not in body["contents"][1]["parts"][0]["functionCall"]
    assert "thoughtSignature" not in body["contents"][1]["parts"][1]
    assert len({item["call_id"] for item in await session.get_items() if item.get("type") == "function_call"}) == 2


@pytest.mark.asyncio
async def test_retained_text_is_independent_of_reasoning_owner_and_origin_is_checked(endpoint, client):
    parts = [{"text": "thinking", "thought": True, "thoughtSignature": "cmVhc29u"}, {"text": "answer", "thoughtSignature": "dGV4dA=="}]
    endpoint.responses = [(200, native_response(parts)), (200, native_response([{"text": "next"}]))]
    model = GeminiModel("gemini-3.5-flash", client=client)
    response = await model.get_response(**request_args())
    items = response.to_input_items()
    await model.get_response(**request_args(items[1:]))
    assert endpoint.requests[-1][1]["contents"] == [{"role": "model", "parts": parts[1:]}]
    with pytest.raises(UserError, match="origin"):
        await GeminiModel("gemini-3.1-pro", client=client).get_response(**request_args(items))
    assert len(endpoint.requests) == 2


@pytest.mark.asyncio
async def test_incomplete_stream_does_not_publish_tool_calls(endpoint, client, monkeypatch):
    from siada.provider import retry
    monkeypatch.setattr(retry, "_backoff", AsyncMock())
    incomplete = native_response([{"text": "partial"}, {"functionCall": {"name": "lookup", "args": {}}}], finish=None)
    endpoint.responses = [(200, sse(incomplete))]
    events = []
    with pytest.raises(MissingFinalResponseError):
        async for event in ModelWrapper(GeminiModel("gemini-3.5-flash", client=client)).stream_response(**request_args()):
            events.append(event)
    assert any(event.type == "response.output_text.delta" for event in events)
    assert not any(event.type in {"response.completed", "response.output_item.done"} for event in events)
    assert len(endpoint.requests) == 1


@pytest.mark.asyncio
async def test_sdk_error_does_not_expose_response_payload_or_exception_chain(endpoint, client):
    secret = "synthetic-sensitive-signature"
    endpoint.responses = [(400, {"error": {"code": 400, "message": secret, "status": "INVALID_ARGUMENT"}})]
    with pytest.raises(GeminiRequestError) as caught:
        await GeminiModel("gemini-3.5-flash", client=client).get_response(**request_args())
    assert secret not in str(caught.value)
    assert secret not in repr(vars(caught.value))
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None
    assert caught.value.status_code == 400


@pytest.mark.asyncio
async def test_shared_model_keeps_concurrent_assemblies_local():
    first_started = asyncio.Event()
    release_first = asyncio.Event()

    class Transport:
        def origin(self, model):
            return {"provider": "synthetic", "model": model, "backend": "gemini_api"}

        async def stream(self, model, contents, config):
            text = contents[0].parts[0].text
            if text == "first":
                first_started.set()
                await release_first.wait()
            yield types.GenerateContentResponse.model_validate(native_response([{"text": text, "thoughtSignature": base64.b64encode(text.encode()).decode()}]))

    model = GeminiModel("gemini-3.5-flash", transport=Transport())

    async def collect(text):
        return [event async for event in model.stream_response(**request_args(text))][-1].response

    first = asyncio.create_task(collect("first"))
    await first_started.wait()
    second = await collect("second")
    release_first.set()
    first_result = await first
    assert first_result.output[0].content[0].text == "first"
    assert second.output[0].content[0].text == "second"
    assert first_result.output[0].provider_data != second.output[0].provider_data
