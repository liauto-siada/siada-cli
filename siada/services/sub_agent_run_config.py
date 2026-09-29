"""
Shared RunConfig builder for sub-agents.

Both run_subtask and smart_memory_search launch sub-agents from inside a tool
call. They need to build a RunConfig from the parent CodeAgentContext rather
than from a RunningSession (the SiadaRunner path). This module provides a
single implementation they can both reuse.
"""
import copy
import logging
from typing import Optional

from agents import RunConfig

from siada.foundation.code_agent_context import CodeAgentContext
from siada.models.model_setting_converter import ModelSettingsConverter
from siada.provider.provider_factory import get_provider, resolve_provider_by_model
from siada.services.input_processor import process_input
from siada.services.model_wrapper import ModelProviderWrapper

logger = logging.getLogger(__name__)


def resolve_sub_agent_llm_config(context: CodeAgentContext):
    """Resolve the effective LLM config for sub-agents launched from ``context``.

    Priority:
      1. conf.yaml ``sub_agent.llm_config.model`` (when set and different from
         the parent's model)
      2. The parent agent's session llm_config (original behaviour)

    Extracted from ``build_sub_agent_run_config`` so other call sites that must
    know the sub-agent's model *before* the run starts (e.g. adapting forked
    tool lists) resolve it exactly the same way.
    """
    parent_llm = context.session.siada_config.llm_config

    llm_config = parent_llm
    try:
        from siada.config.config_loader import load_conf
        conf = load_conf()
        sub_llm = conf.sub_agent_config.llm_config
        if sub_llm and sub_llm.model and sub_llm.model != parent_llm.model_name:
            from siada.models.model_run_config import ModelRunConfig
            mrc = ModelRunConfig(sub_llm.model)
            mrc.provider = resolve_provider_by_model(sub_llm.model, sub_llm.provider)
            llm_config = mrc
    except Exception as e:
        logger.warning("[resolve_sub_agent_llm_config] failed to read sub_agent conf: %s", e)

    return llm_config


def adapt_fork_tools_for_effective_model(tools: list | None, model_name: str | None) -> list | None:
    """Adapt an inherited (forked) tool list to the effective sub-agent model.

    Forked sub-agents inherit the parent's tool list verbatim so the request
    prefix stays cache-aligned.  When the sub-agent runs on a different model
    that does not speak the native Responses apply_patch protocol (anything
    outside GPT-5-or-newer / Astra), the inherited ``ApplyPatchTool`` fails
    ChatCompletions tool conversion outright ("Hosted tools are not supported
    with the ChatCompletions API").  In that case -- and only then -- replace
    it with the regular ``edit`` function tool so the sub-agent keeps a working
    file-editing surface.

    Same-model forks (the common, cache-aligned case) and model names that
    cannot be classified are returned untouched, so this helper is a no-op
    unless the situation actually calls for it.
    """
    if not tools or not model_name:
        return tools

    try:
        from siada.agent_hub.coder.prompt.base.gpt5_instructions import (
            uses_native_patch_file_tools,
        )

        if uses_native_patch_file_tools(model_name):
            return tools

        from siada.tools.coder.native_file_tools import NativeApplyPatchTool
        from siada.tools.coder.file_operator import edit
    except Exception as e:
        logger.warning("[adapt_fork_tools_for_effective_model] skipped: %s", e)
        return tools

    has_native_patch = any(isinstance(tool, NativeApplyPatchTool) for tool in tools)
    if not has_native_patch:
        return tools

    has_edit = any(
        tool is edit or getattr(tool, "name", None) == "edit_file" for tool in tools
    )

    adapted: list = []
    replaced = False
    for tool in tools:
        if isinstance(tool, NativeApplyPatchTool):
            # Keep one editing tool: either the inherited ``edit_file`` (if
            # already present) or a swapped-in ``edit``.
            if not replaced and not has_edit:
                adapted.append(edit)
                replaced = True
            continue
        adapted.append(tool)

    logger.info(
        "[adapt_fork_tools_for_effective_model] model=%s cannot consume native "
        "apply_patch items; replaced NativeApplyPatchTool with edit_file "
        "(tools %d -> %d)",
        model_name, len(tools), len(adapted),
    )
    return adapted


