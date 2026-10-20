"""Reviewed byte-for-byte coding prompt baselines.

All environmental inputs are synthetic and fixed. The hashes cover the entire
UTF-8 prompt, including whitespace, section ordering, and trailing newlines.
The original pre-refactor bytes remain frozen for unchanged families; GLM
and GPT-6 record their reviewed profile-specific adjustments.
"""

import ast
import hashlib
from difflib import unified_diff
from pathlib import Path

import pytest

from siada.agent_hub.coder.prompt import code_gen_prompt
from siada.agent_hub.coder.prompt.assembly import builder as prompt_builder
from siada.agent_hub.coder.prompt.assembly.builder import build_system_prompt
from siada.agent_hub.coder.prompt.sections import capabilities
from siada.agent_hub.coder.prompt.sections.rules import dispatch as rules
from siada.agent_hub.coder.prompt.sections.rules.dispatch import get_rules_section
from siada.agent_hub.coder.prompt.selection.profiles import PromptFamily, resolve_prompt_profile
from siada.services.skills.models import SkillUsageProfile


# Captured from the pre-refactor get_system_prompt implementation with the
# fixtures below. GLM and GPT-6+ have reviewed newer baselines; GPT-6+ adds
# neutral tool wording and explicit-request delegation. Do not
# regenerate these values from the code under test without reviewing the diff.
EXPECTED_SHA256 = {
    "default": (
        "3f34f7a3a28ca1ae111a54eca5f048cf503a602bc9275bfe8c8bf13878746941",
        "84cf745bc97af18a158511177f81faf9cec38cc5e0247d90d8c3ed2101919064",
    ),
    "gpt5": (
        "33ff3d5a31852c5f31a03a85dabe22eb26fbdc9b4478f76a4ee683f9ab5d304f",
        "37490daaae22469dbfe8fc369c99100b2205a344f6eb42b383807a3aae6d2998",
    ),
    "gpt6": (
        "ddd7f4fe8841ec971becdb972679db9e2ba61d4f79fa15b00384c7692b4ec60c",
        "c67e3880f8bfde1a215ed6a5c1a4fee5baf8151fa4481f33876308e0bddc9b42",
    ),
    "gpt61_sol": (
        "3a75fa6c6a5cdadc241b4f88f40c97b05f4abcd33089777b04db97f7df5c5063",
        "9017fd8653d313ba93ad0f7894ba64c0837549c3c4854f0bbd68aeaeb9f5648a",
    ),
    "gpt6_sol": (
        "dbac79b6485e8440b1595c737d172a5f20c10fe66f8918ba141f8be6935c4f83",
        "892bd0a479686a8e4a7d69b96d8c10db725b48c2df860d3ea9cca39026d081c7",
    ),
    "gpt6_luna": (
        "26ac785e4a68b41eed70d0b3c897e58df6b3eb9a53a9878a4163a12983e8f206",
        "7e1868fc5c6fb295ba85bb8ae4640490f459bff12e9b96a51bff68ec7c31f01d",
    ),
    "glm": (
        "7ace41a877dc1f88b697c9dcb617e01fb9a556ea567a5cd32e3221a31b3f9550",
        "a9ece776aa27221e742f6ee28030887e6781aff22427a68359ff6d8504b38374",
    ),
    "future_gpt": (
        "0e9c020a5afe59d5ebbb7dc69d34627810645dfffbf3b3f2a22e53038a1d618b",
        "01dbb0a28e151fce903add0adcd60dfe28d97e592c2986da26292f3728e3e81f",
    ),
}

