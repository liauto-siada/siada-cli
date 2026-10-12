"""Load the Kimi Code template adapted to Siada's runtime.

Adapted from MoonshotAI/kimi-code at commit
72fc1d0a3375b2a87dff602a1d91726a99f360e0, under the MIT License.
Copyright (c) 2026 Moonshot AI. Siada changes the agent identity, tool
contracts, and runtime context. The license is reproduced in docs/CREDITS.md
and distributed with this template.
"""

from functools import lru_cache
from pathlib import Path


_TEMPLATE_PATH = Path(__file__).parent / "templates" / "system.md"


@lru_cache(maxsize=1)
def get_kimi_k3_template() -> str:
    return _TEMPLATE_PATH.read_text(encoding="utf-8").strip()
