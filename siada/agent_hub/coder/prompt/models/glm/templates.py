"""Load the GLM system prompt template.

Adapted from ZCode (https://github.com/zai-org/ZCode, commit 29628c9,
Apache-2.0), with the identity renamed to Siada and runtime placeholders.
ZCode's separate CLI prefix is omitted from Siada's single-string prompt.
"""

from functools import lru_cache
from pathlib import Path


_TEMPLATE_PATH = Path(__file__).parent / "templates" / "system.md"


@lru_cache(maxsize=1)
def get_glm_template() -> str:
    return _TEMPLATE_PATH.read_text(encoding="utf-8").strip()