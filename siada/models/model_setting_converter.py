from agents import ModelSettings
from siada.models.model_base_config import is_claude_model, is_gemini_model, is_glm_model
from siada.models.model_run_config import ModelRunConfig
from openai.types.shared import Reasoning


class ModelSettingsConverter:

    @staticmethod
    def convert_model_settings(model_running_config: ModelRunConfig) -> ModelSettings:

        extra_body = {}
        extra_args = {}

        # Claude models: produce "thinking" in Anthropic API format directly.
        # This must be sent via ``extra_args`` (top-level kwarg to litellm),
        # NOT ``extra_body``. litellm's AnthropicConfig only merges "extra_body"
        # content into the request body for OpenAI-compatible custom_llm_providers
        # (openai/azure/...). For "anthropic"/Bedrock-Anthropic providers (used by
        # the default provider's raw litellm call), there is no such unwrap logic,
        # so a literal "extra_body" key would be forwarded as-is into the request
        # body, which the Bedrock/Anthropic gateway rejects with:
        #   "extra_body: Extra inputs are not permitted"
        # "thinking" passed as a top-level kwarg, however, is natively recognized
        # and mapped by litellm's Anthropic transformation for every provider.
        if is_claude_model(model_running_config.model_name):
            if model_running_config.get_raw_thinking_tokens() is not None:
                if (model_running_config.default_thinking_tokens == -1 or
                    model_running_config.get_raw_thinking_tokens() == -1):
                    extra_args["thinking"] = {"type": "adaptive", "display": "summarized"}
                else:
                    extra_args["thinking"] = {
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
                if is_glm_model(model_running_config.model_name):
                    # GLM uses a "thinking" dict in the request body with
                    # clear_thinking=False for preserved thinking. This keeps
                    # reasoning content in responses so it can be replayed across
                    # multi-turn tool-call conversations, improving effectiveness
                    # and cache hit rates.
                    # Works for both li_provider (extra_body flattened to top-level
                    # kwargs, thinking dict passes through as-is) and
                    # default_provider (extra_body merged into request body by
                    # litellm).
                    thinking_config: dict = {"type": "enabled", "clear_thinking": False}
                    if reasoning.get("adaptive"):
                        thinking_config["type"] = "adaptive"
                    extra_body["thinking"] = thinking_config
                else:
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
            extra_body=extra_body or None,
            extra_args=extra_args or None,
            tool_choice=tool_choice,
            parallel_tool_calls=model_running_config.parallel_tool_calls,
            include_usage=True,
            reasoning=reasoning_item,
        )

        return model_settings
