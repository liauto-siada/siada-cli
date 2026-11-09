"""Tests for group-level access policy (group_policy).

Reference: OpenClaw extensions/feishu/src/policy.ts -> isFeishuGroupAllowed()
"""

import pytest
from unittest.mock import MagicMock

from siada.im.feishu.access_control import LarkAccessControl


def _make_msg(chat_id: str = "oc_test_group") -> MagicMock:
    """Create a minimal IMMessage mock for group policy tests."""
    msg = MagicMock()
    msg.chat_id = chat_id
    msg.chat_type = "group"
    return msg


class TestGroupPolicyOpen:
    """group_policy=open should allow all groups."""

    def test_allows_any_group(self):
        config = {"lark": {"access": {"group_policy": "open"}}}
        ac = LarkAccessControl(config, mode="direct")
        assert ac.check_group_access(_make_msg("oc_any")) is True

    def test_allows_without_group_allow_from(self):
        config = {"lark": {"access": {"group_policy": "open"}}}
        ac = LarkAccessControl(config, mode="direct")
        assert ac.check_group_access(_make_msg()) is True


class TestGroupPolicyDisabled:
    """group_policy=disabled should reject all groups."""

    def test_rejects_all_groups(self):
        config = {"lark": {"access": {"group_policy": "disabled"}}}
        ac = LarkAccessControl(config, mode="direct")
        assert ac.check_group_access(_make_msg("oc_any")) is False

    def test_rejects_even_with_group_allow_from(self):
        config = {
            "lark": {
                "access": {
                    "group_policy": "disabled",
                    "group_allow_from": ["oc_any"],
                },
            },
        }
        ac = LarkAccessControl(config, mode="direct")
        assert ac.check_group_access(_make_msg("oc_any")) is False


class TestGroupPolicyAllowlist:
    """group_policy=allowlist (default) should check group_allow_from."""

    def test_allows_group_in_allowlist(self):
        config = {
            "lark": {
                "access": {
                    "group_policy": "allowlist",
                    "group_allow_from": ["oc_allowed_1", "oc_allowed_2"],
                },
            },
        }
        ac = LarkAccessControl(config, mode="direct")
        assert ac.check_group_access(_make_msg("oc_allowed_1")) is True
        assert ac.check_group_access(_make_msg("oc_allowed_2")) is True

    def test_rejects_group_not_in_allowlist(self):
        config = {
            "lark": {
                "access": {
                    "group_policy": "allowlist",
                    "group_allow_from": ["oc_allowed"],
                },
            },
        }
        ac = LarkAccessControl(config, mode="direct")
        assert ac.check_group_access(_make_msg("oc_not_allowed")) is False

    def test_rejects_when_group_allow_from_empty(self):
        config = {
            "lark": {
                "access": {
                    "group_policy": "allowlist",
                    "group_allow_from": [],
                },
            },
        }
        ac = LarkAccessControl(config, mode="direct")
        assert ac.check_group_access(_make_msg("oc_any")) is False

    def test_rejects_when_group_allow_from_missing(self):
        config = {"lark": {"access": {"group_policy": "allowlist"}}}
        ac = LarkAccessControl(config, mode="direct")
        assert ac.check_group_access(_make_msg("oc_any")) is False

    def test_default_policy_is_allowlist(self):
        """When group_policy is not set, default to allowlist."""
        config = {
            "lark": {
                "access": {
                    "group_allow_from": ["oc_allowed"],
                },
            },
        }
        ac = LarkAccessControl(config, mode="direct")
        assert ac.check_group_access(_make_msg("oc_allowed")) is True
        assert ac.check_group_access(_make_msg("oc_other")) is False


class TestGroupPolicyRelayMode:
    """Relay mode does not support group chat, should always reject."""

    def test_relay_always_rejects(self):
        config = {
            "lark": {
                "access": {
                    "group_policy": "open",
                },
            },
        }
        ac = LarkAccessControl(config, mode="relay")
        assert ac.check_group_access(_make_msg("oc_any")) is False

    def test_relay_rejects_even_with_allowlist(self):
        config = {
            "lark": {
                "access": {
                    "group_policy": "allowlist",
                    "group_allow_from": ["oc_any"],
                },
            },
        }
        ac = LarkAccessControl(config, mode="relay")
        assert ac.check_group_access(_make_msg("oc_any")) is False

    def test_relay_rejects_without_config(self):
        config = {}
        ac = LarkAccessControl(config, mode="relay")
        assert ac.check_group_access(_make_msg("oc_any")) is False


class TestGroupPolicyNoConfig:
    """When no lark.access config exists at all."""

    def test_no_access_config_defaults_to_allowlist_blocks(self):
        """No config -> defaults to allowlist with empty list -> blocks all."""
        config = {"lark": {}}
        ac = LarkAccessControl(config, mode="direct")
        assert ac.check_group_access(_make_msg("oc_any")) is False

    def test_no_lark_config_defaults_to_allowlist_blocks(self):
        config = {}
        ac = LarkAccessControl(config, mode="direct")
        assert ac.check_group_access(_make_msg("oc_any")) is False
