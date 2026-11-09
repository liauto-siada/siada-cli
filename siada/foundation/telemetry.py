"""Inert telemetry compatibility surface for the public distribution."""


class _NoOpTelemetryConfig:
    """Keep reporting disabled while retaining the configuration interface."""

    def __init__(self):
        self.url = ""
        self.conversation_url = ""
        self.user_id = None


class Telemetry:
    """Keep existing capture call sites available without collecting data."""

    def __init__(self):
        self.config = _NoOpTelemetryConfig()
        self.device_id = ""
        self.mac_id = ""

    def captureConversation(self, *args, **kwargs):
        """Conversation collection is disabled."""

    def captureConversationEvent(self, *args, **kwargs):
        """Conversation event collection is disabled."""

    def captureApiTokenUsage(self, *args, **kwargs):
        """Remote token usage collection is disabled."""

    def captureToolEditFileUsage(self, *args, **kwargs):
        """Remote edit usage collection is disabled."""


telemetry = Telemetry()
__all__ = ["Telemetry", "telemetry"]
