from __future__ import annotations
import os
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING

from agents import Model, ModelProvider

from siada.provider.default.chat_completions import (
    DefaultChatClientFactory,
    DefaultOpenAIChatCompletionsModel,
    get_default_chat_wire_model,
)
from siada.provider.default.coverter import covert_to_litellm_model_name
from siada.provider.default.kimi_tool_ordering import (
    get_kimi_tool_ordering_litellm_model_cls,
)
from siada.provider.llm_client import LLMClient
from siada.provider.reasoning_replay import should_replay_reasoning_content
from siada.provider.request_config import (
    default_credentials_scope,
    get_default_credentials,
)

if TYPE_CHECKING:
    from litellm.types.utils import ModelResponse as LitellmModelResponse


def _register_custom_claude_model(model_name: str):
    """Register custom model names in litellm so supports_reasoning() returns True,
    allowing 'thinking' (Claude) and 'reasoning_effort' (Gemini) params to pass through.

    The public build points BASE_URL at a user-configured (OpenAI-compatible)
    endpoint, so the model ids are whatever that gateway exposes: a claude /
    gemini release litellm does not ship yet, or a gateway-specific alias.
    Family detection is therefore name based; ids litellm already knows keep
    their own capability data (``litellm.model_cost``).
    """
    import litellm
    if model_name in litellm.model_cost:
        return

    lower_name = model_name.lower()
    if "claude" in lower_name or "gemini" in lower_name:
        litellm.register_model({model_name: {"supports_reasoning": True}})


