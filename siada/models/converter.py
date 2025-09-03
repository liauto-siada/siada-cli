from agents import ModelSettings
from siada.models.model_base_config import is_gemini_model
from siada.models.model_run_config import ModelRunConfig


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

        model_settings = ModelSettings(
            max_tokens=model_running_config.max_tokens,
            extra_body=extra_body,
            tool_choice=tool_choice,
        )

        return model_settings
