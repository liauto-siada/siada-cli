"""Stream repetition guard for repetition-prone models.

Some models (notably the deepseek-v4-flash variants and lpai-glm-5.3)
occasionally fall into a degenerate repetition loop mid-stream: the same
text unit is emitted over and over until max_tokens. Because deltas are
forwarded to the UI live, the user watches garbage scroll by until the
request finally ends.

This module provides:

- ``is_repetition_guard_model`` -- whitelist check; the guard ONLY applies
  to the whitelisted model families, every other model pays zero cost.
- ``StreamRepetitionDetector`` -- incremental tail-window detector. Feed it
  raw text deltas; it reports once the stream tail consists of >= N copies
  of the same unit.
- ``RepetitiveStreamError`` -- raised by the streaming loop when repetition
  is detected. ConversationTurn catches it, flags the turn with
  ``RETRY_REASON_REPETITIVE_STREAM`` and Controller._maybe_retry_turn
  re-runs the turn (bounded by _MAX_AUTO_RETRIES).

The detection semantics are mirrored in the UI
(siada_cli_ui/src/utils/streamRepetition.ts) so the frontend can hold off
rendering a suspicious stream until the backend confirms the abort via a
``stream_aborted`` lifecycle event. Keep the constants in sync.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Optional, Tuple

# Only these models get the repetition guard. Substring match so both
# "kivy-deepseek-v4-flash" and dated variants ("kivy-deepseek-v4-flash-0731")
# are covered. Mirrors REPETITION_GUARD_MODEL_MARKERS in streamRepetition.ts.
REPETITION_GUARD_MODEL_MARKERS = ("deepseek-v4-flash",)


def is_repetition_guard_model(model_name: Optional[str]) -> bool:
    """Return True only for the repetition-guarded model families."""
    if not model_name:
        return False
    lowered = model_name.lower()
    return any(marker in lowered for marker in REPETITION_GUARD_MODEL_MARKERS)


class RepetitiveStreamError(Exception):
    """Raised when a guarded model's stream falls into a repetition loop."""

    def __init__(self, unit_preview: str, repeat_count: int, unit_length: int):
        self.unit_preview = unit_preview
        self.repeat_count = repeat_count
        self.unit_length = unit_length
        super().__init__(
            f"repetitive stream detected: unit_length={unit_length} "
            f"repeats={repeat_count} unit={unit_preview!r}"
        )


class StreamRepetitionDetector:
    """Incremental detector for tail-repetition loops in a text stream.

    Keeps only a trailing window of the stream. Every ``CHECK_EVERY`` fed
    characters it tests whether the tail ends with >= ``MIN_REPEATS``
    consecutive copies of the same unit (unit length between ``MIN_UNIT``
    and ``MAX_UNIT``). Once triggered it stays triggered (``fired``) so the
    caller can stop feeding it.
    """

    # Tail window kept for analysis (chars).
    WINDOW = 4096
    # Run the (relatively expensive) check every N newly fed chars.
    CHECK_EVERY = 64
    # Unit length bounds. MIN_UNIT=8 filters out benign short repeats
    # (list markers, whitespace runs) while still catching dense CJK loops
    # (a 14-char Chinese sentence is a plausible repetition unit).
    MIN_UNIT = 8
    MAX_UNIT = 600
    # Tail must end with at least this many consecutive copies of the unit.
    MIN_REPEATS = 3
    # The repeating unit must contain at least this many distinct
    # non-whitespace characters -- otherwise long divider runs ("=" x 80,
    # markdown rules) would false-positive.
    MIN_DISTINCT_CHARS = 3

    # Sentence-frequency check: catches "fuzzy" loops where the model cycles
    # through near-identical deliberation sentences (with small variations)
    # that the exact-unit check above can only catch once the loop degenerates
    # into verbatim repeats. If any sentence of >= SENT_MIN_LEN chars appears
    # >= SENT_MAX_COUNT times inside the tail window, the stream is looping.
    # Calibrated on a real 30k-char deepseek-v4-flash hallucination: the loop
    # onset was at 63%, this check fired ~1-2k chars later vs the exact check
    # which only fired at 99.7%.
    SENT_SPLIT_RE = re.compile(r"(?<=[.!?。！？\n])\s+")
    SENT_MIN_LEN = 10
    SENT_MAX_COUNT = 3

    def __init__(self) -> None:
        self._tail: str = ""
        self._since_check: int = 0
        self.fired: bool = False
        self.hit: Optional[Tuple[str, int]] = None  # (unit/sentence, count)
        self.kind: Optional[str] = None  # "exact" | "sentence"

    def feed(self, delta: str) -> Optional[Tuple[str, int]]:
        """Feed a streamed delta; return (unit, repeats) on first detection."""
        if self.fired or not delta:
            return self.hit
        self._tail = (self._tail + delta)[-self.WINDOW:]
        self._since_check += len(delta)
        if self._since_check < self.CHECK_EVERY:
            return None
        self._since_check = 0
        return self._check()

    def _check(self) -> Optional[Tuple[str, int]]:
        tail = self._tail
        n = len(tail)
        max_unit = min(self.MAX_UNIT, n // self.MIN_REPEATS)
        for unit_len in range(self.MIN_UNIT, max_unit + 1):
            unit = tail[n - unit_len:]
            if len({c for c in unit if not c.isspace()}) < self.MIN_DISTINCT_CHARS:
                continue
            repeats = 1
            pos = n - unit_len
            while pos - unit_len >= 0 and tail[pos - unit_len:pos] == unit:
                repeats += 1
                pos -= unit_len
            if repeats >= self.MIN_REPEATS:
                self.fired = True
                self.kind = "exact"
                self.hit = (unit, repeats)
                return self.hit
        return self._check_sentence_frequency()

    def _check_sentence_frequency(self) -> Optional[Tuple[str, int]]:
        """Fuzzy-loop check: any single sentence recurring too often in the
        tail window means the model is cycling through near-identical text."""
        sentences = self.SENT_SPLIT_RE.split(self._tail)
        counts = Counter(
            s.strip() for s in sentences if len(s.strip()) >= self.SENT_MIN_LEN
        )
        if not counts:
            return None
        sentence, occurrences = counts.most_common(1)[0]
        if occurrences >= self.SENT_MAX_COUNT:
            self.fired = True
            self.kind = "sentence"
            self.hit = (sentence, occurrences)
            return self.hit
        return None
