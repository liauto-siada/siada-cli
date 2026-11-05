from __future__ import annotations

import re


# Slash-qualified names retain their explicit provider routing.
_DERIVED_GEMINI_MODEL = re.compile(r"[^/]+?-(gemini(?:-[^/]*)?)", re.IGNORECASE)


def is_gemini_model(model: str | None) -> bool:
    lower_model = (model or "").lower()
    return lower_model.startswith((
        "gemini-", "gemini/", "google/gemini-", "models/gemini-",
    )) or bool(_DERIVED_GEMINI_MODEL.fullmatch(model or ""))


def wire_model_name(model: str) -> str:
    for prefix in ("gemini/", "google/", "models/"):
        if model.startswith(prefix):
            return model.removeprefix(prefix)
    if model.lower().startswith("gemini-"):
        return model
    derived = _DERIVED_GEMINI_MODEL.fullmatch(model)
    if derived:
        return derived.group(1)
    return model
