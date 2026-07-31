"""
Shared RunConfig builder for sub-agents.

Both run_subtask and smart_memory_search launch sub-agents from inside a tool
call. They need to build a RunConfig from the parent CodeAgentContext rather
than from a RunningSession (the SiadaRunner path). This module provides a
single implementation they can both reuse.
"""
import logging

from agents import RunConfig

from siada.foundation.code_agent_context import CodeAgentContext
from siada.models.model_setting_converter import ModelSettingsConverter
from siada.provider.provider_factory import get_provider, resolve_provider_by_model
from siada.services.input_processor import process_input
from siada.services.model_wrapper import ModelProviderWrapper

logger = logging.getLogger(__name__)


def build_sub_agent_run_config(context: CodeAgentContext) -> RunConfig:
    """Build a RunConfig for a sub-agent launched from inside a tool call.

    Reads LLM configuration using the following priority:
      1. conf.yaml sub_agent.llm_config.model
      2. Parent agent's session llm_config (original behaviour)

    Args:
        context: The parent agent's CodeAgentContext. Must have an active session.

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

    parent_llm = context.session.siada_config.llm_config

    # Check conf.yaml sub_agent.llm_config
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
        logger.warning("[build_sub_agent_run_config] failed to read sub_agent conf: %s", e)

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
