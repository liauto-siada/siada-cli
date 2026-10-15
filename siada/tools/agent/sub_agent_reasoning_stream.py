"""Bounded reasoning snapshots for the sub-agent detail view."""

import uuid
from dataclasses import dataclass
from typing import Callable

from siada.tools.agent.sub_agent_notifier import MAX_ENTRY_TEXT_LENGTH


@dataclass
class _Part:
    entry_id: str
    text: str = ""
    complete: bool = False


class SubAgentReasoningStream:
    """Coalesce raw reasoning deltas and deduplicate completed SDK items.

    Each Runner attempt owns an instance so providers may reuse item ids on a
    continuation. Snapshots retain the latest text within the display budget.
    """

    def __init__(self, push: Callable[..., None], on_complete: Callable[[str], None]):
        self._push = push
        self._on_complete = on_complete
        self._parts: dict[tuple[str, str, int], _Part] = {}
        self._seen_items: set[str] = set()

    def _update(
        self, key: tuple[str, str, int], text: str, *, complete: bool, delta: bool,
    ) -> None:
        part = self._parts.get(key)
        if part is None:
            if not text:
                return
            part = self._parts[key] = _Part(f"reasoning_{uuid.uuid4().hex}")
        if part.complete:
            return
        part.text = ((part.text + text) if delta else text)[-MAX_ENTRY_TEXT_LENGTH:]
        part.complete = complete
        self._seen_items.add(key[0])
        self._push(part.text, entry_id=part.entry_id, is_complete=complete)
        if complete:
            self._on_complete(part.text)

    def handle_raw(self, data: object) -> None:
        event_type = getattr(data, "type", "")
        if event_type == "response.created":
            self.finish()
            self._parts.clear()
            self._seen_items.clear()
            return
        for family, index_name in (
            ("reasoning_summary_text", "summary_index"),
            ("reasoning_text", "content_index"),
        ):
            if event_type not in (f"response.{family}.delta", f"response.{family}.done"):
                continue
            complete = event_type.endswith(".done")
            text = getattr(data, "text" if complete else "delta", "") or ""
            item_id = getattr(data, "item_id", None)
            if item_id is None:
                item_id = f"output_{getattr(data, 'output_index', 0)}"
            key = (item_id, family, getattr(data, index_name, 0))
            # Some providers send a done marker without the accumulated text.
            if complete and not text and key in self._parts:
                text = self._parts[key].text
            self._update(key, text, complete=complete, delta=not complete)
            return
        if event_type == "response.output_item.done":
            item = getattr(data, "item", None)
            if getattr(item, "type", None) == "reasoning":
                self.complete_item(item)
        elif event_type == "response.completed":
            self.finish()

    def complete_item(self, item: object) -> None:
        item_id = getattr(item, "id", "") or ""
        if item_id not in self._seen_items:
            # Non-streaming providers can deliver only the completed item.
            parts = list(getattr(item, "summary", None) or [])
            parts += list(getattr(item, "content", None) or [])
            text = "\n".join(
                part.text for part in parts if isinstance(getattr(part, "text", None), str)
            )
            self._update((item_id, "item", 0), text, complete=True, delta=False)
        for key, part in self._parts.items():
            if key[0] == item_id and not part.complete:
                self._update(key, part.text, complete=True, delta=False)

    def finish(self) -> None:
        """Close admitted text even when the stream fails or is cancelled."""
        for key, part in self._parts.items():
            if not part.complete:
                self._update(key, part.text, complete=True, delta=False)