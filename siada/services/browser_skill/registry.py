"""Registry: persisted index of published skills + zero-cost domain pre-filter.

Skills are published from VERIFIED agent executions (design doc §6): after a
success-verified run, its replayable action sequence (agent steps plus any
human interventions) becomes the capacity's replay_steps.json and registry
entry — never unverified demonstrations.

Domain pre-filtering (``candidates_for_domain``) is the first, free step of
the mid-segment matching algorithm: only when it returns a non-empty list
does the matcher spend an LLM call on semantic confirmation.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .models import RegistryEntry
from .paths import atomic_write_text, get_registry_path, skill_dir_for


def load_registry(path: Path | None = None) -> list[RegistryEntry]:
    path = path or get_registry_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return [RegistryEntry.from_dict(s) for s in data.get("skills", [])]


def save_registry(entries: list[RegistryEntry], path: Path | None = None) -> None:
    path = path or get_registry_path()
    out = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "skills": [e.to_dict() for e in entries],
    }
    atomic_write_text(path, json.dumps(out, indent=2, ensure_ascii=False))


def task_capacity_id(domain: str, goal: str) -> str:
    """Deterministic, language-agnostic capacity id for a goal-driven task.

    Same goal text on the same domain always maps to the same capacity, so
    playbook knowledge, replay steps, and feedback attribution all accumulate
    under one id without any LLM naming pass.
    """
    digest = hashlib.sha256((goal or "").strip().encode("utf-8")).hexdigest()[:12]
    return f"{domain}::task-{digest}"


def publish_verified_skill(
    capacity_id: str, domain: str, goal: str, steps: list[dict]
) -> RegistryEntry:
    """Publish a skill from a verified-success execution.

    Writes replay_steps.json + meta.json under the skill dir and upserts the
    registry entry. The playbook (SKILL.md) is rendered separately by
    ``PlaybookStore.export_skill`` from the committed entries.
    """
    if "::" not in capacity_id or not domain:
        raise ValueError("capacity_id must be '<domain>::<name>' with a domain")
    name = capacity_id.split("::", 1)[-1]
    skill_dir = skill_dir_for(domain, name)
    atomic_write_text(
        skill_dir / "replay_steps.json",
        json.dumps(steps, indent=2, ensure_ascii=False),
    )
    atomic_write_text(skill_dir / "meta.json", json.dumps({
        "capacity_id": capacity_id,
        "goal": goal,
        "source": "verified_agent_execution",
        "published_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2, ensure_ascii=False))

    entries = load_registry()
    previous = next((e for e in entries if e.capacity_id == capacity_id), None)
    entry = RegistryEntry(
        capacity_id=capacity_id,
        skill_name=(goal or name)[:60] or name,
        scope=goal or name,
        domains=[domain],
        preconditions=previous.preconditions if previous else [],
        entry_conditions=previous.entry_conditions if previous else [],
        segment_count=previous.segment_count + 1 if previous else 1,
        distill_version=(previous.distill_version + 1) if previous else 1,
        skill_path=str(skill_dir / "SKILL.md"),
        replay_steps_path=str(skill_dir / "replay_steps.json"),
    )
    save_registry([e for e in entries if e.capacity_id != capacity_id] + [entry])
    return entry


def candidates_for_domain(domain: str, entries: list[RegistryEntry] | None = None) -> list[RegistryEntry]:
    """Zero-cost domain pre-filter: registry entries whose `domains` includes
    the given domain. No LLM call — pure local filtering.
    """
    entries = entries if entries is not None else load_registry()
    return [e for e in entries if domain in e.domains]
