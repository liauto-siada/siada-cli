from __future__ import annotations

import base64
import copy
import json
from unittest.mock import AsyncMock, Mock

import pytest
from agents import Agent, ModelSettings, RunConfig, Runner, ToolOutputImage, ToolOutputText
from agents.decorators import function_tool
from agents.exceptions import UserError

from siada.provider.gemini import GeminiModel
from siada.services.file_session import FileSession
from siada.services.model_wrapper import ModelWrapper

from test_gemini_model import native_response, request_args, sse
from test_gemini_replay_boundary import native_provider


IMAGE_BYTES = b"\xff\xd8\xff\x00\xfb\xffsynthetic-jpeg\xff\xd9"
IMAGE_BASE64 = base64.b64encode(IMAGE_BYTES).decode()
IMAGE_URL = f"data:image/jpeg;base64,{IMAGE_BASE64}"
PNG_BASE64 = base64.b64encode(b"\x89PNG\r\n\x1a\nsynthetic-png").decode()
PNG_URL = f"data:image/png;base64,{PNG_BASE64}"


def tool_history(output):
    return [
        {"role": "user", "content": "view the image"},
        {
            "type": "function_call", "call_id": "synthetic-call", "name": "edit_file",
            "arguments": '{"command":"view","path":"image.jpg"}',
        },
        {"type": "function_call_output", "call_id": "synthetic-call", "output": output},
    ]


