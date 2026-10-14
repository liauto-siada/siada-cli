"""
Fast LLM helpers for memory-related LLM calls.

Lightweight tasks (session naming, MemoryAgent, summaries…) don't need the main
agent's flagship model.  This module wraps:

* direct SDK model requests (used by ``MemoryService._generate_slug_via_llm``)
* provider ``RunConfig`` (used by ``MemoryAgent``; with a ``fast_llm_config``
  override the fast Model instance travels on ``RunConfig.model`` instead of
  being resolved from ``RunConfig.model_provider`` at run time)

Model / provider resolution (``_get_fast_model_and_provider``):
  * ``fast_llm_config`` in ``~/.siada-cli/conf.yaml`` (explicit override) →
    the configured model / provider / base_url / api_key / extra_headers,
    e.g. routing fast tasks to a cheaper endpoint than the main model.
    ``fast_llm_config.model`` is required for the override to apply.
    The override is honoured on BOTH fast paths: ``fast_completion`` passes
    ``api_base`` / ``api_key`` / ``extra_headers`` per call, and
    ``build_fast_run_config`` builds the Model with the provider's explicit
    credentials + puts the headers on ``ModelSettings``. Missing fields fall
    back to the main environment (a partial override is still an override).
    Override credentials only ever ride on the built Model / per-call kwargs —
    they are never written to process-global env vars (``DefaultClient`` /
    ``DefaultProvider`` pass them explicitly), so a concurrent main-endpoint
    request keeps its own endpoint and key.
    An override is never dropped silently: a provider that cannot accept
    explicit credentials raises ``ValueError``, and so does ``get_fast_model``
    when the override carries ``extra_headers`` (a bare Model has no
    ``ModelSettings`` channel to carry them).
  * Otherwise the same model / provider as the user's normal config
    (``llm_config`` in ``~/.siada-cli/conf.yaml``) — i.e. the OpenAI-compatible
    endpoint the user configured with their own API key; behaviour is the
    pre-existing ``get_model`` / ``ModelProviderWrapper`` path.

Everything here is local to these lightweight paths — the main agent's model
choice is untouched. Background runs built here also disable tracing (see
``build_fast_run_config``) so session transcripts are not exported.
"""

from typing import Any, Dict, Optional, Tuple

from agents import Model, ModelResponse, RunConfig

from siada.foundation.logging import logger
from siada.models.model_run_config import ModelRunConfig
from siada.models.model_setting_converter import ModelSettingsConverter
from siada.provider.provider_factory import get_provider
from siada.services.input_processor import process_input
from siada.services.model_wrapper import ModelProviderWrapper, ModelWrapper


# Provider this build ships: the OpenAI-compatible endpoint configured in
# conf.yaml (custom base URL + API key). Used for the ``fast_llm_config``
# override default and as the resolution for any provider name this build
# cannot serve.
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


def _resolve_provider(candidate: Optional[str]) -> str:
    """Return a provider name this build can actually serve.

    Only the user-endpoint provider (``default``) is registered here, so a name
    that is unavailable — a leftover key from another distribution, a typo, or
    an unset value — resolves to ``default`` instead of failing later inside
    provider/model construction.
    """
    if candidate and candidate != _DEFAULT_OVERRIDE_PROVIDER:
        try:
            get_provider(candidate)
            return candidate
        except ValueError:
            logger.info(
                "[fast-llm] provider %r is not available in this build; "
                "using %r (user-configured endpoint)",
                candidate,
                _DEFAULT_OVERRIDE_PROVIDER,
            )
    return _DEFAULT_OVERRIDE_PROVIDER


def _get_fast_model_and_provider() -> Tuple[str, str, Dict[str, Any]]:
    """Return ``(model_name, provider_name, call_kwargs)`` for fast LLM tasks.

    Resolution order:

    1. ``fast_llm_config`` in conf.yaml (explicit override) → the configured
       model / provider; ``base_url`` / ``api_key`` / ``extra_headers`` from
       that section are returned in ``call_kwargs``. Callers must apply them:
       ``fast_completion`` merges them into the per-call litellm kwargs (where
       the endpoint parameter is ``api_base``), while ``get_fast_model`` /
       ``build_fast_run_config`` pass them to the provider's explicit-credential
       model builder (where the endpoint parameter is ``base_url``).
       ``fast_llm_config.model`` is required — a section without it is ignored
       with a warning.
    2. Otherwise the user's normal config: the same model / provider the main
       agent runs on (custom endpoint + API key).
    """
    override = _get_user_fast_llm_config()
    if override:
        model = override.get("model")
        if model:
            provider = _resolve_provider(
                override.get("provider") or _DEFAULT_OVERRIDE_PROVIDER
            )
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
    return model, _resolve_provider(provider), {}


def get_fast_model_name() -> str:
    """Return the model name that will be used for fast LLM calls."""
    return _get_fast_model_and_provider()[0]


# ---- Model (for openai-agents Runner) ---------------------------------------

