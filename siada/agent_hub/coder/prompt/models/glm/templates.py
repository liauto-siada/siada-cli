"""Load the GLM system prompt template.

The template copies the ZCode CLI system prompt (https://github.com/zai-org/ZCode,
commit 29628c9, Apache-2.0: ``context/sections/identity.ts``,
``context/dynamic-sections.ts`` and the ``context/sections/env-info.ts`` layout)
with the identity renamed to Siada and runtime facts left as ``${...}``
placeholders for Siada to substitute. ZCode's one-line ``cli-prefix.ts`` message
is omitted: it is a separate wire message in ZCode and would restate the
identity sentence in Siada's single-string prompt.
"""

from functools import lru_cache
from pathlib import Path


_TEMPLATE_PATH = Path(__file__).parent / "templates" / "system.md"


@lru_cache(maxsize=1)
def get_glm_template() -> str:
    return _TEMPLATE_PATH.read_text(encoding="utf-8").strip()
