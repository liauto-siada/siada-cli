from __future__ import annotations


class GeminiRequestError(Exception):
    def __init__(self, status_code: int | None = None, *, retryable: bool = False):
        super().__init__(f"Gemini request failed (HTTP {status_code})." if status_code else "Gemini request failed.")
        self.status_code = status_code
        self.retryable = retryable or status_code == 429 or status_code is not None and status_code >= 500
