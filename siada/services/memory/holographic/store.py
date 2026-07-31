"""SQLite-backed fact storage for holographic memory.

Schema (see design_docs/siada-holographic-memory-introduction.md §4):
- ``facts``         — atomic content + meta (trust, retrieval_count, hrr_vector BLOB)
- ``entities``      — canonical entity table with aliases
- ``fact_entities`` — many-to-many link
- ``facts_fts``     — FTS5 virtual table (jieba-tokenized via custom SQL function)
- ``memory_banks``  — per-category bundled HRR vectors (HRR superposition cache)

Three triggers keep ``facts_fts`` in sync with ``facts`` (insert / delete / update).
The triggers reference a Python-side ``siada_jieba_tokenize`` function that we
register on every connection.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from siada.services.memory.holographic import hrr
from siada.services.memory.holographic.entity_extractor import extract_entities

# Suppress jieba pkg_resources warning the same way memory_db.py does.
with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore", message="pkg_resources is deprecated", category=UserWarning,
    )
    warnings.filterwarnings("ignore", category=SyntaxWarning, module="jieba")
    import jieba

logger = logging.getLogger("siada.holographic.store")
jieba.setLogLevel(logging.WARNING)


# Trust score deltas for fact_feedback. Asymmetric on purpose: bad facts
# should sink twice as fast as good facts can climb. See hermes §7.2.
HELPFUL_DELTA = 0.05
UNHELPFUL_DELTA = -0.10
CORRECT_DELTA = 0.10  # reserved for an explicit "user confirmed" signal

# Safety cap for content length. LLMs have been observed to dump multi-paragraph
# blobs into ``add_fact``; truncating here keeps facts atomic and the FTS index
# trim. Excess content can always be split into multiple facts.
MAX_CONTENT_LENGTH = 2000


_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    fact_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    content         TEXT NOT NULL UNIQUE,
    category        TEXT DEFAULT 'general',
    tags            TEXT DEFAULT '',
    trust_score     REAL DEFAULT 0.5,
    retrieval_count INTEGER DEFAULT 0,
    helpful_count   INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    hrr_vector      BLOB
);

CREATE INDEX IF NOT EXISTS idx_facts_trust    ON facts(trust_score DESC);
CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);

CREATE TABLE IF NOT EXISTS entities (
    entity_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    name_lc     TEXT NOT NULL,
    entity_type TEXT DEFAULT 'unknown',
    aliases     TEXT DEFAULT '',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_entities_name_lc ON entities(name_lc);

CREATE TABLE IF NOT EXISTS fact_entities (
    fact_id   INTEGER NOT NULL REFERENCES facts(fact_id) ON DELETE CASCADE,
    entity_id INTEGER NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
    PRIMARY KEY (fact_id, entity_id)
);

CREATE TABLE IF NOT EXISTS memory_banks (
    bank_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_name        TEXT NOT NULL UNIQUE,
    vector           BLOB NOT NULL,
    dim              INTEGER NOT NULL,
    fact_count       INTEGER DEFAULT 0,
    complex_sum_real BLOB,
    complex_sum_imag BLOB,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    content,
    tags,
    content=facts,
    content_rowid=fact_id,
    tokenize='unicode61'
);
"""

# Triggers reference siada_jieba_tokenize() registered on the connection.
# When jieba is unavailable the function returns the raw string and FTS5
# falls back to its native unicode61 tokenizer (English fine, Chinese degraded).
_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, content, tags)
        VALUES (new.fact_id, siada_jieba_tokenize(new.content), new.tags);
END;

CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, content, tags)
        VALUES ('delete', old.fact_id,
                siada_jieba_tokenize(old.content), old.tags);
END;

CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, content, tags)
        VALUES ('delete', old.fact_id,
                siada_jieba_tokenize(old.content), old.tags);
    INSERT INTO facts_fts(rowid, content, tags)
        VALUES (new.fact_id,
                siada_jieba_tokenize(new.content), new.tags);
