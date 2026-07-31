"""LarkAccessControl - DM and group access control policy checker.

Extracted from LarkController to isolate permission checking logic.
Supports both DM (p2p) and group chat access control.
"""

import logging
from typing import Optional

from siada.im.models import IMMessage

logger = logging.getLogger("siada.im.lark.access_control")


class LarkAccessControl:
    """Access control policy checker for Lark IM.

    DM policies:
    - "open": allow all DMs
    - "allowlist" (default): only allow users listed in allow_from
    """

    def __init__(self, config: dict, mode: str):
        self._config = config
        self._mode = mode

    @staticmethod
    def resolve_pair_key(msg: IMMessage) -> str:
        """Resolve the pair key for access control matching.

        Prefer open_id (ou_xxx), fallback to user_id.
        """
        return msg.sender_open_id or msg.user_id or ""

    def check_group_access(self, msg: IMMessage) -> bool:
        """Check if a group chat is allowed based on access.group_policy config.

        Group policies:
        - "open": allow all group chats
        - "allowlist" (default): only allow groups listed in group_allow_from
        - "disabled": reject all group messages

        In relay mode, group access control is handled server-side by the
        Gateway (same as DM access), so this always returns True.

        Reference: OpenClaw policy.ts -> isFeishuGroupAllowed()
        """
        # Relay mode: access control is handled server-side by the Gateway
        if self._mode == "relay":
            return True

        access_cfg = self._config.get("lark", {}).get("access", {})
        group_policy = access_cfg.get("group_policy", "allowlist")

        if group_policy == "open":
            return True

        if group_policy == "disabled":
            logger.info("group_policy=disabled, blocking group %s", msg.chat_id)
            return False

        # allowlist mode (default)
        group_allow_from = set(access_cfg.get("group_allow_from") or [])
        if not group_allow_from:
            logger.warning(
                "group_policy=allowlist but group_allow_from is empty, blocking all groups"
            )
            return False

        # Check chat_id (group ID like oc_xxx) against allowlist
        if msg.chat_id in group_allow_from:
            return True

        logger.info(
            "Group %s not in group_allow_from, blocked by group_policy=allowlist",
            msg.chat_id,
        )
        return False

    def check_dm_access(self, msg: IMMessage) -> bool:
        """Check if a DM sender is allowed based on access.dm_policy config.

        In relay mode, access control is handled by the Gateway server,
        so this always returns True.

        Returns True if allowed, False if blocked.
        """
        # Relay mode: access control is handled server-side by the Gateway
        if self._mode == "relay":
            return True

        access_cfg = self._config.get("lark", {}).get("access", {})
        dm_policy = access_cfg.get("dm_policy", "allowlist")

        if dm_policy == "open":
            return True

        # allowlist mode (default)
        allow_from = set(access_cfg.get("allow_from") or [])
        if not allow_from:
            logger.warning("dm_policy=allowlist but allow_from is empty, blocking all DMs")
            return False

        if msg.user_id in allow_from:
            return True
        if msg.sender_open_id and msg.sender_open_id in allow_from:
            return True

        return False

    # ── Group config resolution ──────────────────────────────────────

    def _get_group_config(self, chat_id: str) -> Optional[dict]:
        """Resolve per-group config with wildcard fallback.

        Resolution order:
        1. Exact chat_id match in groups config
        2. Wildcard "*" entry
        3. None (no per-group config)

        Reference: OpenClaw policy.ts -> resolveFeishuGroupConfig()
        """
        lark_cfg = self._config.get("lark", {})
        groups_cfg = lark_cfg.get("groups", {})

        if chat_id in groups_cfg:
            return groups_cfg[chat_id]
        if "*" in groups_cfg:
            return groups_cfg["*"]
        return None

    def get_group_config(self, chat_id: str) -> Optional[dict]:
        """Public accessor for per-group config (used by GroupChatHandler)."""
        return self._get_group_config(chat_id)
