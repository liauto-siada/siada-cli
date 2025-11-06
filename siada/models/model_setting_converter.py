from agents import ModelSettings
from siada.models.model_base_config import is_claude_model
from siada.models.model_run_config import ModelRunConfig
from openai.types.shared import Reasoning


class ModelSettingsConverter:

    @staticmethod
    def convert_model_settings(model_running_config: ModelRunConfig) -> ModelSettings:

        extra_body = {}
        reasoning = {}
        if model_running_config.get_reasoning_effort() is not None:
            reasoning["effort"] = model_running_config.get_reasoning_effort()
        if model_running_config.get_raw_thinking_tokens() is not None:
            reasoning["max_tokens"] = model_running_config.get_raw_thinking_tokens()

        if reasoning:
            extra_body["reasoning"] = reasoning

        tool_choice = "auto"
        if model_running_config.extra_params and "tool_choice" in model_running_config.extra_params:
            tool_choice = model_running_config.extra_params["tool_choice"]

        # for the litellm model, we set the reasoning effort to "medium" if not specified to save the thinking blocks
        reasoning_item: Reasoning = None
        if (
            model_running_config.get_raw_thinking_tokens() is not None
            and is_claude_model(model_running_config.model_name)
        ):
            reasoning_item = Reasoning(effort="medium")
        model_settings = ModelSettings(
            max_tokens=model_running_config.max_tokens,
            extra_body=extra_body,
            tool_choice=tool_choice,
            include_usage=True,
            reasoning=reasoning_item,
        )

        return model_settings
