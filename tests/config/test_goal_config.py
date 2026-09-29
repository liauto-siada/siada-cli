import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import yaml

from siada.config.config_loader import GoalConfig, load_conf
from siada.entrypoint.interaction.turn.models import TurnOutput, TurnType
from siada.foundation.code_agent_context import CodeAgentContext
from siada.services.file_session import FileSession
from siada.services.goal import goal_storage
from siada.services.goal.models import GOAL_MAX_TURNS, Goal, GoalVerdict
from siada.services.goal.turn_hooks import maybe_run_goal_verifier
from siada.services.siada_runner import SiadaRunner
from siada.session.session_models import RunningSession
from siada.support.slash_commands import SwitchEvent


def test_goal_config_defaults_to_existing_retry_limit():
    assert GoalConfig().max_turns == GOAL_MAX_TURNS == 6


def test_goal_config_converts_and_clamps_max_turns():
    assert GoalConfig.from_dict({"max_turns": "3"}).max_turns == 3
    assert GoalConfig.from_dict({"max_turns": 0}).max_turns == 1
    assert GoalConfig.from_dict({"max_turns": "invalid"}).max_turns == GOAL_MAX_TURNS


def test_load_conf_reads_goal_max_turns(tmp_path, monkeypatch):
    config_path = tmp_path / "conf.yaml"
    config_path.write_text(yaml.safe_dump({"goal": {"max_turns": 4}}), encoding="utf-8")

    monkeypatch.setattr("siada.config.config_loader.MCPConfigLoader.load_config", lambda: None)
    monkeypatch.setattr("siada.config.config_loader.load_user_model_config", lambda: None)

    config = load_conf(config_path)

    assert config.goal_config.max_turns == 4


def test_configured_limit_reaches_runtime_verifier(tmp_path, monkeypatch):
    config_path = tmp_path / "conf.yaml"
    config_path.write_text("goal:\n  max_turns: 2\nmemory:\n  enabled: false\n", encoding="utf-8")
    monkeypatch.setattr("siada.config.config_loader._get_default_config_path", lambda: config_path)
    monkeypatch.setattr("siada.config.config_loader.MCPConfigLoader.load_config", lambda: None)
    monkeypatch.setattr("siada.config.config_loader.load_user_model_config", lambda: None)

    workspace = str(tmp_path)
    agent = SimpleNamespace(get_context=AsyncMock(return_value=CodeAgentContext(root_dir=workspace)))
    session = RunningSession(
        siada_config=SimpleNamespace(workspace=workspace, agent_name="coder")
    )
    file_session = FileSession(session_id="goal-limit", sessions_dir=tmp_path)
    session.state.openai_session = file_session

    with patch("siada.services.siada_runner.build_combined_memory", return_value=""), patch(
        "siada.foundation.siadaignore_controller.SiadaIgnoreController.initialize"
    ), patch(
        "siada.support.git_info.get_workspace_git_info", return_value=None
    ):
        context = asyncio.run(SiadaRunner._build_agent_context(agent, workspace, session))

    assert context.goal_max_turns == 2
    goal = Goal.create("finish the task")
    context.goal = goal
    turn = SimpleNamespace(get_turn_type=lambda: TurnType.CONVERSATION)
    result = TurnOutput(output="not done", metadata={}, next_action=None)
    notifications = []
    verdict = GoalVerdict(passed=False, reason="work remaining", nextAction="keep working")
    with patch("siada.services.siada_runner.SiadaRunner._context_cache", {("coder", workspace): context}), patch(
        "siada.services.goal.verifier.run_goal_verification",
        new=AsyncMock(return_value=verdict),
    ):
        first = maybe_run_goal_verifier(
            lambda method, payload: notifications.append((method, payload)),
            turn, session, file_session.session_folder, result, enable_notification=False,
        )
        second = maybe_run_goal_verifier(
            lambda method, payload: notifications.append((method, payload)),
            turn, session, file_session.session_folder, result, enable_notification=False,
        )

    assert isinstance(first.output, SwitchEvent)
    assert second is result
    assert goal.consecutive_failures == 2
    assert goal.status == "blocked"
    assert goal_storage.load_goal(file_session.session_folder).status == "blocked"
    assert notifications[-1][1]["goal"]["status"] == "blocked"


def test_help_config_manager_sets_and_validates_goal_limit(tmp_path, monkeypatch, capsys):
    script_path = (
        Path(__file__).resolve().parents[2]
        / "siada/resources/skills/siada-help/scripts/config_manager.py"
    )
    spec = importlib.util.spec_from_file_location("siada_help_config_manager", script_path)
    manager = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(manager)
    config_path = tmp_path / "conf.yaml"
    monkeypatch.setattr(manager, "CONFIG_PATH", config_path)
    monkeypatch.setattr(manager, "BACKUP_PATH", tmp_path / "conf.yaml.bak")

    manager.cmd_set(SimpleNamespace(key="goal.max_turns", value="4"))
    manager.cmd_validate(None)

    assert yaml.safe_load(config_path.read_text(encoding="utf-8")) == {"goal": {"max_turns": 4}}
    assert "[OK]    goal.max_turns = 4" in capsys.readouterr().out
