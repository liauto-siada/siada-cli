"""Abstract base class for IM platform adapters."""

from abc import ABC, abstractmethod
from typing import Optional

from siada.im.models import IMMessage, IMResponse


class IMAdapter(ABC):
    """Platform-specific adapter interface.

    Each IM platform (Lark, WeCom, DingTalk, etc.) implements this
    to handle platform-specific message parsing and sending.
    """

    @abstractmethod
    async def parse_event(self, raw: dict) -> Optional[IMMessage]:
        """Parse a raw platform event into a unified IMMessage."""
        ...

    @abstractmethod
    async def send_message(self, chat_id: str, msg: IMResponse) -> Optional[str]:
        """Send a message to the specified chat.

        Returns the platform message_id on success, None on failure.
        """
        ...

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return platform identifier string (e.g. 'lark')."""
        ...

