from agents import Model, ModelProvider
from agents.extensions.models.litellm_model import LitellmModel


def covert_to_openrouter_model_name(model_name: str) -> str:
    temp_model_name = model_name
    if model_name.startswith("claude-"):
        temp_model_name = model_name.replace("claude-", "anthropic/claude-")
    elif model_name.startswith("deepseek-"):
        if model_name == "deepseek-v3-0324":
            temp_model_name = "deepseek-chat-v3-0324"
        temp_model_name = temp_model_name.replace("deepseek-", "deepseek/deepseek-")
    elif model_name.startswith("o3-"):
        temp_model_name = model_name.replace("o3-", "openai/o3-")
    elif model_name.startswith("gpt-"):
        temp_model_name = model_name.replace("gpt-", "openai/gpt-")
    return temp_model_name


class OpenRouterProvider(ModelProvider):
    """implementation of ModelProvider for OpenRouter by litellm"""

    def get_model(self, model_name: str | None) -> Model:
        """Get a model by name.

        Args:
            model_name: The name of the model to get.

        Returns:
            The model.
        """

        covert_model_name = "openrouter/" + covert_to_openrouter_model_name(model_name)
        return LitellmModel(model=covert_model_name)
