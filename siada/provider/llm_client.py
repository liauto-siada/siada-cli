

from litellm.types.utils import ModelResponse as LitellmModelResponse
from abc import ABC, abstractmethod


class LLMClient(ABC):

    @abstractmethod
    async def completion(self, **kwargs) -> LitellmModelResponse:
        pass
