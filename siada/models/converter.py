from agents import ModelSettings
from litellm import Reasoning
from siada.models.model_run_config import ModelRunConfig


class ModelSettingsConverter:

    @staticmethod
    def convert_model_settings(model_running_config: ModelRunConfig) -> ModelSettings:

        extra_body = {}
        if model_running_config.get_reasoning_effort() is not None:
            extra_body["effort"] = model_running_config.get_reasoning_effort()
        if model_running_config.get_thinking_tokens is not None:
            extra_body["max_tokens"] = model_running_config.get_thinking_tokens()

        model_settings = ModelSettings(
            reasoning=Reasoning(
                effort=model_running_config.reasoning_effort,
            ),
            extra_body=extra_body,
        )

        return model_settings
