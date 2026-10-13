"""GLM template selection, literal substitution, and coding-agent delivery."""

from pathlib import Path
from types import SimpleNamespace

from agents import RunContextWrapper
import pytest

from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder.prompt import code_gen_prompt
from siada.agent_hub.coder.prompt.assembly import glm
from siada.agent_hub.coder.prompt.selection.profiles import PromptFamily, resolve_prompt_profile
from siada.services.skills import SkillMetadata, SkillScope, render_skills_section


@pytest.fixture
def render_prompt(monkeypatch):
    root = Path("/skills")
    skill = SkillMetadata("sample", "Sample instructions", root / "sample/SKILL.md", SkillScope.REPO)

    def fixed_skills(*_args, **kwargs):
        return render_skills_section(
            [skill], skill_roots={SkillScope.REPO: [root]}, usage_profile=kwargs["usage_profile"],
        )

    monkeypatch.setattr(code_gen_prompt.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(code_gen_prompt.os.path, "expanduser", lambda _path: "/home/synthetic")
    monkeypatch.setattr(code_gen_prompt, "get_username", lambda: "synthetic-user")
    monkeypatch.setattr(code_gen_prompt, "_skills_context_window", lambda _model: 128000)
    monkeypatch.setattr(code_gen_prompt, "get_skills_section", fixed_skills)
    monkeypatch.setattr(code_gen_prompt, "get_agents_section", lambda _cwd: "# AGENT TYPES\n\n- reviewer")
    monkeypatch.setattr("siada.agent_hub.coder.code_gen_agent.get_available_lark_tools", lambda: [])

    def render(model_name="glm-5.3", **overrides):
        arguments = {
            "model_name": model_name, "preferred_language": "zh-CN",
            "user_memory": "## Inline Memory\n\nSynthetic memory.",
        }
        arguments.update(overrides)
        return code_gen_prompt.get_system_prompt("/workspace/project", **arguments)

    return render


@pytest.mark.parametrize("model_name", [
    "glm-5.2", "GLM-5.2", "vendor-glm-5.2-flash", "openai/glm-5.2",
    "glm-5.3", "vendor-glm-5.3-flash", "zhipuai/glm-5.3", "glm-5.4",
    "vendor-glm-5.30", "glm-6", "vendor-glm-6.1-flash",
])
@pytest.mark.parametrize("interactive_mode", [True, False])
def test_glm_variants_share_template_and_tool_surface(render_prompt, model_name, interactive_mode):
    profile = resolve_prompt_profile(model_name)
    assert profile.family is PromptFamily.GLM
    assert profile.native_patch_file_tools is False
    assert render_prompt(model_name, interactive_mode=interactive_mode) == render_prompt(
        interactive_mode=interactive_mode,
    )


@pytest.mark.parametrize("model_name", [
    None, "", "glm-5.1", "vendor-glm-5.1", "glm-4.6", "glm-5", "xglm-5.3",
    "chatglm3-6b", "claude-sonnet-5", "gpt-6-astra", "kimi-k3",
])
def test_other_models_keep_their_family(model_name):
    assert resolve_prompt_profile(model_name).family is not PromptFamily.GLM


def test_template_replaces_legacy_builder_and_keeps_siada_sections(render_prompt, monkeypatch):
    monkeypatch.setattr(code_gen_prompt, "get_rules_for_profile", lambda *_a, **_k: pytest.fail("Legacy rules"))
    monkeypatch.setattr(code_gen_prompt, "render_system_prompt", lambda **_k: pytest.fail("Legacy builder"))
    prompt = render_prompt()
    headings = [
        "# Harness", "# Communicating with the user", "# Environment", "# Context management",
        "# CAPABILITIES", "# Runtime instructions", "# PREFERRED LANGUAGE", "# Skills",
        "# AGENT TYPES", "# Combined Memory",
    ]
    lines = prompt.splitlines()
    assert all(lines.count(heading) == 1 for heading in headings)
    assert [lines.index(heading) for heading in headings] == sorted(lines.index(heading) for heading in headings)
    assert prompt.startswith("You are an interactive Siada agent")
    assert "## Git Safety" in prompt
    assert "OWASP top 10" in prompt
    assert "### Skill roots" in prompt
    assert "sample: Sample instructions (file: r0/sample/SKILL.md)" in prompt
    assert "### How to use skills" not in prompt
    assert "${" not in prompt


@pytest.mark.parametrize("interactive_mode", [True, False])
def test_noninteractive_approval_blockers(render_prompt, interactive_mode):
    prompt = render_prompt(interactive_mode=interactive_mode)
    assert ("## Interaction mode" in prompt) is not interactive_mode
    assert ("do not infer approval from elapsed time" in prompt) is not interactive_mode


@pytest.mark.parametrize("blank", [None, "", " \n "])
def test_optional_sections_are_absent(render_prompt, monkeypatch, blank):
    monkeypatch.setattr(code_gen_prompt, "get_skills_section", lambda *_a, **_k: blank)
    monkeypatch.setattr(code_gen_prompt, "get_agents_section", lambda *_a, **_k: blank)
    monkeypatch.setattr(code_gen_prompt, "get_username", lambda: None)
    prompt = render_prompt(user_memory=blank, preferred_language=None)
    for heading in ("# Skills", "# AGENT TYPES", "# Combined Memory", "# PREFERRED LANGUAGE"):
        assert heading not in prompt.splitlines()
    assert "The current user is" not in prompt


def test_subagent_switch_and_extra_capabilities(render_prompt):
    prompt = render_prompt(subagent_enabled=False, extra_capabilities=["- Extra capability."])
    assert "run_subtask" not in prompt
    assert "# AGENT TYPES" not in prompt
    assert prompt.index("# CAPABILITIES") < prompt.index("- Extra capability.") < prompt.index("# Runtime instructions")


def test_runtime_values_are_literal(render_prompt, monkeypatch):
    memory = "Keep `${cwd}`, `$HOME`, `$(example)`, and `{literal}` verbatim."
    monkeypatch.setattr(code_gen_prompt, "get_username", lambda: "synthetic-${os}")
    prompt = render_prompt(user_memory=memory)
    assert memory in prompt
    assert "The current user is synthetic-${os}." in prompt


def test_invalid_placeholder_fails(render_prompt, monkeypatch):
    monkeypatch.setattr(glm, "get_glm_template", lambda: "${missing_runtime_value}")
    with pytest.raises(KeyError, match="missing_runtime_value"):
        render_prompt()


@pytest.mark.parametrize("model_name", ["glm-5.2", "zhipuai/glm-5.3", "glm-6"])
@pytest.mark.asyncio
async def test_coding_agent_delivers_template_and_matching_tools(render_prompt, model_name):
    context = SimpleNamespace(
        root_dir="/workspace/project", combined_memory="## Inline Memory\n\nSynthetic memory.",
        preferred_language="zh-CN", interactive_mode=True, activated_skill_names=set(),
        subagent_enabled=True,
        session=SimpleNamespace(siada_config=SimpleNamespace(
            agent_name="CodeGenAgent", llm_config=SimpleNamespace(model_name=model_name),
        )),
    )
    agent = CodeGenAgent()
    assert await agent.get_system_prompt(RunContextWrapper(context=context)) == render_prompt(model_name)
    tools = {tool.name for tool in agent._get_base_tools(model_name=model_name)}
    assert "edit_file" in tools
    assert "read_file" not in tools
    assert "apply_patch" not in tools