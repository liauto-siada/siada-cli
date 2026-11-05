"""Command input kept separate from model and synchronous tool input."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandInput:
    prompt: str
    command_id: str
    request_id: str
    queue_id: str | None = None