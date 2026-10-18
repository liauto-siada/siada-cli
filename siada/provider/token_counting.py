"""Immutable request-counting information, independent of model lifetimes."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Literal

from agents.models.openai_responses import OpenAIResponsesModel

from siada.provider.reasoning_replay import should_replay_reasoning_content
from siada.provider.responses import ResponsesModel, is_responses_only_model
from siada.services.input_processor import PROCESSING_FUNCTIONS, process_input


@dataclass(frozen=True)
class TokenCountingInfo:
    """Describe counting semantics without retaining models or credentials."""

    model_name: str | None
    protocol: Literal["chat", "responses"] = "chat"
    input_projection: Literal["standard", "siada_responses"] = "standard"
    unavailable_reason: str | None = None


def with_input_processor(info: TokenCountingInfo, processor: Any) -> TokenCountingInfo:
    """Opaque processors remain compatible only with full, uncalibrated recounts."""
    if processor is not None and not (processor is process_input and not PROCESSING_FUNCTIONS):
        return replace(info, unavailable_reason="opaque_processor")
    return info


def token_counting_info_from_model(model: Any) -> TokenCountingInfo:
    """Snapshot the actual model's counting domain; never retain the instance."""
    processors = []
    while getattr(model, "wrapped_model", None) is not None:
        processors.append(getattr(model, "input_processor", None))
        model = model.wrapped_model
    model_name = model if isinstance(model, str) else getattr(model, "model", None)
    native = (
        is_responses_only_model(model_name) if isinstance(model, str)
        else isinstance(model, OpenAIResponsesModel) or getattr(model, "supports_native_responses_items", False)
    )
    local_responses = isinstance(model, ResponsesModel) or isinstance(model, str) and native
    replay = getattr(model, "should_replay_reasoning_content", should_replay_reasoning_content)
    info = TokenCountingInfo(
        model_name=model_name,
        protocol="responses" if native else "chat",
        input_projection="siada_responses" if local_responses else "standard",
        unavailable_reason="unknown_replay_policy" if not native and replay is not should_replay_reasoning_content else None,
    )
    for processor in processors:
        info = with_input_processor(info, processor)
    return info


def provider_token_counting_info(provider: Any, model_name: str | None) -> TokenCountingInfo:
    """Require a pure route description instead of speculative get_model calls."""
    describe = getattr(provider, "get_token_counting_info", None)
    if not callable(describe):
        raise ValueError(
            "Effective context requires a named model provider to implement "
            "get_token_counting_info(); alternatively, pass an explicit Model object."
        )
    info = describe(model_name)
    if not isinstance(info, TokenCountingInfo):
        raise ValueError("get_token_counting_info() must return TokenCountingInfo")
    return info
