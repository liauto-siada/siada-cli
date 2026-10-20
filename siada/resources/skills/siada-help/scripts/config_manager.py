#!/usr/bin/env python3
"""
Siada configuration manager.
Read, modify, and validate ~/.siada-cli/conf.yaml
"""

import argparse
import shutil
import sys
from pathlib import Path

import yaml

# Requires siada virtualenv (same as other skill scripts like manage_cron_task.py).
# ruamel.yaml is a direct dependency of the siada package.
from ruamel.yaml import YAML

CONFIG_PATH = Path.home() / ".siada-cli" / "conf.yaml"
BACKUP_PATH = Path.home() / ".siada-cli" / "conf.yaml.bak"

_ryaml = YAML()
_ryaml.preserve_quotes = True

# Valid config keys and their expected types
VALID_KEYS = {
    "llm_config.model": str,
    "llm_config.provider": str,
    "llm_config.base_url": str,
    "llm_config.api_key": str,
    "llm_config.thinking": bool,
    "llm_config.enable_thinking": bool,
    "llm_config.parallel_tool_calls": bool,
    "llm_config.reasoning_effort": str,
    "llm_config.vision_model": str,
    "llm_config.vision_provider": str,
    "checkpoint_config.enable": bool,
    "checkpoint_config.max_checkpoint_files": int,
    "proactive.enabled": bool,
    "proactive.work_hours": str,
    "proactive.trigger_interval": int,
    "proactive.daily_task_execution_time": str,
    "proactive.daily_im_send_time": str,
    "proactive.auto_execute_enabled": bool,
    "proactive.send_daily_summary_to_im": bool,
    "auto_update.enabled": bool,
    "auto_update.check_interval_minutes": int,
    "auto_update.channel": str,
    "code_agent.max_turns": int,
    "memory.enabled": bool,
    "memory.user_profile_enabled": bool,
    "memory.memory_facts_enabled": bool,
    "memory.memory_char_limit": int,
    "memory.user_char_limit": int,
    "memory.holographic.enabled": bool,
    "memory.holographic.hrr_enabled": bool,
    "memory.holographic.hrr_dim": int,
    "memory.holographic.prefetch_limit": int,
    "memory.holographic.temporal_decay_half_life": int,
    "sub_agent.enabled": bool,
    "sub_agent.allow_recursive_subagents": bool,
    "web.enabled": bool,
    "compaction_strategy": str,
    "command_timeout": int,
    "preferred_language": str,
    "enable_notification": bool,
    "goal.max_turns": int,
    "im.verbose.p2p": bool,
    "im.verbose.group": bool,
    "ui.theme": str,
}

# Top-level keys whose value is an object/list rather than a simple scalar, so
# `set` cannot target them directly (and `validate` must not flag them as unknown).
KNOWN_OBJECT_TOP_KEYS = {"lark", "sub_agent", "memory", "im", "ui", "llm_config", "checkpoint_config"}

# Legacy keys that an older (non-open-source) install could have written. They are
# recognized so such a conf.yaml still parses and validates cleanly, but they are
# purely for backward compatibility: none of them enables a capability in this build.
#   - headroom: the proxy integration is not bundled; no proxy is started and no
#     traffic is routed (the old `--headroom*` CLI flags do not exist)
#   - user_id / access_token / siada_api_key / refresh_token / user_email /
#     email_refresh_token: old account sign-in state. This build signs in with a
#     provider API key only, so the sign-in flow never writes them.
LEGACY_TOP_KEYS = {
    "headroom",
    "user_id",
    "access_token",
    "siada_api_key",
    "refresh_token",
    "user_email",
    "email_refresh_token",
}

LEGACY_TOP_KEY_NOTES = {
    "headroom": "the proxy integration was removed from this build; nothing starts and no traffic is routed",
    "user_id": "old account sign-in state; this build signs in with a provider API key only",
    "access_token": "old account sign-in state; not read by this build",
    "siada_api_key": "old account sign-in state; not read by this build",
    "refresh_token": "old account sign-in state; not read by this build",
    "user_email": "old account sign-in state; not read by this build",
    "email_refresh_token": "old account sign-in state; not read by this build",
}

# Top-level keys accepted by `validate`: every section that holds scalar keys in
# VALID_KEYS, plus the object sections and the legacy keys above. Anything else is
# reported as an unknown key.
KNOWN_TOP_KEYS = (
    {key.split(".")[0] for key in VALID_KEYS}
    | KNOWN_OBJECT_TOP_KEYS
    | LEGACY_TOP_KEYS
)



def _overlay_last_wins(data, effective) -> None:
    """Where duplicate keys made the round-trip tree (ruamel keeps the first
    occurrence) diverge from the plain-dict parse (last occurrence wins),
    take the effective value so the rewrite keeps what config reads used."""
    for key, eff in effective.items():
        if key not in data:
            continue
        cur = data[key]
        if isinstance(cur, dict) and isinstance(eff, dict):
            _overlay_last_wins(cur, eff)
        elif cur != eff:
            data[key] = eff


def _load():
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = f.read()
    try:
        return _ryaml.load(raw) or {}
    except Exception as exc:
        if "duplicate key" not in str(exc).lower():
            raise
    # Duplicate keys (e.g. a section appended twice by an older version):
    # reload tolerating duplicates and take last-occurrence values; the next
    # save rewrites the file without them.
    print(
        f"warning: {CONFIG_PATH} contains duplicate YAML keys; "
        f"saving will remove them (last occurrence wins)"
    )
    # allow_duplicate_keys only takes effect if set before the instance is
    # first used, so the recovery load needs a fresh YAML object.
    recovery = YAML()
    recovery.preserve_quotes = True
    recovery.allow_duplicate_keys = True
    data = recovery.load(raw) or {}
    effective = yaml.safe_load(raw) or {}
    if isinstance(data, dict) and isinstance(effective, dict):
        _overlay_last_wins(data, effective)
    return data


