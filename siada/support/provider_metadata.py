from __future__ import annotations

from typing import Any


def without_provider_metadata(value: Any) -> Any:
    if isinstance(value, list):
        return [without_provider_metadata(item) for item in value]
    if isinstance(value, dict):
        return {
            key: without_provider_metadata(item)
            for key, item in value.items() if key != "provider_data"
        }
    return value
