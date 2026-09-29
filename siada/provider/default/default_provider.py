from __future__ import annotations
import os
from typing import TYPE_CHECKING

from agents import Model, ModelProvider

from siada.provider.default.coverter import covert_to_litellm_model_name
from siada.provider.default.kimi_tool_ordering import (
    get_kimi_tool_ordering_litellm_model_cls,
)
from siada.provider.llm_client import LLMClient
from siada.provider.reasoning_replay import should_replay_reasoning_content

if TYPE_CHECKING:
    from litellm.types.utils import ModelResponse as LitellmModelResponse


def _register_custom_claude_model(model_name: str):
    """Register custom model names in litellm so supports_reasoning() returns True,
    allowing 'thinking' (Claude) and 'reasoning_effort' (Gemini) params to pass through.
    """
    import litellm
    if model_name in litellm.model_cost:
        return

    lower_name = model_name.lower()
    if "aws-claude" in lower_name or "gemini" in lower_name:
        litellm.register_model({model_name: {"supports_reasoning": True}})


class DefaultProvider(ModelProvider):
    """Implementation of ModelProvider for custom models via litellm
    
    Supports any model compatible with litellm by configuring:
    - BASE_URL: The API base URL
    - API_KEY: The API key for authentication
    - MODEL_NAME: The model name to use (e.g., "openai/gpt-4", "anthropic/claude-3")
    """

    def __init__(self):
        # NOTE:
        # Provider instances are created eagerly by provider_factory at import time.
        # API key login, however, may update BASE_URL/API_KEY later at runtime.
        # So we must not cache credentials only once in __init__.
        self.base_url = None
        self.api_key = None

    def _refresh_credentials(self):
        """Refresh credentials from environment for runtime login / reconfigure flows."""
        self.base_url = os.getenv("BASE_URL", None)
        self.api_key = os.getenv("API_KEY", None)

    def _apply_provider_specific_env(self, effective_model_name: str):
        """Populate provider-specific env vars required by some LiteLLM backends."""
        if not self.api_key:
            return

        if "deepseek" in effective_model_name:
            os.environ["DEEPSEEK_API_KEY"] = self.api_key

        if "moonshot/" in effective_model_name or effective_model_name.startswith("kimi-"):
            os.environ["MOONSHOT_API_KEY"] = self.api_key

    def _ensure_openrouter_prefix(self, model_name: str) -> str:
        """Route model ids through litellm's openrouter provider when BASE_URL is OpenRouter.

        OpenRouter catalog ids look like ``vendor/model`` (e.g.
        ``anthropic/claude-3.7-sonnet``) — exactly the shape litellm uses for
        provider routing, so a bare id would be routed as a DIRECT call to
        that vendor with the wrong protocol/URL (e.g. ``anthropic/...`` lands
        on ``/v1/v1/messages``, ``google/...`` needs GEMINI credentials).
        Prefixing with ``openrouter/`` makes litellm use its openrouter
        provider instead: openai-protocol ``/chat/completions`` against the
        configured BASE_URL, with the model id passed through verbatim.
        """
        if "openrouter.ai" not in (self.base_url or ""):
            return model_name
        if model_name.startswith("openrouter/"):
            return model_name
        return f"openrouter/{model_name}"

    def get_model(self, model_name: str | None) -> Model:
        """Get a model by name.

        Args:
            model_name: The name of the model to get. If None, uses MODEL_NAME from environment.

        Returns:
            The model.
        """
        self._refresh_credentials()

        # Responses-API-only models (GPT-5.x family) go through the native
        # Responses protocol layer instead of LiteLLM's responses bridge.
        raw_model_name = model_name or os.getenv("MODEL_NAME")
        from siada.provider.responses import ResponsesModel, is_responses_only_model
        if is_responses_only_model(raw_model_name):
            from siada.provider.default.responses_transport import DefaultResponsesTransport
            return ResponsesModel(model=raw_model_name, transport=DefaultResponsesTransport())

        # Use provided model_name or fall back to configured model_name
        effective_model_name = covert_to_litellm_model_name(model_name)
        effective_model_name = self._ensure_openrouter_prefix(effective_model_name)
        if not effective_model_name.startswith("openrouter/"):
            # Direct vendor routing — set up any provider-specific env vars.
            # (OpenRouter routing needs none; skip it so the OpenRouter key
            # does not leak into DEEPSEEK/MOONSHOT env vars.)
            self._apply_provider_specific_env(effective_model_name)

        from siada.entrypoint import _configure_litellm
        _configure_litellm()

        # Register custom aws-claude-* models so litellm recognizes their capabilities
        _register_custom_claude_model(effective_model_name)

        # LitellmModel subclass that re-pairs function_call outputs with their
        # calls for kimi/moonshot models, mirroring the fix the li provider
        # applies inside its own _fetch_response (li_provider.py:387-391).
        # See siada/provider/default/kimi_tool_ordering.py for the full rationale.
        return get_kimi_tool_ordering_litellm_model_cls()(
            model=effective_model_name,
            base_url=self.base_url,
            api_key=self.api_key,
            should_replay_reasoning_content=should_replay_reasoning_content,
        )


class DefaultClient(LLMClient):
    """Client for custom LLM API using litellm
    
    Supports any model compatible with litellm by configuring:
    - BASE_URL: The API base URL
    - API_KEY: The API key for authentication
    - MODEL_NAME: The model name to use
    """

    def __init__(self):
        self.base_url = None
        self.api_key = None

    def _refresh_credentials(self):
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
        self._refresh_credentials()

        # Set api_base and api_key if available
        if self.base_url:
            kwargs["api_base"] = self.base_url
        if self.api_key:
            kwargs["api_key"] = self.api_key

        model_name = kwargs.get("model")
        if isinstance(model_name, str) and self.api_key:
            if "deepseek" in model_name:
                os.environ["DEEPSEEK_API_KEY"] = self.api_key
            if "moonshot/" in model_name or model_name.startswith("kimi-"):
                os.environ["MOONSHOT_API_KEY"] = self.api_key

        import litellm
        # Use litellm's native async method for better performance
        return await litellm.acompletion(**kwargs)
