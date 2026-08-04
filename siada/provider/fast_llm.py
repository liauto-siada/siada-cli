"""
Fast LLM helpers for memory-related LLM calls.

Lightweight tasks (session naming, MemoryAgent, summaries…) don't need the main
agent's flagship model.  This module wraps:

* ``SiadaClient`` (used by ``MemoryService._generate_slug_via_llm``)
* provider ``RunConfig`` (used by ``MemoryAgent`` via ``RunConfig.model_provider``)

Model / provider resolution (``_get_fast_model_and_provider``):
  * Internal build (``li`` provider available) → ``kivy-deepseek-v4-flash-0731``.
  * Open-source build → same model / provider as the user's normal config
    (``llm_config`` in ``~/.siada-cli/conf.yaml``).

Everything here is local to these lightweight paths — the main agent's model
choice is untouched.
"""

from typing import Any, Optional

import yaml

from agents import Model, RunConfig

from siada.foundation.constants import SIADA_HOME
from siada.foundation.logging import logger
from siada.models.model_run_config import ModelRunConfig
from siada.models.model_setting_converter import ModelSettingsConverter
from siada.provider.provider_factory import get_provider
from siada.services.input_processor import process_input
from siada.services.model_wrapper import ModelProviderWrapper


# Internal build defaults.
_INTERNAL_FAST_MODEL: str = "kivy-deepseek-v4-flash-0731"
_INTERNAL_PROVIDER: str = "li"


def _get_user_llm_config() -> tuple[Optional[str], Optional[str]]:
    """Read ``llm_config.model`` / ``llm_config.provider`` from the user's
    ``~/.siada-cli/conf.yaml``.

    Read fresh on every call (no cache) so mid-session ``/model`` switches —
    which are persisted back to conf.yaml — are picked up immediately.
    """
    try:
        conf_path = SIADA_HOME / "conf.yaml"
        if conf_path.exists():
            with open(conf_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            llm = data.get("llm_config") or {}
            return llm.get("model"), llm.get("provider")
    except Exception as e:
        logger.info(f"[fast-llm] failed to read conf.yaml llm_config: {e}")
    return None, None


def _get_fast_model_and_provider() -> tuple[str, str]:
    """Return ``(model_name, provider_name)`` for fast LLM tasks.

    * Internal build (``li`` provider registered) → pinned fast model.
    * Open-source build → same model / provider as the user's normal config.
    """
    try:
        get_provider(_INTERNAL_PROVIDER)
        return _INTERNAL_FAST_MODEL, _INTERNAL_PROVIDER
    except ValueError:
        pass

    model, provider = _get_user_llm_config()
    if not model:
        # No model configured yet — fall back to the framework default.
        model = ModelRunConfig.get_default_config().model_name
    return model, provider or "default"


def get_fast_model_name() -> str:
    """Return the model name that will be used for fast LLM calls."""
    return _get_fast_model_and_provider()[0]


# ---- Model (for openai-agents Runner) ---------------------------------------

def get_fast_model() -> Model:
    """Return a ``Model`` instance pinned to the fast model."""
    model_name, provider_name = _get_fast_model_and_provider()
    provider = get_provider(provider_name)
    return provider.get_model(model_name)


def build_fast_run_config() -> RunConfig:
    """Build a ``RunConfig`` that forces the fast model.

    Convenience wrapper so MemoryAgent doesn't need to know about model
    settings / provider wiring.
    """
    model_name, provider_name = _get_fast_model_and_provider()

    # Build a ModelRunConfig for the fast model so ModelSettings
    # (parallel_tool_calls, max_tokens, …) comes from model_base_config.
    mrc = ModelRunConfig(model_name)
    mrc.provider = provider_name
    # Disable reasoning/thinking — we want this fast.
    mrc.thinking_tokens = None
    mrc.reasoning_effort = None

    model_settings = ModelSettingsConverter.convert_model_settings(mrc)
    base_provider = get_provider(provider_name)
    provider_wrapper = ModelProviderWrapper(
        base_provider=base_provider,
        input_processor=process_input,
    )

    logger.info(
        f"[fast-llm] build_fast_run_config → model={model_name} "
        f"provider={provider_name}"
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
    """One-shot completion through the fast provider's ``SiadaClient``.

    Args:
        prompt: User prompt content.
        agent_name: Optional override for the AGENT_NAME context variable for
            the duration of this call only.
        **kwargs: Optional overrides forwarded to SiadaClient.completion
                  (e.g. temperature, max_tokens, stream).

    Returns:
        The ``LitellmModelResponse`` returned by SiadaClient.completion.
    """
    # Lazy import so code paths that don't use this don't pay the cost.
    from siada.foundation.context import agent_name_scope
    from siada.provider.client_factory import get_client

    model_name, provider_name = _get_fast_model_and_provider()
    client = get_client(provider_name)

    call_kwargs = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    call_kwargs.update(kwargs)

    logger.info(
        f"[fast-llm] fast_completion -> model={model_name} "
        f"provider={provider_name}"
    )
    with agent_name_scope(agent_name):
        return await client.completion(**call_kwargs)
