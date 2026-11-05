"""Tests for siada.im.config - IM configuration loader (unified conf.yaml)."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


class TestLoadImConfig:
    """Test load_im_config function."""

    def _write_yaml(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_load_valid_lark_config(self, tmp_path):
        """Should load valid conf.yaml with lark provider."""
        config_path = tmp_path / "conf.yaml"
        self._write_yaml(config_path, """
lark:
  mode: direct
  direct:
    app_id: "test_app_id"
    app_secret: "test_secret"
""")
        from siada.im.config import load_im_config

        result = load_im_config(config_path=config_path)
        assert result is not None
        assert result["lark"]["mode"] == "direct"
        assert result["lark"]["direct"]["app_id"] == "test_app_id"

    def test_load_relay_mode_config(self, tmp_path):
        """Should load valid conf.yaml with relay mode."""
        config_path = tmp_path / "conf.yaml"
        self._write_yaml(config_path, """
lark:
  mode: relay
  relay:
    server_url: "ws://localhost:8080"
""")
        from siada.im.config import load_im_config

        result = load_im_config(config_path=config_path)
        assert result is not None
        assert result["lark"]["mode"] == "relay"
        assert result["lark"]["relay"]["server_url"] == "ws://localhost:8080"

    def test_relay_mode_no_defaults_in_load_im_config(self, tmp_path):
        """load_im_config should NOT merge relay defaults (deferred to build_relay_config)."""
        config_path = tmp_path / "conf.yaml"
        self._write_yaml(config_path, """
lark:
  mode: relay
""")
        from siada.im.config import load_im_config

        result = load_im_config(config_path=config_path)
        assert result is not None
        assert result["lark"]["mode"] == "relay"
        # No relay section should be auto-created; defaults are merged lazily
        assert "relay" not in result["lark"] or result["lark"].get("relay") is None

    def test_relay_mode_preserves_explicit_config(self, tmp_path):
        """Should preserve user-specified relay settings without merging defaults."""
        config_path = tmp_path / "conf.yaml"
        self._write_yaml(config_path, """
lark:
  mode: relay
  relay:
    server_url: "ws://custom-server:9090/ws"
    heartbeat_interval: 30
""")
        from siada.im.config import load_im_config

        result = load_im_config(config_path=config_path)
        assert result is not None
        relay = result["lark"]["relay"]
        assert relay["server_url"] == "ws://custom-server:9090/ws"
        assert relay["heartbeat_interval"] == 30
        # reconnect_backoff not set by user, should not be auto-filled
        assert "reconnect_backoff" not in relay

    def test_returns_none_when_file_not_found(self, tmp_path):
        """Should return None when config file doesn't exist."""
        from siada.im.config import load_im_config

        result = load_im_config(config_path=tmp_path / "nonexistent.yaml")
        assert result is None

    def test_returns_none_when_no_mode_set(self, tmp_path):
        """Should return None when lark section exists but mode is not set."""
        config_path = tmp_path / "conf.yaml"
        self._write_yaml(config_path, """
lark:
  workspace: /tmp/test
""")
        from siada.im.config import load_im_config

        result = load_im_config(config_path=config_path)
        assert result is None

    def test_returns_none_for_empty_file(self, tmp_path):
        """Should return None for empty YAML file."""
        config_path = tmp_path / "conf.yaml"
        self._write_yaml(config_path, "")

        from siada.im.config import load_im_config

        result = load_im_config(config_path=config_path)
        assert result is None

    def test_returns_none_for_invalid_yaml_structure(self, tmp_path):
        """Should return None when YAML is not a dict."""
        config_path = tmp_path / "conf.yaml"
        self._write_yaml(config_path, "- item1\n- item2\n")

        from siada.im.config import load_im_config

        result = load_im_config(config_path=config_path)
        assert result is None

    def test_env_var_substitution(self, tmp_path):
        """Should substitute ${VAR} placeholders with env values."""
        config_path = tmp_path / "conf.yaml"
        self._write_yaml(config_path, """
lark:
  mode: direct
  direct:
    app_id: "${TEST_IM_APP_ID}"
    app_secret: "${TEST_IM_APP_SECRET}"
""")
        from siada.im.config import load_im_config

        with patch.dict(os.environ, {
            "TEST_IM_APP_ID": "env_app_id_123",
            "TEST_IM_APP_SECRET": "env_secret_456",
        }):
            result = load_im_config(config_path=config_path)

        assert result is not None
        assert result["lark"]["direct"]["app_id"] == "env_app_id_123"
        assert result["lark"]["direct"]["app_secret"] == "env_secret_456"

    def test_env_var_missing_returns_empty_string(self, tmp_path):
        """Should replace missing env vars with empty string."""
        config_path = tmp_path / "conf.yaml"
        self._write_yaml(config_path, """
lark:
  mode: direct
  direct:
    app_id: "${NONEXISTENT_VAR_12345}"
""")
        from siada.im.config import load_im_config

        with patch.dict(os.environ, {}, clear=False):
            # Ensure the var doesn't exist
            os.environ.pop("NONEXISTENT_VAR_12345", None)
            result = load_im_config(config_path=config_path)

        assert result is not None
        assert result["lark"]["direct"]["app_id"] == ""

    def test_default_config_path_uses_conf_yaml(self):
        """Should use SIADA_HOME / conf.yaml as default path."""
        from siada.config.config_loader import _get_default_config_path
        from siada.foundation.constants import SIADA_HOME

        assert _get_default_config_path() == SIADA_HOME / "conf.yaml"

    def test_returns_none_when_no_lark_section(self, tmp_path):
        """Should return None when no known provider section exists."""
        config_path = tmp_path / "conf.yaml"
        self._write_yaml(config_path, """
llm_config:
  model: "test-model"
""")
        from siada.im.config import load_im_config

        result = load_im_config(config_path=config_path)
        assert result is None

    def test_config_with_access_control(self, tmp_path):
        """Should correctly load access control settings."""
        config_path = tmp_path / "conf.yaml"
        self._write_yaml(config_path, """
lark:
  mode: direct
  access:
    dm_policy: allowlist
    allow_from:
      - "ou_abc123"
      - "ou_def456"
  direct:
    app_id: "test"
    app_secret: "test"
""")
        from siada.im.config import load_im_config

        result = load_im_config(config_path=config_path)
        assert result is not None
        assert result["lark"]["access"]["dm_policy"] == "allowlist"
        assert len(result["lark"]["access"]["allow_from"]) == 2

    def test_extracts_only_lark_section(self, tmp_path):
        """Should only extract lark section, ignoring other config keys."""
        config_path = tmp_path / "conf.yaml"
        self._write_yaml(config_path, """
llm_config:
  model: "test-model"
lark:
  mode: relay
proactive:
  enabled: true
""")
        from siada.im.config import load_im_config

        result = load_im_config(config_path=config_path)
        assert result is not None
        assert "lark" in result
        assert "llm_config" not in result
        assert "proactive" not in result
