"""Offline provider-boundary coverage for admission and stream ownership."""

import copy
from types import SimpleNamespace

import pytest

from siada.services.model_wrapper import ModelProviderWrapper, ModelWrapper


def request_args(items):
    return dict(
        system_instructions=None, input=items, model_settings=None, tools=[],
        output_schema=None, handoffs=[], tracing=None, previous_response_id=None,
        conversation_id=None, prompt=None,
    )


class CapturingModel:
    """Record calls without contacting a provider or creating SDK responses."""

    def __init__(self, *, native=False):
        self.supports_native_responses_items = native
        self.requests = []
        self.closed = False

    async def get_response(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs["input"]))
        return "synthetic response"

    async def stream_response(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs["input"]))
        try:
            yield SimpleNamespace(type="response.output_text.delta", delta="first")
            yield SimpleNamespace(type="response.output_text.delta", delta="second")
            yield SimpleNamespace(type="response.completed")
        finally:
            self.closed = True


def native_patch_items():
    return [
        {"type": "apply_patch_call", "id": "patch-1", "call_id": "call-1",
         "status": "completed", "operation": {"type": "update_file", "path": "a.py", "diff": "@@"}},
        {"type": "apply_patch_call_output", "id": "output-1", "call_id": "call-1",
         "status": "completed", "output": "saved"},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("native", [False, True])
async def test_admission_sees_native_items_before_provider_normalization(baseline, stream, native):
    model = CapturingModel(native=native)
    admitted = []

    async def admit(items):
        assert model.requests == []
        admitted.append(copy.deepcopy(items))

    inner = ModelWrapper(model)
    provider = ModelProviderWrapper(SimpleNamespace(get_model=lambda name: inner), before_request=admit)
    wrapper = provider.get_model("synthetic-model")
    assert wrapper.supports_native_responses_items is native
    items = native_patch_items()
    if stream:
        iterator = wrapper.stream_response(**request_args(items))
        assert admitted == []
        events = [event async for event in iterator]
        assert [event.delta for event in events[:-1]] == ["first", "second"]
        assert events[-1].type == "response.completed"
        assert model.closed
    else:
        assert await wrapper.get_response(**request_args(items)) == "synthetic response"
    assert admitted == [items]
    assert items == native_patch_items()
    assert [item["type"] for item in model.requests[0]] == (
        ["apply_patch_call", "apply_patch_call_output"] if native
        else ["function_call", "function_call_output"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_admission_failure_never_calls_processor_or_provider(baseline, stream):
    model = CapturingModel()
    processed = []

    async def fail(items):
        raise OSError("synthetic admission failure")

    wrapper = ModelWrapper(model, input_processor=lambda items: processed.append(items), before_request=fail)
    with pytest.raises(OSError, match="admission failure"):
        if stream:
            async for _ in wrapper.stream_response(**request_args([])):
                pass
        else:
            await wrapper.get_response(**request_args([]))
    assert model.requests == [] and processed == []


@pytest.mark.asyncio
async def test_early_close_closes_the_owned_provider_iterator(baseline):
    model = CapturingModel()

    async def admit(items):
        pass

    stream = ModelWrapper(model, before_request=admit).stream_response(**request_args([]))
    assert (await anext(stream)).delta == "first"
    assert not model.closed
    await stream.aclose()
    assert model.closed


@pytest.mark.asyncio
async def test_close_before_iteration_does_not_admit_or_open_provider_stream(baseline):
    model = CapturingModel()
    admitted = []

    async def admit(items):
        admitted.append(items)

    stream = ModelWrapper(model, before_request=admit).stream_response(**request_args([]))
    await stream.aclose()
    assert admitted == [] and model.requests == []