def _build_override_model(provider: Any, model_name: str, call_kwargs: Dict[str, Any]) -> Model:
    """Build a ``Model`` carrying the ``fast_llm_config`` override credentials.

    The override may point at a different endpoint / key than the main model —
    that is what it is for — so the Model must be built with those values
    instead of letting the provider read the main endpoint from the
    environment at run time.

    An override is never dropped silently: when credentials are present and the
    provider offers no explicit-credential builder, this raises instead of
    falling back to the main endpoint (which would send the request — and the
    data — to a different place than configured).

    Parameter spelling: ``call_kwargs`` uses LiteLLM's ``api_base`` (correct for
    ``LLMClient.completion``); model construction takes the SDK's ``base_url``.

    ``extra_headers`` is deliberately not consumed here: a ``Model`` has no
    parameter for request headers, so callers must carry them elsewhere
    (``build_fast_run_config`` → ``ModelSettings.extra_headers``,
    ``fast_completion`` → per-call kwargs).
    """
    base_url = call_kwargs.get("api_base")
    api_key = call_kwargs.get("api_key")

    builder = getattr(provider, "get_model_with_credentials", None)
    if builder is None:
        if base_url or api_key:
            raise ValueError(
                "fast_llm_config credentials cannot be applied: provider "
                f"{type(provider).__name__} has no explicit-credential model "
                "builder. Remove base_url/api_key from fast_llm_config or use "
                "the built-in 'default' provider."
            )
        # Headers-only override: credentials stay on the main endpoint, so the
        # ordinary provider path is enough (the headers ride ModelSettings).
        return provider.get_model(model_name)

    return builder(model_name, base_url=base_url, api_key=api_key)


def get_fast_model() -> Model:
    """Return a ``Model`` instance pinned to the fast model.

    With a ``fast_llm_config`` override the model is built with the override
    credentials; without one the provider's usual environment-based
    ``get_model`` is used, unchanged.

    An override carrying ``extra_headers`` is rejected: a bare ``Model`` has no
    ``ModelSettings`` channel to carry request headers, so they would be
    silently dropped and the request would go out without the gateway headers
    the user configured. ``build_fast_run_config`` (ModelSettings) and
    ``fast_completion`` (per-call kwargs) support headers.

    Raises:
        ValueError: when the resolved override carries ``extra_headers``.
    """
    model_name, provider_name, call_kwargs = _get_fast_model_and_provider()
    if call_kwargs.get("extra_headers"):
        raise ValueError(
            "fast_llm_config extra_headers cannot be applied by get_fast_model(): "
            "request headers travel through ModelSettings.extra_headers, which a "
            "bare Model does not carry. Use build_fast_run_config() or "
            "fast_completion() instead."
        )
    provider = get_provider(provider_name)
    if call_kwargs:
        return _build_override_model(provider, model_name, call_kwargs)
    return provider.get_model(model_name)


def build_fast_run_config() -> RunConfig:
    """Build a ``RunConfig`` that forces the fast model.

    Convenience wrapper so MemoryAgent doesn't need to know about model
    settings / provider wiring.

    ``tracing_disabled=True`` on purpose: these runs carry whole session
    transcripts and are started in the background (MemoryAgent, memory review,
    daily summary). With the SDK's default trace export they would be posted to
    ``traces/ingest`` — background memory work must not ship the user's
    transcript there. Main-agent tracing is untouched (it runs with the
    session's own setting/processors, not this config), and nothing here adds
    a new network-export switch.
    """
    model_name, provider_name, call_kwargs = _get_fast_model_and_provider()

    # Build a ModelRunConfig for the fast model so ModelSettings
    # (parallel_tool_calls, max_tokens, …) comes from model_base_config.
    mrc = ModelRunConfig(model_name)
    mrc.provider = provider_name
    # Disable reasoning/thinking — we want this fast.
    mrc.thinking_tokens = None
    mrc.reasoning_effort = None

    model_settings = ModelSettingsConverter.convert_model_settings(mrc)
    base_provider = get_provider(provider_name)

    if call_kwargs:
        # The provider wrapper resolves the model from the environment at run
        # time, which would silently drop the override — build the Model up
        # front and hand the instance to the Runner. The input-processing
        # wrapper travels with it, exactly like
        # ``ModelProviderWrapper.get_model`` would have wrapped it.
        model: Model = ModelWrapper(
            _build_override_model(base_provider, model_name, call_kwargs),
            process_input,
        )
        extra_headers = call_kwargs.get("extra_headers")
        if extra_headers:
            # The LiteLLM model constructor takes only model / base_url /
            # api_key — request headers travel through ModelSettings, which
            # LitellmModel merges into the outgoing headers.
            model_settings.extra_headers = dict(extra_headers)
        logger.info(
            f"[fast-llm] build_fast_run_config → model={model_name} "
            f"provider={provider_name} (fast_llm_config override)"
        )
        return RunConfig(
            tracing_disabled=True,
            model=model,
            model_settings=model_settings,
        )

    provider_wrapper = ModelProviderWrapper(
        base_provider=base_provider,
        input_processor=process_input,
    )

    logger.info(
        f"[fast-llm] build_fast_run_config → model={model_name} "
        f"provider={provider_name}"
    )

    return RunConfig(
        tracing_disabled=True,
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
