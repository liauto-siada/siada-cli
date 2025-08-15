from agents import Model, ModelProvider
from agents.extensions.models.litellm_model import LitellmModel
import litellm

from siada.provider.llm_client import LLMClient
from litellm.types.utils import ModelResponse as LitellmModelResponse

from siada.provider.openrouter.coverter import covert_to_openrouter_model_name


class OpenRouterProvider(ModelProvider):
    """implementation of ModelProvider for OpenRouter by litellm"""

    def get_model(self, model_name: str | None) -> Model:
        """Get a model by name.

        Args:
            model_name: The name of the model to get.

        Returns:
            The model.
        """

        covert_model_name = covert_to_openrouter_model_name(model_name)
        return LitellmModel(model=covert_model_name)


class OpenRouterClient(LLMClient):

    def completion(self, **kwargs) -> LitellmModelResponse:
        model = kwargs.get("model")
        kwargs["model"] = covert_to_openrouter_model_name(model)
        return litellm.completion(**kwargs)
