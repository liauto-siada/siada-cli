from agents import ModelSettings
from siada.models.model_base_config import is_claude_model, is_gemini_model
from siada.models.model_run_config import ModelRunConfig
from openai.types.shared import Reasoning


class ModelSettingsConverter:

    @staticmethod
    def convert_model_settings(model_running_config: ModelRunConfig) -> ModelSettings:

        extra_body = {}

        # Claude models: produce "thinking" in Anthropic API format directly.
        # Both default provider (litellm) and li provider accept this format.
        # Non-Claude/non-Gemini models: produce "reasoning" for li provider conversion.
        if is_claude_model(model_running_config.model_name):
            if model_running_config.get_raw_thinking_tokens() is not None:
                if (model_running_config.default_thinking_tokens == -1 or
                    model_running_config.get_raw_thinking_tokens() == -1):
                    extra_body["thinking"] = {"type": "adaptive"}
                else:
                    extra_body["thinking"] = {
                        "type": "enabled",
                        "budget_tokens": model_running_config.get_raw_thinking_tokens()
                    }
        elif not is_gemini_model(model_running_config.model_name):
            # Gemini uses reasoning_effort via litellm's thinkingLevel mapping.
            # Other models (OpenAI, DeepSeek, etc.) use "reasoning" for li provider.
            reasoning = {}
            if model_running_config.get_reasoning_effort() is not None:
                reasoning["effort"] = model_running_config.get_reasoning_effort()
            if model_running_config.get_raw_thinking_tokens() is not None:
                if (model_running_config.default_thinking_tokens == -1 or
                    model_running_config.get_raw_thinking_tokens() == -1):
                    reasoning["adaptive"] = True
                else:
                    reasoning["max_tokens"] = model_running_config.get_raw_thinking_tokens()
            if reasoning:
                extra_body["reasoning"] = reasoning

        tool_choice = "auto"
        if model_running_config.extra_params and "tool_choice" in model_running_config.extra_params:
            tool_choice = model_running_config.extra_params["tool_choice"]

        reasoning_item: Reasoning = None
        if is_claude_model(model_running_config.model_name):
            # For Claude, set reasoning effort to "medium" to save the thinking blocks
            if model_running_config.get_raw_thinking_tokens() is not None:
                reasoning_item = Reasoning(effort="medium")
        elif is_gemini_model(model_running_config.model_name):
            # For Gemini 3+, reasoning_effort is mapped to thinkingLevel by litellm
            # (e.g., "low"→"low", "medium"→"medium", "high"→"high")
            effort = model_running_config.get_reasoning_effort()
            if effort is not None:
                reasoning_item = Reasoning(effort=effort)
        model_settings = ModelSettings(
            max_tokens=model_running_config.max_tokens,
            extra_body=extra_body,
            tool_choice=tool_choice,
            parallel_tool_calls=model_running_config.parallel_tool_calls,
            include_usage=True,
            reasoning=reasoning_item,
        )

        return model_settings
