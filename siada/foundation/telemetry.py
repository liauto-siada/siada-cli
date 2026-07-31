try:
    from siada.internal.foundation.telemetry import *  # noqa: F401,F403
except ImportError:
    class _NoOpTelemetryConfig:
        """Stub config when siada.internal is not available."""
        def __init__(self):
            self.url = ""
            self.conversation_url = ""
            self.user_id = None

    class Telemetry:
        """No-op telemetry stub when siada.internal is not available."""
        def __init__(self):
            self.config = _NoOpTelemetryConfig()
            self.device_id = ""
            self.mac_id = ""

        def captureConversation(self, **kwargs):
            pass

        def captureConversationEvent(self, **kwargs):
            pass

        def captureApiTokenUsage(self, **kwargs):
            pass

        def captureToolEditFileUsage(self, **kwargs):
            pass

    telemetry = Telemetry()