class DefaultProvider(ModelProvider):
    """Provider for OpenAI Chat Completions and retained Claude/Gemini routes.

    OpenAI Chat-compatible endpoints use ``BASE_URL`` and ``API_KEY``. Claude
    and Gemini continue to use their existing LiteLLM/native-provider paths.
    """

    # Credential source markers for ``_build_model``: the Responses-API-only
    # branch treats a per-call override (``fast_llm_config``) differently from
    # the environment-driven ``get_model`` the SDK calls.
    _CREDENTIALS_ENV = "env"
    _CREDENTIALS_OVERRIDE = "override"

    def __init__(self):
        # NOTE:
        # Provider instances are created eagerly by provider_factory at import time.
        # API key login, however, may update BASE_URL/API_KEY later at runtime.
        # So we must not cache credentials only once in __init__.
        self.base_url = None
        self.api_key = None
        self._chat_client_factory = DefaultChatClientFactory()
        # Per-model factories pinned to explicit (fast_llm_config) credentials,
        # keyed by the credential pair they were built with; closed together
        # with the shared one. Keying is what keeps a repeated override — the
        # same fast_llm_config resolved on every task — at one factory / client
        # instead of one more client per call until aclose().
        self._pinned_chat_client_factories: dict[
            tuple[str | None, str | None], DefaultChatClientFactory
        ] = {}
        from siada.provider.default.responses_transport import (
            DefaultResponsesTransport,
        )

        self._responses_transport = DefaultResponsesTransport()

    def _refresh_credentials(self):
        """Refresh credentials from environment for runtime login / reconfigure flows."""
        self.base_url = os.getenv("BASE_URL", None)
        self.api_key = os.getenv("API_KEY", None)

    def request_scope(
        self, *, base_url: str | None = None, api_key: str | None = None
    ) -> AbstractContextManager[None]:
        """Use isolated endpoint credentials while retaining runtime ownership."""
        return default_credentials_scope(base_url=base_url, api_key=api_key)

    def _ensure_openrouter_prefix(self, model_name: str, base_url: str | None = None) -> str:
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
        effective_base_url = self.base_url if base_url is None else base_url
        if "openrouter.ai" not in (effective_base_url or ""):
            return model_name
        if model_name.startswith("openrouter/"):
            return model_name
        return f"openrouter/{model_name}"

    def get_model(self, model_name: str | None) -> Model:
        """Get a model by name (the SDK ``ModelProvider`` entry point).

        Credentials are re-read from the environment on every call: login /
        reconfigure flows may update BASE_URL / API_KEY after this provider
        instance was created.

        Args:
            model_name: The name of the model to get. If None, uses MODEL_NAME from environment.

        Returns:
            The model.
        """
        self._refresh_credentials()
        base_url, api_key = get_default_credentials()
        return self._build_model(
            model_name,
            base_url=base_url,
            api_key=api_key,
            credentials_source=self._CREDENTIALS_ENV,
        )

    def get_model_with_credentials(
        self,
        model_name: str | None,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> Model:
        """Build a ``Model`` pinned to explicit credentials (``fast_llm_config``).

        Kept separate from the SDK-compatible ``get_model(name)`` so callers that
        want the override endpoint (e.g. ``siada.provider.fast_llm``) do not have
        to route credentials through ``os.environ``: the values only live on the
        returned model, so concurrent requests built for the main endpoint keep
        the credentials they were created with.

        Fields the caller omits (``None``) fall back to the environment, so a
        partial override keeps the main endpoint / key for the half it does not
        configure.

        Calls that resolve to the same ``(base_url, api_key)`` pair share one
        pinned factory — and therefore one client — until ``aclose()``. Those
        two values are frozen on the factory, so reusing it cannot let a later
        login / reconfigure flow change what an override sends.

        Note the naming: LiteLLM's ``acompletion`` takes ``api_base`` (what
        ``fast_completion`` passes per call), while this model constructor takes
        ``base_url`` — fast_llm translates between the two.
        """
        return self._build_model(
            model_name,
            base_url=base_url or os.getenv("BASE_URL", None),
            api_key=api_key or os.getenv("API_KEY", None),
            credentials_source=self._CREDENTIALS_OVERRIDE,
        )

    def _build_model(
        self,
        model_name: str | None,
        *,
        base_url: str | None,
        api_key: str | None,
        credentials_source: str,
    ) -> Model:
        """Shared model builder — the single place credentials enter a model.

        ``base_url`` / ``api_key`` are the *effective* credentials (explicit value
        with an environment fallback, resolved by the caller). They are stored on
        the returned model only: no process-global env var is written here, so
        concurrent requests keep the credentials they were built with.

        ``credentials_source`` marks where those credentials came from — the
        Responses-API-only branch below can only honour the environment pair.
        """
        # Responses-API-only models (GPT-5.x family) go through the native
        # Responses protocol layer instead of LiteLLM's responses bridge.
        raw_model_name = model_name or os.getenv("MODEL_NAME")
        from siada.provider.responses import ResponsesModel, is_responses_only_model
        if is_responses_only_model(raw_model_name):
            # A bare pinned model outlives a request scope. Its credentials
            # must match the transport's active task-local configuration.
            active_base_url, active_api_key = get_default_credentials()
            if credentials_source == self._CREDENTIALS_OVERRIDE and (
                base_url != active_base_url
                or api_key != active_api_key
            ):
                raise ValueError(
                    "fast_llm_config credentials cannot be applied to the "
                    f"Responses-API-only model {raw_model_name!r}: this build's "
                    "Responses transport reads BASE_URL / API_KEY from the "
                    "environment. Remove base_url/api_key from fast_llm_config "
                    "or use a chat-completions model."
                )
            return ResponsesModel(
                model=raw_model_name,
                transport=self._responses_transport,
            )

        # Keep native Anthropic/Gemini traffic on their existing LiteLLM paths.
        lower_model_name = (raw_model_name or "").lower()
        effective_model_name = covert_to_litellm_model_name(raw_model_name or "")
        uses_responses_bridge = effective_model_name.startswith(
            ("openai/responses/", "responses/")
        )
        if (
            "claude" not in lower_model_name
            and "anthropic" not in lower_model_name
            and "gemini" not in lower_model_name
            and not uses_responses_bridge
        ):
            wire_model = get_default_chat_wire_model(raw_model_name or "", base_url)
            if credentials_source == self._CREDENTIALS_OVERRIDE:
                # The shared factory re-reads BASE_URL / API_KEY from the
                # environment on every call; an explicit override must keep the
                # caller's endpoint and key, so it gets its own pinned factory.
                # The factory is reused for the same credential pair: they are
                # frozen on it, so a second identical override would otherwise
                # hold a second client (and connection pool) for the rest of the
                # session.
                credentials = (base_url, api_key)
                client_factory = self._pinned_chat_client_factories.get(credentials)
                if client_factory is None:
                    client_factory = DefaultChatClientFactory(
                        base_url=base_url, api_key=api_key
                    )
                    self._pinned_chat_client_factories[credentials] = client_factory
            else:
                client_factory = self._chat_client_factory
            return DefaultOpenAIChatCompletionsModel(
                model=wire_model,
                client_factory=client_factory,
                should_replay_reasoning_content=should_replay_reasoning_content,
            )

        # Resolve the name the same way the branches above do: a caller may pass
        # None and rely on MODEL_NAME (``covert_to_litellm_model_name`` needs a
        # str, so an unset MODEL_NAME falls back to the empty name here too).
        effective_model_name = covert_to_litellm_model_name(raw_model_name or "")
        effective_model_name = self._ensure_openrouter_prefix(effective_model_name, base_url)

        # NOTE: building a model never writes process-global env vars. The
        # effective credentials ride on the returned model only (both the
        # environment path and a per-call ``fast_llm_config`` override), so a
        # concurrent request can never pick up another request's endpoint/key.

        from siada.entrypoint import _configure_litellm
        _configure_litellm()

        # Register custom claude / gemini ids (gateway aliases, releases litellm
        # does not ship yet) so litellm reports supports_reasoning() == True and
        # lets 'thinking' / 'reasoning_effort' pass through.
        _register_custom_claude_model(effective_model_name)

        # Keep the legacy LiteLLM model for Claude/Gemini and Responses bridge
        # aliases. The shared Kimi ordering mixin remains available for callers
        # that still use this legacy transport.
        # NOTE: the LiteLLM model constructor takes model / base_url / api_key
        # only — request headers are not a constructor parameter, they travel
        # through ``ModelSettings.extra_headers`` (fast_llm puts them there).
        return get_kimi_tool_ordering_litellm_model_cls()(
            model=effective_model_name,
            base_url=base_url,
            api_key=api_key,
            should_replay_reasoning_content=should_replay_reasoning_content,
        )

    async def aclose(self) -> None:
        """Close Chat Completions and Responses clients owned by this provider."""
        errors: list[Exception] = []
        for close in (
            self._chat_client_factory.aclose,
            self._responses_transport.aclose,
        ):
            try:
                await close()
            except Exception as exc:
                errors.append(exc)

        for factory in tuple(self._pinned_chat_client_factories.values()):
            try:
                await factory.aclose()
            except Exception as exc:
                errors.append(exc)
        self._pinned_chat_client_factories.clear()

        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise ExceptionGroup(
                "Failed to close one or more default provider resources",
                errors,
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
                     and 'api_base' / 'api_key' / 'extra_headers' to point a
                     single call at another endpoint.
            
        Returns:
            LitellmModelResponse: The completion response

        When custom_llm_provider is omitted, known model families are normalized
        for LiteLLM, OpenRouter endpoints use OpenRouter routing, and bare custom
        aliases use the OpenAI-compatible protocol with their model ID preserved.

        Credential precedence: explicit per-call kwargs win over the process
        environment. The environment (BASE_URL / API_KEY) only fills in the
        values the caller did not pass — otherwise the ``fast_llm_config``
        override carried by ``fast_llm.fast_completion`` would be clobbered by
        the main endpoint's credentials.

        The resolved pair travels as ``api_base`` / ``api_key`` kwargs on this
        call only. In particular no vendor env var (DEEPSEEK_API_KEY /
        MOONSHOT_API_KEY) is written: those are process-global, so an override
        key would leak into concurrent main-endpoint requests; LiteLLM honours
        the explicit per-call kwargs instead.
        """
        self._refresh_credentials()

        # Set api_base and api_key if available — but never overwrite values the
        # caller passed explicitly.
        if self.base_url and not kwargs.get("api_base"):
            kwargs["api_base"] = self.base_url
        if self.api_key and not kwargs.get("api_key"):
            kwargs["api_key"] = self.api_key

        # LiteLLM cannot infer a provider from arbitrary gateway model aliases.
        # Preserve explicit routing; otherwise normalize known model families
        # and send bare aliases through the configured OpenAI-compatible API.
        model_name = kwargs.get("model")
        if model_name and not kwargs.get("custom_llm_provider"):
            model_name = covert_to_litellm_model_name(model_name)
            if "openrouter.ai" in (kwargs.get("api_base") or ""):
                if not model_name.startswith("openrouter/"):
                    model_name = f"openrouter/{model_name}"
            elif "/" not in model_name:
                kwargs["custom_llm_provider"] = "openai"
            kwargs["model"] = model_name

        import litellm
        # Use litellm's native async method for better performance
        return await litellm.acompletion(**kwargs)
