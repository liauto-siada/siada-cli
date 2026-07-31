"""Top-level façade for the holographic memory system.

Wires up ``FactStore`` + ``FactRetriever`` and exposes the operations the
rest of siada-agenthub needs:

- ``handle_tool_call(name, args)`` — dispatch ``fact_store`` / ``fact_feedback`` actions
- ``prefetch(query)``              — top-N facts as a markdown block to inject before user msg
- ``on_memory_write(action, target, content)`` — mirror inline ``memory`` tool writes
- ``initialize`` / ``shutdown``    — lifecycle bookkeeping (config-driven dim drift handling)

The provider is **not** an ABC subclass — siada has no plugin loader yet and
adding a base class for one implementation just adds churn. We can pull out
an interface later if a second backend lands.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable, List, Optional

from siada.config.config_loader import HolographicConfig
from siada.foundation.constants import SIADA_HOME
from siada.services.memory.holographic.retrieval import FactRetriever
from siada.services.memory.holographic.store import FactStore

logger = logging.getLogger("siada.holographic.provider")


# Mapping from inline memory ``target`` to holographic ``category``.
# Mirroring is one-way: memory tool writes flow into holographic, but
# holographic writes never touch the markdown files (they're a frozen
# system-prompt snapshot).
_TARGET_TO_CATEGORY = {
    "user": "user_pref",
    "memory": "general",
}

# Suggested categories (soft-validated; LLM is free to use others).
SUGGESTED_CATEGORIES = (
    "user_pref", "project", "tool", "decision", "env", "general",
)


def _default_db_path() -> Path:
    """Default location: ``~/.siada-cli/workspace/memory/holographic/facts.db``."""
    return SIADA_HOME / "workspace" / "memory" / "holographic" / "facts.db"


def _resolve_db_path(raw: Optional[str]) -> Path:
    """Resolve ``db_path`` config: expand env tokens or fall back to default."""
    if not raw:
        return _default_db_path()
    expanded = str(raw).replace("$SIADA_HOME", str(SIADA_HOME))
    expanded = expanded.replace("${SIADA_HOME}", str(SIADA_HOME))
    return Path(expanded).expanduser()


# Guidance text appended to ``combined_memory`` whenever a HolographicProvider
# is initialized for the run. Lives next to the provider so any tweak to the
# fact_store contract is one edit away from the implementation that enforces
# it. The ``{fact_count}`` placeholder is filled in once per snapshot —
# see ``siada.services.memory.combined_memory`` for the cache-vs-correctness
# discussion.
#
# Tone is intentionally passive: like ``MEMORY_GUIDANCE`` we describe what's
# available without instructing the model to "always" probe / reason. Past
# experiments with the more aggressive "WHEN TO PREFER fact_store..." phrasing
# nudged the LLM into running probe / search on every turn even when the
# query was unrelated to stored facts, wasting tool budget. The model is
# free to consult ``fact_store`` when the situation warrants it; we just
# tell it the tool is available.
#
# The "(holographic)" suffix used to advertise the underlying HRR / vector
# implementation in the heading. Internal jargon — dropped from the
# user-facing prompt because the LLM doesn't need to know how the store
# works to use it.
#
# The "follow the user when stored facts conflict" rule that used to live
# at the bottom of this template was pulled out and merged with the
# analogous rule from the inline-memory guidance into
# ``combined_memory._MEMORY_LAYERS_COMMON_RULES``. Keeping it in a single
# shared block instead of duplicating it across layers means future tweaks
# (e.g. adding "follow rule_memory first") only need a single edit.
HOLOGRAPHIC_GUIDANCE_TEMPLATE = """\
====
Structured Fact Memory

A structured fact store is also available. It currently holds
**{fact_count} facts** with named entities (people, projects, tools,
decisions). The `fact_store` tool can search, probe, list, or update these
facts when relevant — for example when the user references an entity you
might already know about, or the current task lines up with a stored fact
category.

