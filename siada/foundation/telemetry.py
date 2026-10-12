"""No-op telemetry surface for the open-source distribution.

Nothing is reported from this distribution: the exported ``telemetry``
singleton keeps the attribute and method surface public callers use, and every
capture method is inert. ``Telemetry`` stays importable and callable so
existing reporting call sites keep working unchanged.
"""


class _NoOpTelemetryConfig:
    """Inert telemetry configuration.

    ``conversation_url`` stays empty on purpose: reporting call sites treat a
    non-empty value as "a telemetry backend is configured", so the empty value
    keeps those paths switched off.
    """

    def __init__(self):
        self.url = ""
        self.conversation_url = ""
        self.user_id = None


class Telemetry:
    """Inert telemetry client; every capture call is a no-op."""

    def __init__(self):
        self.config = _NoOpTelemetryConfig()
        self.device_id = ""
        self.mac_id = ""

    def captureConversation(self, *args, **kwargs):
        """No-op: conversation turns are not reported."""

    def captureConversationEvent(self, *args, **kwargs):
        """No-op: conversation events are not reported."""

    def captureApiTokenUsage(self, *args, **kwargs):
        """No-op: API token usage is not reported."""

    def captureToolEditFileUsage(self, *args, **kwargs):
        """No-op: tool edit usage is not reported."""


telemetry = Telemetry()

__all__ = ["Telemetry", "telemetry"]
