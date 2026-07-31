"""Monkey-patches applied to the third-party ``openai-agents`` SDK at startup.

Currently:

- **Soft handling of unknown tool names.** Weaker / faster models (e.g. the
  user-mentioned "deepseek v4 flash") sometimes hallucinate tool names that
  don't exist on the agent, e.g. ``read_skill`` instead of the real skill
  invocation tool. The vendored SDK's ``process_model_response`` raises
  ``ModelBehaviorError("Tool X not found in agent Y")`` in that case, which
  bubbles up as a fatal "Agent Execution Error" to the user.

  Instead, we patch ``process_model_response`` to detect such unknown
  function-tool calls *before* the SDK raises, and inject a synthetic
  ``FunctionTool`` stub into ``all_tools`` whose ``on_invoke_tool`` returns a
  short feedback message listing the genuinely-available tool names. The SDK
  then naturally treats the call as a normal function-tool invocation, the
  stub "executes", and its output goes back to the model as a regular
  ``function_call_output`` item — giving the model the information it needs
  to self-correct on the next turn.

The patch is best-effort: any failure during injection silently falls through
to the original (unmodified) SDK behavior, so we never make startup worse.
"""

from __future__ import annotations

import logging
from typing import Any, List, Set

logger = logging.getLogger(__name__)

_PATCHED = False
_LITELLM_PATCHED = False


def apply_sdk_patches() -> None:
    """Apply all siada-side monkey-patches to the agents SDK. Idempotent.

    NOTE: this runs inside the agents warmup background thread, which may race
    with the main thread's ``import litellm``. Do NOT import litellm submodules
    here — that can trigger a "partially initialized module 'litellm'" circular
    import. litellm-side patches live in ``apply_litellm_patches`` and must be
    applied only once litellm is fully loaded (see ``apply_litellm_patches``).
    """
    global _PATCHED
    if _PATCHED:
        return
    try:
        _patch_unknown_tool_to_synthetic_stub()
        _PATCHED = True
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to apply agents SDK patches: %s", exc, exc_info=True)


def apply_litellm_patches() -> None:
    """Apply litellm-side monkey-patches. Idempotent.

    Must be called only *after* litellm has been fully imported — e.g. right
    before ``litellm.acompletion`` in the request path — to avoid a partial
    import race with the concurrent agents warmup thread.
    """
    global _LITELLM_PATCHED
    if _LITELLM_PATCHED:
        return
    try:
        _patch_disable_gemini_function_call_id_forwarding()
        _LITELLM_PATCHED = True
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to apply litellm patches: %s", exc, exc_info=True)



