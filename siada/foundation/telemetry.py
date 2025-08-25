import os
import requests
import json
import time
import uuid
from pathlib import Path


class TelemetryConfig:

    def __init__(self):
        self.url = ""
        self.is_enabled = False
        self._load_config()

    def _load_config(self):
        # Check if li_telemetry.py file exists
        li_telemetry_path = os.path.join(os.path.dirname(__file__), "li_telemetry.py")

        if os.path.exists(li_telemetry_path):
            try:
                from . import li_telemetry
                self.url = li_telemetry.TELEMETRY_URL
                self.is_enabled = True
            except (ImportError, AttributeError):
                self.url = ""
                self.is_enabled = False
        else:
            self.url = ""
            self.is_enabled = False


class Telemetry:
    """Telemetry tracking and reporting class"""

    def __init__(self):
        self.config = TelemetryConfig()
        self.home_dir = str(Path.home())
        self.mac_id = str(uuid.getnode())

    def captureAgentUsage(self, agent_name: str):
        if not self.config.is_enabled or not self.config.url:
            # If telemetry is not enabled or URL is empty, skip reporting
            return

        try:
            telemetry_data = {
                "agentName": agent_name,
                "homeDir": self.home_dir,
                "macId": self.mac_id
            }

            response = requests.post(
                self.config.url,
                json=telemetry_data,
                headers={"Content-Type": "application/json"},
                timeout=5  # 5 second timeout
            )

            # TODO: Check the correctness of print
            if response.status_code != 200:
                print(f"Telemetry upload failed with status: {response.status_code}")

        except Exception as e:
            # Telemetry failures should not affect main functionality, so handle silently
            print(f"Telemetry error: {e}")

telemetry = Telemetry()