"""Playbook store: SQLite queue, lease, versioning, evidence validation and
idempotent delta merging for the Browser Skill Graph (design §4 and §7).

The SQLite file is the single source of truth: raw execution records, the
pending/claimed task queue, playbook entries, per-capacity versions, delta
audits and old snapshots all live in one database under the skills root
(``browser_skills/playbooks.sqlite3``).

Reliability rules implemented here:
- short-lived connections, parameterized SQL, ``busy_timeout`` (standard lib
  only, no external services);
- ``claim`` uses a cross-process lease + token; expired leases are recoverable;
- one transaction per ``apply_delta``: token/version/schema/evidence checks,
  knowledge update, processed marker and audit row either all commit or none
  do; a second identical submission returns the stored result (idempotent);
- derived ``SKILL.md`` files are written via unique temp file + atomic replace
  and can always be rebuilt from the database.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import time
from pathlib import Path

from . import paths
from .models import ExecutionRecord, VerificationResult

_LEASE_SECONDS = 120.0
_MAX_BACKOFF = 300.0
# 2**9 (512 s) already exceeds _MAX_BACKOFF; capping here keeps the exponent
# computation far below the float overflow boundary even for huge attempt counts.
_BACKOFF_EXPONENT_CAP = 60
_BUSY_TIMEOUT_MS = 5000
_DB_FILENAME = "playbooks.sqlite3"

_SOURCES = ("agent", "demonstration")
_VERIFICATION_STATUSES = ("success", "failure", "unknown")
_KINDS = ("strategy", "pitfall", "guard", "verification")
_SIGNALS = ("helpful", "harmful")

_OP_KEYS = {
    "add": ("kind", "content", "condition", "evidence_ids"),
    "update": ("entry_id", "kind", "content", "condition", "evidence_ids"),
    "retire": ("entry_id", "reason", "evidence_ids"),
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    capacity_id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS entries (
    capacity_id TEXT NOT NULL,
    entry_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    condition TEXT NOT NULL,
    status TEXT NOT NULL,
    helpful INTEGER NOT NULL DEFAULT 0,
    harmful INTEGER NOT NULL DEFAULT 0,
    evidence_ids TEXT NOT NULL,
    PRIMARY KEY (capacity_id, entry_id)
);
CREATE INDEX IF NOT EXISTS idx_entries_capacity_status
    ON entries(capacity_id, status);

CREATE TABLE IF NOT EXISTS executions (
    execution_id TEXT PRIMARY KEY,
    capacity_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    goal TEXT NOT NULL,
    events TEXT NOT NULL,
    verification TEXT NOT NULL,
    source TEXT NOT NULL,
    used_entry_ids TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    token TEXT,
    lease_until REAL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at REAL NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    result_snapshot TEXT
);
CREATE INDEX IF NOT EXISTS idx_executions_claim
    ON executions(status, lease_until, next_attempt_at);

CREATE TABLE IF NOT EXISTS deltas (
    execution_id TEXT PRIMARY KEY,
    capacity_id TEXT NOT NULL,
    from_version INTEGER NOT NULL,
    to_version INTEGER NOT NULL,
    old_snapshot TEXT NOT NULL,
    operations TEXT NOT NULL,
    feedback TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""

_WS_RUN = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Collapse whitespace runs and trim; the deterministic identity form."""
    return _WS_RUN.sub(" ", text).strip()


