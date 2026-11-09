from __future__ import annotations

import threading
from collections.abc import AsyncIterator
import httpx
from aiohttp import ClientError
from google import genai
from google.genai import errors, types

from siada.provider.lifecycle import EventLoopOwnership
from siada.provider.gemini.errors import GeminiRequestError


def _safe_failure(error: Exception) -> GeminiRequestError:
    if isinstance(error, errors.APIError):
        return GeminiRequestError(error.code)
    if isinstance(error, (httpx.RequestError, ClientError, TimeoutError)):
        return GeminiRequestError(retryable=True)
    return GeminiRequestError()


class GeminiTransport:
    provider = "google"
    backend = "gemini_api"

    def __init__(self, client: genai.Client | None = None):
        self._borrowed_client = client
        self._clients: dict[tuple[str | None, str], genai.Client] = {}
        self._lock = threading.Lock()
        self._loop = EventLoopOwnership()
        self._closed = False
        if client is not None and client.vertexai:
            self.backend = "vertex_ai"

    def origin(self, model: str) -> dict[str, str]:
        return {"provider": self.provider, "model": model, "backend": self.backend}

    def _request_model_name(self, model: str) -> str:
        return model

    def _client_for(self, base_url: str | None, api_key: str) -> genai.Client:
        with self._lock:
            self._loop.check()
            if self._closed:
                raise RuntimeError("Gemini transport is closed.")
            key = (base_url, api_key)
            client = self._clients.get(key)
            if client is None:
                api_version = "v1beta"
                if base_url and base_url.rstrip("/").endswith(("/v1beta", "/v1")):
                    base_url, api_version = base_url.rstrip("/").rsplit("/", 1)
                client = genai.Client(vertexai=False, api_key=api_key, http_options=types.HttpOptions(
                    base_url=base_url, api_version=api_version, retry_options=types.HttpRetryOptions(attempts=1),
                ))
                self._clients[key] = client
            return client

    async def _prepare(self, config: types.GenerateContentConfig, model: str) -> tuple[genai.Client, types.GenerateContentConfig]:
        self._loop.check()
        if self._closed:
            raise RuntimeError("Gemini transport is closed.")
        if self._borrowed_client is None:
            raise RuntimeError("An official Gen AI client or a configured provider transport is required.")
        return self._borrowed_client, config

    async def _refresh_auth(self, status_code: int | None) -> bool:
        return False

    async def generate(self, model: str, contents: list[types.Content], config: types.GenerateContentConfig) -> types.GenerateContentResponse:
        for attempt in range(2):
            client, config = await self._prepare(config, model)
            failure = None
            try:
                return await client.aio.models.generate_content(model=self._request_model_name(model), contents=contents, config=config)
            except Exception as error:
                failure = _safe_failure(error)
            if attempt == 0 and await self._refresh_auth(failure.status_code):
                continue
            raise failure
        raise AssertionError("Unreachable Gemini retry state.")

    async def stream(self, model: str, contents: list[types.Content], config: types.GenerateContentConfig) -> AsyncIterator[types.GenerateContentResponse]:
        for attempt in range(2):
            client, config = await self._prepare(config, model)
            stream = None
            failure = None
            interrupted = False
            exposed = False
            try:
                stream = await client.aio.models.generate_content_stream(model=self._request_model_name(model), contents=contents, config=config)
                async for response in stream:
                    exposed = True
                    yield response
            except BaseException as error:
                interrupted = True
                if not isinstance(error, Exception):
                    raise
                failure = _safe_failure(error)
            finally:
                if stream is not None:
                    try:
                        await stream.aclose()
                    except Exception as error:
                        if not interrupted:
                            failure = _safe_failure(error)
            if failure is None:
                return
            if attempt == 0 and not exposed and await self._refresh_auth(failure.status_code):
                continue
            raise failure

    async def aclose(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._loop.check(bind=False)
            self._closed = True
            clients = list(self._clients.values())
            self._clients.clear()
        failures = []
        for client in clients:
            try:
                await client.aio.aclose()
            except BaseException as error:
                failures.append(error)
            try:
                client.close()
            except BaseException as error:
                failures.append(error)
        if failures:
            if len(failures) == 1:
                raise failures[0]
            raise BaseExceptionGroup("Failed to close Gemini resources.", failures)
