"""Guardrails for the bundled public ``siada-help`` skill.

These tests pin what the open-source build can actually do:

* ``config_manager.py`` only writes keys that exist in this build (no headroom
  proxy, no legacy account sign-in state) while still tolerating a ``conf.yaml``
  migrated from an older build
* the bundled references describe shipped behavior (API-key sign-in, direct
  Lark mode, ``models.json``, real commands) instead of removed features

The script is exercised through its own functions with ``CONFIG_PATH`` and
``BACKUP_PATH`` monkeypatched onto ``tmp_path``, so nothing here reads or writes
the real ``~/.siada-cli`` directory.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO_ROOT / "siada" / "resources" / "skills" / "siada-help"
SCRIPT_PATH = SKILL_DIR / "scripts" / "config_manager.py"
SKILL_MD = SKILL_DIR / "SKILL.md"
FEATURES_MD = SKILL_DIR / "references" / "features.md"
CONFIGURATION_MD = SKILL_DIR / "references" / "configuration.md"

# Rows of the "valid config keys" table in SKILL.md, e.g. "| `ui.theme` | string |"
SCALAR_TABLE_ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*(string|bool|int)\s*\|")
SCALAR_TYPES = {"string": str, "bool": bool, "int": int}


def _load_manager():
    spec = importlib.util.spec_from_file_location(
        "siada_help_config_manager_public_test", SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def manager(tmp_path, monkeypatch):
    module = _load_manager()
    monkeypatch.setattr(module, "CONFIG_PATH", tmp_path / "conf.yaml")
    monkeypatch.setattr(module, "BACKUP_PATH", tmp_path / "conf.yaml.bak")
    return module


@pytest.fixture()
def docs():
    return {
        "SKILL.md": SKILL_MD.read_text(encoding="utf-8"),
        "features.md": FEATURES_MD.read_text(encoding="utf-8"),
        "configuration.md": CONFIGURATION_MD.read_text(encoding="utf-8"),
    }


# --------------------------------------------------------------------------- #
# config_manager.py: write scope
# --------------------------------------------------------------------------- #

def test_documented_scalar_keys_match_script_whitelist(manager):
    documented = {}
    for line in SKILL_MD.read_text(encoding="utf-8").splitlines():
        match = SCALAR_TABLE_ROW.match(line)
        if match:
            documented[match.group(1)] = match.group(2)

    assert documented, "SKILL.md no longer documents any scalar config keys"
    assert set(documented) == set(manager.VALID_KEYS)
    for key, type_name in documented.items():
        assert manager.VALID_KEYS[key] is SCALAR_TYPES[type_name]


def test_removed_features_are_not_writable(manager):
    for key in (
        "headroom.enabled",
        "headroom.port",
        "user_id",
        "access_token",
        "siada_api_key",
        "refresh_token",
        "pre_plan",
        "auto_plan",
        "execution_mode",
    ):
        assert key not in manager.VALID_KEYS
        with pytest.raises(SystemExit) as excinfo:
            manager.cmd_set(SimpleNamespace(key=key, value="true"))
        assert excinfo.value.code == 1


def test_known_top_keys_cover_valid_object_and_legacy_sections(manager):
    assert set(manager.VALID_KEYS) & set(manager.LEGACY_TOP_KEYS) == set()
    assert manager.LEGACY_TOP_KEYS <= manager.KNOWN_TOP_KEYS
    assert manager.KNOWN_OBJECT_TOP_KEYS <= manager.KNOWN_TOP_KEYS
    assert {key.split(".")[0] for key in manager.VALID_KEYS} <= manager.KNOWN_TOP_KEYS


def test_legacy_keys_validate_without_claiming_the_feature_works(manager, capsys):
    manager.CONFIG_PATH.write_text(
        "llm_config:\n"
        "  model: claude-sonnet-5\n"
        "headroom:\n"
        "  enabled: true\n"
        "  port: 8787\n"
        "user_id: legacy-user\n",
        encoding="utf-8",
    )

    manager.cmd_validate(None)
    out = capsys.readouterr().out

    assert "Unknown top-level key" not in out
    assert "[OK]    headroom" not in out
    assert "legacy key 'headroom'" in out
    assert "legacy key 'user_id'" in out
    assert "compatibility only" in out
    assert "All checks passed" not in out


def test_validate_reports_non_mapping_root(manager, capsys):
    manager.CONFIG_PATH.write_text("- just\n- a\n- list\n", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        manager.cmd_validate(None)

    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "[ERROR]" in err
    assert "mapping" in err


def test_validate_reports_yaml_parse_error(manager, capsys):
    manager.CONFIG_PATH.write_text("llm_config: [unterminated\n", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        manager.cmd_validate(None)

    assert excinfo.value.code == 1
    assert "YAML parse error" in capsys.readouterr().err


def test_validate_flags_unknown_keys_and_type_mismatch(manager, capsys):
    manager.CONFIG_PATH.write_text(
        "proactive:\n"
        "  enabled: 'yes'\n"
        "  trigger_interval: true\n"
        "mystery_section: 1\n",
        encoding="utf-8",
    )

    manager.cmd_validate(None)
    out = capsys.readouterr().out

    assert "[WARN]  Unknown top-level key: 'mystery_section'" in out
    assert "[WARN]  proactive.enabled: expected bool, got str ('yes')" in out
    assert "[WARN]  proactive.trigger_interval: expected int, got bool (True)" in out
    assert "All checks passed" not in out


@pytest.mark.parametrize("key", ["pre_plan", "auto_plan", "execution_mode"])
def test_removed_planning_keys_validate_as_unknown(manager, capsys, key):
    manager.CONFIG_PATH.write_text(f"{key}: true\n", encoding="utf-8")

    manager.cmd_validate(None)

    out = capsys.readouterr().out
    assert f"Unknown top-level key: {key!r}" in out
    assert "All checks passed" not in out


def test_validate_passes_a_valid_config(manager, capsys):
    manager.CONFIG_PATH.write_text(
        "llm_config:\n  model: claude-sonnet-5\nproactive:\n  enabled: true\n",
        encoding="utf-8",
    )

    manager.cmd_validate(None)
    out = capsys.readouterr().out

    assert "[OK]    llm_config.model = 'claude-sonnet-5'" in out
    assert "[OK]    proactive.enabled = True" in out
    assert "All checks passed" in out


def test_set_preserves_comments_quotes_and_writes_backup(manager, capsys):
    original = (
        "# top comment\n"
        "llm_config:\n"
        '  model: "claude-sonnet-5"  # inline note\n'
        "\n"
        "# section comment\n"
        "proactive:\n"
        "  enabled: true\n"
    )
    manager.CONFIG_PATH.write_text(original, encoding="utf-8")

    manager.cmd_set(SimpleNamespace(key="proactive.trigger_interval", value="30"))

    updated = manager.CONFIG_PATH.read_text(encoding="utf-8")
    assert "# top comment" in updated
    assert "# inline note" in updated
    assert "# section comment" in updated
    assert '"claude-sonnet-5"' in updated
    assert yaml.safe_load(updated) == {
        "llm_config": {"model": "claude-sonnet-5"},
        "proactive": {"enabled": True, "trigger_interval": 30},
    }
    assert manager.BACKUP_PATH.read_text(encoding="utf-8") == original

    out = capsys.readouterr().out
    assert "siada-cli --restart-daemon" in out
    assert "siada --stop-daemon" not in out


def test_get_reports_set_and_missing_values(manager, capsys):
    manager.CONFIG_PATH.write_text(
        "llm_config:\n  model: claude-sonnet-5\n", encoding="utf-8"
    )

    manager.cmd_get(SimpleNamespace(key="llm_config.model"))
    manager.cmd_get(SimpleNamespace(key="llm_config.missing"))
    out = capsys.readouterr().out

    assert "claude-sonnet-5" in out
    assert "(key not set: llm_config.missing)" in out


# --------------------------------------------------------------------------- #
# Bundled references: no removed features, no invented commands
# --------------------------------------------------------------------------- #

def test_docs_point_at_models_json(docs):
    for name, text in docs.items():
        assert "model_config.json" not in text, name
        assert "models.json" in text, name


def test_docs_never_use_a_bare_siada_command(docs):
    for name, text in docs.items():
        assert "siada --stop-daemon" not in text, name
        assert "siada --restart-daemon" not in text, name
        assert "`siada`" not in text, name


def test_configuration_reference_has_no_relay_instructions(docs):
    configuration = docs["configuration.md"]

    assert "lark.relay.server_url" not in configuration
    assert "lark.direct.access" not in configuration
    assert "lark.access.dm_policy" in configuration
    assert '"direct"' in configuration

    for line in configuration.splitlines():
        if "relay" in line:
            assert (
                "legacy" in line or "not bundled" in line or "no effect" in line
            ), line


def test_headroom_section_is_documented_as_removed(docs):
    configuration = docs["configuration.md"]

    assert "headroom (legacy, not supported)" in configuration
    for line in configuration.splitlines():
        if "--headroom" in line:
            assert "removed" in line or "not part" in line, line


def test_features_document_api_key_signin_and_estimates(docs):
    features = docs["features.md"]

    assert "provider API key" in features
    assert "/configure" in features
    assert "/logout" in features
    assert "clear all stored credentials" not in features
    assert "models.json" in features
    assert "7.0 CNY per USD" in features


def test_features_do_not_promise_learning_or_replay_from_the_trace(docs):
    features = docs["features.md"]

    assert "does not learn from runs" in features
    assert "keeps no trained or persisted model" in features
    assert "browser_replay" in features


def test_no_invented_login_slash_command(docs):
    for name, text in docs.items():
        assert "`/login`" not in text, name


def test_removed_planning_controls_are_not_documented(docs):
    for name, text in docs.items():
        assert "`/pre-plan-mode`" not in text, name
        assert "`/auto-plan`" not in text, name
        assert "`pre_plan`" not in text, name
        assert "`auto_plan`" not in text, name
        assert "`execution_mode`" not in text, name


def test_legacy_auth_flags_are_described_as_rejected(docs):
    for name, text in docs.items():
        assert "no-op" not in text, name
        assert "liidDisabled" not in text, name


def test_proactive_safety_defaults_stay_documented(docs):
    features = docs["features.md"]
    configuration = docs["configuration.md"]

    for name, text in (("features.md", features), ("configuration.md", configuration)):
        assert "06:00" in text, name
        assert "08:30" in text, name
    assert "default is `false` for safety" in configuration
    assert "auto_execute_enabled" in configuration


def test_lark_direct_credentials_stay_documented(docs):
    for name, text in docs.items():
        if name == "SKILL.md":
            continue
        assert "lark.direct.app_id" in text, name
        assert "app_secret" in text, name