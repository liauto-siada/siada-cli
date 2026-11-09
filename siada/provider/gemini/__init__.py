from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .gemini_model import GeminiModel


def __getattr__(name: str):
    if name == "GeminiModel":
        from .gemini_model import GeminiModel

        return GeminiModel
    raise AttributeError(name)

__all__ = ["GeminiModel"]
