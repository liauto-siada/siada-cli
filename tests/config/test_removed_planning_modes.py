"""Planning switches are removed without affecting normal coding requests."""

import importlib.util
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from agents import RunContextWrapper

from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder.prompt import code_gen_prompt
from siada.agent_hub.coder.prompt.assembly.builder import build_system_prompt, render_system_prompt
from siada.agent_hub.coder.prompt.sections.rules.dispatch import get_rules_section
from siada.config.config_loader import Config, load_conf
from siada.entrypoint.args_parser.args import get_parser
from siada.foundation.code_agent_context import CodeAgentContext
from siada.support.slash_commands import ARGUMENT_HINTS, SlashCommands


def test_old_planning_config_is_ignored_and_normal_settings_still_load(tmp_path, monkeypatch):
    config_path = tmp_path / "conf.yaml"
    config_path.write_text(
        "pre_plan: true\nexecution_mode: plan\npreferred_language: zh-CN\n"
        "code_agent:\n  max_turns: 27\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("siada.config.config_loader._ensure_config_up_to_date", lambda _: None)
    monkeypatch.setattr("siada.config.config_loader.MCPConfigLoader.load_config", lambda: None)
    monkeypatch.setattr("siada.config.config_loader.load_user_model_config", lambda: None)

    config = load_conf(config_path)

    assert config.preferred_language == "zh-CN"
    assert config.code_agent_config.max_turns == 27
    for field in ("pre_plan", "execution_mode"):
        assert field not in Config.__dataclass_fields__
        assert field not in CodeAgentContext.model_fields
        assert not hasattr(config, field)


def test_cli_and_commands_no_longer_advertise_planning_switches():
    parser = get_parser([], None)
    assert "--mode" not in parser._option_string_actions
    assert not hasattr(parser.parse_args([]), "execution_mode")

    commands = SlashCommands.__new__(SlashCommands)
    available = commands.get_commands()
    assert "/mode" not in available
    assert "/pre-plan-mode" not in available
    assert "pre-plan-mode" not in ARGUMENT_HINTS
    assert "/model" in available


def test_prompt_entry_points_no_longer_accept_planning_switches():
    for renderer in (code_gen_prompt.get_system_prompt, build_system_prompt, render_system_prompt, get_rules_section):
        parameters = inspect.signature(renderer).parameters
        assert "pre_plan" not in parameters
        assert "execution_mode" not in parameters


@pytest.mark.asyncio
async def test_coding_agent_preserves_prompt_argument_mapping(monkeypatch):
    render = Mock(return_value="synthetic prompt")
    monkeypatch.setattr(code_gen_prompt, "get_system_prompt", render)
    context = SimpleNamespace(
        root_dir="/synthetic/workspace", interactive_mode=False,
        combined_memory="synthetic memory", preferred_language="zh-CN",
        session=SimpleNamespace(siada_config=SimpleNamespace(
            agent_name="coder", llm_config=SimpleNamespace(model_name="gpt-6-sol"),
        )),
        activated_skill_names={"sample"}, subagent_enabled=False,
    )

    assert await CodeGenAgent().get_system_prompt(RunContextWrapper(context)) == "synthetic prompt"
    render.assert_called_once_with(
        "/synthetic/workspace", False, "synthetic memory", "zh-CN", "coder",
        model_name="gpt-6-sol", activated_skill_names={"sample"}, subagent_enabled=False,
    )


def test_help_config_manager_rejects_removed_keys():
    path = Path(__file__).resolve().parents[2] / "siada/resources/skills/siada-help/scripts/config_manager.py"
    spec = importlib.util.spec_from_file_location("removed_planning_help_config", path)
    manager = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(manager)
    assert "pre_plan" not in manager.VALID_KEYS
    assert "execution_mode" not in manager.VALID_KEYS
