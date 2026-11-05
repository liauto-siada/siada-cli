from __future__ import annotations

import json
from typing import Any

from siada.provider.gemini.converter import function_declarations
from siada.provider.gemini.replay import decode_replay


def estimate_input_tokens(items: Any, tools=None, *, model_name: str = "gemini") -> int:
    texts: list[str] = []

    def measure(value: Any) -> int:
        if isinstance(value, dict):
            if value.get("type") in {"input_image", "image_url"}:
                return 8192
            return sum(8192 if key in {"inline_data", "file_data"} else measure(entry)
                       for key, entry in value.items() if key not in {"thought_signature", "thoughtSignature", "provider_data"}) + 4
        if isinstance(value, list):
            return sum(measure(entry) for entry in value)
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        if text:
            texts.append(text)
        return 0

    if isinstance(items, str):
        count = measure(items)
    else:
        count = 0
        for item in items:
            metadata = decode_replay(item)
            if metadata is not None:
                if "contents" in metadata:
                    count += measure(metadata["contents"])
                elif "parts" in metadata:
                    count += measure([record["part"] for record in metadata["parts"]])
            else:
                count += measure(item)
    if tools:
        count += measure([declaration.model_dump(mode="json", exclude_none=True) for declaration in function_declarations(tools, [])])
    if texts:
        combined = "\n".join(texts) if len(texts) > 1 else texts[0]
        try:
            import litellm

            count += int(litellm.token_counter(model=model_name, text=combined))
        except Exception:
            count += max(1, len(combined) // 4)
    return count
