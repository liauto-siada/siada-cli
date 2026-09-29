"""Tests for the shared SwitchEvent ai_analysis_prompt follow-up shaping."""
from siada.entrypoint.interaction.turn_input import format_ai_analysis_followup


def test_non_goal_prompt_passes_through_unchanged():
    assert (
        format_ai_analysis_followup("analyze the cost calculation", goal_command=False)
        == "analyze the cost calculation"
    )


def test_goal_prompt_gets_full_command_prefix():
    assert (
        format_ai_analysis_followup("使用worktree 增加功能", goal_command=True)
        == "/goal 使用worktree 增加功能"
    )