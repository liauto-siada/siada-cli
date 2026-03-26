"""
Shared RunConfig builder for sub-agents.

Both run_subtask and smart_memory_search launch sub-agents from inside a tool
call. They need to build a RunConfig from the parent CodeAgentContext rather
than from a RunningSession (the SiadaRunner path). This module provides a
single implementation they can both reuse.
"""
from agents import RunConfig

from siada.foundation.code_agent_context import CodeAgentContext
from siada.models.model_setting_converter import ModelSettingsConverter
from siada.provider.provider_factory import get_provider
from siada.services.input_processor import process_input
from siada.services.model_wrapper import ModelProviderWrapper


def build_sub_agent_run_config(context: CodeAgentContext) -> RunConfig:
    """Build a RunConfig for a sub-agent launched from inside a tool call.

    Reads LLM configuration directly from the parent agent's session, which is
    always available when a tool is executing. Does not rely on LLM_CONFIG
    context variables.

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

    llm_config = context.session.siada_config.llm_config
    model_settings = ModelSettingsConverter.convert_model_settings(llm_config)
    model_provider = get_provider(llm_config.provider)
    provider_wrapper = ModelProviderWrapper(
        base_provider=model_provider,
        input_processor=process_input,
    )

    return RunConfig(
        tracing_disabled=context.session.siada_config.tracing_disabled,
        model=llm_config.model_name,
        model_provider=provider_wrapper,
        model_settings=model_settings,
    )