END;
"""


def _siada_jieba_tokenize(text: Optional[str]) -> str:
    """SQL-callable text preprocessor: jieba-segment then space-join.

    Mirrors ``MemoryDatabase._prepare_text_for_fts`` so both indexes stay
    consistent in their tokenization.
    """
    if not text:
        return ""
    try:
        return " ".join(jieba.cut(text))
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug("siada_jieba_tokenize failed: %s", exc)
        return text


class FactStore:
    """SQLite + FTS5 + HRR-vector storage for atomic facts."""

    def __init__(
        self,
        db_path: Path,
        *,
        hrr_dim: int = 1024,
        hrr_enabled: bool = True,
        default_trust: float = 0.5,
        custom_dict: Optional[Iterable[str]] = None,
    ):
        self.db_path = Path(db_path)
        self.hrr_dim = int(hrr_dim)
        self.hrr_enabled = bool(hrr_enabled)
        self.default_trust = float(default_trust)
        self.custom_dict: List[str] = list(custom_dict or [])

        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._fts_available: bool = False

        self._init_db()

    # ---------------------------------------------------------------- #
    # Lifecycle
    # ---------------------------------------------------------------- #

    def _init_db(self) -> None:
        """Open the connection, register helpers, create schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=10.0,
            isolation_level=None,  # autocommit; we control txns explicitly
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")

        # Best-effort WAL — falls back gracefully on NFS / FUSE / SMB.
        try:
            self._conn.execute("PRAGMA journal_mode=WAL;")
        except sqlite3.OperationalError as exc:
            logger.debug("[holographic] WAL not available, using default: %s", exc)

        # Register jieba tokenizer first; the FTS triggers reference it.
        self._conn.create_function(
            "siada_jieba_tokenize", 1, _siada_jieba_tokenize, deterministic=True,
        )

        # Apply core schema first, then FTS5 (which is optional), then triggers
        # (which need both base table and FTS5 to exist).
        with self._lock:
            self._conn.executescript(_SCHEMA)
            try:
                self._conn.executescript(_FTS_SCHEMA)
                self._fts_available = True
            except sqlite3.OperationalError as exc:
                self._fts_available = False
                logger.warning("[holographic] FTS5 unavailable: %s", exc)
            if self._fts_available:
                self._conn.executescript(_TRIGGERS)

        logger.info(
            "[holographic] FactStore initialized at %s (hrr_dim=%d, hrr_enabled=%s, fts=%s)",
            self.db_path, self.hrr_dim, self.hrr_enabled, self._fts_available,
        )

    @property
    def fts_available(self) -> bool:
        return self._fts_available

    def close(self) -> None:
        """Release the SQLite connection. Safe to call multiple times."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:  # pragma: no cover — defensive
                    pass
                self._conn = None

    def __enter__(self) -> "FactStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ---------------------------------------------------------------- #
    # Entity resolution
    # ---------------------------------------------------------------- #

    def _resolve_entity(self, name: str, etype: str) -> int:
        """Look up an entity by name (case-insensitive); create if missing.

        Three-step search order:
          1. ``name_lc`` exact match (indexed)
          2. ``aliases`` substring match against the comma-padded form
          3. INSERT new row

        ``etype`` is only consulted when creating; existing entities keep their
        original type. The first writer wins.
        """
        name = (name or "").strip()
        if not name:
            raise ValueError("entity name must be non-empty")
        etype = (etype or "unknown").strip() or "unknown"
        name_lc = name.lower()

        cur = self._conn.execute(
            "SELECT entity_id FROM entities WHERE name_lc = ? LIMIT 1",
            (name_lc,),
        )
        row = cur.fetchone()
        if row:
            return int(row["entity_id"])

        # Aliases stored as ',a,b,c,'-padded in the LIKE expression.
        cur = self._conn.execute(
            """
            SELECT entity_id FROM entities
             WHERE aliases != ''
               AND ',' || lower(aliases) || ',' LIKE '%,' || ? || ',%'
             LIMIT 1
            """,
            (name_lc,),
        )
        row = cur.fetchone()
        if row:
            return int(row["entity_id"])

        cur = self._conn.execute(
            "INSERT INTO entities (name, name_lc, entity_type) VALUES (?, ?, ?)",
            (name, name_lc, etype),
        )
        return int(cur.lastrowid)

    def _link_fact_entity(self, fact_id: int, entity_id: int) -> None:
        """Idempotent (fact_id, entity_id) link insertion."""
        self._conn.execute(
            "INSERT OR IGNORE INTO fact_entities (fact_id, entity_id) VALUES (?, ?)",
            (fact_id, entity_id),
        )

    def _entity_names_for_fact(self, fact_id: int) -> List[str]:
        """Return canonical entity names linked to this fact (insertion order)."""
        cur = self._conn.execute(
            """
            SELECT e.name FROM entities e
              JOIN fact_entities fe ON fe.entity_id = e.entity_id
             WHERE fe.fact_id = ?
             ORDER BY fe.rowid
            """,
            (fact_id,),
        )
        return [row["name"] for row in cur.fetchall()]

    # ---------------------------------------------------------------- #
    # HRR vector + bank
    # ---------------------------------------------------------------- #

    def _compute_and_store_hrr(self, fact_id: int, content: str) -> None:
        """Recompute the fact's HRR vector from current entity links + content.

        Caller must invoke this *after* fact_entities have been inserted, so the
        role-bound entity component is included in the vector.
        """
        if not self.hrr_enabled:
            return
        entities = self._entity_names_for_fact(fact_id)
        vector = hrr.encode_fact(content, entities, self.hrr_dim)
        self._conn.execute(
            "UPDATE facts SET hrr_vector = ? WHERE fact_id = ?",
            (hrr.phases_to_bytes(vector), fact_id),
        )

    def _rebuild_bank(self, category: str) -> None:
        """Rebundle every HRR vector in this category into a single bank vector.

        Phase 1 implementation: full rebuild on each write, O(N_cat × dim).
        Phase 2 will reuse ``complex_sum_real/imag`` for incremental updates.
        """
        if not self.hrr_enabled:
            return
        bank_name = f"cat:{category}"
        cur = self._conn.execute(
            "SELECT hrr_vector FROM facts "
            "WHERE category = ? AND hrr_vector IS NOT NULL",
            (category,),
        )
        rows = cur.fetchall()
        if not rows:
            self._conn.execute(
                "DELETE FROM memory_banks WHERE bank_name = ?",
                (bank_name,),
            )
            return

        vectors = [hrr.bytes_to_phases(row["hrr_vector"]) for row in rows]
        bank_vector = hrr.bundle(*vectors)
        hrr.snr_estimate(self.hrr_dim, len(vectors))  # debug-log only

        self._conn.execute(
            """
            INSERT INTO memory_banks (bank_name, vector, dim, fact_count, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(bank_name) DO UPDATE SET
                vector     = excluded.vector,
                dim        = excluded.dim,
                fact_count = excluded.fact_count,
                updated_at = CURRENT_TIMESTAMP
            """,
            (bank_name, hrr.phases_to_bytes(bank_vector), self.hrr_dim, len(vectors)),
        )

    # ---------------------------------------------------------------- #
    # Public CRUD: add / update / remove
    # ---------------------------------------------------------------- #

    def add_fact(
        self,
        content: str,
        *,
        category: str = "general",
        tags: str = "",
    ) -> dict:
        """Insert a new fact (or return the existing one on UNIQUE conflict).

        Side effects in order:
          1. INSERT into ``facts`` (UNIQUE on ``content`` → return existing fact_id)
          2. extract entities → ``_resolve_entity`` → ``_link_fact_entity``
          3. ``_compute_and_store_hrr``
          4. ``_rebuild_bank(category)``

        Returns ``{"success": bool, "fact_id": int, "created": bool, ...}``.
        """
        if not content or not content.strip():
            return {"success": False, "error": "content must be non-empty"}
        content = content.strip()
        if len(content) > MAX_CONTENT_LENGTH:
            content = content[:MAX_CONTENT_LENGTH]
            truncated = True
        else:
            truncated = False
        category = (category or "general").strip() or "general"
        tags = (tags or "").strip()

        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                cur = self._conn.execute(
                    "SELECT fact_id FROM facts WHERE content = ? LIMIT 1",
                    (content,),
                )
                existing = cur.fetchone()
                if existing:
                    self._conn.execute("COMMIT")
                    return {
                        "success": True,
                        "fact_id": int(existing["fact_id"]),
                        "created": False,
                        "truncated": truncated,
                        "duplicate": True,
                    }
                cur = self._conn.execute(
                    """
                    INSERT INTO facts (content, category, tags, trust_score)
                    VALUES (?, ?, ?, ?)
                    """,
                    (content, category, tags, self.default_trust),
                )
                fact_id = int(cur.lastrowid)

                # Extract entities, resolve, link.
                pairs = extract_entities(content, custom_dict=self.custom_dict)
                entity_names: List[str] = []
                for name, etype in pairs:
                    try:
                        eid = self._resolve_entity(name, etype)
                        self._link_fact_entity(fact_id, eid)
                        entity_names.append(name)
                    except Exception as exc:  # pragma: no cover — defensive
                        logger.debug(
                            "entity link failed for %r: %s", name, exc,
                        )

                # HRR after entity links so role-binding sees them.
                self._compute_and_store_hrr(fact_id, content)
                self._rebuild_bank(category)
                self._conn.execute("COMMIT")
            except Exception:
                try:
                    self._conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise

        return {
            "success": True,
            "fact_id": fact_id,
            "created": True,
            "truncated": truncated,
            "duplicate": False,
            "category": category,
            "entities": entity_names,
        }

    def update_fact(
        self,
        fact_id: int,
        *,
        content: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[str] = None,
        trust_delta: Optional[float] = None,
    ) -> dict:
        """Patch an existing fact's content / metadata / trust.

        Recomputes the HRR vector and rebuilds the affected bank(s) when the
        content or category changes.
        """
        if not isinstance(fact_id, int) or fact_id <= 0:
            return {"success": False, "error": "fact_id must be a positive int"}

        sets: List[str] = []
        params: List = []
        with self._lock:
            cur = self._conn.execute(
                "SELECT content, category FROM facts WHERE fact_id = ?",
                (fact_id,),
            )
            row = cur.fetchone()
            if not row:
                return {"success": False, "error": f"fact {fact_id} not found"}
            old_content = row["content"]
            old_category = row["category"]

            new_content = old_content
            new_category = old_category

            if content is not None:
                new_content = content.strip()
                if not new_content:
                    return {"success": False, "error": "content must be non-empty"}
                if len(new_content) > MAX_CONTENT_LENGTH:
                    new_content = new_content[:MAX_CONTENT_LENGTH]
                sets.append("content = ?")
                params.append(new_content)
            if category is not None:
                new_category = (category or "general").strip() or "general"
                sets.append("category = ?")
                params.append(new_category)
            if tags is not None:
                sets.append("tags = ?")
                params.append(tags)
            if trust_delta is not None:
                sets.append(
                    "trust_score = MAX(0.0, MIN(1.0, trust_score + ?))"
                )
                params.append(float(trust_delta))
            if not sets:
                return {"success": True, "fact_id": fact_id, "no_op": True}
            sets.append("updated_at = CURRENT_TIMESTAMP")

            try:
                self._conn.execute("BEGIN IMMEDIATE")
                self._conn.execute(
                    f"UPDATE facts SET {', '.join(sets)} WHERE fact_id = ?",
                    (*params, fact_id),
                )
                # If content changed, refresh entity links + HRR vector.
                if content is not None:
                    self._conn.execute(
                        "DELETE FROM fact_entities WHERE fact_id = ?",
                        (fact_id,),
                    )
                    pairs = extract_entities(
                        new_content, custom_dict=self.custom_dict,
                    )
                    for name, etype in pairs:
                        try:
                            eid = self._resolve_entity(name, etype)
                            self._link_fact_entity(fact_id, eid)
                        except Exception as exc:  # pragma: no cover
                            logger.debug(
                                "entity link failed for %r: %s", name, exc,
                            )
                    self._compute_and_store_hrr(fact_id, new_content)
                # Rebuild bank(s) only when HRR-relevant fields changed.
                if content is not None or category is not None:
                    self._rebuild_bank(new_category)
                    if old_category != new_category:
                        self._rebuild_bank(old_category)
                self._conn.execute("COMMIT")
            except Exception:
                try:
                    self._conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise

        return {"success": True, "fact_id": fact_id}

    def remove_fact(self, fact_id: int) -> dict:
        """Hard-delete a fact and its entity links; rebuilds the affected bank."""
        if not isinstance(fact_id, int) or fact_id <= 0:
            return {"success": False, "error": "fact_id must be a positive int"}
        with self._lock:
            cur = self._conn.execute(
                "SELECT category FROM facts WHERE fact_id = ?",
                (fact_id,),
            )
            row = cur.fetchone()
            if not row:
                return {"success": False, "error": f"fact {fact_id} not found"}
            category = row["category"]
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                self._conn.execute(
                    "DELETE FROM facts WHERE fact_id = ?", (fact_id,),
                )
                # ON DELETE CASCADE handles fact_entities; FTS trigger handles index.
                self._rebuild_bank(category)
                self._conn.execute("COMMIT")
            except Exception:
                try:
                    self._conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
        return {"success": True, "fact_id": fact_id}

    # ---------------------------------------------------------------- #
    # Feedback
    # ---------------------------------------------------------------- #

    def record_feedback(
        self,
        fact_id: int,
        action: str,
        *,
        comment: Optional[str] = None,
    ) -> dict:
        """Apply a trust-score delta. ``action`` ∈ {helpful, unhelpful, correct}."""
        action = (action or "").strip().lower()
        if action == "helpful":
            delta = HELPFUL_DELTA
        elif action == "unhelpful":
            delta = UNHELPFUL_DELTA
        elif action == "correct":
            delta = CORRECT_DELTA
        else:
            return {
                "success": False,
                "error": f"unknown action {action!r}; expected helpful/unhelpful/correct",
            }
        with self._lock:
            cur = self._conn.execute(
                "SELECT trust_score FROM facts WHERE fact_id = ?", (fact_id,),
            )
            row = cur.fetchone()
            if not row:
                return {"success": False, "error": f"fact {fact_id} not found"}
            self._conn.execute(
                """
                UPDATE facts
                   SET trust_score = MAX(0.0, MIN(1.0, trust_score + ?)),
                       helpful_count = helpful_count + ?,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE fact_id = ?
                """,
                (delta, 1 if action != "unhelpful" else 0, fact_id),
            )
            cur = self._conn.execute(
                "SELECT trust_score FROM facts WHERE fact_id = ?", (fact_id,),
            )
            new_trust = float(cur.fetchone()["trust_score"])
        if comment:
            logger.debug(
                "[holographic] feedback fact=%d action=%s comment=%r",
                fact_id, action, comment[:200],
            )
        return {
            "success": True,
            "fact_id": fact_id,
            "action": action,
            "trust_score": new_trust,
            "delta": delta,
        }

    # ---------------------------------------------------------------- #
    # Read / list
    # ---------------------------------------------------------------- #

    def get_fact(self, fact_id: int) -> Optional[dict]:
        """Fetch a single fact (without HRR vector). Returns None if missing."""
        cur = self._conn.execute(
            """
            SELECT fact_id, content, category, tags, trust_score,
                   retrieval_count, helpful_count, created_at, updated_at
              FROM facts WHERE fact_id = ?
            """,
            (fact_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def list_facts(
        self,
        *,
        category: Optional[str] = None,
        min_trust: float = 0.0,
        limit: int = 50,
    ) -> List[dict]:
        """List facts ordered by trust desc, optionally filtered by category."""
        sql = (
            "SELECT fact_id, content, category, tags, trust_score, "
            "retrieval_count, helpful_count, created_at, updated_at "
            "FROM facts WHERE trust_score >= ?"
        )
        params: List = [float(min_trust)]
        if category:
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY trust_score DESC, updated_at DESC LIMIT ?"
        params.append(int(limit))
        cur = self._conn.execute(sql, tuple(params))
        return [dict(row) for row in cur.fetchall()]

    def increment_retrieval_count(self, fact_ids: Iterable[int]) -> None:
        """Bump retrieval_count for a batch of facts. Best-effort, never raises."""
        ids = [int(fid) for fid in fact_ids if fid is not None]
        if not ids:
            return
        try:
            placeholders = ",".join("?" * len(ids))
            with self._lock:
                self._conn.execute(
                    f"UPDATE facts SET retrieval_count = retrieval_count + 1 "
                    f"WHERE fact_id IN ({placeholders})",
                    tuple(ids),
                )
        except Exception as exc:  # pragma: no cover
            logger.debug("[holographic] increment_retrieval_count failed: %s", exc)

    def fact_count(self, *, category: Optional[str] = None) -> int:
        """Return the total number of facts (optionally filtered by category)."""
        if category:
            cur = self._conn.execute(
                "SELECT COUNT(*) AS n FROM facts WHERE category = ?",
                (category,),
            )
        else:
            cur = self._conn.execute("SELECT COUNT(*) AS n FROM facts")
        return int(cur.fetchone()["n"])

    def categories(self) -> List[Tuple[str, int]]:
        """Return ``[(category, count), ...]`` sorted by count desc."""
        cur = self._conn.execute(
            "SELECT category, COUNT(*) AS n FROM facts "
            "GROUP BY category ORDER BY n DESC"
        )
        return [(row["category"], int(row["n"])) for row in cur.fetchall()]

    # ---------------------------------------------------------------- #
    # Helpers for FactRetriever
    # ---------------------------------------------------------------- #

    def fts_candidates(
        self,
        query: str,
        *,
        limit: int = 30,
        category: Optional[str] = None,
    ) -> List[dict]:
        """Generate FTS5 candidates with normalized rank in [0, 1].

        Uses jieba-tokenized OR-of-tokens query to match the way content was
        indexed at write time. Falls back to LIKE if FTS5 isn't available or the
        compiled query can't parse.
        """
        if not query or not query.strip():
            return []
        if not self._fts_available:
            return self._fallback_like_candidates(query, limit=limit, category=category)
        # Build OR-joined token query, escaping FTS5 special characters.
        tokens = [t for t in jieba.cut(query.strip()) if t and t.strip()]
        if not tokens:
            tokens = [query.strip()]
        # Wrap each token in double quotes to defang FTS5 operators.
        safe_tokens = []
        for tok in tokens:
            tok = tok.replace('"', '""').strip()
            if tok:
                safe_tokens.append(f'"{tok}"')
        if not safe_tokens:
            return []
        fts_query = " OR ".join(safe_tokens)

        sql = (
            "SELECT f.fact_id, f.content, f.category, f.tags, f.trust_score, "
            "f.retrieval_count, f.helpful_count, f.created_at, f.updated_at, "
            "f.hrr_vector, fts.rank AS fts_rank "
            "FROM facts_fts fts JOIN facts f ON f.fact_id = fts.rowid "
            "WHERE facts_fts MATCH ?"
        )
        params: List = [fts_query]
        if category:
            sql += " AND f.category = ?"
            params.append(category)
        sql += " ORDER BY fts.rank LIMIT ?"
        params.append(int(limit))

        try:
            rows = list(self._conn.execute(sql, tuple(params)).fetchall())
        except sqlite3.OperationalError as exc:
            logger.debug("[holographic] FTS5 query failed (%s); falling back to LIKE", exc)
            return self._fallback_like_candidates(query, limit=limit, category=category)

        if not rows:
            return []
        # FTS5 rank is negative: smaller (more negative) is better.
        # Normalize to [0, 1] within this batch.
        raw_ranks = [abs(r["fts_rank"]) for r in rows]
        max_rank = max(raw_ranks) if raw_ranks else 1.0
        out: List[dict] = []
        for row, raw in zip(rows, raw_ranks):
            d = dict(row)
            d["fts_rank_norm"] = (raw / max_rank) if max_rank > 0 else 0.0
            out.append(d)
        return out

    def _fallback_like_candidates(
        self,
        query: str,
        *,
        limit: int = 30,
        category: Optional[str] = None,
    ) -> List[dict]:
        """Last-resort LIKE search for environments without FTS5."""
        like_pattern = f"%{query.strip()}%"
        sql = (
            "SELECT fact_id, content, category, tags, trust_score, "
            "retrieval_count, helpful_count, created_at, updated_at, hrr_vector "
            "FROM facts WHERE content LIKE ?"
        )
        params: List = [like_pattern]
        if category:
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY trust_score DESC LIMIT ?"
        params.append(int(limit))
        rows = list(self._conn.execute(sql, tuple(params)).fetchall())
        out: List[dict] = []
        for row in rows:
            d = dict(row)
            # No real rank; assign a flat score so downstream weighting still works.
            d["fts_rank_norm"] = 0.5
            out.append(d)
        return out

    def iter_facts_with_vectors(
        self,
        *,
        category: Optional[str] = None,
        min_trust: float = 0.0,
        require_hrr: bool = True,
    ) -> List[dict]:
        """Stream all facts (with HRR vectors) for full-scan retrieval actions."""
        sql = (
            "SELECT fact_id, content, category, tags, trust_score, "
            "retrieval_count, helpful_count, created_at, updated_at, hrr_vector "
            "FROM facts WHERE trust_score >= ?"
        )
        params: List = [float(min_trust)]
        if category:
            sql += " AND category = ?"
            params.append(category)
        if require_hrr:
            sql += " AND hrr_vector IS NOT NULL"
        cur = self._conn.execute(sql, tuple(params))
        return [dict(row) for row in cur.fetchall()]

    def get_bank_vector(self, category: str) -> Optional[bytes]:
        """Return the raw HRR bank BLOB for a category, or None if missing."""
        cur = self._conn.execute(
            "SELECT vector FROM memory_banks WHERE bank_name = ?",
            (f"cat:{category}",),
        )
        row = cur.fetchone()
        return row["vector"] if row else None

    def get_entities_for_facts(self, fact_ids: Iterable[int]) -> dict[int, set[str]]:
        """Bulk-fetch lowercased entity name sets for ``contradict`` overlap calc."""
        ids = [int(fid) for fid in fact_ids if fid is not None]
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        cur = self._conn.execute(
            f"""
            SELECT fe.fact_id, e.name_lc FROM fact_entities fe
              JOIN entities e ON e.entity_id = fe.entity_id
             WHERE fe.fact_id IN ({placeholders})
            """,
            tuple(ids),
        )
        out: dict[int, set[str]] = {fid: set() for fid in ids}
        for row in cur.fetchall():
            out[int(row["fact_id"])].add(row["name_lc"])
        return out

    def rebuild_all_vectors(self, *, dim: Optional[int] = None) -> int:
        """Recompute every fact's HRR vector and every category bank.

        Used on ``hrr_dim`` changes (drift between conf and on-disk dim) and as
        a recovery hook. Returns the number of facts processed.
        """
        if not self.hrr_enabled:
            return 0
        if dim is not None:
            self.hrr_dim = int(dim)
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                cur = self._conn.execute("SELECT fact_id, content FROM facts")
                rows = list(cur.fetchall())
                for row in rows:
                    self._compute_and_store_hrr(int(row["fact_id"]), row["content"])
                cats = {row["category"] for row in self._conn.execute(
                    "SELECT DISTINCT category FROM facts"
                ).fetchall()}
                # Drop any banks whose category no longer exists, then rebuild
                # the live ones so dim mismatches don't linger.
                self._conn.execute(
                    "DELETE FROM memory_banks WHERE bank_name NOT IN ({})".format(
                        ",".join("?" * len(cats))
                    ) if cats else "DELETE FROM memory_banks",
                    tuple(f"cat:{c}" for c in cats),
                )
                for cat in cats:
                    self._rebuild_bank(cat)
                self._conn.execute("COMMIT")
            except Exception:
                try:
                    self._conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
        return len(rows)

    def get_existing_bank_dim(self) -> Optional[int]:
        """Read the ``dim`` of any existing memory bank, or None when empty.

        Used by the provider on startup to detect ``hrr_dim`` drift between
        config and on-disk vectors.
        """
        cur = self._conn.execute("SELECT dim FROM memory_banks LIMIT 1")
        row = cur.fetchone()
        return int(row["dim"]) if row else None