MODEL_PROFILES = (
    (None, "default"),
    ("", "default"),
    ("claude-sonnet-5", "default"),
    ("glm-5.1", "default"),
    ("xglm-5.2", "default"),
    ("kimi-k2.6", "default"),
    ("kimi-k2.99", "default"),
    ("k2.6", "default"),
    ("gpt-5.4", "gpt5"),
    ("vendor-gpt-5.6-nova", "gpt5"),
    ("vendor-gpt-5.4-glm-5.3", "gpt5"),
    ("gpt-6-astra", "gpt6"),
    ("astra", "gpt6"),
    ("vendor-gpt-6.1-glm-5.3", "gpt6"),
    ("gpt-6.1-sol", "gpt61_sol"),
    ("vendor-gpt-6.1-sol", "gpt61_sol"),
    ("gpt-6-sol", "gpt6_sol"),
    ("gpt-6-luna", "gpt6_luna"),
    ("zhipuai/glm-5.2-flash", "glm"),
    ("zhipuai/glm-5.3", "glm"),
    ("vendor-gpt-7-nova", "future_gpt"),
    ("gpt-7-astra", "future_gpt"),
)

MODES = ({}, {"interactive_mode": False})

# One readable full-prompt baseline per distinct profile/tool combination.
# The hash matrix above covers both interaction modes.
SNAPSHOT_CASES = (
    ("default", "claude-sonnet-5", 0),
    ("gpt5", "gpt-5.4", 0),
    ("gpt6", "gpt-6-astra", 1),
    ("glm", "zhipuai/glm-5.3", 1),
    ("future_gpt", "vendor-gpt-7-nova", 0),
)


