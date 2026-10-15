"""Session-scoped input admitted at the next model request boundary."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import uuid4

from siada.services.memory.holographic.marker import wrap_user_input

if TYPE_CHECKING:
    from agents.run import ModelInputData
    from siada.foundation.code_agent_context import CodeAgentContext


@dataclass
class SteeringQueue:
    session_id: str
    pending: list[tuple[str, str]] = field(default_factory=list)
    accepted: dict[str, str] = field(default_factory=dict)

    def append(self, text: str, request_id: str | None = None) -> None:
        identity = request_id or uuid4().hex
        if identity in self.accepted:
            if self.accepted[identity] != text:
                raise RuntimeError("Steering request ID was reused with different content")
            return
        if len(self.pending) >= 100:
            raise RuntimeError("Too many pending steering messages")
        self.pending.append((identity, text))
        self.accepted[identity] = text

    async def inject(
        self,
        model_data: ModelInputData,
        context: CodeAgentContext,
        persist_items: Callable[[list, list[str]], Awaitable[None]] | None = None,
    ) -> None:
        if not self.pending or getattr(getattr(context, "session", None), "session_id", None) != self.session_id:
            return
        batch = list(self.pending)
        items = [{"role": "user", "content": wrap_user_input(text)} for _, text in batch]
        identities = [f"steer:{identity}" for identity, _ in batch]
        # Leave the batch queued on storage failure or cancellation. Additions
        # arriving while persistence awaits remain for the following request.
        if persist_items is not None:
            await persist_items(items, identities)
        else:
            store = context.session.openai_session
            if store is None:
                raise RuntimeError("Steering requires session storage")
            await store.add_items(items)
        del self.pending[:len(batch)]
        model_data.input = list(model_data.input) + items


current_steering: ContextVar[SteeringQueue | None] = ContextVar("current_steering", default=None)