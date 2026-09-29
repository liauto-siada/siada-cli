"""Shared LLM call + JSON-extraction helpers for the Browser Skill Graph.

All LLM calls in this package go through ``siada.provider.fast_llm.fast_completion``
(the lightweight model already used for memory slug generation etc. — see
design doc §9), so classify/distill/match all share one model policy.
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)


async def call_fast_llm(prompt: str, *, agent_name: str) -> str:
    """One-shot completion through the fast provider; returns raw text.

    Returns "" on any failure (missing choices, exception, timeout) so
    callers can treat "no answer" uniformly without try/except everywhere.

    Reasoning is pinned to ``low``: these prompts carry full trajectory
    evidence (tens of KB), and a default/high reasoning effort on the fast
    model pushes generation past the callers' 60 s timeout (verified with a
    real stuck record: bare call > 70 s vs 18.9 s with ``low``).
    """
    from siada.provider.fast_llm import fast_completion

    # NB: ``asyncio.timeout`` at the call sites cannot reliably interrupt
    # litellm — its retry layer swallows the cancellation and the single-shot
    # socket timeout defaults to LLM_API_POST_TIMEOUT (1200 s), so a slow
    # gateway would hang this coroutine far beyond the caller's budget and
    # the worker's lease. Pass an explicit short timeout so the failure
    # surfaces at the socket layer instead: litellm aborts the connection
    # and raises Timeout, which we swallow into "" as usual.
    try:
        response = await fast_completion(
            prompt, agent_name=agent_name, timeout=50,
            extra_body={"reasoning_effort": "low"},
        )
    except Exception as e:  # noqa: BLE001 — never let a matching/distill call crash the caller
        logger.warning("[browser-skill] fast_completion failed (%s): %s", agent_name, e)
        return ""

    if not response or not getattr(response, "choices", None):
        return ""
    choice = response.choices[0]
    content = getattr(getattr(choice, "message", None), "content", None)
    return content or ""


def parse_json_from_model(text: str) -> dict:
    """Best-effort JSON extraction from an LLM response.

    Handles plain JSON, ```json fenced blocks, and stray leading/trailing
    text around a single JSON object.
    """
    if not text:
        return {}
    text = text.strip()

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
            text = text[brace_start : brace_end + 1]

    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        logger.debug("[browser-skill] model output was not a JSON object")
        return {}
