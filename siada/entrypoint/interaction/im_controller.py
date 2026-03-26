"""Abstract base class for IM (Instant Messaging) controllers.

Defines the interface that all IM controllers (Lark, WeCom, DingTalk, etc.)
must implement to integrate with the SiadaDaemon.
"""

import abc
import logging
from typing import Optional

from siada.session.ownership import SessionOwner

logger = logging.getLogger("siada.im_controller")


class ImController(abc.ABC):
    """Abstract IM controller that bridges messaging platforms to SiadaRunner.

    Subclasses must implement:
    - start(): connect transport and begin processing messages
    - stop(): gracefully disconnect and clean up
    - is_running: property indicating whether the controller is active
    - owner_type: the SessionOwner enum value for ownership tracking
    - workspace: the workspace path used by the controller (for session ownership)
    """

    @abc.abstractmethod
    async def start(self) -> None:
        """Connect transport and start the message processing loop."""
        ...

    @abc.abstractmethod
    async def stop(self) -> None:
        """Stop the controller and disconnect transport."""
        ...

    @property
    @abc.abstractmethod
    def is_running(self) -> bool:
        """Whether the controller is currently running."""
        ...

    @property
    @abc.abstractmethod
    def owner_type(self) -> SessionOwner:
        """The session owner type for ownership tracking."""
        ...

    @property
    @abc.abstractmethod
    def workspace(self) -> Optional[str]:
        """The workspace path used by this controller."""
        ...

    @classmethod
    @abc.abstractmethod
    def create_if_configured(cls) -> Optional["ImController"]:
        """Factory method: load config and create controller if properly configured.

        Returns:
            An ImController instance if config exists and is valid, None otherwise.
        """
        ...
