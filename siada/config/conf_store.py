"""Centralised raw read/write access to ``~/.siada-cli/conf.yaml``.

All direct YAML I/O on conf.yaml goes through this module so that format
and IO errors are caught and reported once, consistently, instead of each
call site hand-rolling its own ``yaml.safe_load`` + ``except Exception``.

Read path (PyYAML, plain dicts — used by the many "read fresh each call"
readers):

    read_conf_dict()          -> whole file as a dict ({} on any error)
    get_conf_value(key, ...)  -> dotted-key lookup, e.g. "llm_config.model"
    get_conf_section(key)     -> mapping section or {}

Write paths (atomic: tmp file + os.replace, so a crash never leaves a
truncated conf.yaml):

    write_conf_dict(data)     -> full-file replace (comments NOT preserved)
    update_conf(mutator)      -> read-modify-write that PRESERVES comments
                                 (ruamel round-trip); mutator returns False
                                 to abort the write
    save_conf_fields(mapping) -> convenience: set several dotted keys at once

Error policy: every function catches OSError / YAML errors, logs a single
warning per distinct error (with file path and, for syntax errors, the
line/column), and returns a safe fallback ({} / default / False). Config
problems must never crash an entry point (CLI, ACP server, daemon, IM).
"""

from __future__ import annotations

import io
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

import yaml

from siada.foundation.constants import SIADA_HOME
from siada.foundation.logging import logger


def get_conf_path() -> Path:
    """Return the canonical conf.yaml path."""
    return SIADA_HOME / "conf.yaml"


# Distinct errors already warned about in this process — readers such as
# fast_llm intentionally re-read conf.yaml on every call, so without this a
# broken file would spam the log once per turn.
_warned_errors: set[str] = set()


def _warn_once(message: str) -> None:
    if message in _warned_errors:
        logger.debug(message)
        return
    _warned_errors.add(message)
    logger.warning(message)


def _describe_yaml_error(exc: yaml.YAMLError) -> str:
    mark = getattr(exc, "problem_mark", None)
    problem = getattr(exc, "problem", None)
    if mark is not None:
        return f"line {mark.line + 1}, column {mark.column + 1}: {problem or exc}"
    return str(exc)


def read_conf_dict(
    config_path: Optional[Path] = None,
    on_error: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Read conf.yaml as a plain dict. Returns {} when missing or invalid.

    ``on_error`` (if given) receives a human-readable message when the file
    exists but cannot be parsed — interactive entry points use this to show
    the problem to the user, in addition to the logged warning.
    """

    def _fail(message: str) -> Dict[str, Any]:
        _warn_once(message)
        if on_error is not None:
            try:
                on_error(message)
            except Exception:
                pass
        return {}

    path = config_path or get_conf_path()
    try:
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        return _fail(
            f"conf.yaml has a YAML syntax error ({_describe_yaml_error(exc)}) "
            f"in {path}; treating it as empty. Please fix the file."
        )
    except OSError as exc:
        return _fail(f"Failed to read {path}: {exc}; treating it as empty.")
    if data is None:
        return {}
    if not isinstance(data, dict):
        return _fail(
            f"conf.yaml top level is {type(data).__name__}, expected a mapping, "
            f"in {path}; treating it as empty."
        )
    return data


def get_conf_value(key: str, default: Any = None, config_path: Optional[Path] = None) -> Any:
    """Look up a dotted key (e.g. "llm_config.model") in conf.yaml."""
    node: Any = read_conf_dict(config_path)
    for part in key.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return default
        node = node[part]
    return node


def get_conf_section(key: str, config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Return a mapping section of conf.yaml ({} when absent or not a mapping)."""
    value = get_conf_value(key, default=None, config_path=config_path)
    if value is None:
        return {}
    if not isinstance(value, dict):
        _warn_once(
            f"conf.yaml section '{key}' is {type(value).__name__}, "
            f"expected a mapping; ignoring it."
        )
        return {}
    return value


def _atomic_write_text(path: Path, text: str) -> None:
    """Write text to path atomically (tmp file + os.replace).

    On Windows, os.replace fails with PermissionError while another
    process holds the target file open (e.g. readers re-loading
    conf.yaml), so the replace is retried briefly before giving up.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        attempts = 3
        for attempt in range(attempts):
            try:
                os.replace(tmp_name, path)
                break
            except PermissionError:
                if attempt == attempts - 1:
                    raise
                time.sleep(0.05)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_conf_dict(data: Mapping[str, Any], config_path: Optional[Path] = None) -> bool:
    """Overwrite conf.yaml with the given mapping (comments are NOT preserved).

    Prefer update_conf() when modifying an existing user file; this is for
    cases that intentionally rewrite the whole document.
    """
    path = config_path or get_conf_path()
    try:
        buf = io.StringIO()
        yaml.safe_dump(dict(data), buf, default_flow_style=False, allow_unicode=True)
        _atomic_write_text(path, buf.getvalue())
        return True
    except Exception as exc:
        logger.warning(f"Failed to write {path}: {exc}")
        return False


def update_conf(
    mutator: Callable[[Dict[str, Any]], Any],
    config_path: Optional[Path] = None,
) -> bool:
    """Read-modify-write conf.yaml, preserving comments and formatting.

    The file is loaded with ruamel (round-trip), passed to ``mutator`` for
    in-place edits, and written back atomically. If ``mutator`` returns
    ``False`` the write is skipped (treated as success — nothing to do).

    Returns False (and logs a warning) on any read/parse/write error.
    """
    path = config_path or get_conf_path()
    try:
        from ruamel.yaml import YAML

        path.parent.mkdir(parents=True, exist_ok=True)
        ryaml = YAML()
        ryaml.preserve_quotes = True
        data = ryaml.load(path) if path.exists() else None
        if data is None:
            data = {}
        if not isinstance(data, dict):
            logger.warning(
                f"conf.yaml top level is {type(data).__name__}, expected a mapping, "
                f"in {path}; refusing to update."
            )
            return False
        if mutator(data) is False:
            return True
        buf = io.StringIO()
        ryaml.dump(data, buf)
        _atomic_write_text(path, buf.getvalue())
        return True
    except Exception as exc:
        mark = getattr(exc, "problem_mark", None)
        if mark is not None:
            logger.warning(
                f"Failed to update {path}: YAML syntax error at "
                f"line {mark.line + 1}, column {mark.column + 1}: "
                f"{getattr(exc, 'problem', None) or exc}"
            )
        else:
            logger.warning(f"Failed to update {path}: {exc}")
        return False


def save_conf_fields(fields: Mapping[str, Any], config_path: Optional[Path] = None) -> bool:
    """Set several dotted keys (e.g. {"llm_config.model": "x"}) in one write."""

    def _apply(data: Dict[str, Any]) -> None:
        for key, value in fields.items():
            node = data
            parts = key.split(".")
            for part in parts[:-1]:
                child = node.get(part)
                if not isinstance(child, dict):
                    child = {}
                    node[part] = child
                node = child
            node[parts[-1]] = value

    return update_conf(_apply, config_path)
