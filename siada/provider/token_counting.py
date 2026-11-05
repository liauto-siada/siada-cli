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
    protocol: Literal["chat", "responses", "gemini"] = "chat"
    input_projection: Literal["standard", "siada_responses", "siada_gemini"] = "standard"
    unavailable_reason: str | None = None
    replay_domain: str | None = None


def project_request_schemas(info: TokenCountingInfo, tools: list, handoffs: list, output_schema: Any, *, model_name: str | None = None) -> dict[str, Any]:
    from agents.models.chatcmpl_converter import Converter
    from agents.models.openai_responses import Converter as ResponsesConverter
    from openai import omit

    from siada.provider.responses.sanitize import sanitize_responses_tools_for_openai

    if info.protocol == "gemini":
        from siada.provider.gemini.converter import function_declarations

        wire_tools = [value.model_dump(mode="json", exclude_none=True) for value in function_declarations(tools, handoffs)]
        wire_output = output_schema.json_schema() if output_schema is not None and not output_schema.is_plain_text() else None
    elif info.protocol == "responses":
        wire_tools = ResponsesConverter.convert_tools(tools, handoffs, model=model_name or info.model_name).tools
        if info.input_projection == "siada_responses":
            wire_tools = sanitize_responses_tools_for_openai(wire_tools)
        wire_output = ResponsesConverter.get_response_format(output_schema)
    else:
        wire_tools = [Converter.tool_to_openai(tool) for tool in tools]
        wire_tools.extend(Converter.convert_handoff_tool(value) for value in handoffs)
        wire_output = Converter.convert_response_format(output_schema)
    return {"tools": wire_tools, "output": None if wire_output is omit else wire_output}


def replay_counting_domain(info: TokenCountingInfo) -> dict[str, Any]:
    if info.protocol == "gemini":
        from siada.provider.gemini.replay import REPLAY_VERSION

        return {"replay_domain": info.replay_domain, "signature_envelope_version": REPLAY_VERSION}
    return {}


def estimate_provider_input_tokens(info: TokenCountingInfo | None, items: Any, tools=None) -> tuple[int, str] | None:
    if info is not None and info.protocol == "gemini":
        from siada.provider.gemini.counting import estimate_input_tokens

        return estimate_input_tokens(items, tools), "google-genai:litellm-token-counter"
    return None


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
    if getattr(model, "request_protocol", None) == "gemini":
        info = TokenCountingInfo(model_name, "gemini", "siada_gemini", replay_domain=model.replay_domain)
    else:
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


def token_counting_info_from_config(config: Any, *, model_name: str | None = None) -> TokenCountingInfo:
    """Describe a configured route without resolving a model or retaining state."""
    model_name = model_name if model_name is not None else getattr(config, "model_name", None)
    provider = getattr(config, "provider", None)
    if isinstance(provider, str):
        from siada.provider.provider_factory import get_provider

        return provider_token_counting_info(get_provider(provider), model_name)
    return token_counting_info_from_model(model_name if isinstance(model_name, str) else None)


def context_token_counting_info(context: Any) -> TokenCountingInfo:
    """Prefer the admitted run's immutable route over configuration aliases."""
    info = getattr(getattr(context, "runtime_session", None), "token_counting_info", None)
    if isinstance(info, TokenCountingInfo):
        return replace(info, model_name=info.model_name or context.model_run_config.model_name)
    return token_counting_info_from_config(context.model_run_config)
