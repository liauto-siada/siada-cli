"""
Fast LLM helpers for memory-related LLM calls.

Lightweight tasks (session naming, MemoryAgent, summaries…) don't need the main
agent's flagship model.  This module wraps:

* ``SiadaClient`` (used by ``MemoryService._generate_slug_via_llm``)
* provider ``RunConfig`` (used by ``MemoryAgent`` via ``RunConfig.model_provider``)

Model / provider resolution (``_get_fast_model_and_provider``):
  * ``fast_llm_config`` in ``~/.siada-cli/conf.yaml`` (explicit override) →
    the configured model / provider / base_url / api_key / extra_headers,
    e.g. routing fast tasks to a private gateway instead of the internal li
    proxy. ``fast_llm_config.model`` is required for the override to apply.
  * Internal build (``li`` provider available) → the model flagged
    ``is_kivy_fast_model`` / ``is_lpai_fast_model`` / ``is_other_fast_model``
    in ``model_base_config``, following the gateway family of the user's main
    model (``kivy-*`` main model → kivy flag, ``lpai-*`` → lpai flag,
    anything else → other flag); falls back to the built-in deepseek-v4-flash
    defaults when no flagged model exists. The flags are remotely
    controllable via Apollo (siada-server model config), like any other
    ModelBaseConfig field.
  * Open-source build → same model / provider as the user's normal config
    (``llm_config`` in ``~/.siada-cli/conf.yaml``).

Everything here is local to these lightweight paths — the main agent's model
choice is untouched.
"""

from typing import Any, Dict, Optional, Tuple

from agents import Model, RunConfig

from siada.foundation.logging import logger
from siada.models.model_run_config import ModelRunConfig
from siada.models.model_setting_converter import ModelSettingsConverter
from siada.provider.provider_factory import get_provider
from siada.services.input_processor import process_input
from siada.services.model_wrapper import ModelProviderWrapper


# Internal build fallback defaults, used when no model in the (possibly
# remotely overridden) model settings carries the corresponding
# is_kivy/lpai/other_fast_model flag. The fast model follows the gateway
# family of the user's main model: kivy and lpai families fall back to the
# kivy gateway flash, other families to the baidu gateway flash (the pre-flag
# behavior for non-kivy models).
_INTERNAL_FAST_MODEL_KIVY: str = "lpai-glm-5.3"
_INTERNAL_FAST_MODEL_BAIDU: str = "lpai-glm-5.3"
_INTERNAL_PROVIDER: str = "li"

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


def _get_internal_fast_model(user_model: Optional[str]) -> str:
    """Pick the internal fast model by the gateway family of the user's main
    model: ``kivy-*`` → the model flagged ``is_kivy_fast_model``,
    ``lpai-*`` → ``is_lpai_fast_model``, anything else (including unset) →
    ``is_other_fast_model``.

    The flags live on ModelBaseConfig (see model_base_config) and are
    remotely controllable via Apollo. Falls back to the built-in
    deepseek-v4-flash defaults when no flagged model exists (e.g.
    user-defined model settings replaced the built-in list).
    """
    if user_model and user_model.startswith("kivy-"):
        flag, fallback = "is_kivy_fast_model", _INTERNAL_FAST_MODEL_KIVY
    elif user_model and user_model.startswith("lpai-"):
        flag, fallback = "is_lpai_fast_model", _INTERNAL_FAST_MODEL_KIVY
    else:
        flag, fallback = "is_other_fast_model", _INTERNAL_FAST_MODEL_BAIDU

    from siada.models.model_base_config import get_model_settings

    for config in get_model_settings():
        if getattr(config, flag):
            return config.model_name
    return fallback


def _get_fast_model_and_provider() -> Tuple[str, str, Dict[str, Any]]:
    """Return ``(model_name, provider_name, call_kwargs)`` for fast LLM tasks.

    Resolution order:

    1. ``fast_llm_config`` in conf.yaml (explicit override) → the configured
       model / provider; ``base_url`` / ``api_key`` / ``extra_headers`` from
       that section are returned in ``call_kwargs`` for direct completion
       calls (``fast_completion``). ``fast_llm_config.model`` is required —
       a section without it is ignored with a warning.
    2. Internal build (``li`` provider registered) → fast model on the same
       gateway family as the user's main model.
    3. Open-source build → same model / provider as the user's normal config.
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

    try:
        get_provider(_INTERNAL_PROVIDER)
        user_model, _ = _get_user_llm_config()
        return _get_internal_fast_model(user_model), _INTERNAL_PROVIDER, {}
    except ValueError:
        pass

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

    model_name, provider_name, override_kwargs = _get_fast_model_and_provider()
    client = get_client(provider_name)

    call_kwargs = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    # Explicit per-call kwargs (kwargs) take precedence over the conf.yaml
    # fast_llm_config override (override_kwargs).
    call_kwargs.update(override_kwargs)
    call_kwargs.update(kwargs)

    logger.info(
        f"[fast-llm] fast_completion -> model={model_name} "
        f"provider={provider_name}"
    )
    with agent_name_scope(agent_name):
        return await client.completion(**call_kwargs)
