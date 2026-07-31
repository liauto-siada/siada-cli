"""
Tests for skill-derived slash commands in SlashCommands.
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Pre-import to break circular-import chain:
# slash_commands -> checkpoint_tracker -> session.task_message_state
import siada.session  # noqa: F401
import siada.support.checkpoint_tracker  # noqa: F401

from siada.support.slash_commands import SlashCommands, SwitchEvent
from siada.services.skills.models import SkillMetadata, SkillScope, SkillLoadOutcome


def _make_session(workspace: str = "/tmp/ws") -> MagicMock:
    session = MagicMock()
    session.siada_config.workspace = workspace
    return session


def _make_skill(name: str, description: str = "A skill") -> SkillMetadata:
    return SkillMetadata(
        name=name,
        description=description,
        path=Path(f"/fake/{name}/SKILL.md"),
        scope=SkillScope.USER,
    )


def _make_outcome(*skill_names) -> SkillLoadOutcome:
    return SkillLoadOutcome(
        skills=[_make_skill(n) for n in skill_names]
    )


# ---------------------------------------------------------------------------
# get_commands — skill discovery
# ---------------------------------------------------------------------------

class TestGetCommandsSkillDiscovery:

    def _make_slash_commands(self) -> SlashCommands:
        io = MagicMock()
        sc = SlashCommands(io=io)
        # Disable custom command loading so it doesn't touch the filesystem
        sc.custom_command_service = MagicMock()
        sc.custom_command_service.get_command_names.return_value = []
        return sc

    def test_skill_commands_appear_in_get_commands(self):
        """Skills are returned as /skill-name entries."""
        sc = self._make_slash_commands()
        session = _make_session()
        outcome = _make_outcome("brainstorming", "docx")

        with patch(
            "siada.services.skills.SkillsManager"
        ) as MockManager:
            MockManager.get_instance.return_value.get_skills.return_value = outcome
            commands = sc.get_commands(session)

        assert "/brainstorming" in commands
        assert "/docx" in commands

    def test_skill_command_does_not_shadow_builtin(self):
        """A skill named 'model' must not duplicate the built-in /model command."""
        sc = self._make_slash_commands()
        session = _make_session()
        outcome = _make_outcome("model")  # conflicts with built-in /model

        with patch(
            "siada.services.skills.SkillsManager"
        ) as MockManager:
            MockManager.get_instance.return_value.get_skills.return_value = outcome
            commands = sc.get_commands(session)

        # /model appears exactly once
        assert commands.count("/model") == 1

    def test_skill_commands_absent_without_session(self):
        """Without a session, no skill commands are added."""
        sc = self._make_slash_commands()

        with patch(
            "siada.services.skills.SkillsManager"
        ) as MockManager:
            commands = sc.get_commands(session=None)

        MockManager.get_instance.assert_not_called()
        assert "/brainstorming" not in commands

    def test_skill_load_error_is_swallowed(self):
        """An exception from SkillsManager must not propagate out of get_commands."""
        sc = self._make_slash_commands()
        session = _make_session()

        with patch(
            "siada.services.skills.SkillsManager"
        ) as MockManager:
            MockManager.get_instance.side_effect = RuntimeError("boom")
            commands = sc.get_commands(session)  # must not raise

        # Built-in commands are still returned
        assert "/help" in commands


# ---------------------------------------------------------------------------
# do_run — skill execution
# ---------------------------------------------------------------------------

class TestDoRunSkillExecution:

    def _make_slash_commands(self) -> SlashCommands:
        io = MagicMock()
        sc = SlashCommands(io=io)
        sc.custom_command_service = MagicMock()
        sc.custom_command_service.get_command.return_value = None
        sc.custom_command_service.get_command_names.return_value = []
        return sc

    def test_skill_command_returns_switch_event(self):
        """Running a skill command returns SwitchEvent(ai_analysis_prompt=...)."""
        sc = self._make_slash_commands()
        session = _make_session()
        skill = _make_skill("brainstorming", "Brainstorming skill")
        outcome = SkillLoadOutcome(skills=[skill])

        with patch(
            "siada.services.skills.SkillsManager"
        ) as MockManager:
            MockManager.get_instance.return_value.get_skills.return_value = outcome
            MockManager.get_instance.return_value.get_skill_by_name.return_value = skill
            result = sc.do_run(session, "brainstorming", "design a login feature")

        assert isinstance(result, SwitchEvent)
        prompt = result.kwargs["ai_analysis_prompt"]
        assert "brainstorming" in prompt
        assert "design a login feature" in prompt

    def test_skill_command_without_args(self):
        """Running a skill command with no args still returns a valid prompt."""
        sc = self._make_slash_commands()
        session = _make_session()
        skill = _make_skill("docx")
        outcome = SkillLoadOutcome(skills=[skill])

        with patch(
            "siada.services.skills.SkillsManager"
        ) as MockManager:
            MockManager.get_instance.return_value.get_skills.return_value = outcome
            MockManager.get_instance.return_value.get_skill_by_name.return_value = skill
            result = sc.do_run(session, "docx", "")

        assert isinstance(result, SwitchEvent)
        prompt = result.kwargs["ai_analysis_prompt"]
        assert "docx" in prompt

    def test_unknown_command_falls_through_to_not_found(self):
        """A command that matches neither built-in, custom, nor skill prints error."""
        sc = self._make_slash_commands()
        session = _make_session()

        with patch(
            "siada.services.skills.SkillsManager"
        ) as MockManager:
            MockManager.get_instance.return_value.get_skills.return_value = SkillLoadOutcome()
            MockManager.get_instance.return_value.get_skill_by_name.return_value = None
            result = sc.do_run(session, "nonexistent-command", "")

        sc.io.print_info.assert_called()
        assert result is None

    def test_skill_lookup_error_falls_through_to_not_found(self):
        """An exception during skill lookup must not propagate; prints not-found."""
        sc = self._make_slash_commands()
        session = _make_session()

        with patch(
            "siada.services.skills.SkillsManager"
        ) as MockManager:
            MockManager.get_instance.side_effect = RuntimeError("boom")
            result = sc.do_run(session, "brainstorming", "")

        sc.io.print_info.assert_called()
        assert result is None
