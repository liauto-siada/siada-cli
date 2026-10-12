"""
Model configuration helpers for the CLI entrypoint.
"""
import json
import os
from dataclasses import fields
from types import SimpleNamespace
from typing import Optional

from siada.config.config_loader import Config
from siada.foundation.logging import logger
from siada.models.model_run_config import ModelRunConfig


def get_api_key_provider_models(provider_id: str, selected_model: str, base_url: str = '') -> list:
    """Load provider models, falling back to the selected model on cache errors.

    The emergency fallback does not infer model-family capabilities; the
    gateway uses its own defaults when metadata cannot be loaded.
    """
    from siada.provider.models_dev import get_provider_model_configs

    try:
        return get_provider_model_configs(provider_id, selected_model, base_url)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        logger.warning(
            "[model_setup] Unable to load provider model configs; "
            "falling back if a model is selected: %s",
            exc,
        )
    if selected_model:
        from siada.models.model_base_config import ModelBaseConfig

        return [ModelBaseConfig(
            model_name=selected_model,
            context_window=128_000,
            max_tokens=8192,
            parallel_tool_calls=True,
        )]
    return []


def _user_model_settings(model_config) -> list:
    """Convert user model entries while preserving all shared configuration fields."""
    from siada.models.model_base_config import ModelBaseConfig

    return [
        ModelBaseConfig(**{
            field.name: getattr(model, field.name)
            for field in fields(ModelBaseConfig)
            if hasattr(model, field.name)
        })
        for model in model_config.models
    ]


def merge_provider_models_into_user_settings(provider_models: list) -> None:
    """Add provider-catalogue models without replacing the user's models.json.

    ``models.json`` is authoritative
    for the models it defines: a catalogue entry for the same model may carry
    different defaults and no custom thinking budgets / prices, so an existing
    entry is never replaced. Only models the user catalogue does not know yet
    are appended — which is also what lets a selected ``--model`` resolve later
    in the same session. Nothing is written back to disk.

    Shared by the login flow (``siadahub._apply_login``), the default-provider
    pre-load in ``get_config`` and ``/configure`` so all three keep the same
    "merge, never replace" semantics.
    """
    from siada.models import model_base_config

    existing = model_base_config._user_model_settings
    if existing is None:
        # A session can switch to the default provider after startup without
        # having loaded models.json yet. Preserve that catalogue as well.
        from siada.config.model_config import load_user_model_config

        user_config = load_user_model_config()
        if user_config is None:
            model_base_config.set_user_model_settings(provider_models)
            return
        existing = _user_model_settings(user_config)
        model_base_config.set_user_model_settings(existing)

    existing_names = {model.model_name for model in existing}
    for provider_model in provider_models:
        if provider_model.model_name not in existing_names:
            existing.append(provider_model)
            existing_names.add(provider_model.model_name)


def _pre_load_default_provider_models(conf: Optional[Config], model_name: str) -> None:
    """Pre-populate model settings from stored default-provider config in conf.yaml.

    Called when get_config() encounters provider='default' but the model is not
    yet in model settings (e.g. on the second launch, before _apply_login runs).
    If models_dev has entries for the stored provider_id, they are loaded so that
    configure_model_settings() can succeed without waiting for _apply_login.

    Loading goes through ``merge_provider_models_into_user_settings``: a
    models.json catalogue already loaded for this session keeps its custom
    fields (thinking budgets, prices, …) and only gains missing models.
    """
    try:
        provider_id: str = ''
        base_url: str = ''
        if conf and conf.llm_config:
            # provider_id may not be a declared field on LLMConfig but is written
            # to conf.yaml by login_prompt._save_provider_config(); use getattr.
            provider_id = getattr(conf.llm_config, 'provider_id', '') or ''
            base_url = getattr(conf.llm_config, 'base_url', '') or ''

        provider_models = get_api_key_provider_models(provider_id, model_name, base_url)
        if provider_models:
            merge_provider_models_into_user_settings(provider_models)
            logger.info(
                f"[model_setup] Pre-loaded {len(provider_models)} model(s) for "
                f"provider_id={provider_id!r} (default provider, second launch)"
            )
    except Exception as exc:
        logger.debug(f"[model_setup] _pre_load_default_provider_models failed: {exc}")