def inline_image(encoded=IMAGE_BASE64, mime_type="image/jpeg"):
    return {"inline_data": {"mime_type": mime_type, "data": base64.urlsafe_b64encode(base64.b64decode(encoded)).decode()}}


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(("output", "text", "images"), [
    ("unchanged\ntext", "unchanged\ntext", []),
    ([], "", []),
    ([{"type": "input_text", "text": "first\n"}, {"type": "input_text", "text": "second"}], "first\nsecond", []),
    ([{"type": "input_image", "image_url": IMAGE_URL, "detail": "auto"}], "", [inline_image()]),
    ([
        {"type": "input_text", "text": "first image\n"},
        {"type": "input_image", "image_url": IMAGE_URL},
        {"type": "input_text", "text": "second image"},
        {"type": "input_image", "image_url": PNG_URL},
    ], "first image\nsecond image", [inline_image(), inline_image(PNG_BASE64, "image/png")]),
    ([{"type": "image_url", "image_url": {"url": IMAGE_URL, "detail": "high"}}], "", [inline_image()]),
])
async def test_tool_results_use_native_function_response_parts(endpoint, native_provider, stream, output, text, images):
    final = native_response([{"text": "done"}])
    endpoint.responses = [(200, sse(final) if stream else final)]
    history = tool_history(output)
    original = copy.deepcopy(history)
    _provider_name, provider = native_provider
    model = provider.get_model("gemini-4-synthetic")
    if stream:
        events = [event async for event in model.stream_response(**request_args(history))]
        assert events[-1].response.output[0].content[0].text == "done"
    else:
        assert (await model.get_response(**request_args(history))).output[0].content[0].text == "done"
    response = {"name": "edit_file", "response": {"output": text}}
    if images:
        response["parts"] = images
    assert endpoint.requests[0][1]["contents"] == [
        {"role": "user", "parts": [{"text": "view the image"}]},
        {"role": "model", "parts": [{
            "functionCall": {"name": "edit_file", "args": {"command": "view", "path": "image.jpg"}},
            "thoughtSignature": "skip_thought_signature_validator",
        }]},
        {"role": "user", "parts": [{"functionResponse": response}]},
    ]
    assert history == original
    assert len(endpoint.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("output", [
    [{"type": "input_image", "image_url": "data:image/jpeg;base64,invalid-sensitive-image!"}],
    [{"type": "input_image", "image_url": "data:image/jpeg;base64"}],
    [{"type": "input_image", "image_url": "data:image/jpeg,not-base64"}],
    [{"type": "input_image", "image_url": "data:image/jpeg;base64,"}],
    [{"type": "input_image", "image_url": f"data:application/pdf;base64,{IMAGE_BASE64}"}],
    [{"type": "input_image", "image_url": f"data:;base64,{IMAGE_BASE64}"}],
    [{"type": "input_image", "file_id": "file-sensitive-handle"}],
    [{"type": "input_image", "image_url": "https://images.test/sensitive-image.jpg"}],
    [{"type": "input_file", "file_id": "file-sensitive-handle"}],
    {"type": "input_image", "image_url": IMAGE_URL},
    ["invalid-sensitive-content"],
    None,
])
async def test_invalid_tool_media_fails_safely_before_request(endpoint, client, stream, output):
    history = tool_history(output)
    original = copy.deepcopy(history)
    model = GeminiModel("gemini-4-synthetic", client=client)
    with pytest.raises(UserError) as caught:
        if stream:
            async for event in model.stream_response(**request_args(history)):
                pass
        else:
            await model.get_response(**request_args(history))
    assert "sensitive" not in str(caught.value)
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None
    assert endpoint.requests == []
    assert history == original


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_signed_parallel_image_results_survive_history_reload(endpoint, client, tmp_path, stream):
    signed = [
        {"functionCall": {"id": "native-image", "name": "edit_file", "args": {}}, "thoughtSignature": "c3ludGhldGlj"},
        {"functionCall": {"id": "native-text", "name": "lookup", "args": {}}},
    ]
    endpoint.responses = [
        (200, native_response(signed)),
        (200, sse(native_response([{"text": "done"}])) if stream else native_response([{"text": "done"}])),
    ]
    model = GeminiModel("gemini-4-synthetic", client=client)
    calls = (await model.get_response(**request_args())).to_input_items()
    history = [*calls,
        {"type": "function_call_output", "call_id": calls[1]["call_id"], "output": "text result"},
        {"type": "function_call_output", "call_id": calls[0]["call_id"], "output": [
            {"type": "input_image", "image_url": IMAGE_URL, "detail": "auto"},
        ]},
    ]
    session = FileSession("synthetic-image-history", sessions_dir=tmp_path)
    await session.add_items(history)
    restored = await FileSession("synthetic-image-history", sessions_dir=tmp_path).get_items()
    original = copy.deepcopy(restored)
    fresh = GeminiModel("gemini-4-synthetic", client=client)
    if stream:
        events = [event async for event in fresh.stream_response(**request_args(restored))]
        assert events[-1].type == "response.completed"
    else:
        await fresh.get_response(**request_args(restored))
    assert endpoint.requests[1][1]["contents"] == [
        {"role": "model", "parts": signed},
        {"role": "user", "parts": [
            {"functionResponse": {"id": "native-image", "name": "edit_file", "response": {"output": ""}, "parts": [inline_image()]}},
            {"functionResponse": {"id": "native-text", "name": "lookup", "response": {"output": "text result"}}},
        ]},
    ]
    assert restored == original
    assert "provider_data" not in json.dumps(endpoint.requests[1][1])
    assert len(endpoint.requests) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("image_only", [False, True])
async def test_runner_passes_tool_output_images_and_replays_them(endpoint, client, tmp_path, stream, image_only):
    @function_tool
    def edit_file(command: str, path: str) -> list[ToolOutputText | ToolOutputImage]:
        assert command == "view"
        assert path == "image.jpg"
        image = ToolOutputImage(image_url=IMAGE_URL, detail="auto")
        return [image] if image_only else [ToolOutputText(text="image evidence"), image]

    signed = [{
        "functionCall": {"name": "edit_file", "args": {"command": "view", "path": "image.jpg"}},
        "thoughtSignature": "c3ludGhldGlj",
    }]
    responses = [native_response(signed), native_response([{"text": "done"}])]
    endpoint.responses = [(200, sse(response) if stream else response) for response in responses]
    session = FileSession("synthetic-image-runner", sessions_dir=tmp_path)
    agent = Agent(name="synthetic", model=ModelWrapper(GeminiModel("gemini-4-synthetic", client=client)), tools=[edit_file])
    config = RunConfig(tracing_disabled=True)
    if stream:
        result = Runner.run_streamed(agent, "view the image", session=session, run_config=config)
        async for event in result.stream_events():
            pass
    else:
        result = await Runner.run(agent, "view the image", session=session, run_config=config)
    assert result.final_output == "done"
    body = endpoint.requests[1][1]
    assert body["contents"][1] == {"role": "model", "parts": signed}
    assert body["contents"][2] == {"role": "user", "parts": [{"functionResponse": {
        "name": "edit_file", "response": {"output": "" if image_only else "image evidence"}, "parts": [inline_image()],
    }}]}
    restored = await FileSession("synthetic-image-runner", sessions_dir=tmp_path).get_items()
    output = next(item["output"] for item in restored if item.get("type") == "function_call_output")
    assert output[-1] == {"type": "input_image", "image_url": IMAGE_URL, "detail": "auto"}
    endpoint.responses = [(200, native_response([{"text": "next"}]))]
    await GeminiModel("gemini-4-synthetic", client=client).get_response(**request_args([
        *restored, {"role": "user", "content": "describe the image again"},
    ]))
    assert endpoint.requests[2][1]["contents"][:3] == body["contents"]
    assert len(endpoint.requests) == 3