def _entry_id(capacity_id: str, kind: str, condition: str, content: str, seq: int) -> str:
    """Stable 64-hex id from capacity + normalized identity + creation seq.

    The creation sequence keeps ids stable across content updates (an updated
    entry keeps its id) while still allowing the pre-update content to be
    added again as a genuinely new entry. Identical first-time adds in
    identically-built stores get the same id.
    """
    key = "\x00".join(
        (capacity_id, kind, _normalize(condition), _normalize(content), str(seq))
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class _Sequence:
    """Monotonic per-transaction counter for newly created entry ids."""

    def __init__(self, start: int):
        self.value = start

    def next(self) -> int:
        current = self.value
        self.value += 1
        return current


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


def _merge_evidence(existing: list[str], extra: list[str]) -> list[str]:
    return _dedupe(list(existing) + list(extra))


def _validate_domain(domain: str) -> str:
    """Reject anything that could escape the skills root as a path segment."""
    if not isinstance(domain, str) or not domain:
        raise ValueError("domain must be a non-empty string")
    if domain != domain.strip() or domain in (".", ".."):
        raise ValueError(f"unsafe domain: {domain!r}")
    if any(ch in domain for ch in ("/", "\\", "\x00")):
        raise ValueError(f"unsafe domain: {domain!r}")
    part = Path(domain)
    if part.is_absolute() or len(part.parts) != 1 or part.name != domain:
        raise ValueError(f"unsafe domain: {domain!r}")
    return domain


def _split_capacity(capacity_id: str) -> tuple[str, str]:
    if not isinstance(capacity_id, str) or "::" not in capacity_id:
        raise ValueError(f"invalid capacity_id: {capacity_id!r}")
    domain_part, name = capacity_id.split("::", 1)
    if not domain_part or not name:
        raise ValueError(f"invalid capacity_id: {capacity_id!r}")
    return domain_part, name


def _validate_record(record: ExecutionRecord) -> None:
    if not isinstance(record, ExecutionRecord):
        raise ValueError("record must be an ExecutionRecord")
    if not isinstance(record.execution_id, str) or not record.execution_id.strip():
        raise ValueError("execution_id must be a non-empty string")
    capacity_domain, _ = _split_capacity(record.capacity_id)
    if capacity_domain != record.domain:
        raise ValueError("capacity_id must belong to the record domain")
    if not isinstance(record.goal, str) or not record.goal.strip():
        raise ValueError("goal must be a non-empty string")
    if record.source not in _SOURCES:
        raise ValueError(f"invalid source: {record.source!r}")
    verification = record.verification
    if not isinstance(verification, VerificationResult):
        raise ValueError("verification must be a VerificationResult")
    if verification.status not in _VERIFICATION_STATUSES:
        raise ValueError(f"invalid verification status: {verification.status!r}")
    if not isinstance(record.events, list) or not all(
        isinstance(event, dict) for event in record.events
    ):
        raise ValueError("events must be a list of dicts")
    if not isinstance(record.used_entry_ids, list) or not all(
        isinstance(entry_id, str) for entry_id in record.used_entry_ids
    ):
        raise ValueError("used_entry_ids must be a list of strings")


def _fill_event_ids(record: ExecutionRecord) -> list[dict]:
    """Deep-copy events, filling missing ``event_id`` with ``id:index``.

    An event that explicitly carries an empty ``event_id`` is rejected: only a
    completely absent key gets the derived id. Identity fields (event_id,
    used_entry_ids) are never changed by sanitization.
    """
    events = copy.deepcopy(record.events)
    for index, event in enumerate(events):
        if "event_id" not in event:
            filled = dict(event)
            filled["event_id"] = f"{record.execution_id}:{index}"
            events[index] = filled
        else:
            event_id = event["event_id"]
            if not isinstance(event_id, str) or not event_id.strip():
                raise ValueError("event_id must be a non-empty string when present")
    ids = [str(event.get("event_id", "")) for event in events]
    if any(not event_id for event_id in ids):
        raise ValueError("every event needs a non-empty event_id")
    if len(ids) != len(set(ids)):
        raise ValueError("event_ids must be unique within a record")
    for event in events:
        try:
            json.dumps(event, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as exc:  # sets, NaN, ...
            raise ValueError(f"events must be JSON-serializable: {exc}") from exc
    return events


def _record_payload(record: ExecutionRecord, events: list[dict]) -> dict:
    return {
        "execution_id": record.execution_id,
        "capacity_id": record.capacity_id,
        "domain": record.domain,
        "goal": record.goal,
        "events": json.dumps(events, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
        "verification": json.dumps(
            {"status": record.verification.status, "reason": record.verification.reason},
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ),
        "source": record.source,
        "used_entry_ids": json.dumps(
            record.used_entry_ids, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ),
    }


def _row_to_record(row: sqlite3.Row) -> ExecutionRecord:
    verification = json.loads(row["verification"])
    return ExecutionRecord(
        execution_id=row["execution_id"],
        capacity_id=row["capacity_id"],
        domain=row["domain"],
        goal=row["goal"],
        events=json.loads(row["events"]),
        verification=VerificationResult(verification["status"], verification.get("reason", "")),
        source=row["source"],
        used_entry_ids=json.loads(row["used_entry_ids"]),
    )


def _entry_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["entry_id"],
        "kind": row["kind"],
        "content": row["content"],
        "condition": row["condition"],
        "status": row["status"],
        "helpful": row["helpful"],
        "harmful": row["harmful"],
        "evidence_ids": json.loads(row["evidence_ids"]),
    }


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class PlaybookStore:
    """SQLite-backed playbook: queue + lease, entries, versions, audit."""

    def __init__(self, path: Path | None = None):
        if path is None:
            path = paths.get_skills_root() / _DB_FILENAME
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existed = self.path.exists()
        connection = self._connect()
        try:
            connection.executescript(_SCHEMA)
            connection.commit()
        finally:
            connection.close()
        if not existed:
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=_BUSY_TIMEOUT_MS / 1000.0)
        connection.isolation_level = None  # autocommit; explicit BEGIN IMMEDIATE
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
        return connection

    # ------------------------------------------------------------------ queue

    def enqueue(self, record: ExecutionRecord) -> bool:
        """Insert one execution record. Idempotent per execution_id.

        Returns True on insert; False when an identical record already exists;
        raises ValueError when the same id has a different payload or any
        validation rule is violated.
        """
        _validate_record(record)
        domain = _validate_domain(record.domain)
        events = _fill_event_ids(record)
        payload = _record_payload(record, events)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM executions WHERE execution_id = ?", (record.execution_id,)
            ).fetchone()
            if row is not None:
                connection.execute("ROLLBACK")
                if _same_record(row, payload):
                    return False
                raise ValueError(
                    f"execution {record.execution_id} already exists with a different payload"
                )
            snap = connection.execute(
                "SELECT domain FROM snapshots WHERE capacity_id = ?",
                (record.capacity_id,),
            ).fetchone()
            if snap is not None and snap["domain"] != domain:
                connection.execute("ROLLBACK")
                raise ValueError(
                    f"capacity {record.capacity_id} is bound to domain "
                    f"{snap['domain']!r}, not {domain!r}"
                )
            connection.execute(
                "INSERT INTO executions (execution_id, capacity_id, domain, goal, events,"
                " verification, source, used_entry_ids) VALUES (?,?,?,?,?,?,?,?)",
                (
                    record.execution_id,
                    record.capacity_id,
                    domain,
                    record.goal,
                    payload["events"],
                    payload["verification"],
                    record.source,
                    payload["used_entry_ids"],
                ),
            )
            connection.execute(
                "INSERT OR IGNORE INTO snapshots (capacity_id, domain, version) VALUES (?,?,0)",
                (record.capacity_id, domain),
            )
            connection.execute("COMMIT")
            return True
        except Exception:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            connection.close()

    def pending_count(self) -> int:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM executions WHERE status IN ('pending','claimed')"
            ).fetchone()
        finally:
            connection.close()
        return row["count"]

    def claim(self) -> dict | None:
        """Claim the next eligible execution with a cross-process lease.

        One consumer for the whole database at a time (design §4): if any
        lease is still live, ``claim`` returns None. Otherwise the earliest
        pending (or expired-lease) record is claimed with a fresh token and a
        120 s lease. Returns ``{"record", "token", "version"}`` or None.
        """
        now = time.time()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            busy = connection.execute(
                "SELECT 1 FROM executions WHERE status = 'claimed' AND lease_until > ? LIMIT 1",
                (now,),
            ).fetchone()
            if busy is not None:
                connection.execute("ROLLBACK")
                return None
            candidate = connection.execute(
                "SELECT execution_id FROM executions WHERE "
                "(status = 'pending' AND next_attempt_at <= ?) OR "
                "(status = 'claimed' AND lease_until <= ?) "
                "ORDER BY rowid LIMIT 1",
                (now, now),
            ).fetchone()
            if candidate is None:
                connection.execute("ROLLBACK")
                return None
            token = os.urandom(16).hex()
            deadline = now + _LEASE_SECONDS
            connection.execute(
                "UPDATE executions SET status='claimed', token=?, lease_until=?,"
                " attempts=attempts + 1, last_error='' WHERE execution_id=?",
                (token, deadline, candidate["execution_id"]),
            )
            full = connection.execute(
                "SELECT * FROM executions WHERE execution_id = ?",
                (candidate["execution_id"],),
            ).fetchone()
            snap = connection.execute(
                "SELECT version FROM snapshots WHERE capacity_id = ?",
                (full["capacity_id"],),
            ).fetchone()
            connection.execute("COMMIT")
            return {
                "record": _row_to_record(full),
                "token": token,
                "version": snap["version"] if snap else 0,
            }
        except Exception:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            connection.close()

    def release(self, execution_id: str, token: str, error: str = "") -> None:
        """Return a claimed execution to pending; no-op for stale tokens.

        With a non-empty error the retry is backed off exponentially
        (capped at 300 s) using the record's attempt counter; an empty error
        allows an immediate retry. Releasing with a token that does not own
        the current lease changes nothing.
        """
        if not isinstance(token, str):
            return
        now = time.time()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status, token, attempts FROM executions WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
            if row is None or row["status"] != "claimed" or row["token"] != token:
                connection.execute("ROLLBACK")
                return
            if error:
                exponent = min(max(int(row["attempts"]), 1), _BACKOFF_EXPONENT_CAP)
                backoff = min(_MAX_BACKOFF, 2.0 ** exponent)
                next_attempt_at = now + backoff
            else:
                next_attempt_at = now
            connection.execute(
                "UPDATE executions SET status='pending', next_attempt_at=?,"
                " last_error=?, token=NULL, lease_until=NULL"
                " WHERE execution_id=? AND token=?",
                (next_attempt_at, error or "", execution_id, token),
            )
            connection.execute("COMMIT")
        except Exception:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            connection.close()

    def renew(self, execution_id: str, token: str) -> bool:
        """Extend a live claimed lease by another 120 s.

        Returns True only when the record is currently claimed by ``token``
        and the lease has not expired yet; a wrong token, an unknown record,
        a released record, or an expired lease all return False — renew never
        resurrects a dead lease.
        """
        if not isinstance(token, str):
            return False
        now = time.time()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status, token, lease_until FROM executions WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
            if row is None or row["status"] != "claimed" or row["token"] != token:
                connection.execute("ROLLBACK")
                return False
            if row["lease_until"] is None or row["lease_until"] <= now:
                connection.execute("ROLLBACK")
                return False
            connection.execute(
                "UPDATE executions SET lease_until = ? WHERE execution_id = ? AND token = ?",
                (now + _LEASE_SECONDS, execution_id, token),
            )
            connection.execute("COMMIT")
            return True
        except Exception:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            connection.close()

    def get_record(self, execution_id: str) -> ExecutionRecord | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM executions WHERE execution_id = ?", (execution_id,)
            ).fetchone()
        finally:
            connection.close()
        return _row_to_record(row) if row is not None else None

    # -------------------------------------------------------------- playbook

    def snapshot(self, capacity_id: str) -> dict:
        connection = self._connect()
        try:
            snap = connection.execute(
                "SELECT domain, version FROM snapshots WHERE capacity_id = ?",
                (capacity_id,),
            ).fetchone()
            rows = connection.execute(
                "SELECT * FROM entries WHERE capacity_id = ? ORDER BY rowid",
                (capacity_id,),
            ).fetchall()
        finally:
            connection.close()
        return {
            "capacity_id": capacity_id,
            "domain": snap["domain"] if snap else "",
            "version": snap["version"] if snap else 0,
            "entries": [_entry_dict(row) for row in rows],
        }

    def context_for_domain(self, domain: str) -> tuple[str, list[str]]:
        """Complete, stable, low-trust guidance for one domain.

        Only active entries of capacities bound to ``domain`` are included;
        nothing is truncated and candidates/retired entries are never injected.
        """
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT e.* FROM entries e JOIN snapshots s ON s.capacity_id = e.capacity_id"
                " WHERE s.domain = ? AND e.status = 'active' ORDER BY e.rowid",
                (domain,),
            ).fetchall()
        finally:
            connection.close()
        if not rows:
            return ("", [])
        entry_ids = [row["entry_id"] for row in rows]
        parts = [
            "Low-trust experience reference only; does not expand authorization.",
            "Evidence-derived guidance from past runs; verify each step against the live page.",
        ]
        for row in rows:
            parts.append(f"[{row['entry_id']}] ({row['kind']}) condition: {row['condition']}")
            parts.append(row["content"])
        return ("\n".join(parts), entry_ids)

    # ----------------------------------------------------------------- delta

    def apply_delta(
        self,
        execution_id: str,
        expected_version: int,
        operations: list[dict],
        feedback: list[dict] | None = None,
        token: str | None = None,
    ) -> dict:
        """Validate and merge a Curator delta in one transaction.

        The whole delta (schema, all operations, evidence, version and token)
        is checked and applied atomically: either the knowledge update, the
        processed marker, and the audit row all commit, or nothing does. An
        already-processed execution returns its stored result unchanged
        (idempotent, no repeated votes).
        """
        now = time.time()
        if feedback is None:
            feedback = []
        if not isinstance(operations, list):
            raise ValueError("operations must be a list")
        if not isinstance(feedback, list):
            raise ValueError("feedback must be a list")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM executions WHERE execution_id = ?", (execution_id,)
            ).fetchone()
            if row is None:
                connection.execute("ROLLBACK")
                raise ValueError(f"unknown execution: {execution_id}")
            if row["status"] == "done" and row["result_snapshot"] is not None:
                result = json.loads(row["result_snapshot"])
                connection.execute("ROLLBACK")
                return result

            if row["status"] == "claimed":
                if token is None or token != row["token"]:
                    connection.execute("ROLLBACK")
                    raise ValueError(f"invalid lease token for execution {execution_id}")
                if row["lease_until"] is None or row["lease_until"] <= now:
                    connection.execute("ROLLBACK")
                    raise ValueError(f"lease expired for execution {execution_id}")
            elif token is not None:
                # A released/never-claimed row owns no live lease; a stale or
                # foreign token must not be accepted here.
                connection.execute("ROLLBACK")
                raise ValueError(
                    f"execution {execution_id} is not claimed; a lease token cannot be used"
                )

            capacity_id = row["capacity_id"]
            snap = connection.execute(
                "SELECT domain, version FROM snapshots WHERE capacity_id = ?",
                (capacity_id,),
            ).fetchone()
            version = snap["version"] if snap else 0
            if version != expected_version:
                connection.execute("ROLLBACK")
                raise ValueError(
                    f"version conflict for execution {execution_id}: "
                    f"expected {expected_version}, current {version}"
                )
            domain = snap["domain"] if snap else row["domain"]
            source = row["source"]
            verification_status = json.loads(row["verification"])["status"]
            verified = source == "agent" and verification_status in ("success", "failure")
            event_ids = {str(event.get("event_id", "")) for event in json.loads(row["events"])}
            used_entry_ids = set(json.loads(row["used_entry_ids"]))

            entry_rows = connection.execute(
                "SELECT * FROM entries WHERE capacity_id = ? ORDER BY rowid", (capacity_id,)
            ).fetchall()
            entries = [_entry_dict(entry_row) for entry_row in entry_rows]
            old_snapshot = {
                "capacity_id": capacity_id,
                "domain": domain,
                "version": version,
                "entries": [_entry_dict(entry_row) for entry_row in entry_rows],
            }

            for op in operations:
                _validate_operation(op, entries, event_ids, verified)
            seq_row = connection.execute(
                "SELECT COALESCE(MAX(rowid), 0) AS max_rowid FROM entries"
            ).fetchone()
            seq = _Sequence(seq_row["max_rowid"] + 1)
            for op in operations:
                _apply_operation(entries, op, verified, capacity_id, seq)
            _validate_feedback(feedback, entries, used_entry_ids, event_ids, verified)
            _apply_feedback(entries, feedback)

            new_version = version + 1
            for entry in entries:
                _upsert_entry(connection, capacity_id, entry)
            connection.execute(
                "INSERT INTO snapshots (capacity_id, domain, version) VALUES (?,?,?)"
                " ON CONFLICT(capacity_id) DO UPDATE SET domain=excluded.domain,"
                " version=excluded.version",
                (capacity_id, domain, new_version),
            )
            result = {
                "capacity_id": capacity_id,
                "domain": domain,
                "version": new_version,
                "entries": entries,
            }
            connection.execute(
                "INSERT INTO deltas (execution_id, capacity_id, from_version, to_version,"
                " old_snapshot, operations, feedback, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    execution_id,
                    capacity_id,
                    version,
                    new_version,
                    _dump_json(old_snapshot),
                    _dump_json(operations),
                    _dump_json(feedback),
                    now,
                ),
            )
            connection.execute(
                "UPDATE executions SET status='done', result_snapshot=?, token=NULL,"
                " lease_until=NULL, next_attempt_at=0 WHERE execution_id=?",
                (_dump_json(result), execution_id),
            )
            connection.execute("COMMIT")
            return result
        except Exception:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            connection.close()

    # ----------------------------------------------------------------- export

    def export_skill(self, capacity_id: str) -> Path:
        """Deterministically render SKILL.md from the SQLite source of truth.

        The file is written via a unique temporary file plus atomic
        ``os.replace``; a failed export never corrupts the previous artifact
        or the database. The target path must stay inside the skills root.
        """
        snap = self.snapshot(capacity_id)
        if not snap["domain"]:
            raise ValueError(f"unknown capacity: {capacity_id}")
        _split_capacity(capacity_id)
        domain = _validate_domain(snap["domain"])
        _, capacity_name = capacity_id.split("::", 1)
        root = paths.get_skills_root().resolve()
        destination = paths.skill_dir_for(domain, capacity_name) / "SKILL.md"
        if not _is_within(destination.resolve(), root):
            raise ValueError("skill path escapes the skills root")
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = render_playbook(snap, include_candidates=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(destination.parent), prefix=".skill-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, destination)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        try:
            os.chmod(destination, 0o600)
        except OSError:
            pass
        return destination


def _same_record(row: sqlite3.Row, payload: dict) -> bool:
    return (
        row["capacity_id"] == payload["capacity_id"]
        and row["domain"] == payload["domain"]
        and row["goal"] == payload["goal"]
        and row["events"] == payload["events"]
        and row["verification"] == payload["verification"]
        and row["source"] == payload["source"]
        and row["used_entry_ids"] == payload["used_entry_ids"]
    )


def _upsert_entry(connection: sqlite3.Connection, capacity_id: str, entry: dict) -> None:
    connection.execute(
        "INSERT INTO entries (capacity_id, entry_id, kind, content, condition, status,"
        " helpful, harmful, evidence_ids) VALUES (?,?,?,?,?,?,?,?,?)"
        " ON CONFLICT(capacity_id, entry_id) DO UPDATE SET kind=excluded.kind,"
        " content=excluded.content, condition=excluded.condition, status=excluded.status,"
        " helpful=excluded.helpful, harmful=excluded.harmful,"
        " evidence_ids=excluded.evidence_ids",
        (
            capacity_id,
            entry["id"],
            entry["kind"],
            entry["content"],
            entry["condition"],
            entry["status"],
            entry["helpful"],
            entry["harmful"],
            _dump_json(entry["evidence_ids"]),
        ),
    )


def _dump_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _validate_operation(
    op: object, entries: list[dict], event_ids: set[str], verified: bool
) -> None:
    if not isinstance(op, dict):
        raise ValueError("operation must be a dict")
    op_type = op.get("op")
    if op_type not in _OP_KEYS:
        raise ValueError(f"invalid operation type: {op_type!r}")
    allowed = set(_OP_KEYS[op_type]) | {"op"}
    if set(op.keys()) != allowed:
        extra = sorted(set(op.keys()) - allowed)
        missing = sorted(allowed - set(op.keys()))
        raise ValueError(f"operation {op_type} has invalid fields: extra={extra} missing={missing}")

    if op_type in ("add", "update"):
        kind = op.get("kind")
        if kind not in _KINDS:
            raise ValueError(f"invalid kind: {kind!r}")
        if not _normalize(op.get("content", "")):
            raise ValueError("content must be non-empty")
        if not _normalize(op.get("condition", "")):
            raise ValueError("condition must be non-empty")

    if op_type in ("update", "retire"):
        if not verified:
            raise ValueError("only verified agent records may update or retire entries")
        entry_id = op.get("entry_id")
        if not isinstance(entry_id, str) or not entry_id:
            raise ValueError("entry_id is required")
        if not any(entry["id"] == entry_id for entry in entries):
            raise ValueError(f"entry {entry_id!r} does not exist in this capacity")

    if op_type == "retire":
        if not _normalize(op.get("reason", "")):
            raise ValueError("retire requires a reason")

    evidence = op.get("evidence_ids")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("evidence_ids must be a non-empty list")
    if not all(isinstance(eid, str) and eid in event_ids for eid in evidence):
        raise ValueError("evidence_ids must reference event_ids of this record")


def _apply_operation(
    entries: list[dict], op: dict, verified: bool, capacity_id: str, seq: _Sequence
) -> None:
    op_type = op["op"]
    if op_type == "add":
        identity = (op["kind"], _normalize(op["content"]), _normalize(op["condition"]))
        match = None
        for entry in entries:
            if (entry["kind"], _normalize(entry["content"]), _normalize(entry["condition"])) == identity:
                match = entry
                break
        if match is None:
            entries.append(
                {
                    "id": _entry_id(
                        capacity_id, op["kind"], op["condition"], op["content"], seq.next()
                    ),
                    "kind": op["kind"],
                    # Keep the original text (edge-trimmed only): normalized
                    # whitespace would destroy meaningful code formatting.
                    "content": op["content"].strip(),
                    "condition": op["condition"].strip(),
                    "status": "active" if verified else "candidate",
                    "helpful": 0,
                    "harmful": 0,
                    "evidence_ids": _dedupe(op["evidence_ids"]),
                }
            )
            return
        match["evidence_ids"] = _merge_evidence(match["evidence_ids"], op["evidence_ids"])
        if verified and match["status"] == "candidate":
            match["status"] = "active"
        return

    target = next(entry for entry in entries if entry["id"] == op["entry_id"])
    if op_type == "update":
        identity = (op["kind"], _normalize(op["content"]), _normalize(op["condition"]))
        for entry in entries:
            if entry["id"] != target["id"] and (
                entry["kind"],
                _normalize(entry["content"]),
                _normalize(entry["condition"]),
            ) == identity:
                raise ValueError("update would create a normalized duplicate")
        target["kind"] = op["kind"]
        target["content"] = op["content"].strip()
        target["condition"] = op["condition"].strip()
        target["evidence_ids"] = _merge_evidence(target["evidence_ids"], op["evidence_ids"])
        if target["status"] != "active":
            target["status"] = "active"  # explicitly revives retired entries
        return

    # retire
    target["status"] = "retired"
    target["evidence_ids"] = _merge_evidence(target["evidence_ids"], op["evidence_ids"])


def _validate_feedback(
    feedback: list[dict],
    entries: list[dict],
    used_entry_ids: set[str],
    event_ids: set[str],
    verified: bool,
) -> None:
    if not feedback:
        return
    if not verified:
        raise ValueError("feedback requires a verified agent record")
    seen: set[str] = set()
    for item in feedback:
        if not isinstance(item, dict):
            raise ValueError("feedback item must be a dict")
        if not set(item.keys()) <= {"entry_id", "signal", "evidence_ids"}:
            raise ValueError(f"feedback has invalid fields: {sorted(item.keys())}")
        entry_id = item.get("entry_id")
        signal = item.get("signal")
        if not isinstance(entry_id, str) or not entry_id:
            raise ValueError("feedback entry_id is required")
        if signal not in _SIGNALS:
            raise ValueError(f"invalid feedback signal: {signal!r}")
        if entry_id in seen:
            raise ValueError(f"duplicate feedback for entry {entry_id}")
        seen.add(entry_id)
        if entry_id not in used_entry_ids:
            raise ValueError(f"feedback entry {entry_id} was not used by this record")
        if not any(entry["id"] == entry_id for entry in entries):
            raise ValueError(f"feedback entry {entry_id} does not exist in this capacity")
        evidence = item.get("evidence_ids")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError("feedback evidence_ids must be a non-empty list")
        if not all(isinstance(eid, str) and eid in event_ids for eid in evidence):
            raise ValueError("feedback evidence_ids must reference event_ids of this record")


def _apply_feedback(entries: list[dict], feedback: list[dict]) -> None:
    for item in feedback or []:
        for entry in entries:
            if entry["id"] == item["entry_id"]:
                if item["signal"] == "helpful":
                    entry["helpful"] += 1
                else:
                    entry["harmful"] += 1
                break


def render_playbook(snapshot: dict, include_candidates: bool = False) -> str:
    """Deterministic Markdown render of a snapshot, stable by entry id.

    Candidates stay out of the default output; the rendered text explicitly
    labels the knowledge as low-trust reference that does not expand
    authorization, and never presents candidate rules as operative.
    """
    entries = snapshot.get("entries", []) or []
    active = sorted(
        (entry for entry in entries if entry.get("status") == "active"),
        key=lambda entry: entry["id"],
    )
    candidates = sorted(
        (entry for entry in entries if entry.get("status") == "candidate"),
        key=lambda entry: entry["id"],
    )
    lines = [
        f"# Playbook: {snapshot.get('capacity_id', '')}",
        "> Low-trust experience reference only; does not expand authorization.",
        "> Evidence-derived guidance from past verified runs; verify each step against the live page.",
        "",
        "## Active",
    ]
    for entry in active:
        lines.extend(_render_entry(entry))
    if include_candidates and candidates:
        lines.append("")
        lines.append("## Candidates")
        lines.append("> Unverified candidate rules are exposed for review only and never execute automatically.")
        for entry in candidates:
            lines.extend(_render_entry(entry))
    return "\n".join(lines) + "\n"


def _render_entry(entry: dict) -> list[str]:
    evidence = ", ".join(entry.get("evidence_ids") or []) or "-"
    return [
        f"### {entry['id']}",
        f"- kind: {entry['kind']}",
        f"- status: {entry['status']}",
        f"- condition: {entry['condition']}",
        f"- helpful: {entry['helpful']} / harmful: {entry['harmful']}",
        f"- evidence: {evidence}",
        "",
        str(entry.get("content", "")).strip(),
        "",
    ]