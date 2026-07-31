
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from litellm.types.utils import ModelResponse as LitellmModelResponse


class LLMClient(ABC):

    @abstractmethod
    async def completion(self, **kwargs) -> LitellmModelResponse:
        pass
