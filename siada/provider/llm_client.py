

from litellm.types.utils import ModelResponse as LitellmModelResponse
from abc import ABC, abstractmethod


class LLMClient(ABC):

    @abstractmethod
    def completion(self, **kwargs) -> LitellmModelResponse:
        pass