def _model_override_llm_config(model_name: str, base_llm_config):
    """Build the effective LLM config for a definition-specified model.

    The provider always follows ``base_llm_config`` — the provider this spawn
    would use anyway (conf.yaml ``sub_agent.llm_config.provider`` when set, the
    parent's provider otherwise) — so switching the model never switches the
    gateway.

    Returns None when *model_name* is not in the model catalog: the override is
    then ignored by the caller, so the run keeps the configured sub-agent model
    (with a warning) instead of silently falling back to a default model.
    """
    from siada.models.model_base_config import get_model_config
    from siada.models.model_run_config import ModelRunConfig

    if get_model_config(model_name) is None:
        logger.warning(
            "[build_sub_agent_run_config] agent definition model '%s' is not a "
            "known model; ignoring the override",
            model_name,
        )
        return None

    llm_config = ModelRunConfig(model_name)
    llm_config.provider = resolve_provider_by_model(
        model_name, base_llm_config.provider
    )
    return llm_config


def _with_reasoning_effort(llm_config, effort: str):
    """Return a copy of ``llm_config`` carrying the requested reasoning effort.

    The copy matters: ``resolve_sub_agent_llm_config`` normally hands back the
    parent session's own ``ModelRunConfig`` object, and mutating it would leak
    the sub-agent's effort setting into every later parent turn.
    """
    from siada.services.agents.runtime import resolve_effort_for_model

    effective = copy.copy(llm_config)
    coerced = resolve_effort_for_model(
        effort,
        effective.model_name,
        getattr(effective, "default_reasoning_effort", None),
    )
    if coerced:
        effective.set_reasoning_effort(coerced)
        logger.info(
            "[build_sub_agent_run_config] effort '%s' -> '%s' for model %s",
            effort,
            coerced,
            effective.model_name,
        )
    return effective


def build_sub_agent_run_config(
    context: CodeAgentContext,
    effort: Optional[str] = None,
    model: Optional[str] = None,
) -> RunConfig:
    """Build a RunConfig for a sub-agent launched from inside a tool call.

    Reads LLM configuration using the following priority:
      1. user-defined agent definition model (``model`` argument, from the
         ``.agents/agents/*.md`` ``model`` field)
      2. conf.yaml sub_agent.llm_config.model
      3. Parent agent's session llm_config (original behaviour)

    Args:
        context: The parent agent's CodeAgentContext. Must have an active session.
        effort: Optional reasoning-effort level requested by a user-defined agent
            definition (``.agents/agents/*.md`` ``effort`` field). The level is
            mapped onto the levels the effective sub-agent model accepts, and
            applied to a copy of the resolved LLM config so the parent session's
            own /effort setting is never mutated.
        model: Optional model override requested by a user-defined agent
            definition (``.agents/agents/*.md`` ``model`` field). Takes
            precedence over the conf.yaml sub-agent model; an unknown model
            name is ignored with a warning, keeping the configured model.

    Returns:
        RunConfig ready to pass to Runner.run / Runner.run_streamed.

    Raises:
        ValueError: If context or context.session is None.
    """
    if not context or not context.session:
        raise ValueError(
            "[build_sub_agent_run_config] An active session is required. "
            "This function must be called from within a running agent tool."
        )

    llm_config = resolve_sub_agent_llm_config(context)

    if model and model != llm_config.model_name:
        override = _model_override_llm_config(model, llm_config)
        if override is not None:
            llm_config = override

    if effort:
        llm_config = _with_reasoning_effort(llm_config, effort)

    model_settings = ModelSettingsConverter.convert_model_settings(llm_config)
    model_provider = get_provider(
        resolve_provider_by_model(llm_config.model_name, llm_config.provider)
    )
    provider_wrapper = ModelProviderWrapper(
        base_provider=model_provider,
        input_processor=process_input,
    )

    return RunConfig(
        tracing_disabled=context.session.siada_config.tracing_disabled,
        model=llm_config.model_name,
        model_provider=provider_wrapper,
        model_settings=model_settings,
        workflow_name="SubTaskAgent",
    )