@pytest.fixture
def render_prompt(monkeypatch):
    def fixed_skills(cwd, *, context_window, activated_skill_names, usage_profile):
        return (
            f"## Skills\n- {usage_profile.name}\n- {context_window}\n"
            f"- {','.join(sorted(activated_skill_names or ()))}"
        )

    monkeypatch.setattr(code_gen_prompt.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(code_gen_prompt.os.path, "expanduser", lambda _path: "/home/synthetic")
    monkeypatch.setattr(code_gen_prompt, "get_username", lambda: "synthetic-user")
    monkeypatch.setattr(code_gen_prompt, "_skills_context_window", lambda _model: 128000)
    monkeypatch.setattr(code_gen_prompt, "get_skills_section", fixed_skills)
    monkeypatch.setattr(code_gen_prompt, "get_agents_section", lambda _cwd: "# AGENT TYPES\n- reviewer")

    def render(model_name, **overrides):
        arguments = {
            "model_name": model_name,
            "user_memory": "## Inline Memory\nSynthetic memory.",
            "preferred_language": "zh-CN",
            "activated_skill_names": {"sample"},
        }
        arguments.update(overrides)
        return code_gen_prompt.get_system_prompt("/workspace/project", **arguments)

    return render


def _sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("model_name, profile", MODEL_PROFILES)
@pytest.mark.parametrize("mode_index, mode", enumerate(MODES))
def test_coding_prompt_matches_reviewed_bytes(render_prompt, model_name, profile, mode_index, mode):
    prompt = render_prompt(model_name, **mode)
    assert _sha256(prompt) == EXPECTED_SHA256[profile][mode_index]


@pytest.mark.parametrize("profile, model_name, mode_index", SNAPSHOT_CASES)
def test_coding_prompt_matches_readable_snapshot(render_prompt, profile, model_name, mode_index):
    snapshot = Path(__file__).parent / "fixtures" / f"system_prompt_{profile}.snap"
    expected_bytes = snapshot.read_bytes()
    expected_hash = EXPECTED_SHA256[profile][mode_index]
    assert hashlib.sha256(expected_bytes).hexdigest() == expected_hash, (
        f"{snapshot.name} does not match the reviewed byte baseline"
    )

    actual_bytes = render_prompt(model_name, **MODES[mode_index]).encode("utf-8")
    if actual_bytes != expected_bytes:
        diff = "".join(unified_diff(
            expected_bytes.decode("utf-8").splitlines(keepends=True),
            actual_bytes.decode("utf-8").splitlines(keepends=True),
            fromfile=str(snapshot),
            tofile="rendered prompt",
        ))
        pytest.fail(
            f"Prompt differs from {snapshot.name}: expected {len(expected_bytes)} bytes "
            f"({expected_hash}), got {len(actual_bytes)} bytes "
            f"({hashlib.sha256(actual_bytes).hexdigest()})\n{diff}"
        )


def test_snapshot_failure_identifies_changed_lines(render_prompt, monkeypatch):
    monkeypatch.setattr(
        code_gen_prompt, "INTRO",
        code_gen_prompt.INTRO.replace("highly skilled", "synthetically changed"),
    )

    with pytest.raises(pytest.fail.Exception) as error:
        test_coding_prompt_matches_readable_snapshot(
            render_prompt, "default", "claude-sonnet-5", 0
        )

    assert "system_prompt_default.snap" in str(error.value)
    assert "-You are Siada, a highly skilled" in str(error.value)
    assert "+You are Siada, a synthetically changed" in str(error.value)


@pytest.mark.parametrize(
    "model_name, overrides, expected_sha256",
    (
        ("gpt-5.4", {"extra_capabilities": ["- Extra one.", "- Extra two."]},
         "8d0fccdc6950187d76279093d4ed5db526ce2e2c9a038cbb872413b7fe85e524"),
        ("zhipuai/glm-5.3", {"subagent_enabled": False},
         "c1154ec504471786dedd30878e70cda92ad4578409fadcc37acdda2d884ca5ba"),
        ("claude-sonnet-5", {"preferred_language": None},
         "f86f308585157725e1f0b4536b785748d6fec3c94ac01efa873baa60cf302ce9"),
        ("gpt-6-astra", {"user_memory": None},
         "ec2677830e9badc4b40b2ca4683e0d8118bf89b642e0812775a99fc3d7280972"),
    ),
)
def test_optional_sections_match_reviewed_bytes(render_prompt, model_name, overrides, expected_sha256):
    assert _sha256(render_prompt(model_name, **overrides)) == expected_sha256


@pytest.mark.parametrize(
    "model_name, expected_hashes",
    (
        ("gpt-5.4", (
            "027ed7b026e4816b9e5b9e512d55062d0c2f7fbc137265119e1a37cc484241ad",
            "1105f7b0a5ff7d41c70ca0cf90d096cd2a7ec73fef1fd4985d0f9a62ad92b5ee",
        )),
        ("gpt-6-astra", (
            "8b01ed314a29cbc95aed1f628e268ec38af92600233870b330ac6107d517a1a2",
            "31b58071b5d6d535680dca0ec895d3f6624e05e60b81c65b3c48e5407145af8a",
        )),
    ),
)
@pytest.mark.parametrize("mode_index, mode", enumerate(MODES))
def test_gpt_rules_keep_exact_bytes_across_modes(model_name, expected_hashes, mode_index, mode):
    rendered = get_rules_section(
        "/workspace/project", "Darwin", "/home/synthetic", model_name=model_name, **mode
    )
    assert _sha256(rendered) == expected_hashes[mode_index]


@pytest.mark.parametrize("model_name", ["gpt-5.4", "gpt-6-astra"])
@pytest.mark.parametrize("interactive_mode", [True, False])
def test_gpt_rule_skeleton_keeps_shared_sections_in_order(model_name, interactive_mode):
    rendered = get_rules_section(
        "/workspace/project", "Darwin", "/home/synthetic",
        model_name=model_name, interactive_mode=interactive_mode,
    )
    headings = (
        "## Core Principles", "## Git Safety", "## Harness & System Reminders",
        "## Completion Discipline", "# SYSTEM INFORMATION",
    )
    for heading in headings:
        assert rendered.splitlines().count(heading) == 1
    positions = [rendered.index(heading) for heading in headings]
    assert positions == sorted(positions)
    assert rendered.splitlines().count("## When to Ask the User") == (model_name == "gpt-6-astra")


def test_rule_dispatcher_keeps_family_renderers_in_separate_modules():
    def functions_in(path: Path) -> set[str]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        return {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}

    root = Path(rules.__file__).resolve().parents[2]
    dispatcher = root / "sections/rules/dispatch.py"
    assert functions_in(dispatcher) == {"get_rules_section", "get_rules_for_profile"}
    assert not any(
        isinstance(node, (ast.Assign, ast.AnnAssign))
        for node in ast.parse(dispatcher.read_text(encoding="utf-8")).body
    )
    for module, renderer in (
        ("models/default/rules.py", "_get_default_rules_section"),
        ("models/gpt5/rules.py", "_get_gpt5_rules_section"),
        ("models/gpt6/rules.py", "_get_gpt6_rules_section"),
    ):
        assert renderer in functions_in(root / module)


@pytest.mark.parametrize(
    "model_name, family, skill_profile, native_patch",
    (
        (None, PromptFamily.DEFAULT, SkillUsageProfile.STRICT, False),
        ("claude-sonnet-5", PromptFamily.DEFAULT, SkillUsageProfile.STRICT, False),
        ("glm-5.1", PromptFamily.DEFAULT, SkillUsageProfile.STRICT, False),
        ("xglm-5.2", PromptFamily.DEFAULT, SkillUsageProfile.STRICT, False),
        ("gpt-5.4", PromptFamily.GPT5, SkillUsageProfile.STRICT, True),
        ("vendor-gpt-5.6-nova", PromptFamily.GPT5, SkillUsageProfile.STRICT, True),
        ("gpt-6-astra", PromptFamily.GPT6, SkillUsageProfile.GPT6, True),
        ("astra", PromptFamily.GPT6, SkillUsageProfile.GPT6, True),
        ("gpt-7-astra", PromptFamily.DEFAULT, SkillUsageProfile.STRICT, True),
        ("vendor-gpt-7-nova", PromptFamily.DEFAULT, SkillUsageProfile.STRICT, True),
        ("zhipuai/glm-5.2-flash", PromptFamily.GLM, SkillUsageProfile.STRICT, False),
        ("zhipuai/glm-5.3", PromptFamily.GLM, SkillUsageProfile.STRICT, False),
        ("kimi-k3", PromptFamily.KIMI_K3, SkillUsageProfile.STRICT, False),
        ("vendor-kimi-k3", PromptFamily.KIMI_K3, SkillUsageProfile.STRICT, False),
        ("kimi-k3.1", PromptFamily.KIMI_K3, SkillUsageProfile.STRICT, False),
        ("kimi-k3.5", PromptFamily.KIMI_K3, SkillUsageProfile.STRICT, False),
        ("kimi-k4", PromptFamily.KIMI_K3, SkillUsageProfile.STRICT, False),
        ("k3.1", PromptFamily.KIMI_K3, SkillUsageProfile.STRICT, False),
        ("k4", PromptFamily.KIMI_K3, SkillUsageProfile.STRICT, False),
    ),
)
def test_profile_keeps_prompt_family_separate_from_tool_surface(
    model_name, family, skill_profile, native_patch
):
    profile = resolve_prompt_profile(model_name)
    assert profile.model_name == model_name
    assert profile.family is family
    assert profile.skill_usage_profile is skill_profile
    assert profile.native_patch_file_tools is native_patch


@pytest.mark.parametrize("model_name", [
    "gpt-5.4", "kimi-k3", "k3.1", "vendor-kimi-k3.5", "kimi-k4", "glm-5.2", "glm-5.3", "glm-6",
])
def test_main_path_resolves_profile_once(monkeypatch, render_prompt, model_name):
    resolved_models = []

    def resolve_once(model_name):
        resolved_models.append(model_name)
        return resolve_prompt_profile(model_name)

    def unexpected_resolution(_model_name):
        raise AssertionError("The main path must pass the selected profile to every renderer")

    monkeypatch.setattr(code_gen_prompt, "resolve_prompt_profile", resolve_once)
    for module in (capabilities, prompt_builder, rules):
        monkeypatch.setattr(module, "resolve_prompt_profile", unexpected_resolution)

    render_prompt(model_name)
    assert resolved_models == [model_name]
