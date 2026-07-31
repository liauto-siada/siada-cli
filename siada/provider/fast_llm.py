"""
Fast LLM helpers for memory-related LLM calls.

Lightweight tasks (session naming, MemoryAgent, summaries…) don't need the main agent's
flagship model. The fast model/provider are configurable via environment
variables and default to the session's main model:

* ``SIADA_FAST_MODEL``    — dedicated fast model name (optional)
* ``SIADA_FAST_PROVIDER`` — provider for the fast model (default: "default")

Everything here is local to these lightweight paths — the main agent's model
choice is untouched.
"""

import os
from typing import Any, Optional

from agents import Model, RunConfig

from siada.foundation.context import get_context_var, LLM_CONFIG
from siada.foundation.logging import logger
from siada.models.model_run_config import ModelRunConfig
from siada.models.model_setting_converter import ModelSettingsConverter
from siada.provider.provider_factory import get_provider
from siada.services.input_processor import process_input
from siada.services.model_wrapper import ModelProviderWrapper


# ---- Policy -----------------------------------------------------------------
# Pinned here so a single place controls the fast-model routing.
FAST_MODEL_NAME: str = os.getenv("SIADA_FAST_MODEL", "")
FAST_PROVIDER_NAME: str = os.getenv("SIADA_FAST_PROVIDER", "default")


def _resolve_fast_model_name() -> str:
    """Resolve the fast model name: env override, else the session's main model."""
    if FAST_MODEL_NAME:
        return FAST_MODEL_NAME
    llm_config = get_context_var(LLM_CONFIG)
    model_name = getattr(llm_config, "model_name", None) if llm_config else None
    if model_name:
        return model_name
    raise ValueError(
        "No fast model configured; set SIADA_FAST_MODEL or run within a session"
    )


# ---- Model (for openai-agents Runner) ---------------------------------------

def get_fast_model() -> Model:
    """Return a ``Model`` instance pinned to the fast model."""
    provider = get_provider(FAST_PROVIDER_NAME)
    return provider.get_model(_resolve_fast_model_name())


def build_fast_run_config() -> RunConfig:
    """Build a ``RunConfig`` that forces the fast model.

    Convenience wrapper so MemoryAgent doesn't need to know about model
    settings / provider wiring.
    """
    model_name = _resolve_fast_model_name()
    # Build a ModelRunConfig for the fast model so ModelSettings
    # (parallel_tool_calls, max_tokens, …) comes from model_base_config.
    mrc = ModelRunConfig(model_name)
    mrc.provider = FAST_PROVIDER_NAME
    # Disable reasoning/thinking — we want this fast.
    mrc.thinking_tokens = None
    mrc.reasoning_effort = None

    model_settings = ModelSettingsConverter.convert_model_settings(mrc)
    base_provider = get_provider(FAST_PROVIDER_NAME)
    provider_wrapper = ModelProviderWrapper(
        base_provider=base_provider,
        input_processor=process_input,
    )

    logger.info(
        f"[fast-llm] build_fast_run_config → model={model_name} "
        f"provider={FAST_PROVIDER_NAME}"
    )

    return RunConfig(
        tracing_disabled=False,
        model=model_name,
        model_provider=provider_wrapper,
        model_settings=model_settings,
    )


# ---- Simple completion (for slug generation) --------------------------------

async def fast_completion(
    prompt: str,
    *,
    agent_name: Optional[str] = None,
    **kwargs: Any,
) -> Optional[Any]:
    """One-shot completion through the configured provider, pinned to
    the fast model.

    Args:
        prompt: User prompt content.
        agent_name: Optional override for the AGENT_NAME context variable for
            the duration of this call only.
        **kwargs: Optional overrides forwarded to the client's completion
                  (e.g. temperature, max_tokens, stream).

    Returns:
        The completion response returned by the provider client.
    """
    # Lazy import so code paths that don't use this don't pay the cost.
    from siada.foundation.context import agent_name_scope
    from siada.provider.client_factory import get_client

    model_name = _resolve_fast_model_name()
    client = get_client(FAST_PROVIDER_NAME)

    call_kwargs = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    call_kwargs.update(kwargs)

    logger.debug(
        f"[fast-llm] fast_completion -> model={model_name} "
        f"provider={FAST_PROVIDER_NAME}"
    )
    with agent_name_scope(agent_name):
        return await client.completion(**call_kwargs)
