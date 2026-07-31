"""Entity extraction for holographic memory facts.

Two complementary tracks:

1. **Regex track** (English-friendly) — multi-word capitalized phrases,
   double/single-quoted spans, and ``X aka Y`` patterns. Inherited from
   hermes-holographic-memory-design.md §5.1.

2. **jieba pos-tag track** (Chinese + tech terms) — keep tokens whose POS
   tag indicates a named entity (person / place / organization / proper
   noun) and tokens that match a curated tech-term dictionary.

Returned entities are ``(name, entity_type)`` pairs; deduplication is
case-insensitive, preserving the first-seen surface form as the canonical
name. Single-character tokens are dropped to avoid noise.
"""

from __future__ import annotations

import logging
import re
import warnings
from typing import Iterable, List, Tuple

# Same warning suppression as memory_db.py to keep import quiet.
with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore", message="pkg_resources is deprecated", category=UserWarning,
    )
    warnings.filterwarnings("ignore", category=SyntaxWarning, module="jieba")
    import jieba
    import jieba.posseg as pseg

logger = logging.getLogger("siada.holographic.entity_extractor")
jieba.setLogLevel(logging.WARNING)


# --------------------------------------------------------------------- #
# Regex track — patterns from hermes-holographic-memory-design.md §5.1
# --------------------------------------------------------------------- #

_RE_CAPITALIZED = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b")
_RE_DOUBLE_QUOTE = re.compile(r'"([^"]+)"')
_RE_SINGLE_QUOTE = re.compile(r"'([^']+)'")
_RE_AKA = re.compile(
    r"(\w+(?:\s+\w+)*)\s+(?:aka|also known as)\s+(\w+(?:\s+\w+)*)",
    re.IGNORECASE,
)


def _extract_by_pattern(content: str) -> List[Tuple[str, str]]:
    """Run the four regex rules and return ``(name, entity_type)`` pairs."""
    out: List[Tuple[str, str]] = []
    for m in _RE_CAPITALIZED.finditer(content):
        out.append((m.group(1).strip(), "unknown"))
    for m in _RE_DOUBLE_QUOTE.finditer(content):
        token = m.group(1).strip()
        if token:
            # Heuristic: snake_case / single-word lowercase → tool, else unknown.
            etype = "tool" if (" " not in token and token.islower()) else "unknown"
            out.append((token, etype))
    for m in _RE_SINGLE_QUOTE.finditer(content):
        token = m.group(1).strip()
        if token:
            etype = "tool" if (" " not in token and token.islower()) else "unknown"
            out.append((token, etype))
    for m in _RE_AKA.finditer(content):
        a, b = m.group(1).strip(), m.group(2).strip()
        if a:
            out.append((a, "person"))
        if b:
            out.append((b, "person"))
    return out


# --------------------------------------------------------------------- #
# jieba pos-tag track — Chinese + tech terms
# --------------------------------------------------------------------- #

# jieba flag (POS tag) → entity_type.
# 'eng' deliberately omitted: jieba tags every Latin token as 'eng', which
# would flood the entity table with noise like 'the', 'is', 'for'. We rescue
# real tech terms via the tech-dict membership check below instead.
_POS_TO_TYPE = {
    "nr": "person",   # 人名 (person name)
    "nrt": "person",  # transliterated person
    "nrfg": "person", # other person
    "ns": "place",    # 地名 (place name)
    "nt": "org",      # 机构团体 (org / institution)
    "nz": "project",  # 其他专名 (other proper noun — often project / product)
}

# Default tech-term dictionary — tokens commonly missed by stock jieba POS.
# Lowercase comparison; users can extend via ``HolographicConfig.custom_dict``.
_DEFAULT_TECH_DICT = {
    # languages / runtimes
    "python", "java", "javascript", "typescript", "golang", "rust", "kotlin",
    "swift", "scala", "ruby", "perl", "php", "node", "deno",
    # frameworks
    "django", "flask", "fastapi", "spring", "react", "vue", "angular", "nextjs",
    "nuxt", "express", "rails", "laravel",
    # data
    "postgres", "postgresql", "mysql", "mongodb", "redis", "kafka", "elasticsearch",
    "clickhouse", "sqlite", "duckdb", "snowflake",
    # infra
    "docker", "kubernetes", "k8s", "terraform", "ansible", "jenkins", "gitlab",
    "github", "aws", "gcp", "azure",
    # tools mentioned in the design docs
    "vim", "emacs", "vscode", "pytest", "ruff", "mypy", "poetry", "uv",
    "lark", "feishu",
    # siada/hermes/openclaw ecosystem
    "siada", "hermes", "openclaw", "agenthub", "claw",
}

# Single-char tokens are too noisy regardless of POS.
_MIN_TOKEN_LEN = 2


def _build_tech_dict(custom_terms: Iterable[str] | None) -> set[str]:
    """Combine the default tech dict with user-supplied terms (lowercased)."""
    out = set(_DEFAULT_TECH_DICT)
    if custom_terms:
        for term in custom_terms:
            if term:
                out.add(str(term).lower())
    return out


def _extract_by_jieba(content: str, tech_dict: set[str]) -> List[Tuple[str, str]]:
    """jieba pos-tag pass: keep entity-like POS tags + tech-dict matches."""
    out: List[Tuple[str, str]] = []
    try:
        pairs = list(pseg.cut(content))
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug("jieba.posseg.cut failed: %s", exc)
        return out

    for token, flag in pairs:
        token = token.strip()
        if not token or len(token) < _MIN_TOKEN_LEN:
            continue
        # Skip pure punctuation that jieba sometimes returns under non-noun tags.
        if not any(c.isalnum() or ord(c) > 127 for c in token):
            continue
        if flag in _POS_TO_TYPE:
            out.append((token, _POS_TO_TYPE[flag]))
        elif token.lower() in tech_dict:
            # Tech term match wins regardless of POS — this rescues 'eng'
            # / 'x' / generic 'n' tokens that jieba wouldn't have flagged.
            out.append((token, "tech"))
    return out


# --------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------- #

def _dedupe_preserve_order(items: Iterable[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """Case-insensitive dedup; preserve first-seen surface form and type."""
    seen: dict[str, Tuple[str, str]] = {}
    for name, etype in items:
        key = name.lower()
        if key and key not in seen:
            seen[key] = (name, etype)
    return list(seen.values())


def add_custom_dict(custom_terms: Iterable[str] | None) -> None:
    """Register user-supplied terms with jieba so it stops over-segmenting them.

    Idempotent — safe to call repeatedly across sessions / tests.
    """
    if not custom_terms:
        return
    for term in custom_terms:
        if term:
            try:
                jieba.add_word(str(term))
            except Exception as exc:  # pragma: no cover — defensive
                logger.debug("jieba.add_word(%r) failed: %s", term, exc)


def extract_entities(
    content: str,
    *,
    custom_dict: Iterable[str] | None = None,
) -> List[Tuple[str, str]]:
    """Extract ``(name, entity_type)`` pairs from a fact's content.

    Both the regex and jieba tracks are run; results are merged then
    case-insensitively deduplicated. The regex track wins on conflict
    because it ran first.
    """
    if not content or not content.strip():
        return []
    tech_dict = _build_tech_dict(custom_dict)
    add_custom_dict(custom_dict)
    merged = _extract_by_pattern(content) + _extract_by_jieba(content, tech_dict)
    return _dedupe_preserve_order(merged)