After using a fact in your answer you may call
`fact_feedback(fact_id, "helpful")` so its trust score rises; this is
optional.
===="""


class HolographicProvider:
    """Façade owning a ``FactStore`` + ``FactRetriever`` for one workspace."""

    def __init__(self, config: HolographicConfig):
        self.config = config
        self.db_path = _resolve_db_path(config.db_path)
        self._store: Optional[FactStore] = None
        self._retriever: Optional[FactRetriever] = None

    @classmethod
    def from_config(cls, config: HolographicConfig) -> "HolographicProvider":
        return cls(config)

    # ---------------------------------------------------------------- #
    # Lifecycle
    # ---------------------------------------------------------------- #

    def initialize(self) -> None:
        """Open the SQLite store and wire up the retriever.

        Detects ``hrr_dim`` drift between conf and on-disk vectors; when they
        diverge, runs ``rebuild_all_vectors`` so the user can change ``hrr_dim``
        in conf.yaml without manually wiping the DB.
        """
        self._store = FactStore(
            self.db_path,
            hrr_dim=self.config.hrr_dim,
            hrr_enabled=self.config.hrr_enabled,
            default_trust=self.config.default_trust,
            custom_dict=self.config.custom_dict,
        )
        # Detect dim drift — user might have raised hrr_dim in conf.yaml
        # while the DB on disk holds vectors at the old size. Rebuild once
        # so search/probe don't crash on shape mismatch.
        existing = self._store.get_existing_bank_dim()
        if existing is not None and existing != self.config.hrr_dim:
            logger.warning(
                "[holographic] hrr_dim drift detected: on-disk=%d, config=%d; "
                "rebuilding all HRR vectors (this may take a few seconds).",
                existing, self.config.hrr_dim,
            )
            try:
                n = self._store.rebuild_all_vectors(dim=self.config.hrr_dim)
                logger.info("[holographic] rebuilt %d facts at dim=%d",
                            n, self.config.hrr_dim)
            except Exception as exc:  # pragma: no cover — defensive
                logger.error("[holographic] dim-drift rebuild failed: %s", exc)
        self._retriever = FactRetriever(
            self._store,
            hrr_dim=self.config.hrr_dim,
            hrr_enabled=self.config.hrr_enabled,
            default_min_trust=self.config.min_trust_threshold,
            temporal_half_life_days=self.config.temporal_decay_half_life,
        )
        logger.info(
            "[holographic] initialized at %s (hrr_dim=%d, prefetch_limit=%d)",
            self.db_path, self.config.hrr_dim, self.config.prefetch_limit,
        )

    def shutdown(self) -> None:
        """Release the SQLite handle. Safe to call multiple times."""
        try:
            if self._store is not None:
                self._store.close()
        finally:
            self._store = None
            self._retriever = None

    # Convenience access for tests / direct callers.
    @property
    def store(self) -> Optional[FactStore]:
        return self._store

    @property
    def retriever(self) -> Optional[FactRetriever]:
        return self._retriever

    # ---------------------------------------------------------------- #
    # Hook: prefetch
    # ---------------------------------------------------------------- #

    def prefetch(self, query: str, *, limit: Optional[int] = None) -> str:
        """Return a markdown-formatted block to inject before the user message.

        Empty string when there's nothing to inject — caller is expected to
        treat that as "skip injection". Always exception-safe: prefetch must
        never break the main turn pipeline.
        """
        if self._retriever is None or not query or not query.strip():
            return ""
        n = int(limit if limit is not None else self.config.prefetch_limit)
        if n <= 0:
            return ""
        try:
            results = self._retriever.search(
                query, min_trust=self.config.min_trust_threshold, limit=n,
            )
        except Exception as exc:  # pragma: no cover — defensive
            logger.debug("[holographic] prefetch failed: %s", exc)
            return ""
        if not results:
            return ""
        lines = ["## Holographic Memory (top relevant facts)"]
        for r in results:
            trust = float(r.get("trust_score") or 0.0)
            fid = r.get("fact_id", "?")
            content = (r.get("content") or "").strip().replace("\n", " ")
            # Cap any single fact at 240 chars to keep injection compact.
            if len(content) > 240:
                content = content[:237] + "..."
            lines.append(f"- [{trust:.1f} #{fid}] {content}")
        return "\n".join(lines)

    # ---------------------------------------------------------------- #
    # Hook: on_memory_write — mirror inline memory tool
    # ---------------------------------------------------------------- #

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        *,
        tags: Optional[str] = None,
    ) -> None:
        """Mirror inline ``memory(action='add', target=...)`` writes into facts.db.

        Only ``add`` is mirrored — ``replace`` and ``remove`` are LLM-driven
        edits to the markdown snapshot and shouldn't be auto-propagated.
        """
        if self._store is None:
            return
        if (action or "").lower() != "add":
            return
        if not content or not content.strip():
            return
        category = _TARGET_TO_CATEGORY.get(target, "general")
        logger.info(
            f"[holographic-mirror] Mirroring built-in memory write: target={target} → category={category}, content={content[:80]}..."
        )
        try:
            res = self._store.add_fact(
                content,
                category=category,
                tags=(tags or "from_memory_tool"),
            )
            logger.info(f"[holographic-mirror] Mirror success: fact_id={res.get('fact_id')}, created={res.get('created')}")
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning(
                f"[holographic-mirror] Mirror add_fact failed: {exc}", exc_info=True
            )

    # ---------------------------------------------------------------- #
    # Hook: tool dispatch
    # ---------------------------------------------------------------- #

    def handle_tool_call(self, tool_name: str, args: dict) -> str:
        """Dispatch ``fact_store`` / ``fact_feedback`` calls to the right method.

        Returns a JSON string per siada's tool protocol; never raises out.
        """
        try:
            if tool_name == "fact_store":
                result = self._handle_fact_store(args or {})
            elif tool_name == "fact_feedback":
                result = self._handle_fact_feedback(args or {})
            else:
                result = {
                    "success": False,
                    "error": f"unknown holographic tool: {tool_name}",
                }
        except KeyError as exc:
            result = {"success": False, "error": f"missing argument: {exc}"}
        except Exception as exc:  # pragma: no cover — defensive
            logger.exception("[holographic] tool %s failed", tool_name)
            result = {"success": False, "error": str(exc)}
        return json.dumps(result, ensure_ascii=False)

    # ---------------------------------------------------------------- #
    # _handle_fact_store — switch on action
    # ---------------------------------------------------------------- #

    def _handle_fact_store(self, args: dict) -> dict:
        if self._store is None or self._retriever is None:
            return {"success": False, "error": "holographic memory not initialized"}
        action = (args.get("action") or "").strip().lower()
        if not action:
            return {"success": False, "error": "action is required"}

        if action == "add":
            content = args.get("content")
            if not content:
                return {"success": False, "error": "content is required for add"}
            return self._store.add_fact(
                content,
                category=args.get("category") or "general",
                tags=args.get("tags") or "",
            )

        if action == "search":
            query = args.get("query") or args.get("content") or ""
            if not query:
                return {"success": False, "error": "query is required for search"}
            results = self._retriever.search(
                query,
                category=args.get("category"),
                min_trust=_safe_float(args.get("min_trust")),
                limit=int(args.get("limit") or 10),
            )
            return {"success": True, "action": "search", "results": results}

        if action == "probe":
            entity = args.get("entity")
            if not entity:
                return {"success": False, "error": "entity is required for probe"}
            results = self._retriever.probe(
                entity,
                category=args.get("category"),
                min_trust=_safe_float(args.get("min_trust")),
                limit=int(args.get("limit") or 10),
            )
            return {"success": True, "action": "probe", "results": results}

        if action == "related":
            entity = args.get("entity")
            if not entity:
                return {"success": False, "error": "entity is required for related"}
            results = self._retriever.related(
                entity,
                category=args.get("category"),
                min_trust=_safe_float(args.get("min_trust")),
                limit=int(args.get("limit") or 10),
            )
            return {"success": True, "action": "related", "results": results}

        if action == "reason":
            entities = args.get("entities") or []
            if isinstance(entities, str):
                # LLMs sometimes pass a comma-separated string by mistake.
                entities = [e.strip() for e in entities.split(",") if e.strip()]
            if not entities:
                return {"success": False, "error": "entities is required for reason"}
            results = self._retriever.reason(
                list(entities),
                category=args.get("category"),
                min_trust=_safe_float(args.get("min_trust")),
                limit=int(args.get("limit") or 10),
            )
            return {"success": True, "action": "reason", "results": results}

        if action == "contradict":
            results = self._retriever.contradict(
                category=args.get("category"),
                threshold=float(args.get("threshold") or 0.4),
                limit=int(args.get("limit") or 5),
            )
            return {"success": True, "action": "contradict", "results": results}

        if action == "update":
            fact_id = args.get("fact_id")
            if fact_id is None:
                return {"success": False, "error": "fact_id is required for update"}
            return self._store.update_fact(
                int(fact_id),
                content=args.get("content"),
                category=args.get("category"),
                tags=args.get("tags"),
                trust_delta=_safe_float(args.get("trust_delta")),
            )

        if action == "remove":
            fact_id = args.get("fact_id")
            if fact_id is None:
                return {"success": False, "error": "fact_id is required for remove"}
            return self._store.remove_fact(int(fact_id))

        if action == "list":
            return {
                "success": True,
                "action": "list",
                "results": self._store.list_facts(
                    category=args.get("category"),
                    min_trust=float(args.get("min_trust") or 0.0),
                    limit=int(args.get("limit") or 20),
                ),
            }

        return {"success": False, "error": f"unknown action: {action}"}

    # ---------------------------------------------------------------- #
    # _handle_fact_feedback
    # ---------------------------------------------------------------- #

    def _handle_fact_feedback(self, args: dict) -> dict:
        if self._store is None:
            return {"success": False, "error": "holographic memory not initialized"}
        fact_id = args.get("fact_id")
        action = args.get("action")
        if fact_id is None:
            return {"success": False, "error": "fact_id is required"}
        if not action:
            return {"success": False, "error": "action is required"}
        return self._store.record_feedback(
            int(fact_id),
            str(action),
            comment=args.get("comment"),
        )

    # ---------------------------------------------------------------- #
    # Misc helpers (used by SiadaRunner / tests)
    # ---------------------------------------------------------------- #

    def fact_count(self, *, category: Optional[str] = None) -> int:
        """Return total facts in the store (or in a single category)."""
        return self._store.fact_count(category=category) if self._store else 0

    def is_ready(self) -> bool:
        """True after ``initialize`` has succeeded."""
        return self._store is not None and self._retriever is not None


def _safe_float(value: Any) -> Optional[float]:
    """Best-effort float coercion; returns ``None`` on empty / invalid input."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
