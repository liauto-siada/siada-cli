"""OpenAI Responses API protocol implementation (transport-agnostic).

``ResponsesModel`` adapts the agents SDK ``Model`` interface to the native
OpenAI Responses API. It contains only protocol logic — request param
building, input/tool sanitization, reasoning config resolution, streaming
event patching, usage normalization — and delegates authentication/routing
to an injected ``ResponsesTransport``.

Used by:
- the internal ``li`` provider (via ``LiProxyResponsesTransport``) for
  Responses-only models such as the GPT-5 family;
- the open-source ``default`` provider (via ``DefaultResponsesTransport``)
  for the same model families against a plain OpenAI-compatible endpoint.
"""
from __future__ import annotations

from typing import Any, AsyncIterator

from agents import AgentOutputSchemaBase
from agents.handoffs import Handoff
from agents.items import ModelResponse, TResponseInputItem, TResponseStreamEvent
from agents.model_settings import ModelSettings
from agents.models.interface import Model, ModelTracing
from agents.models.openai_responses import Converter as OpenAIResponsesConverter
from agents.tool import Tool
from agents.tracing import generation_span
from agents.usage import Usage
from openai import omit
from openai.types.responses import Response
from openai.types.responses.response_reasoning_item import Summary as ReasoningSummary
from openai.types.responses.response_usage import InputTokensDetails

from siada.foundation.logging import logger
from siada.provider.responses.sanitize import (
    ensure_reasoning_summary_nonempty,
    sanitize_input_reasoning_items,
    sanitize_responses_tools_for_openai,
)
from siada.provider.responses.transport import ResponsesTransport


def is_responses_only_model(model_name: str | None) -> bool:
    """Whether the model must go through the native Responses API.

    Currently the GPT-5 family (gpt-5, gpt-5.1, gpt-5.4, gpt-5-codex, ...).
    Providers use this to route between their Chat Completions path and
    ``ResponsesModel``.
    """
    if not model_name:
        return False
    name = str(model_name).lower()
    return "gpt-5" in name or "gpt5" in name


