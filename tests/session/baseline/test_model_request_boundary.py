"""Offline provider-boundary coverage for admission and stream ownership."""

import copy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from siada.services.model_wrapper import ModelProviderWrapper, ModelWrapper
from siada.services.input_processor import process_input


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


@pytest.mark.parametrize("processor", [None, process_input])
@pytest.mark.parametrize("admission", [False, True])
def test_model_resolution_callback_precedes_all_wrapper_paths(baseline, processor, admission):
    model = CapturingModel(native=True)
    resolved = []

    async def admit(items):
        assert resolved == [model]

    provider = ModelProviderWrapper(
        SimpleNamespace(get_model=lambda name: model), input_processor=processor,
        before_request=admit if admission else None, on_model_resolved=resolved.append,
    )
    result = provider.get_model("synthetic-alias")
    assert resolved == [model]
    assert model.requests == []
    if processor is None and not admission:
        assert result is model
    else:
        assert isinstance(result, ModelWrapper)
        assert result.wrapped_model is model
        assert result.input_processor is processor
        assert result.supports_native_responses_items


def test_model_resolution_failure_does_not_return_untracked_model(baseline):
    model = CapturingModel()

    def fail(model):
        raise RuntimeError("synthetic resolution failure")

    provider = ModelProviderWrapper(SimpleNamespace(get_model=lambda name: model), on_model_resolved=fail)
    with pytest.raises(RuntimeError, match="resolution failure"):
        provider.get_model("synthetic-alias")
    assert model.requests == []


def test_provider_resolution_always_delegates_without_caching(baseline):
    models = [CapturingModel() for _ in range(4)]
    base = SimpleNamespace(get_model=Mock(side_effect=models))
    observed = []
    provider = ModelProviderWrapper(base, on_model_resolved=observed.append)
    first = provider.get_model("synthetic-alias")
    second = provider.get_model("synthetic-alias")
    third = provider.get_model("another-alias")
    assert first is not second
    assert observed == [first, second, third]
    assert base.get_model.call_count == 3
    next_run = ModelProviderWrapper(base)
    assert next_run.get_model("synthetic-alias") is not first


def test_failed_resolution_callback_does_not_retain_model(baseline):
    models = [CapturingModel(), CapturingModel(), CapturingModel()]
    base = SimpleNamespace(get_model=Mock(side_effect=models))
    callback = Mock(side_effect=[RuntimeError("synthetic callback failure"), None, None])
    provider = ModelProviderWrapper(base, on_model_resolved=callback)
    with pytest.raises(RuntimeError, match="callback failure"):
        provider.get_model("synthetic-alias")
    assert provider.get_model("synthetic-alias") is models[1]
    assert provider.get_model("synthetic-alias") is models[2]
    assert base.get_model.call_count == 3
    assert [call.args[0] for call in callback.call_args_list] == models


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_verification_failure_precedes_admission_processing_and_transport(baseline, stream):
    model = CapturingModel()
    admission = Mock()
    processor = Mock()
    error = ValueError("synthetic counting mismatch")
    verify = Mock(side_effect=error)
    wrapper = ModelWrapper(model, processor, before_request=admission, verify_model=verify)
    with pytest.raises(ValueError) as caught:
        if stream:
            async for _ in wrapper.stream_response(**request_args([])):
                pass
        else:
            await wrapper.get_response(**request_args([]))
    assert caught.value is error
    verify.assert_called_once_with(model)
    admission.assert_not_called()
    processor.assert_not_called()
    assert model.requests == []