def _save(data) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Backup before writing
    if CONFIG_PATH.exists():
        shutil.copy2(CONFIG_PATH, BACKUP_PATH)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        _ryaml.dump(data, f)


def _get_nested(data: dict, dotted_key: str):
    parts = dotted_key.split(".")
    node = data
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _set_nested(data: dict, dotted_key: str, value) -> None:
    parts = dotted_key.split(".")
    node = data
    for part in parts[:-1]:
        if part not in node or not isinstance(node[part], dict):
            node[part] = {}
        node = node[part]
    node[parts[-1]] = value


def _coerce(value_str: str, expected_type):
    if expected_type == bool:
        if value_str.lower() in ("true", "1", "yes"):
            return True
        if value_str.lower() in ("false", "0", "no"):
            return False
        raise ValueError(f"Expected boolean, got: {value_str!r}")
    if expected_type == int:
        return int(value_str)
    return value_str  # str


def _type_name(value) -> str:
    """Friendly type name for messages (ruamel wraps scalars in subclasses)."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def cmd_view(_args) -> None:
    if not CONFIG_PATH.exists():
        print("(config file is empty or does not exist)")
        return
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        print(f.read(), end="")


def cmd_get(args) -> None:
    data = _load()
    value = _get_nested(data, args.key)
    if value is None:
        print(f"(key not set: {args.key})")
    else:
        print(value)


def cmd_set(args) -> None:
    key = args.key
    if key not in VALID_KEYS:
        print(f"ERROR: Unknown config key: {key!r}", file=sys.stderr)
        print(f"Valid keys: {', '.join(sorted(VALID_KEYS))}", file=sys.stderr)
        sys.exit(1)

    expected_type = VALID_KEYS[key]
    try:
        value = _coerce(args.value, expected_type)
    except (ValueError, TypeError) as e:
        print(f"ERROR: Invalid value for {key!r}: {e}", file=sys.stderr)
        sys.exit(1)

    data = _load()
    _set_nested(data, key, value)
    _save(data)

    print(f"Set {key} = {value!r}")
    print(f"Backup saved to: {BACKUP_PATH}")
    print()
    print("NOTE: Restart the siada daemon for changes to take effect:")
    print("  siada-cli --restart-daemon")
    print("(or stop it with 'siada-cli --stop-daemon'; it auto-starts again on the next launch)")


def cmd_validate(_args) -> None:
    if not CONFIG_PATH.exists():
        print("Config file does not exist, using defaults.")
        return
    try:
        data = _load()
    except Exception as e:
        print(f"[ERROR] YAML parse error: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, dict):
        print(
            "[ERROR] conf.yaml root must be a YAML mapping of keys to values, "
            f"got {type(data).__name__}",
            file=sys.stderr,
        )
        sys.exit(1)

    issues = []

    # Check for unknown top-level keys.
    # KNOWN_TOP_KEYS covers the sections that VALID_KEYS can target, the object
    # sections, and the legacy keys described above - so a valid conf.yaml is not
    # reported as having unknown keys.
    unknown_top = set(data.keys()) - KNOWN_TOP_KEYS

    for key in sorted(unknown_top):
        issues.append(f"[WARN]  Unknown top-level key: {key!r}")

    # Legacy keys are tolerated, but they do not enable anything in this build.
    for key in sorted(LEGACY_TOP_KEYS & set(data.keys())):
        issues.append(
            f"[WARN]  legacy key {key!r} is kept for compatibility only: "
            f"{LEGACY_TOP_KEY_NOTES[key]}"
        )

    # Check value types for all present keys
    type_names = {bool: "bool", int: "int", str: "str"}
    for dotted_key, expected_type in sorted(VALID_KEYS.items()):
        value = _get_nested(data, dotted_key)
        if value is None:
            continue  # key not set — skip, not an error
        # YAML parses bare true/false as bool already, and integers as int
        actual_ok = isinstance(value, expected_type)
        # bool is a subclass of int in Python, guard against that
        if expected_type == int and isinstance(value, bool):
            actual_ok = False
        if actual_ok:
            print(f"[OK]    {dotted_key} = {value!r}")
        else:
            actual_name = _type_name(value)
            expected_name = type_names.get(expected_type, expected_type.__name__)
            issues.append(
                f"[WARN]  {dotted_key}: expected {expected_name}, got {actual_name} ({value!r})"
            )

    for issue in issues:
        print(issue)

    if not issues:
        print("\nAll checks passed. Config format looks correct.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Siada configuration manager")
    sub = parser.add_subparsers(dest="action", required=True)

    sub.add_parser("view", help="Print current configuration")
    sub.add_parser("validate", help="Validate config file syntax")

    get_p = sub.add_parser("get", help="Get a config value by dotted key")
    get_p.add_argument("--key", required=True, help="Dotted key, e.g. llm_config.model")

    set_p = sub.add_parser("set", help="Set a config value")
    set_p.add_argument("--key", required=True, help="Dotted key, e.g. proactive.enabled")
    set_p.add_argument("--value", required=True, help="New value")

    args = parser.parse_args()
    dispatch = {"view": cmd_view, "get": cmd_get, "set": cmd_set, "validate": cmd_validate}
    dispatch[args.action](args)


if __name__ == "__main__":
    main()
