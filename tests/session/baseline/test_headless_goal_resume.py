"""The resumed-goal CLI path reports verifier failure instead of success."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from siada.entrypoint import siadahub
from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn
from siada.entrypoint.interaction.turn.models import TurnOutput
from siada.services.goal import goal_storage, verifier
from siada.services.goal.models import Goal, GoalVerdict
from siada.services.siada_runner import SiadaRunner
from siada.support.resume_service import ResumeService


@pytest.mark.parametrize("status", ["active", "blocked"])
def test_resumed_goal_verification_failure_exits_nonzero(baseline, monkeypatch, status):
    source = baseline.session("saved-goal")
    goal = Goal.create("Finish the resumed synthetic goal")
    goal.status = status
    goal_storage.save_goal(source.openai_session.session_folder, goal)
    session = baseline.session("resume-placeholder")
    config = session.siada_config
    config.interactive = False
    config.io.print = Mock()
    config.io.print_error = Mock()
    context = baseline.context(session)
    resume = ResumeService(config.workspace)
    data = resume.session_manager.load_session(source.session_id, source.openai_session.session_folder)

    def restore(args, target, io):
        assert args.resume == source.session_id
        resume.restore_to_running_session(data, target)
        return True, data

    async def execute(*args, **kwargs):
        await SiadaRunner._prepare_context_for_run(context, session)
        return TurnOutput(output="partial resumed answer", metadata={}, next_action=None)

    monkeypatch.setattr(siadahub, "_try_restore_session", restore)
    monkeypatch.setattr(siadahub, "_apply_login", lambda *args: None)
    monkeypatch.setattr(siadahub, "_ensure_agents_ready", lambda: None)
    monkeypatch.setattr(siadahub, "_ensure_litellm_ready", lambda: None)
    # The post-run quota lookup is unrelated to Goal resume and must stay offline.
    monkeypatch.setattr(SiadaRunner, "find_session_context", lambda _: context)
    monkeypatch.setattr(ConversationTurn, "execute", execute)
    check = AsyncMock(return_value=GoalVerdict(passed=False, reason="Synthetic verification failed"))
    monkeypatch.setattr(verifier, "run_goal_verification", check)
    result = siadahub._run_noninteractive(
        SimpleNamespace(resume=source.session_id, prompt="Continue the goal"),
        session, config, config.io, config.llm_config,
        SimpleNamespace(hook_runner=None),
    )
    assert result == 1
    assert session.session_id == source.session_id
    assert context.goal.status == "blocked"
    assert goal_storage.load_goal(session.openai_session.session_folder).status == "blocked"
    check.assert_awaited_once()
    assert "Goal not achieved" in config.io.print_error.call_args.args[0]
    assert goal.objective in config.io.print_error.call_args.args[0]
