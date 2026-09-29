"""Per-ACP-session mid-segment prediction state machine.

Owned by SiadaTurnRunner (one instance per session, keyed by tabId). Fed
trajectory events as they arrive via SiadaAcpAgent.ext_notification; decides
when to trigger an LLM confirmation call and whether to surface a proactive
suggestion. See design doc §6/§8.

Algorithm (cheap-first):
1. Maintain a sliding window of pending events for the session's current tab,
   reset on navigation-to-new-domain or an idle gap (mirrors the atomizer's
   boundary rules, applied live instead of after the fact).
2. On every new batch: look up the current domain's registry candidates
   (zero-cost, local filtering via registry.candidates_for_domain).
3. Only if candidates exist AND the window has accumulated enough action
   events AND at least one candidate hasn't been reminded yet in this
   session, spend one LLM call to semantically confirm a match.
4. On confirmed match, mark that capacity as "reminded" for this session so
   it is only suggested once (design doc §7 "single reminder").
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field

from .event_utils import registered_domain, sanitize_events, summarize_events
from .llm_utils import call_fast_llm, parse_json_from_model
from .models import RegistryEntry
from .registry import candidates_for_domain, load_registry

logger = logging.getLogger(__name__)

MIN_ACTIONS_TO_CONFIRM = 3
IDLE_RESET_MS = 15_000
MATCH_CONFIDENCE_THRESHOLD = 0.6

MATCH_PROMPT = """\
You are checking whether a user's IN-PROGRESS browser actions are the start
of a known capability. Only confirm a match if the evidence is a clear
prefix of the candidate's expected entry conditions — if unsure, say no
match.

## User's actions so far (most recent segment, still in progress)
{event_summary}

## Candidate capacities on this domain
{candidates}

Output JSON only:
{{"matched_capacity_id": "domain::capacity-id or null", "confidence": 0.0-1.0}}
"""


def _format_candidates(candidates: list[RegistryEntry]) -> str:
    lines = []
    for c in candidates:
        entry_desc = ", ".join(c.entry_conditions) or c.scope
        lines.append(f"- {c.capacity_id} ({c.skill_name}): entry conditions = {entry_desc}")
    return "\n".join(lines)


@dataclass
class MatchResult:
    capacity_id: str
    skill_name: str
    scope: str
    skill_path: str
    replay_steps_path: str
    goal: str = ""
    start_step: int | None = None
    verification_conditions: list[dict] = field(default_factory=list)
    parameters: dict[str, str] = field(default_factory=dict)


@dataclass
class BrowserSkillSessionState:
    """One instance per ACP session, tracking a single tab's live event
    window and which capacities have already been suggested this session.
    """

    session_id: str
    tab_id: int | None = None
    _pending_events: list[dict] = field(default_factory=list)
    _last_event_ts: float = field(default_factory=lambda: 0.0)
    _current_domain: str = ""
    _reminded: set[str] = field(default_factory=set)
    _confirm_attempted_this_window: bool = False

    def _reset_window(self, domain: str) -> None:
        self._pending_events = []
        self._current_domain = domain
        self._confirm_attempted_this_window = False

    def _maybe_reset_on_boundary(self, events: list[dict]) -> None:
        if not events:
            return
        first = events[0]
        now_ts = first.get("ts", time.time() * 1000)
        domain = registered_domain(first.get("url", ""))

        if self._current_domain and domain and domain != self._current_domain:
            self._reset_window(domain)
        elif self._last_event_ts and now_ts - self._last_event_ts > IDLE_RESET_MS:
            self._reset_window(domain)
        elif not self._current_domain:
            self._current_domain = domain

        self._last_event_ts = events[-1].get("ts", now_ts)

    def _action_count(self) -> int:
        return sum(1 for e in self._pending_events if e.get("type") == "action")

    async def on_events(self, events: list[dict]) -> MatchResult | None:
        """Feed newly-arrived trajectory events; returns a MatchResult if a
        proactive suggestion should be surfaced now, else None.
        """
        if not events:
            return None

        for event in sanitize_events(events):
            self._maybe_reset_on_boundary([event])
            self._pending_events.append(event)

        if not self._current_domain:
            return None

        candidates = candidates_for_domain(self._current_domain, load_registry())
        candidates = [c for c in candidates if c.capacity_id not in self._reminded]
        if not candidates:
            return None

        if self._action_count() < MIN_ACTIONS_TO_CONFIRM:
            return None

        # Avoid spamming the LLM: at most one confirmation attempt per window
        # regardless of how many more events arrive before a boundary reset.
        if self._confirm_attempted_this_window:
            return None
        self._confirm_attempted_this_window = True

        match = await self._confirm_match(candidates)
        if match is None:
            return None

        self._reminded.add(match.capacity_id)
        return match

    async def _confirm_match(self, candidates: list[RegistryEntry]) -> MatchResult | None:
        prompt = MATCH_PROMPT.format(
            event_summary=summarize_events(self._pending_events),
            candidates=_format_candidates(candidates),
        )
        text = await call_fast_llm(prompt, agent_name="browser_skill_matcher")
        data = parse_json_from_model(text)

        capacity_id = data.get("matched_capacity_id")
        confidence = data.get("confidence", 0)
        if (
            not isinstance(capacity_id, str)
            or not isinstance(confidence, (float, int))
            or isinstance(confidence, bool)
            or not math.isfinite(confidence)
            or not MATCH_CONFIDENCE_THRESHOLD <= confidence <= 1
        ):
            return None

        entry = next((c for c in candidates if c.capacity_id == capacity_id), None)
        if entry is None:
            return None

        logger.info(
            "[browser-skill] session=%s matched capacity=%s confidence=%.2f",
            self.session_id, capacity_id, confidence,
        )
        return MatchResult(
            capacity_id=entry.capacity_id,
            skill_name=entry.skill_name,
            scope=entry.scope,
            skill_path=entry.skill_path,
            replay_steps_path=entry.replay_steps_path,
        )
