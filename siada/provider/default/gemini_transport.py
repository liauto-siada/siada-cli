from __future__ import annotations

import os

from agents.exceptions import UserError
from google import genai
from google.genai import types

from siada.provider.gemini.transport import GeminiTransport
from siada.provider.request_config import default_credentials_scope, get_default_credentials, has_request_credentials


class DefaultGeminiTransport(GeminiTransport):
    provider = "default"

    async def _prepare(self, config: types.GenerateContentConfig, model: str) -> tuple[genai.Client, types.GenerateContentConfig]:
        base_url, api_key = get_default_credentials()
        if not has_request_credentials():
            base_url = os.getenv("GEMINI_BASE_URL") or base_url
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or api_key
        if not api_key:
            raise UserError("GEMINI_API_KEY or API_KEY is required for native Gemini.")
        if base_url and ("openrouter.ai" in base_url or base_url.rstrip("/").endswith("/v1")):
            raise UserError("Native Gemini requires a Gemini endpoint, not a Chat endpoint; configure GEMINI_BASE_URL or an official client.")
        return self._client_for(base_url or None, api_key), config


class PinnedDefaultGeminiTransport(DefaultGeminiTransport):
    """Reuse owned clients with immutable credentials for background fast models."""

    def __init__(self, base_url: str | None, api_key: str | None):
        super().__init__()
        self._credentials = (base_url, api_key)

    async def _prepare(self, config: types.GenerateContentConfig, model: str) -> tuple[genai.Client, types.GenerateContentConfig]:
        base_url, api_key = self._credentials
        with default_credentials_scope(base_url=base_url or "", api_key=api_key or ""):
            return await super()._prepare(config, model)
