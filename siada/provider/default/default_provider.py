import os
from agents import Model, ModelProvider
from agents.extensions.models.litellm_model import LitellmModel
import litellm

from siada.entrypoint import _configure_litellm_logging

from siada.provider.default.coverter import covert_to_litellm_model_name
from siada.provider.llm_client import LLMClient
from litellm.types.utils import ModelResponse as LitellmModelResponse


class DefaultProvider(ModelProvider):
    """Implementation of ModelProvider for custom models via litellm
    
    Supports any model compatible with litellm by configuring:
    - BASE_URL: The API base URL
    - API_KEY: The API key for authentication
    - MODEL_NAME: The model name to use (e.g., "openai/gpt-4", "anthropic/claude-3")
    """

    def __init__(self):
        _configure_litellm_logging()

        # Get base_url, api_key and model_name from environment variables
        self.base_url = os.getenv("BASE_URL", None)
        self.api_key = os.getenv("API_KEY", None)

    def get_model(self, model_name: str | None) -> Model:
        """Get a model by name.

        Args:
            model_name: The name of the model to get. If None, uses MODEL_NAME from environment.

        Returns:
            The model.
        """
        # Use provided model_name or fall back to configured model_name
        effective_model_name = covert_to_litellm_model_name(model_name)
        if "deepseek" in effective_model_name:
            os.environ["DEEPSEEK_API_KEY"] = self.api_key

        return LitellmModel(
            model=effective_model_name, base_url=self.base_url, api_key=self.api_key
        )


class DefaultClient(LLMClient):
    """Client for custom LLM API using litellm
    
    Supports any model compatible with litellm by configuring:
    - BASE_URL: The API base URL
    - API_KEY: The API key for authentication
    - MODEL_NAME: The model name to use
    """

    def __init__(self):
        # Get base_url, api_key and model_name from environment variables
        self.base_url = os.getenv("BASE_URL")
        self.api_key = os.getenv("API_KEY")

    async def completion(self, **kwargs) -> LitellmModelResponse:
        """Call LLM API for completion.
        
        Args:
            **kwargs: Arguments to pass to litellm.acompletion
                     Can include 'model' to override the default model
            
        Returns:
            LitellmModelResponse: The completion response
        """
        # Set api_base and api_key if available
        if self.base_url:
            kwargs["api_base"] = self.base_url
        if self.api_key:
            kwargs["api_key"] = self.api_key

        # Use litellm's native async method for better performance
        return await litellm.acompletion(**kwargs)