def _normalize_reasoning(
    reasoning: Any,
    reasoning_effort: str | None = None,
) -> dict[str, Any] | None:
    """Normalize reasoning config to a plain dict before sending upstream.

    Background:
    - siada-plugin sends a plain JSON object such as
      ``{"effort": "xhigh", "summary": "auto"}``
    - The Python OpenAI SDK can serialize ``Reasoning`` Pydantic objects using
      field aliases (for example ``summary`` -> ``generate_summary``), which
      is incompatible with some proxies' Responses API forwarding behavior.

    To keep parity with siada-plugin, convert Pydantic-like objects into a
    plain dict using the raw ``summary`` key.
    """
    if reasoning is None and reasoning_effort is None:
        return None

    if isinstance(reasoning, dict):
        normalized = dict(reasoning)
        if "generate_summary" in normalized and "summary" not in normalized:
            normalized["summary"] = normalized.pop("generate_summary")
        if normalized.get("effort") is None and reasoning_effort is not None:
            normalized["effort"] = reasoning_effort
        if normalized.get("effort") is not None and "summary" not in normalized:
            normalized["summary"] = "auto"
        return normalized or None

    effort = getattr(reasoning, "effort", None) or reasoning_effort
    max_tokens = getattr(reasoning, "max_tokens", None)

    normalized: dict[str, Any] = {}
    if effort is not None:
        normalized["effort"] = effort
        normalized["summary"] = "auto"
    if max_tokens is not None:
        normalized["max_tokens"] = max_tokens

    if normalized:
        return normalized

    model_dump = getattr(reasoning, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        if isinstance(dumped, dict):
            return _normalize_reasoning(dumped, reasoning_effort)

    return None


class ResponsesModel(Model):
    """Model implementation speaking the native OpenAI Responses API.

    Environment concerns (auth, base URL routing, tracing headers) are
    delegated to the injected ``transport``.
    """

    def __init__(self, model: str, transport: ResponsesTransport):
        super().__init__()
        self.model = model
        self._transport = transport

    @staticmethod
    def _should_default_reasoning(model_name: str | None) -> bool:
        """Return True for reasoning-capable model families that expect a
        ``reasoning`` parameter on every Responses API call.

        siada-plugin's ``normalizeOpenaiReasoningEffort`` defaults unspecified
        effort to ``"medium"`` and always sends
        ``reasoning: {effort, summary: "auto"}``, which is how it guarantees
        ``response.reasoning_summary_text.delta`` events are emitted. We
        match that behaviour here: for GPT-5 / o-series reasoning models,
        inject a minimal reasoning config if the caller did not supply one.

        We intentionally do NOT default reasoning for non-reasoning
        families (e.g. gpt-4, classic chat models) since sending
        ``reasoning`` to them would either error or change their output
        shape in unexpected ways.
        """
        if not model_name:
            return False
        name = model_name.lower()
        # GPT-5 family (gpt-5, gpt-5.1, gpt-5.2, gpt-5.4, gpt-5-codex, ...)
        if "gpt-5" in name:
            return True
        # o-series reasoning models (o1, o3, o4-mini, ...)
        if name.startswith("o1") or name.startswith("o3") or name.startswith("o4"):
            return True
        return False

    def _build_request_params(
        self,
        *,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: Any | None,
    ) -> dict[str, Any]:
        """Build OpenAI Responses API compatible request parameters."""
        converted = OpenAIResponsesConverter.convert_tools(tools, handoffs) if tools or handoffs else None

        request_params: dict[str, Any] = {
            "model": self.model,
            "input": sanitize_input_reasoning_items(input),
        }

        if system_instructions:
            request_params["instructions"] = system_instructions

        if converted:
            request_params["tools"] = sanitize_responses_tools_for_openai(converted.tools)
            if converted.includes:
                request_params["include"] = converted.includes

        text_config = OpenAIResponsesConverter.get_response_format(output_schema)
        if text_config is not omit:
            request_params["text"] = text_config

        if model_settings.temperature is not None:
            request_params["temperature"] = model_settings.temperature

        if model_settings.max_tokens is not None:
            request_params["max_output_tokens"] = model_settings.max_tokens

        # Resolve the effective reasoning config.
        #
        # ``ModelSettingsConverter`` populates reasoning in two different
        # places depending on model family:
        #   * Claude / Gemini → ``ModelSettings.reasoning`` (as ``Reasoning(effort=...)``)
        #   * All others (GPT-5.x, DeepSeek, etc.) → ``ModelSettings.extra_body["reasoning"]``
        #     as a plain dict like ``{"effort": "xhigh", "max_tokens": 8192}``.
        #
        # The OpenAI Responses API only understands the top-level ``reasoning``
        # parameter; anything tucked inside ``extra_body`` is silently ignored
        # by Responses forwarders, which is why GPT-5.x never streamed
        # ``response.reasoning_summary_text.delta`` events for us — without
        # ``reasoning`` on the request the model simply does not emit a
        # thinking summary at all.
        #
        # So: hoist ``extra_body["reasoning"]`` up to the top level if present,
        # merging it with whatever the ModelSettings.reasoning field already
        # contains. We also pop it from extra_body so the upstream does not
        # get a duplicated payload.
        extra_body_copy: dict[str, Any] | None = (
            dict(model_settings.extra_body) if isinstance(model_settings.extra_body, dict) else None
        )
        reasoning_config: Any = model_settings.reasoning
        if extra_body_copy is not None:
            extra_body_reasoning = extra_body_copy.pop("reasoning", None)
            if extra_body_reasoning:
                if reasoning_config is None:
                    reasoning_config = extra_body_reasoning
                elif isinstance(reasoning_config, dict):
                    merged = dict(reasoning_config)
                    merged.update(extra_body_reasoning)
                    reasoning_config = merged
                else:
                    # ModelSettings.reasoning is a ``Reasoning`` pydantic; dict
                    # from extra_body takes precedence because it carries the
                    # richer config (effort + max_tokens, etc.).
                    reasoning_config = extra_body_reasoning

        # ------------------------------------------------------------------
        # Default reasoning for GPT-5.x when the caller did not specify one.
        #
        # siada-plugin (see ``normalizeOpenaiReasoningEffort`` in
        # ``siada-plugin/src/shared/storage/types.ts``) defaults the effort to
        # ``"medium"`` when no effort is supplied, so the Responses API call
        # always carries ``reasoning: {effort: "medium", summary: "auto"}``
        # and the model emits ``response.reasoning_summary_text.delta``
        # events. In siada-cli, by contrast, ``gpt-5.4`` has
        # ``default_reasoning_effort = None``, which means ``reasoning``
        # was missing from the request entirely — the root cause of empty
        # thinking summaries on this protocol path.
        #
        # We match siada-plugin's behaviour: if we are going to send to a
        # GPT-5-family model and nothing set reasoning yet, inject a minimal
        # ``{"effort": "low", "summary": "auto"}`` so thinking streams on.
        # The ``summary: "auto"`` part is what actually drives
        # ``reasoning_summary_text.delta`` emission; the ``effort`` field
        # controls how much thinking the model does.
        # ------------------------------------------------------------------
        if reasoning_config is None and self._should_default_reasoning(self.model):
            reasoning_config = {"effort": "low", "summary": "auto"}
            logger.debug(
                f"[ResponsesModel] No reasoning supplied for model {self.model!r}; "
                f"defaulting to {reasoning_config!r} (matches siada-plugin default) "
                f"so ``response.reasoning_summary_text.delta`` events are emitted."
            )

        # Normalize to a plain dict here (protocol layer) so every transport
        # receives spec-shaped JSON and none of them needs to know about
        # ``Reasoning`` pydantic serialization quirks.
        normalized_reasoning = _normalize_reasoning(reasoning_config)
        if normalized_reasoning is not None:
            request_params["reasoning"] = normalized_reasoning

        if model_settings.parallel_tool_calls is not None and tools:
            request_params["parallel_tool_calls"] = model_settings.parallel_tool_calls

        tool_choice = OpenAIResponsesConverter.convert_tool_choice(model_settings.tool_choice)
        if tool_choice is not omit:
            request_params["tool_choice"] = tool_choice

        # Do not send previous_response_id — mirrors siada-plugin's
        # usePreviousResponseId: false. Sending a stale / un-stored ID causes
        # a 400 "item not found" error from the upstream service.

        if conversation_id:
            request_params["conversation"] = conversation_id

        if prompt is not None:
            request_params["prompt"] = prompt

        if model_settings.store is not None:
            request_params["store"] = model_settings.store

        if model_settings.metadata is not None:
            request_params["metadata"] = model_settings.metadata

        if model_settings.truncation is not None:
            request_params["truncation"] = model_settings.truncation

        if model_settings.top_p is not None:
            request_params["top_p"] = model_settings.top_p

        if model_settings.extra_query is not None:
            request_params["extra_query"] = model_settings.extra_query

        # Only attach extra_body if there are keys left after hoisting
        # ``reasoning``. An empty dict would bloat the payload for no reason.
        if extra_body_copy:
            request_params["extra_body"] = extra_body_copy

        if model_settings.extra_headers is not None:
            request_params["extra_headers"] = model_settings.extra_headers

        if model_settings.extra_args:
            request_params.update(model_settings.extra_args)

        return request_params

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: Any | None,
    ) -> ModelResponse:
        """Get a response from OpenAI Responses API."""
        with generation_span(
            model=self.model,
            model_config=model_settings.to_json_dict() | {"model_impl": "responses_api_direct"},
            disabled=tracing.is_disabled(),
        ) as span:
            request_params = self._build_request_params(
                system_instructions=system_instructions,
                input=input,
                model_settings=model_settings,
                tools=tools,
                output_schema=output_schema,
                handoffs=handoffs,
                previous_response_id=previous_response_id,
                conversation_id=conversation_id,
                prompt=prompt,
            )

            try:
                # Call Responses API via the injected transport
                response, llm_request_body = await self._transport.create(**request_params)

                # Safety net: the upstream may return reasoning items with an
                # empty ``summary: []`` on the non-streaming path too. Fill
                # with a placeholder so session persistence + next-turn replay
                # stay valid. (Mirrors the stream_response patch pattern.)
                ensure_reasoning_summary_nonempty(getattr(response, "output", []) or [])

                # Extract usage information
                usage = self._extract_usage(response)

                # Update tracing span
                if tracing.include_data():
                    span.span_data.output = [item.model_dump() for item in response.output]

                span.span_data.usage = {
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
                }

                # Response.output is already a list of output items
                return ModelResponse(
                    output=response.output,
                    usage=usage,
                    response_id=response.id,
                )

            except Exception as e:
                logger.error(f"OpenAI Responses API error: {e}")
                raise

    async def stream_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: Any | None,
    ) -> AsyncIterator[TResponseStreamEvent]:
        """Stream a response from OpenAI Responses API.

        Mirrors siada-plugin's createResponseStream: call responses.create once,
        then iterate native Responses API events directly — no chat-completion
        bridging needed because the upstream returns native events.
        """
        with generation_span(
            model=self.model,
            model_config=model_settings.to_json_dict() | {"model_impl": "responses_api_direct_stream"},
            disabled=tracing.is_disabled(),
        ):
            request_params = self._build_request_params(
                system_instructions=system_instructions,
                input=input,
                model_settings=model_settings,
                tools=tools,
                output_schema=output_schema,
                handoffs=handoffs,
                previous_response_id=previous_response_id,
                conversation_id=conversation_id,
                prompt=prompt,
            )

            try:
                stream, _llm_request_body = await self._transport.create_stream(**request_params)

                # Track function-call metadata by item ID so delta events can be
                # enriched with call_id / name — mirrors siada-plugin's
                # functionCallByItemId Map in createResponseStream.
                def _truncate(s: str, head: int = 20, tail: int = 20) -> str:
                    if len(s) <= head + tail + 3:
                        return s
                    return s[:head] + "..." + s[-tail:]

                function_call_by_item_id: dict[str, dict[str, Any]] = {}

                # Accumulate reasoning summary text per item ID — mirrors
                # siada-plugin's ReasoningHandler.processReasoningDelta.
                #
                # The upstream streams reasoning text via
                # ``response.reasoning_summary_text.delta`` events but may leave
                # ``summary: []`` empty in the final ``response.completed``
                # output. We collect the delta text here and patch it back into
                # the reasoning item on ``response.output_item.done`` and
                # ``response.completed`` so the agents SDK sees a fully
                # populated ``ReasoningItem.summary``.
                #
                # Also remember the ``encrypted_content`` seen on
                # ``response.output_item.added`` so that if the final item loses
                # it (some proxy routes strip it), we can restore it before
                # persistence.
                reasoning_text_by_item_id: dict[str, str] = {}
                reasoning_encrypted_by_item_id: dict[str, str] = {}

                def _patch_reasoning_item(item: Any) -> None:
                    """Fill a ReasoningItem's summary + encrypted_content from
                    the locally accumulated delta state.

                    Invariant after this call:
                      - ``item.summary`` is a non-empty list. If delta text was
                        collected, it contains a single summary_text entry with
                        the accumulated text. Otherwise it contains a single
                        whitespace placeholder so the item remains valid when
                        replayed.
                      - ``item.encrypted_content`` is restored from the initial
                        ``output_item.added`` event if the final event dropped it.
                    """
                    if item is None:
                        return
                    if getattr(item, "type", None) != "reasoning":
                        return

                    item_id = getattr(item, "id", None) or ""
                    text = reasoning_text_by_item_id.get(item_id, "")
                    current_summary = getattr(item, "summary", None)
                    has_summary = bool(current_summary) and (
                        not isinstance(current_summary, list) or len(current_summary) > 0
                    )

                    if not has_summary:
                        try:
                            if text:
                                item.summary = [
                                    ReasoningSummary(type="summary_text", text=text)
                                ]
                                logger.debug(
                                    f"[stream_response] patched reasoning summary "
                                    f"for item {item_id}: {len(text)} chars"
                                )
                            else:
                                # Placeholder so ``sanitize_input_reasoning_items``
                                # keeps this item on the next turn. Without this,
                                # an upstream returning an empty summary for short
                                # answers would put the paired assistant message
                                # at risk of orphaning.
                                item.summary = [
                                    ReasoningSummary(type="summary_text", text=" ")
                                ]
                                logger.debug(
                                    f"[stream_response] placeholder reasoning summary "
                                    f"for item {item_id} (no delta text collected)"
                                )
                        except Exception as patch_err:
                            logger.debug(
                                f"[stream_response] could not patch reasoning summary: {patch_err}"
                            )

                    # Restore encrypted_content if we captured it on .added but
                    # the final event dropped it.
                    if (
                        item_id in reasoning_encrypted_by_item_id
                        and not getattr(item, "encrypted_content", None)
                    ):
                        try:
                            item.encrypted_content = reasoning_encrypted_by_item_id[item_id]
                        except Exception:
                            pass

                async for event in stream:
                    event_type = getattr(event, "type", None)

                    if event_type == "response.output_item.added":
                        item = getattr(event, "item", None)
                        if item:
                            item_type = getattr(item, "type", None)
                            item_id = getattr(item, "id", None)

                            if item_type == "function_call" and item_id:
                                function_call_by_item_id[item_id] = {
                                    "call_id": getattr(item, "call_id", None),
                                    "name": getattr(item, "name", None),
                                    "id": item_id,
                                }
                            elif item_type == "reasoning" and item_id:
                                # Capture encrypted_content up front; it may be
                                # absent from the later done/completed events.
                                encrypted = getattr(item, "encrypted_content", None)
                                if encrypted:
                                    reasoning_encrypted_by_item_id[item_id] = encrypted

                    elif event_type == "response.function_call_arguments.delta":
                        item_id = getattr(event, "item_id", None)
                        if item_id and item_id in function_call_by_item_id:
                            meta = function_call_by_item_id[item_id]
                            logger.debug(
                                f"[stream_response] tool delta: item_id={item_id} "
                                f"call_id={meta.get('call_id')} name={meta.get('name')}"
                            )

                    elif event_type == "response.reasoning_summary_text.delta":
                        # Primary channel for reasoning text. The upstream emits
                        # these as the model thinks; we accumulate and patch
                        # back into the ReasoningItem later. Matches
                        # siada-plugin's handling of the same event type.
                        item_id = getattr(event, "item_id", None)
                        delta = getattr(event, "delta", "") or ""
                        if item_id and delta:
                            reasoning_text_by_item_id[item_id] = (
                                reasoning_text_by_item_id.get(item_id, "") + delta
                            )

                    elif event_type == "response.reasoning_summary_part.added":
                        # Some providers send the text as a ``part.text`` payload
                        # on ``.added`` instead of as a delta. Respect that too.
                        item_id = getattr(event, "item_id", None)
                        part = getattr(event, "part", None)
                        part_text = getattr(part, "text", "") if part else ""
                        if item_id and part_text:
                            reasoning_text_by_item_id[item_id] = (
                                reasoning_text_by_item_id.get(item_id, "") + part_text
                            )

                    elif event_type == "response.reasoning_text.delta":
                        # Non-summary reasoning stream (rare). Still worth
                        # capturing for visibility.
                        item_id = getattr(event, "item_id", None)
                        delta = getattr(event, "delta", "") or ""
                        if item_id and delta:
                            reasoning_text_by_item_id[item_id] = (
                                reasoning_text_by_item_id.get(item_id, "") + delta
                            )

                    elif event_type == "response.output_item.done":
                        # Patch the reasoning item summary here so that the
                        # agents SDK stores a populated ReasoningItem.
                        item = getattr(event, "item", None)
                        _patch_reasoning_item(item)

                    elif event_type == "response.completed":
                        # Also patch the reasoning items inside the final
                        # response object so that ModelResponse.output (which
                        # the session persists) contains populated summaries.
                        response_obj = getattr(event, "response", None)
                        if response_obj is not None:
                            for out_item in getattr(response_obj, "output", []) or []:
                                if getattr(out_item, "type", None) == "reasoning":
                                    _patch_reasoning_item(out_item)

                        if response_obj is not None:
                            logger.debug(
                                "[stream_response] response.completed "
                                f"reasoning_text_collected="
                                f"{ {k: len(v) for k, v in reasoning_text_by_item_id.items()} }"
                            )

                        usage = getattr(response_obj, "usage", None)
                        if usage:
                            # The Responses API reports ``input_tokens`` inclusive
                            # of cached tokens (cached_tokens is a subset, not an
                            # additional bucket) — same OpenAI-style semantics as
                            # ``_extract_usage`` already corrects for on the
                            # non-streaming path. Unlike that path, this raw
                            # ``response_obj.usage`` is what gets yielded via the
                            # event below and picked up verbatim by the agents
                            # SDK as the final ``ModelResponse.usage`` for the
                            # streaming path, so it must be corrected here too —
                            # otherwise downstream cache-hit-rate/cost
                            # calculations silently double count cached tokens.
                            details = getattr(usage, "input_tokens_details", None)
                            cached_tokens = getattr(details, "cached_tokens", 0) or 0
                            if cached_tokens:
                                response_obj.usage = usage.model_copy(
                                    update={"input_tokens": usage.input_tokens - cached_tokens}
                                )
                                usage = response_obj.usage

                            input_tokens = getattr(usage, "input_tokens", 0) or 0
                            output_tokens = getattr(usage, "output_tokens", 0) or 0
                            reasoning_tokens = (
                                getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", 0) or 0
                            )
                            logger.debug(
                                f"[stream_response] response.completed usage: "
                                f"input={input_tokens} output={output_tokens} reasoning={reasoning_tokens} "
                                f"cached={cached_tokens}"
                            )

                    elif event_type == "response.incomplete":
                        reason = getattr(
                            getattr(getattr(event, "response", None), "incomplete_details", None),
                            "reason",
                            None,
                        )
                        logger.warning(f"[stream_response] response.incomplete: reason={reason}")

                    # ----------------------------------------------------------
                    # SSE event trace log — one line per event, shows the full
                    # flow:  created → output_item.added → delta(s) →
                    #         output_item.done → completed
                    # ----------------------------------------------------------
                    _sse_extra = ""
                    if event_type == "response.created":
                        _sse_extra = f"response_id={getattr(getattr(event, 'response', None), 'id', None)}"
                    elif event_type == "response.output_item.added":
                        _item = getattr(event, "item", None)
                        _sse_extra = (
                            f"item_type={getattr(_item, 'type', None)} "
                            f"item_id={getattr(_item, 'id', None)}"
                        )
                    elif event_type == "response.output_item.done":
                        _item = getattr(event, "item", None)
                        _sse_extra = (
                            f"item_type={getattr(_item, 'type', None)} "
                            f"item_id={getattr(_item, 'id', None)}"
                        )
                    elif event_type in (
                        "response.output_text.delta",
                        "response.reasoning_summary_text.delta",
                        "response.reasoning_text.delta",
                    ):
                        _delta = getattr(event, "delta", "") or ""
                        _item_id = getattr(event, "item_id", None)
                        _accumulated = reasoning_text_by_item_id.get(_item_id, "") if _item_id else ""
                        _sse_extra = (
                            f"item_id={_item_id} "
                            f"delta={_truncate(_delta)!r} "
                            f"accumulated={_truncate(_accumulated)!r}"
                        )
                    elif event_type == "response.function_call_arguments.delta":
                        _delta = getattr(event, "delta", "") or ""
                        _fc_item_id = getattr(event, "item_id", None)
                        _fc_call_id = (
                            function_call_by_item_id.get(_fc_item_id, {}).get("call_id")
                            if _fc_item_id else None
                        )
                        _sse_extra = (
                            f"item_id={_fc_item_id} "
                            f"call_id={_fc_call_id} "
                            f"delta={_truncate(_delta)!r}"
                        )
                    elif event_type == "response.completed":
                        _resp = getattr(event, "response", None)
                        _usage = getattr(_resp, "usage", None)
                        _sse_extra = (
                            f"response_id={getattr(_resp, 'id', None)} "
                            f"output_count={len(getattr(_resp, 'output', None) or [])} "
                            f"input_tokens={getattr(_usage, 'input_tokens', None)} "
                            f"output_tokens={getattr(_usage, 'output_tokens', None)}"
                        )
                    logger.debug(f"[SSE] {event_type} {_sse_extra}".rstrip())

                    yield event

            except Exception as e:
                logger.error(f"OpenAI Responses API streaming error: {e}")
                raise

    def _extract_usage(self, response: Response) -> Usage:
        """Extract usage information from Response object."""
        if not hasattr(response, "usage") or not response.usage:
            return Usage()

        usage_data = response.usage

        # Extract cached tokens if available
        cached_tokens = 0
        if hasattr(usage_data, "input_tokens_details"):
            details = usage_data.input_tokens_details
            if hasattr(details, "cached_tokens"):
                cached_tokens = details.cached_tokens or 0

        return Usage(
            requests=1,
            input_tokens=usage_data.input_tokens - cached_tokens,
            output_tokens=usage_data.output_tokens,
            total_tokens=usage_data.total_tokens,
            input_tokens_details=InputTokensDetails(cached_tokens=cached_tokens),
        )