def get_config(args, io, conf: Optional[Config] = None) -> ModelRunConfig:
    """
    Configure and create model instance.

    Priority: args > config file > defaults.
    Raises ValueError on invalid configuration.
    """
    logger.debug("Entering get_config function")
    config = ModelRunConfig.get_default_config()
    logger.debug(f"Default config loaded: {config.model_name}")

    final_model = args.model or (conf.llm_config.model if conf and conf.llm_config else None)
    final_provider = args.provider or (conf.llm_config.provider if conf and conf.llm_config else None)
    # Save the user's explicitly configured provider before any auto-routing.
    # Used to re-resolve provider if the model falls back to a different model family.
    user_preferred_provider = final_provider

    # Resolve provider overrides while preserving the user's selected endpoint.
    from siada.provider.provider_factory import resolve_provider_by_model
    resolved_provider = resolve_provider_by_model(final_model, final_provider)
    if resolved_provider != final_provider:
        logger.info(
            f"[model_setup] Auto-routing model {final_model!r} to provider "
            f"{resolved_provider!r} (was {final_provider!r})"
        )
        final_provider = resolved_provider

    logger.debug(f"Final model: {final_model}, Final provider: {final_provider}")

    # If provider is 'default', load user-defined model configurations
    if final_provider == "default" and conf and conf.model_config:
        logger.info("Loading user-defined model configurations for 'default' provider")
        from siada.models.model_base_config import set_user_model_settings

        user_models = _user_model_settings(conf.model_config)
        logger.debug(f"Loaded {len(user_models)} user-defined models")
        set_user_model_settings(user_models)

        if final_model is None and conf.model_config.default_model:
            final_model = conf.model_config.default_model
            logger.info(f"Using default model from user configuration: {final_model}")
            if args.verbose:
                io.print_info(f"Using default model from user configuration: {final_model}")

    if final_model is not None:
        logger.info(f"Configuring model: {final_model}")
        config.model_name = final_model
        try:
            config.configure_model_settings(config.model_name)
        except ValueError:
            if final_provider == "default":
                # For 'default' provider, model settings are populated later in
                # _apply_login() via get_api_key_provider_models(). Try to pre-load
                # them here from the stored conf so the second launch doesn't fail.
                _pre_load_default_provider_models(conf, final_model)
                try:
                    config.configure_model_settings(config.model_name)
                except ValueError:
                    # Still not found — this is fine; _apply_login will add the
                    # model to settings after the provider is confirmed.
                    logger.warning(
                        f"Model {final_model!r} not yet in model settings "
                        f"(default provider); will be configured after login."
                    )
            else:
                raise

        # If the model was silently replaced by a fallback, re-resolve the provider
        # using the user's original preferred provider so the fallback model gets
        # a provider consistent with the user's configured endpoint.
        if config.model_name != final_model:
            re_resolved = resolve_provider_by_model(config.model_name, user_preferred_provider)
            if re_resolved != final_provider:
                logger.info(
                    f"[model_setup] Re-routing fallback model {config.model_name!r} "
                    f"to provider {re_resolved!r} (was {final_provider!r})"
                )
                final_provider = re_resolved

    if final_provider is not None:
        logger.info(f"Setting provider: {final_provider}")
        config.provider = final_provider

    # Persist the resolved provider for the shared request callbacks.
    try:
        from siada.entrypoint import set_current_provider
        set_current_provider(config.provider or "")
    except Exception:
        pass

    if config.provider is None:
        error_msg = "No provider specified. Please set provider in agent_config.yaml or use --provider option"
        logger.error(error_msg)
        io.print_error(error_msg)
        raise ValueError(error_msg)

    if config.provider == "default":
        # Pre-load credentials from conf.yaml into env. Do NOT raise when they
        # are missing: the interactive login flow runs after get_config() and
        # collects base_url/api_key there (API-key-only fallback).
        if conf and conf.llm_config:
            for name, field_name in (
                ("BASE_URL", "base_url"),
                ("API_KEY", "api_key"),
            ):
                value = getattr(conf.llm_config, field_name, None)
                if isinstance(value, str) and value.strip() and not (os.getenv(name) or "").strip():
                    os.environ[name] = value.strip()
        if not (os.getenv("BASE_URL") or "").strip() or not (os.getenv("API_KEY") or "").strip():
            logger.info(
                "BASE_URL/API_KEY not set for default provider yet; "
                "the login flow will collect them interactively."
            )

    if args.reasoning_effort is not None:
        if (
            not config.supports_extra_params
            or "reasoning_effort" not in config.supports_extra_params
        ):
            error_msg = f"Model {config.model_name} does not support reasoning effort"
            logger.error(error_msg)
            io.print_error(error_msg)
            raise ValueError(error_msg)
        config.set_reasoning_effort(args.reasoning_effort)
        logger.info(f"Reasoning effort set to: {args.reasoning_effort}")
    elif conf and conf.llm_config and conf.llm_config.reasoning_effort is not None:
        # reasoning_effort: CLI > conf.yaml > model default
        if (
            not config.supports_extra_params
            or "reasoning_effort" not in config.supports_extra_params
        ):
            error_msg = f"Model {config.model_name} does not support reasoning effort"
            logger.error(error_msg)
            io.print_error(error_msg)
            # raise ValueError(error_msg)
        # conf.yaml is model-agnostic: map the persisted intent onto the
        # levels the startup model accepts (e.g. "xhigh" set on Claude must
        # become "max" when the startup model is a GLM-5.3).
        from siada.models.model_base_config import coerce_reasoning_effort
        mapped_effort = coerce_reasoning_effort(
            config.model_name,
            conf.llm_config.reasoning_effort,
            config.default_reasoning_effort,
        )
        config.set_reasoning_effort(mapped_effort)
        # Record the ORIGINAL intent (not the mapped level) so in-session
        # model switches keep mapping from the user's chosen level.
        config.user_reasoning_effort = conf.llm_config.reasoning_effort
        if mapped_effort != conf.llm_config.reasoning_effort:
            logger.info(
                f"Reasoning effort set from conf.yaml: {conf.llm_config.reasoning_effort} "
                f"(mapped to {mapped_effort} for {config.model_name})"
            )
        else:
            logger.info(f"Reasoning effort set from conf.yaml: {conf.llm_config.reasoning_effort}")

    # thinking_tokens: CLI > conf.yaml > model default
    # Note: conf.yaml uses `enable_thinking` (the actual API param name for
    # OpenAI-provider models like v4 flash) as the primary key; `thinking` is
    # kept as a legacy alias. `false` disables thinking, `true`/unset keeps the
    # model default (which for v4 flash is default_thinking_tokens -> enable_thinking).
    conf_thinking = conf.llm_config.enable_thinking if conf and conf.llm_config and conf.llm_config.enable_thinking is not None else (conf.llm_config.thinking if conf and conf.llm_config else None)
    if args.thinking is False:
        config.thinking_tokens = None
        config.enable_thinking = False
        logger.info("Thinking/reasoning disabled by CLI flag (--no-thinking)")
    elif args.thinking is True:
        config.enable_thinking = True
    elif conf_thinking is not None:
        config.enable_thinking = conf_thinking
        if not conf_thinking:
            config.thinking_tokens = None
            logger.info("Thinking/reasoning disabled by conf.yaml setting (enable_thinking)")

    # parallel_tool_calls: CLI > conf.yaml > model default
    if args.parallel_tool_calls is False:
        config.parallel_tool_calls = False
        logger.info("Parallel tool calls disabled by CLI flag (--no-parallel-tool-calls)")
    elif args.parallel_tool_calls is True:
        pass
    elif conf and conf.llm_config and conf.llm_config.parallel_tool_calls is not None:
        config.parallel_tool_calls = conf.llm_config.parallel_tool_calls
        if not config.parallel_tool_calls:
            logger.info("Parallel tool calls disabled by conf.yaml setting")

    if args.verbose:
        io.print_info("Model settings:")
        for attr in sorted(fields(ModelRunConfig), key=lambda x: x.name):
            value = getattr(config, attr.name)
            val_str = "None" if value is None else json.dumps(value, indent=4)
            io.print_info(f"{attr.name}: {val_str}")

    return config


def get_config_from_conf(io, conf: Optional[Config] = None) -> ModelRunConfig:
    """Build model config from conf only, reusing the CLI config resolution logic."""
    args = SimpleNamespace(
        model=None,
        provider=None,
        verbose=False,
        reasoning_effort=None,
        thinking=None,
        parallel_tool_calls=None,
    )
    return get_config(args, io, conf)