def _patch_disable_gemini_function_call_id_forwarding() -> None:
    """Stop litellm from adding an ``id`` field to Gemini function call parts.

    litellm >= 1.91 forwards the OpenAI tool-call ``id`` onto the Gemini
    ``function_call`` / ``function_response`` parts for "gemini-3+" models when
    ``custom_llm_provider == "gemini"`` (Google AI Studio semantics). Note that
    ``gemini-3.5-flash`` is classified as gemini-3+ because litellm only checks
    for the substring ``"gemini-3"``.

    Our li-mate gateway sets ``custom_llm_provider == "gemini"`` but actually
    serves Gemini traffic through Vertex AI, which rejects the extra ``id`` field
    with an HTTP 400::

        Unknown name "id" at 'contents[..].parts[0].function_call': Cannot find field.

    Since siada never talks to Google AI Studio directly, force the forwarding
    off so the ``id`` is never emitted, regardless of model / provider.

    Why patch instead of alternatives:
    - Changing ``custom_llm_provider`` to ``vertex_ai`` would also disable the
      forwarding, but it switches litellm's whole request pipeline (URL path
      ``/publishers/google/models/...`` + GCP OAuth auth) away from the AI Studio
      ``/v1beta`` + api-key protocol the li-mate gateway actually speaks, so it
      is a cross-service change, not a drop-in fix.
    - litellm exposes no public flag for this behavior (only this private
      static method), so a monkey-patch is the least-invasive client-side fix.

    Long-term / cleaner fix: have the li-mate gateway strip the ``id`` from
    ``function_call`` / ``function_response`` parts before forwarding to Vertex.
    That removes the client-side dependency on a litellm private method entirely,
    at which point this patch can be dropped.

    NOTE: this depends on litellm's private ``_forward_gemini_function_call_id``;
    re-check it when bumping litellm. The caller in ``apply_sdk_patches`` wraps
    this in try/except, so a rename would only make the bug resurface, never crash.
    """

    try:
        from litellm.llms.vertex_ai.gemini.vertex_and_google_ai_studio_gemini import (
            VertexGeminiConfig,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug(
            "Skip gemini function_call id patch; litellm import failed: %s", exc
        )
        return

    # ``_forward_gemini_function_call_id`` is a @staticmethod on the config class;
    # keep it a staticmethod so existing call sites keep working unchanged.
    VertexGeminiConfig._forward_gemini_function_call_id = staticmethod(
        lambda model, custom_llm_provider=None: False
    )
    logger.debug(
        "Patched litellm VertexGeminiConfig._forward_gemini_function_call_id -> False"
    )



def _patch_unknown_tool_to_synthetic_stub() -> None:
    from agents import FunctionTool
    from agents._tool_identity import (
        build_function_tool_lookup_map,
        get_function_tool_lookup_key_for_call,
    )
    from agents.run_internal import turn_resolution as _turn_mod
    from openai.types.responses import ResponseFunctionToolCall

    _orig_process_model_response = _turn_mod.process_model_response

    def _make_unknown_tool_stub(
        unknown_name: str,
        agent_name: str,
        available_names: List[str],
    ) -> FunctionTool:
        listing = ", ".join(sorted({n for n in available_names if n})) or "(none)"
        feedback = (
            f"Error: tool `{unknown_name}` does not exist on agent `{agent_name}`. "
            f"Available tools on this agent are: {listing}. "
            "Do not call `" + unknown_name + "` again. "
            "Either pick one of the available tools above, or, if no tool fits, "
            "answer the user directly without a tool call."
        )

        async def _on_invoke(_ctx: Any, _args: str) -> str:
            return feedback

        return FunctionTool(
            name=unknown_name,
            description=(
                f"(auto-generated stub) Tool `{unknown_name}` is not registered on "
                f"agent `{agent_name}`. Calling this returns a corrective message "
                "listing the real tools."
            ),
            params_json_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": True,
            },
            on_invoke_tool=_on_invoke,
            strict_json_schema=False,
        )

    def _patched_process_model_response(
        *,
        agent: Any,
        all_tools: Any,
        response: Any,
        output_schema: Any,
        handoffs: Any,
        existing_items: Any = None,
        **extra_kwargs: Any,
    ) -> Any:
        # ``extra_kwargs`` captures any parameters added by newer SDK versions
        # (e.g. ``run_config`` introduced in openai-agents 0.17.x) so we can
        # forward them verbatim without breaking on signature changes.

        # TEMP DIAGNOSTIC: log the concrete output item types so we can verify
        # whether non-Responses-API model paths (e.g. chat-completions via
        # deepseek-v4-flash) produce ResponseFunctionToolCall or something else.
        try:
            _diag_types = [
                type(o).__name__
                for o in (getattr(response, "output", None) or [])
            ]
            logger.info(
                "patched_process_model_response: agent=%s response.output types = %s",
                getattr(agent, "name", "agent"),
                _diag_types,
            )
        except Exception:  # pragma: no cover - defensive
            pass

        try:
            handoff_names: Set[str] = {
                getattr(h, "tool_name", None) for h in (handoffs or [])
            }
            handoff_names.discard(None)

            function_tools = [t for t in all_tools if isinstance(t, FunctionTool)]
            existing_keys = set(build_function_tool_lookup_map(function_tools).keys())
            available_names: List[str] = [t.name for t in function_tools] + list(
                handoff_names
            )

            extra_stubs: List[FunctionTool] = []
            already_synthesized: Set[str] = set()
            agent_name = getattr(agent, "name", "agent")

            for output in getattr(response, "output", None) or []:
                if not isinstance(output, ResponseFunctionToolCall):
                    logger.info(
                        "stub-check: skip non-FunctionToolCall output type=%s",
                        type(output).__name__,
                    )
                    continue
                name = getattr(output, "name", None)
                if not isinstance(name, str) or not name:
                    logger.info("stub-check: skip empty/non-str name=%r", name)
                    continue
                # Log the tool call arguments so we can see what command the
                # model is trying to execute (e.g. run_cmd's shell command).
                logger.info(
                    "stub-check: tool_call name=%s arguments=%s call_id=%s",
                    name,
                    getattr(output, "arguments", None),
                    getattr(output, "call_id", None),
                )
                # Real handoff — leave alone.

                if name in handoff_names:
                    logger.info("stub-check: name=%s is a handoff, leave alone", name)
                    continue
                # SDK has its own synthetic for json_tool_call when output_schema is set.
                if output_schema is not None and name == "json_tool_call":
                    logger.info(
                        "stub-check: name=%s is json_tool_call w/ output_schema, leave alone",
                        name,
                    )
                    continue
                # Already a registered function tool — leave alone.
                lookup_key = get_function_tool_lookup_key_for_call(output)
                in_existing = lookup_key is not None and lookup_key in existing_keys
                logger.info(
                    "stub-check: name=%s lookup_key=%r in_existing_keys=%s "
                    "existing_keys_sample=%s",
                    name,
                    lookup_key,
                    in_existing,
                    sorted(existing_keys)[:10],
                )
                if in_existing:
                    continue
                if name in already_synthesized:
                    logger.info("stub-check: name=%s already synthesized this turn", name)
                    continue
                already_synthesized.add(name)
                logger.info(
                    "stub-check: WILL INJECT stub for name=%s on agent=%s",
                    name,
                    agent_name,
                )
                extra_stubs.append(
                    _make_unknown_tool_stub(name, agent_name, available_names)
                )

            if extra_stubs:
                logger.info(
                    "Injecting synthetic stub(s) for unknown tool call(s) on "
                    "agent=%s: %s",
                    agent_name,
                    [t.name for t in extra_stubs],
                )
                all_tools = list(all_tools) + extra_stubs
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(
                "unknown-tool stub injection skipped due to error: %s",
                exc,
                exc_info=True,
            )

        return _orig_process_model_response(
            agent=agent,
            all_tools=all_tools,
            response=response,
            output_schema=output_schema,
            handoffs=handoffs,
            existing_items=existing_items,
            **extra_kwargs,
        )

    _turn_mod.process_model_response = _patched_process_model_response
    logger.debug("Patched agents.run_internal.turn_resolution.process_model_response")
