#!/usr/bin/env python3
"""
Siada configuration manager.
Read, modify, and validate ~/.siada-cli/conf.yaml
"""

import argparse
import shutil
import sys
from pathlib import Path

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
    "llm_config.parallel_tool_calls": bool,
    "checkpoint_config.enable": bool,
    "checkpoint_config.max_checkpoint_files": int,
    "proactive.enabled": bool,
    "proactive.work_hours": str,
    "proactive.trigger_interval": int,
    "proactive.daily_task_execution_time": str,
    "proactive.auto_execute_enabled": bool,
    "command_timeout": int,
    "pre_plan": bool,
    "preferred_language": str,
}


def _load():
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return _ryaml.load(f) or {}


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
    print("  siada --stop-daemon")
    print("  siada")


def cmd_validate(_args) -> None:
    if not CONFIG_PATH.exists():
        print("Config file does not exist, using defaults.")
        return
    try:
        data = _load()
    except Exception as e:
        print(f"[ERROR] YAML parse error: {e}", file=sys.stderr)
        sys.exit(1)

    issues = []

    # Check for unknown top-level keys
    known_top = {"llm_config", "checkpoint_config", "proactive", "command_timeout", "user_id", "pre_plan", "preferred_language"}
    unknown_top = set(data.keys()) - known_top
    for key in sorted(unknown_top):
        issues.append(f"[WARN]  Unknown top-level key: {key!r}")

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
            actual_name = type(value).__name__
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
