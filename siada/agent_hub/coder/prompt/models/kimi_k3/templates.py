"""Load the Kimi Code template adapted to Siada's runtime."""

from functools import lru_cache
from pathlib import Path


_TEMPLATE_PATH = Path(__file__).parent / "templates" / "system.md"


@lru_cache(maxsize=1)
def get_kimi_k3_template() -> str:
    return _TEMPLATE_PATH.read_text(encoding="utf-8").strip()
