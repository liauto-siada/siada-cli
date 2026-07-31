"""Tests for LarkSlashCommandHandler `/skill-name` slash-command support.

Covers the fix that allows IM (Lark) users to invoke skill-based slash
commands (e.g. ``/siada-help``) which resolve to an AI analysis prompt.

Imports are deferred inside test functions to avoid triggering the
``siada.session <-> siada.support.checkpoint_tracker`` circular-import
situation that trips the module collector when top-level imports happen
in a specific order.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


# ── Helpers ────────────────────────────────────────────────────────────


def _make_session(workspace: Path):
    """Build a minimal stand-in for RunningSession that satisfies the handler."""
    siada_config = SimpleNamespace(workspace=str(workspace))
    return SimpleNamespace(
        session_id="test-session",
        siada_config=siada_config,
        state=SimpleNamespace(),
    )


def _make_handler():
    # Pre-import session modules BEFORE slash_commands to work around a
    # pre-existing circular-import quirk between
    #   siada.session.session_models <-> siada.support.checkpoint_tracker
    # which is otherwise only masked by incidental import ordering.
    import siada.session.session_models  # noqa: F401
    import siada.support.slash_commands  # noqa: F401

    from siada.im.feishu.slash_command_handler import LarkSlashCommandHandler


    lark_io = MagicMock()
    lark_io.print_info = MagicMock()
    lark_io.print_error = MagicMock()
    lark_io.set_context = MagicMock()

    card_sender = MagicMock()
    card_sender.send_im = AsyncMock()

    handler = LarkSlashCommandHandler(
        lark_io=lark_io, card_sender=card_sender, verbose_config=None,
        controller=None,
    )
    return handler


def _make_msg(content: str):
    from siada.im.models import IMMessage

    return IMMessage(
        request_id="req-1", platform="lark",
        user_id="u", chat_id="c", chat_type="p2p",
        content_type="text", content=content,
        timestamp=0, raw={}, message_id="m",
        sender_name="n", sender_open_id="o",
    )


# ── Tests ──────────────────────────────────────────────────────────────


def test_allowed_commands_without_session_excludes_skills(tmp_path):
    """Backward-compat: no session → only built-in commands are listed."""
    handler = _make_handler()
    allowed = handler._get_im_allowed_commands()
    # siada-help ships with the repo's built-in skills, so it MUST be absent
    # when session is not provided.
    assert "siada-help" not in allowed


def test_allowed_commands_with_session_includes_skills(tmp_path):
    """With a session, skill names are registered as IM-allowed commands."""
    handler = _make_handler()
    session = _make_session(tmp_path)
    allowed = handler._get_im_allowed_commands(session)
    # siada-help ships with siada/resources/skills/siada-help so it should be
    # visible once the skill service can resolve the workspace.
    assert "siada-help" in allowed


def test_skill_help_description_is_included(tmp_path):
    """/help text should render skill descriptions when session is provided."""
    handler = _make_handler()
    session = _make_session(tmp_path)
    help_text = handler._build_im_help(session)
    # The help block should list the skill command,
    # and the description shouldn't be "No description available".
    assert "/siada-help" in help_text
    # Grab the line that starts with /siada-help and ensure it has some text
    for line in help_text.splitlines():
        if line.lstrip().startswith("/siada-help"):
            remainder = line.split("/siada-help", 1)[1].strip()
            assert remainder, "skill help line must contain a description"
            assert remainder != "No description available."
            break
    else:  # pragma: no cover - defensive
        pytest.fail("/siada-help line missing from help")


def test_plugin_command_not_blocked_in_im_mode(tmp_path):
    """``/plugin`` should be allowed in IM mode so users can manage skills remotely.

    Built-in ``cmd_plugin`` falls back to plain-text IO output when the IO
    has no ACP adapter (as is the case for LarkIO), so there is no reason
    to keep it in _IM_BLOCKED_COMMANDS.
    """
    handler = _make_handler()
    session = _make_session(tmp_path)
    allowed = handler._get_im_allowed_commands(session)
    assert "plugin" in allowed, (
        "Expected /plugin to be part of IM-allowed commands after unblocking; "
        f"got {sorted(allowed)[:15]}..."
    )


def test_handle_dispatches_skill_as_ai_analysis(tmp_path):

    """
    A `/skill-name` message must NOT be rejected by the allowed-commands
    filter and must be routed through SlashCommands.run(), which returns a
    SwitchEvent(ai_analysis_prompt=...) for the handler to execute.
    """
    from siada.support.slash_commands import SwitchEvent

    handler = _make_handler()
    session = _make_session(tmp_path)
    msg = _make_msg("/siada-help what can you do")

    # Stub out _handle_switch_event to capture the dispatched event instead
    # of running the agent pipeline.
    captured: dict = {}

    async def _capture_switch(event, m, s):
        captured["event"] = event
        captured["msg"] = m

    handler._handle_switch_event = _capture_switch  # type: ignore[assignment]

    handled = asyncio.run(handler.handle(msg, session))
    assert handled is True

    # The handler must NOT have sent the "not supported" reject reply.
    reject_calls = [
        c for c in handler._card_sender.send_im.call_args_list
        if "not supported" in (c.args[2] if len(c.args) >= 3 else "")
    ]
    assert not reject_calls, (
        "Skill slash command was rejected as unsupported: "
        f"{handler._card_sender.send_im.call_args_list}"
    )

    # And the event returned by SlashCommands.do_run must be an
    # ai_analysis_prompt SwitchEvent carrying the skill invocation.
    event = captured.get("event")
    assert isinstance(event, SwitchEvent), (
        f"expected SwitchEvent, got {event!r}"
    )
    prompt = event.kwargs.get("ai_analysis_prompt", "")
    assert "siada-help" in prompt, (
        f"ai_analysis_prompt should reference the skill, got: {prompt!r}"
    )
    assert "what can you do" in prompt, (
        "skill args should be forwarded into the prompt body"
    )


def test_goal_command_is_blocked_in_im_mode(tmp_path):
    """``/goal`` is temporarily not supported in Lark/Feishu IM mode.

    The standing-goal feature's GoalStatusBar / verifier UX is currently
    ACP-frontend-only, so there is no way to surface goal state in IM yet.
    ``/goal`` must therefore stay out of the IM-allowed commands set, and a
    user issuing it should get the generic "not supported in IM mode"
    message rather than actually starting a goal.
    """
    handler = _make_handler()
    session = _make_session(tmp_path)
    allowed = handler._get_im_allowed_commands(session)
    assert "goal" not in allowed, (
        "Expected /goal to be blocked in IM mode; "
        f"got {sorted(allowed)[:15]}..."
    )


def test_goal_command_message_rejected_with_not_supported_notice(tmp_path):
    """Sending ``/goal <objective>`` in IM should be rejected, not executed."""
    handler = _make_handler()
    session = _make_session(tmp_path)
    msg = _make_msg("/goal ship the feature by friday")

    handled = asyncio.run(handler.handle(msg, session))

    assert handled is True
    handler._card_sender.send_im.assert_awaited_once()
    call_args = handler._card_sender.send_im.call_args
    sent_text = call_args.args[2] if len(call_args.args) >= 3 else ""
    assert "not supported in IM mode" in sent_text
    assert "/goal" in sent_text
