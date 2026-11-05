"""
Fast LLM helpers for memory-related LLM calls.

Lightweight tasks (session naming, MemoryAgent, summaries…) don't need the main
agent's flagship model.  This module wraps:

* direct SDK model requests (used by ``MemoryService._generate_slug_via_llm``)
* provider ``RunConfig`` (used by ``MemoryAgent`` via ``RunConfig.model_provider``)

Model / provider resolution (``_get_fast_model_and_provider``):
  * ``fast_llm_config`` in ``~/.siada-cli/conf.yaml`` (explicit override) →
    the configured model / provider / base_url / api_key / extra_headers,
    ``fast_llm_config.model`` is required for the override to apply.
  * Otherwise → same model / provider as the user's normal config
    (``llm_config`` in ``~/.siada-cli/conf.yaml``).

Everything here is local to these lightweight paths — the main agent's model
choice is untouched.
"""

from typing import Any, Dict, Optional, Tuple

from agents import Model, ModelResponse, RunConfig

from siada.foundation.logging import logger
from siada.models.model_run_config import ModelRunConfig
from siada.models.model_setting_converter import ModelSettingsConverter
from siada.provider.provider_factory import get_provider
from siada.services.input_processor import process_input
from siada.services.model_wrapper import ModelProviderWrapper


# Default provider for the ``fast_llm_config`` override (openai-compatible
# endpoint via BASE_URL / API_KEY — the same provider the main agent uses for
# custom gateways).
_DEFAULT_OVERRIDE_PROVIDER: str = "default"


def _get_user_fast_llm_config() -> Dict[str, Any]:
    """Read the ``fast_llm_config`` section from the user's
    ``~/.siada-cli/conf.yaml`` ({} when absent or not a mapping).

    Read fresh on every call (no cache) so config edits are picked up
    immediately, mirroring ``_get_user_llm_config``.
    """
    from siada.config.conf_store import get_conf_section

    return get_conf_section("fast_llm_config")


def _get_user_llm_config() -> tuple[Optional[str], Optional[str]]:
    """Read ``llm_config.model`` / ``llm_config.provider`` from the user's
    ``~/.siada-cli/conf.yaml``.

    Read fresh on every call (no cache) so mid-session ``/model`` switches —
    which are persisted back to conf.yaml — are picked up immediately.
    """
    from siada.config.conf_store import get_conf_section

    llm = get_conf_section("llm_config")
    return llm.get("model"), llm.get("provider")


def _get_fast_model_and_provider() -> Tuple[str, str, Dict[str, Any]]:
    """Return ``(model_name, provider_name, call_kwargs)`` for fast LLM tasks.

    Resolution order:

    1. ``fast_llm_config`` in conf.yaml (explicit override) → the configured
       model / provider; ``base_url`` / ``api_key`` / ``extra_headers`` from
       that section are returned in ``call_kwargs`` for direct completion
       calls (``fast_completion``). ``fast_llm_config.model`` is required —
       a section without it is ignored with a warning.
    2. Same model / provider as the user's normal config.
    """
    override = _get_user_fast_llm_config()
    if override:
        model = override.get("model")
        if model:
            provider = override.get("provider") or _DEFAULT_OVERRIDE_PROVIDER
            call_kwargs: Dict[str, Any] = {}
            if override.get("base_url"):
                call_kwargs["api_base"] = override["base_url"]
            if override.get("api_key"):
                call_kwargs["api_key"] = override["api_key"]
            if isinstance(override.get("extra_headers"), dict):
                call_kwargs["extra_headers"] = dict(override["extra_headers"])
            return model, provider, call_kwargs
        logger.warning(
            "[fast-llm] fast_llm_config present but missing 'model'; "
            "ignoring the override"
        )

    model, provider = _get_user_llm_config()
    if not model:
        # No model configured yet — fall back to the framework default.
        model = ModelRunConfig.get_default_config().model_name
    return model, provider or "default", {}


def get_fast_model_name() -> str:
    """Return the model name that will be used for fast LLM calls."""
    return _get_fast_model_and_provider()[0]


# ---- Model (for openai-agents Runner) ---------------------------------------

def get_fast_model() -> Model:
    """Return a ``Model`` instance pinned to the fast model."""
    model_name, provider_name, _ = _get_fast_model_and_provider()
    provider = get_provider(provider_name)
    return provider.get_model(model_name)


def build_fast_run_config() -> RunConfig:
    """Build a ``RunConfig`` that forces the fast model.

    Convenience wrapper so MemoryAgent doesn't need to know about model
    settings / provider wiring.
    """
    model_name, provider_name, _ = _get_fast_model_and_provider()

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
) -> ModelResponse:
    """One-shot SDK completion through the wrapped, loop-owned fast provider.

    Args:
        prompt: User prompt content.
        agent_name: Optional override for the AGENT_NAME context variable for
            the duration of this call only.
        **kwargs: Request-local SDK settings and endpoint overrides
                  (e.g. temperature, max_tokens, timeout, messages, stream).

    Returns:
        The final SDK ``ModelResponse``. Streaming transport is consumed
        internally by default; pass stream=False for non-streaming transport.
    """
    # Lazy import so code paths that don't use this don't pay the cost.
    from siada.provider.one_shot import one_shot_completion

    model_name, provider_name, override_kwargs = _get_fast_model_and_provider()
    call_kwargs = {
        "model": model_name,
        "stream": True,
    }
    # Explicit per-call kwargs (kwargs) take precedence over the conf.yaml
    # fast_llm_config override (override_kwargs).
    call_kwargs.update(override_kwargs)
    call_kwargs.update(kwargs)

    logger.info(
        f"[fast-llm] fast_completion -> model={model_name} "
        f"provider={provider_name}"
    )
    return await one_shot_completion(
        prompt, provider=provider_name, agent_name=agent_name, **call_kwargs
    )
