"""Data models for the /goal feature.

Goal: persisted per-session state (see goal_storage.py for the JSON file
this backs — <session_dir>/goal.json).

GoalVerdict: the shape the independent verifier LLM call (see verifier.py)
returns. It is NOT set as the forked Agent's ``output_type`` — a structured
output_type would fold a JSON schema into the outgoing request and bust the
provider's prompt cache (the entire reason verifier.py exists). Instead the
verifier is prompted to reply with a plain JSON object, which
``verifier._parse_goal_verdict`` parses back into this shape.
"""
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _seconds_between(start_at: str, end_at: str) -> float:
    """Return a nonnegative duration, tolerating malformed legacy timestamps."""
    try:
        start = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_at.replace("Z", "+00:00"))
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return max(0.0, (end - start).total_seconds())
    except (AttributeError, TypeError, ValueError):
        return 0.0


GoalStatus = Literal["active", "paused", "blocked", "complete"]


# Default safety limit for consecutive failed verifier turns. The user may
# override it with ``goal.max_turns`` in conf.yaml. System errors retain their
# separate, smaller breaker below.
GOAL_MAX_TURNS = 6


# After this many consecutive verifier SYSTEM errors (not genuine "not yet
# achieved" judgments -- see GoalVerdict.systemError / verifier.py's
# exception handlers), a goal auto-transitions to "blocked" much faster
# than the configured consecutive-failure limit above. A system/infra error
# (model behavior error, tool-call-instead-of-verdict, unexpected exception)
# tells us nothing about whether the objective was actually reached, so
# letting it eat into the normal failed-verdict budget would both hide real
# infra problems and burn through retries for no reason.
# Kept small and distinct so a broken verifier call surfaces to the user
# quickly instead of silently retrying many times.

GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS = 2


class Goal(BaseModel):
    objective: str
    status: GoalStatus = "active"
    consecutive_failures: int = 0
    # Consecutive verifier rounds that ended in a SYSTEM error (see
    # GoalVerdict.systemError) rather than a genuine "not yet achieved"
    # judgment. Tracked separately from consecutive_failures so a run of
    # infra errors trips the (much smaller) GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS
    # threshold instead of silently consuming the generous budget reserved
    # for genuine judgments. Reset to 0 on any genuine (non-system-error)
    # verifier round.
    consecutive_system_errors: int = 0
    # Total number of verifier rounds run against THIS goal (incremented once
    # per _maybe_run_goal_verifier call, regardless of pass/fail) -- surfaced
    # to the frontend as "N turns" in the Goal achieved/not-yet-achieved
    # summary line. Resets naturally via Goal.create() whenever a goal is
    # replaced (see goal_storage.append_goal_history for the outgoing one).
    turns: int = 0
    # Display records are persisted separately from the model conversation.
    # They survive compaction, completion, replacement and session restoration.
    verification_results: list[dict] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)
    # Session-owned active intervals include verification, but exclude stopped
    # time. Preserve fractions across repeated blocking and reactivation.
    active_elapsed_seconds: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)
    active_started_at: Optional[str] = None
    # Whether the hidden <system-reminder> has already been merged into a
    # turn's input for THIS activation of the goal (see
    # SiadaRunner._maybe_merge_goal_reminder / prompts.merge_goal_reminder_into_input).
    # The reminder is merged into the real, persisted turn input exactly
    # once per activation -- not every turn -- because once it lands in
    # api_history.json it stays there; re-merging on every subsequent turn
    # would keep appending the same multi-paragraph block into persisted
    # history forever. Reset to False whenever the goal (re)activates: a
    # brand new goal via Goal.create(), or a "blocked" goal reactivated by
    # Controller._maybe_reset_goal_on_new_turn. A "paused" goal reactivated
    # after an interruption keeps the flag: its reminder is already in the
    # persisted history, so re-merging it would only duplicate the block.
    reminder_injected: bool = False

    @model_validator(mode="after")
    def initialize_legacy_timing(self) -> "Goal":
        """Seed old goals from their only available lifecycle timestamps."""
        if not {"active_elapsed_seconds", "active_started_at"} & self.model_fields_set:
            if self.status == "active":
                self.active_started_at = self.created_at
            else:
                self.active_elapsed_seconds = _seconds_between(self.created_at, self.updated_at)
        return self


    @classmethod
    def create(cls, objective: str) -> "Goal":
        timestamp = _now_iso()
        return cls(
            objective=objective,
            status="active",
            consecutive_failures=0,
            consecutive_system_errors=0,
            created_at=timestamp,
            updated_at=timestamp,
            active_started_at=timestamp,
            reminder_injected=False,
        )

    def elapsed_seconds(self, now: Optional[str] = None) -> float:
        """Total active duration; stopped goals remain stable after reload."""
        end_at = (now or _now_iso()) if self.status == "active" else self.updated_at
        return self.active_elapsed_seconds + (
            _seconds_between(self.active_started_at, end_at) if self.active_started_at else 0.0
        )

    def set_status(self, status: GoalStatus) -> None:
        """Settle the current interval before changing lifecycle state."""
        timestamp = _now_iso()
        self.active_elapsed_seconds = self.elapsed_seconds(timestamp)
        self.active_started_at = timestamp if status == "active" else None
        self.status = status
        self.updated_at = timestamp


    def touch(self) -> None:
        """Bump updated_at after non-status changes; set_status owns transitions."""
        self.updated_at = _now_iso()


class GoalVerdict(BaseModel):
    passed: bool
    reason: str
    # Smallest next useful action when passed=False (becomes the next
    # iteration title in the app UI). Empty string when passed=True, or
    # when the objective is a conversational non-task that's already handled.
    nextAction: str = ""
    # True ONLY when this verdict is a mechanical fail-safe produced by
    # verify_goal_with_context/_retry_with_structured_output's exception
    # handlers (ModelBehaviorError, MaxTurnsExceeded, or any other
    # unexpected exception) -- i.e. the verifier call itself blew up and
    # never got a chance to judge the objective. This is a purely
    # code-level classification set by verifier.py, NEVER something the
    # LLM reports about itself (the model has no "systemError" field in
    # its JSON response shape -- see prompts.build_verifier_request_message).
    # turn_hooks.maybe_run_goal_verifier uses this to apply the much
    # smaller GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS budget instead of treating
    # it like an ordinary "not yet achieved" judgment.
    systemError: bool = False
