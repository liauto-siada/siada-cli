"""VerboseConfig - Per chat-type verbose output configuration for IM.

Controls the level of detail shown in stream output:
- ON  (verbose=True):  Show 💭 Thinking + 🔧 Tool Calls + 💬 Answer
- OFF (verbose=False): Show only 💬 Answer (minimal output)

Granularity: split by chat_type (``p2p`` vs ``group``), not per chat_id.

Defaults:
- P2P (single chat): verbose ON
- Group chat:        verbose OFF

Persisted to the main configuration file (``conf.yaml``) under the key
``im.verbose.{p2p|group}`` so user preferences survive process restarts
and are managed alongside the rest of the Siada configuration.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from siada.config.config_loader import save_conf_field

logger = logging.getLogger("siada.im.verbose_config")


# Default verbose state per chat_type.
_DEFAULTS: Dict[str, bool] = {
    "p2p": True,
    "group": False,
}


class VerboseConfig:
    """Verbose configuration persisted in ``conf.yaml`` under ``im.verbose``.

    Storage layout (YAML)::

        im:
          verbose:
            p2p: true
            group: false

    The ``platform_name`` parameter is accepted for API compatibility with
    existing callers, but is not used: the verbose setting is global across
    IM platforms and only split by chat_type.
    """

    def __init__(self, platform_name: Optional[str] = None):
        self._platform_name = platform_name
        # Cached overrides loaded from conf.yaml. Missing keys fall back
        # to the built-in defaults in ``_DEFAULTS``.
        self._overrides: Dict[str, bool] = {}
        self.load()

    # ── Persistence ───────────────────────────────────────────────────

    def load(self) -> None:
        """Load per chat-type verbose overrides from ``conf.yaml``."""
        try:
            # Reload conf.yaml directly to pick up external edits.
            import yaml
            from siada.config.config_loader import _get_default_config_path

            config_path = _get_default_config_path()
            if not config_path.exists():
                self._overrides = {}
                return

            with open(config_path, "r", encoding="utf-8") as f:
                data: Dict[str, Any] = yaml.safe_load(f) or {}

            im_section = data.get("im") or {}
            verbose_section = im_section.get("verbose") or {}
            overrides: Dict[str, bool] = {}
            if isinstance(verbose_section, dict):
                for k in ("p2p", "group"):
                    if k in verbose_section and verbose_section[k] is not None:
                        overrides[k] = bool(verbose_section[k])
            self._overrides = overrides
            logger.debug(
                "Loaded verbose config from conf.yaml: %s", self._overrides,
            )
        except Exception as e:
            logger.warning("Failed to load verbose config from conf.yaml: %s", e)
            self._overrides = {}

    # ── Query / mutate ────────────────────────────────────────────────

    @staticmethod
    def _normalize_chat_type(chat_type: str) -> str:
        """Normalize ``chat_type`` to one of ``p2p`` / ``group``."""
        return "p2p" if chat_type == "p2p" else "group"

    def is_verbose(self, chat_id: str, chat_type: str) -> bool:
        """Return whether verbose output is enabled for a given chat.

        Resolution order:
        1. Persisted override for chat_type (``p2p`` or ``group``) in
           ``conf.yaml``.
        2. Built-in default: ``p2p`` → True, ``group`` → False.

        The ``chat_id`` parameter is accepted for API compatibility but is
        not used by the new chat-type-scoped model.
        """
        key = self._normalize_chat_type(chat_type)
        if key in self._overrides:
            return self._overrides[key]
        return _DEFAULTS[key]

    def set_verbose(self, chat_type: str, verbose: bool) -> None:
        """Persist the verbose flag for the given chat_type to ``conf.yaml``.

        Writes to ``im.verbose.{p2p|group}`` while preserving comments /
        formatting of the rest of the file.
        """
        key = self._normalize_chat_type(chat_type)
        self._overrides[key] = verbose
        ok = save_conf_field(f"im.verbose.{key}", verbose)
        if ok:
            logger.info(
                "Verbose set to %s for chat_type=%s (persisted to conf.yaml)",
                verbose, key,
            )
        else:
            logger.warning(
                "Failed to persist verbose=%s for chat_type=%s", verbose, key,
            )

    def get_status_text(self, chat_id: str, chat_type: str) -> str:
        """Build a human-readable status string for ``/verbose`` output."""
        key = self._normalize_chat_type(chat_type)
        current = self.is_verbose(chat_id, chat_type)
        has_override = key in self._overrides
        default_label = "on" if _DEFAULTS[key] else "off"

        status = "on" if current else "off"
        source = (
            "conf.yaml override" if has_override else f"default for {key}"
        )

        return (
            f"Verbose mode: **{status}** ({source})\n"
            f"Default for {key}: {default_label}\n\n"
            f"Persisted in `conf.yaml` under `im.verbose.{key}`.\n"
            f"Usage: `/verbose on` or `/verbose off`"
        )
