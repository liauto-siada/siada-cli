from __future__ import annotations
from typing import TYPE_CHECKING

from agents import Model, ModelProvider

from siada.provider.llm_client import LLMClient
from siada.provider.openrouter.coverter import covert_to_openrouter_model_name
from siada.provider.reasoning_replay import should_replay_reasoning_content

if TYPE_CHECKING:
    from litellm.types.utils import ModelResponse as LitellmModelResponse


class OpenRouterProvider(ModelProvider):
    """implementation of ModelProvider for OpenRouter by litellm"""
    def get_model(self, model_name: str | None) -> Model:
        """Get a model by name.

        Args:
            model_name: The name of the model to get.

        Returns:
            The model.
        """
        from siada.entrypoint import _configure_litellm
        _configure_litellm()
        from agents.extensions.models.litellm_model import LitellmModel
        covert_model_name = covert_to_openrouter_model_name(model_name)
        return LitellmModel(
            model=covert_model_name,
            should_replay_reasoning_content=should_replay_reasoning_content,
        )


class OpenRouterClient(LLMClient):

    async def completion(self, **kwargs) -> LitellmModelResponse:
        import litellm
        model = kwargs.get("model")
        kwargs["model"] = covert_to_openrouter_model_name(model)
        # Use litellm's native async method for better performance
        return await litellm.acompletion(**kwargs)
