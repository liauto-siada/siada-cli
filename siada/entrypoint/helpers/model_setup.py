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
    """Return a ModelBaseConfig list for the given provider from the models_dev cache."""
    try:
        from siada.provider.models_dev import get_provider_model_configs
        return get_provider_model_configs(provider_id, selected_model, base_url)
    except Exception:
        pass
    if selected_model:
        from siada.models.model_base_config import ModelBaseConfig
        return [ModelBaseConfig(
            model_name=selected_model,
            context_window=128_000,
            max_tokens=8192,
            parallel_tool_calls=True,
        )]
    return []


def _pre_load_default_provider_models(conf: Optional[Config], model_name: str) -> None:
    """Pre-populate model settings from stored default-provider config in conf.yaml.

    Called when get_config() encounters provider='default' but the model is not
    yet in model settings (e.g. on the second launch, before _apply_login runs).
    If models_dev has entries for the stored provider_id, they are loaded so that
    configure_model_settings() can succeed without waiting for _apply_login.
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
            from siada.models.model_base_config import set_user_model_settings
            set_user_model_settings(provider_models)
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

    # Resolve the provider for the model (handles legacy keys like
    # "openai_agents" -> "li").
    # This dilutes the user-facing "provider" concept: users only need to pick the model.
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
        from siada.models.model_base_config import set_user_model_settings, ModelBaseConfig

        user_models = []
        for user_model in conf.model_config.models:
            user_models.append(ModelBaseConfig(
                model_name=user_model.model_name,
                context_window=user_model.context_window,
                max_tokens=user_model.max_tokens,
                supports_images=user_model.supports_images,
                supports_vision_bridge=user_model.supports_vision_bridge,
                supports_prompt_cache=user_model.supports_prompt_cache,
                supports_extra_params=user_model.supports_extra_params,
                parallel_tool_calls=user_model.parallel_tool_calls,
                default_thinking_tokens=user_model.default_thinking_tokens,
                default_reasoning_effort=user_model.default_reasoning_effort,
                input_price=user_model.input_price,
                output_price=user_model.output_price,
                cache_write_price=user_model.cache_write_price,
                cache_read_price=user_model.cache_read_price,
            ))

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
        # a correct provider (e.g. unknown-gpt5-x falls back to kivy-kimi-k3 → li).
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

    # Persist the resolved provider so the litellm token-refresh callback can
    # determine whether IDaaS auth should be skipped (e.g. for 'default' provider).
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
            if os.getenv("BASE_URL") is None:
                base_url = getattr(conf.llm_config, "base_url", None)
                if base_url:
                    os.environ["BASE_URL"] = base_url
            if os.getenv("API_KEY") is None:
                api_key = getattr(conf.llm_config, "api_key", None)
                if api_key:
                    os.environ["API_KEY"] = api_key
        if os.getenv("BASE_URL") is None or os.getenv("API_KEY") is None:
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
