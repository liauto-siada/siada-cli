"""
Turn Models Module

Contains data models and type definitions for interaction turns.
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from agents import TResponseInputItem

from siada.support.slash_commands import SwitchEvent


class TurnType(Enum):
    """Types of interaction turns"""

    COMMAND = "command"  # Slash commands (/help, /edit, etc.)
    CONVERSATION = "conversation"  # Regular AI conversation


# Generic metadata key a TurnOutput can set to request that Controller
# (see Controller._maybe_retry_turn) transparently retry this turn via the
# SwitchEvent(ai_analysis_prompt=...) mechanism. A string "reason" (not a
# single-purpose boolean) so future retry-worthy conditions can register
# a new value here without inventing a new metadata key each time.
RETRY_REASON_METADATA_KEY = "retry_reason"

# Known retry reasons -- each maps to a notice in RETRY_NOTICES below.
RETRY_REASON_TRUNCATED_REASONING_ONLY = "truncated_reasoning_only"
# Guarded models (whitelist in stream_repetition.py) falling into a repetition
# loop mid-stream -- see stream_repetition.py / ConversationTurn.output_stream_content.
RETRY_REASON_REPETITIVE_STREAM = "repetitive_stream"

# Per-reason notice text sent to the model as the next turn's input when
# Controller._maybe_retry_turn triggers a retry. Lives alongside the
# RETRY_REASON_* constants (not in Controller) since it's part of the
# retry-reason vocabulary, not the dispatch mechanism that consumes it.
#
# Wrapped in <system-reminder> (same convention as prompts.py /
# todo_reminder_processor.py) so message_classifier._is_whole_system_reminder
# strips it from what's replayed on session resume/pullHistory.
RETRY_NOTICES: Dict[str, str] = {
    # Chat Completions/LiteLLM truncated-stream guard -- see
    # ConversationTurn._is_truncated_reasoning_only_completion.
    RETRY_REASON_TRUNCATED_REASONING_ONLY: (
        "<system-reminder>\n"
        "Your previous response appears to have been interrupted before "
        "any answer or tool call was produced (this can happen due to a "
        "network/stream interruption on the model provider side). Please "
        "continue and provide your actual response to the user's last "
        "message now.\n"
        "</system-reminder>"
    ),
    # Repetition-loop guard for whitelisted models -- see
    # stream_repetition.py. The aborted (repetitive) stream is discarded by
    # the UI; this notice asks the model to answer again without looping.
    RETRY_REASON_REPETITIVE_STREAM: (
        "<system-reminder>\n"
        "Your previous response was aborted because it fell into a "
        "repetition loop (the same text was generated over and over). "
        "Please answer the user's last message again, and do NOT repeat "
        "the same sentence or paragraph unchanged.\n"
        "</system-reminder>"
    ),
}


@dataclass
class TurnInput:
    """Input data for a turn"""

    use_input: str | List[TResponseInputItem] # Raw user input - can be a string or list


@dataclass
class TurnOutput:
    """Output data from a turn"""

    output: str | SwitchEvent  # Response content
    metadata: Dict[str, Any]  # Response metadata
    next_action: Optional[str]  # Suggested next action