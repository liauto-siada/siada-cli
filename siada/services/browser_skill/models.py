"""Dataclasses shared across the Browser Skill Graph."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReplayStep:
    """One deterministic replay step, matching chrome-acp's ``ReplayStep``
    (packages/shared/src/acp/types.ts). Consumed directly by the
    ``browser_replay`` MCP tool."""

    kind: str  # click|input|select|keydown|scroll|navigate
    target: dict | None = None
    value: str | None = None
    key: str | None = None
    url: str | None = None
    scrollX: int | None = None
    scrollY: int | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class VerificationResult:
    """Three-state outcome of a browser task (design doc §3.1).

    - success:  every pre-agreed postcondition was observed after execution.
    - failure:  a definitive tool error, an aborted run, or a known
                postcondition that was not satisfied.
    - unknown:  no pre-agreed acceptance conditions, incomplete observations,
                or ambiguous tool results. ``isError=false`` alone is not
                success, and page text like ``## Error`` is not failure.
    """

    status: str = "unknown"
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status not in ("success", "failure", "unknown"):
            raise ValueError(
                f"invalid verification status {self.status!r}; "
                "expected success|failure|unknown"
            )


@dataclass
class ExecutionRecord:
    """Raw evidence plus the three-state result of one executed task.

    Events carry the full merged evidence stream: the agent's browser tool
    calls AND any human interventions on the same tab (trajectory events,
    labeled ``origin: "human"``) that arrived while the turn was active.
    ``used_entry_ids`` records which playbook entries were actually injected
    for feedback attribution.
    """

    execution_id: str
    capacity_id: str  # f"{domain}::{capacity}"
    domain: str
    goal: str
    events: list[dict] = field(default_factory=list)
    verification: VerificationResult = field(default_factory=VerificationResult)
    source: str = "agent"  # agent (kept for schema compat; demos removed)
    used_entry_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.source not in ("agent", "demonstration"):
            raise ValueError(
                f"invalid source {self.source!r}; expected agent|demonstration"
            )


@dataclass
class RegistryEntry:
    """Persisted, queryable summary of one published skill."""

    capacity_id: str
    skill_name: str
    scope: str
    domains: list[str]
    preconditions: list[str]
    entry_conditions: list[str]
    segment_count: int
    distill_version: int
    skill_path: str
    replay_steps_path: str

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, data: dict) -> "RegistryEntry":
        return cls(
            capacity_id=data["capacity_id"],
            skill_name=data.get("skill_name", data["capacity_id"]),
            scope=data.get("scope", ""),
            domains=list(data.get("domains", [])),
            preconditions=list(data.get("preconditions", [])),
            entry_conditions=list(data.get("entry_conditions", [])),
            segment_count=data.get("segment_count", 0),
            distill_version=data.get("distill_version", 0),
            skill_path=data.get("skill_path", ""),
            replay_steps_path=data.get("replay_steps_path", ""),
        )
