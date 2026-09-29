"""
Tests for Controller._build_pending_input_for_ai_analysis.

Regression coverage for a bug where /goal's kickoff turn was the one user
input entry point that reached the model *without* the
<user_input>...</user_input> wrapper every other entry point applies to
literal, human-authored text (see
``siada.services.memory.holographic.marker.wrap_user_input`` and its other
call sites: ``ConversationTurn`` for plain-string turns,
``PendingUserInputInjector`` for multimodal/mid-turn-queued list-shaped
turns). The bug: /goal builds its pending_input as a Responses-API list
directly in this method, so it never reaches ConversationTurn's own
isinstance(str) wrap check — meaning the raw "/goal <objective>" text was
persisted and sent to the model completely unwrapped.
"""
from siada.entrypoint.interaction.controller import Controller
from siada.services.memory.holographic.marker import (
    USER_INPUT_BEGIN,
    USER_INPUT_END,
    strip_user_input,
)


class TestBuildPendingInputForAiAnalysis:
    def test_non_goal_callers_get_a_bare_passthrough_string(self):
        """/init, /issue_fix and other generic SwitchEvent(ai_analysis_prompt=...)
        consumers must keep getting a plain string back, unchanged."""
        result = Controller._build_pending_input_for_ai_analysis(
            "analyze the cost calculation", goal_command=False
        )
        assert result == "analyze the cost calculation"

    def test_goal_wraps_the_full_command_text_in_user_input_tags(self):
        """/goal must get back a Responses-API input list whose single
        input_text part is the *entire* "/goal <objective>" text wrapped in
        <user_input>...</user_input>, exactly like every other entry point
        wraps literal human-authored text before it reaches the model."""
        result = Controller._build_pending_input_for_ai_analysis(
            "使用worktree 为当前项目增加功能", goal_command=True
        )

        assert isinstance(result, list) and len(result) == 1
        message = result[0]
        assert message["role"] == "user"
        parts = message["content"]
        assert isinstance(parts, list) and len(parts) == 1
        text = parts[0]["text"]
        assert parts[0]["type"] == "input_text"

        # The whole literal command text must be wrapped, prefix included.
        assert text.startswith(USER_INPUT_BEGIN)
        assert text.endswith(USER_INPUT_END)
        assert strip_user_input(text) == "/goal 使用worktree 为当前项目增加功能"

    def test_goal_does_not_double_wrap_an_already_wrapped_objective(self):
        """wrap_user_input() is itself idempotent, but exercise the /goal
        branch with an objective that already looks wrapped to make sure no
        double <user_input> nesting sneaks in via the "/goal " prefix
        concatenation."""
        result = Controller._build_pending_input_for_ai_analysis(
            "do the thing", goal_command=True
        )
        text = result[0]["content"][0]["text"]
        assert text.count(USER_INPUT_BEGIN) == 1
        assert text.count(USER_INPUT_END) == 1
