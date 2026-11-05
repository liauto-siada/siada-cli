"""Frozen pre-refactor output matrices for every system-prompt rendering path."""

import hashlib
import json
from itertools import product
from pathlib import Path
from unittest.mock import patch

import pytest

from siada.agent_hub.coder.prompt import code_gen_prompt


MODEL_NAMES = (
    None, "claude-sonnet-5", "gpt-5.4", "gpt-6-astra", "astra", "gpt-6-sol",
    "gpt-6-luna", "vendor/gpt-6.1-sol", "glm-5.3", "kimi-k3.5",
    "deepseek-v4-flash", "vendor/deepseek-${cwd}", "gpt-7-nova",
)
OPERATING_SYSTEMS = ("Darwin", "Linux", "Windows")
TOOL_SETS = (None, set(), {"web_search"}, {"web_fetch"}, {"web_search", "web_fetch"})
SKILLS_CATALOG = (
    "  ## Skills\n\n### Skill roots\n\n- `r0` = `/synthetic/skills`\n\n"
    "### Available skills\n\n- sample (file: r0/sample/SKILL.md)\n"
    "### How to use skills\nOriginal usage guidance.\n\n"
)
AGENTS_CATALOG = "  # AGENT TYPES\n\n- reviewer: Synthetic review agent.\n\n"
MEMORY = "\n## Inline Memory\n\nSynthetic 中文 memory.\n\n"
OPTIONAL_SECTIONS = tuple(
    ("synthetic-user", SKILLS_CATALOG if skills else None,
     AGENTS_CATALOG if agents else None, MEMORY if memory else None)
    for skills, agents, memory in product((False, True), repeat=3)
) + (
    (None, None, None, None),
    ("", "", "", ""),
    (" \n ", " \n ", " \n ", " \n "),
    ("user-${cwd}", "## Skills\n${cwd} $$ {{literal}}",
     "# AGENT TYPES\n${model} $$", "${runtime_instructions} 中文 $$ {{include:literal}}"),
)
BASELINE_PATH = Path(__file__).parent / "fixtures" / "system_prompt_rendering_sha256.json"


def collect_rendering_digest(model_name: str | None, os_name: str) -> tuple[int, str]:
    digest = hashlib.sha256()
    case_count = 0
    with (
        patch.object(code_gen_prompt.platform, "system", return_value=os_name),
        patch.object(code_gen_prompt.os.path, "expanduser", return_value="/home/synthetic-${os}"),
        patch.object(code_gen_prompt, "_skills_context_window", return_value=128000),
        patch.object(code_gen_prompt, "get_username") as username_mock,
        patch.object(code_gen_prompt, "get_skills_section") as skills_mock,
        patch.object(code_gen_prompt, "get_agents_section") as agents_mock,
    ):
        for interactive_mode, subagent_enabled, language, tool_names, optional, extras in product(
            (True, False), (True, False), (None, "", "zh-CN"), TOOL_SETS,
            OPTIONAL_SECTIONS, (None, ["- Extra ${cwd}.", "- Extra 中文 capability.\n"]),
        ):
            username, skills, agents, memory = optional
            username_mock.return_value = username
            skills_mock.return_value = skills
            agents_mock.return_value = agents
            prompt_bytes = code_gen_prompt.get_system_prompt(
                "/workspace/project-${home_dir}", model_name=model_name,
                interactive_mode=interactive_mode, subagent_enabled=subagent_enabled,
                preferred_language=language, user_memory=memory, agent_name="SyntheticAgent",
                available_tool_names=tool_names, extra_capabilities=extras,
                activated_skill_names={"sample"},
            ).encode("utf-8")
            digest.update(len(prompt_bytes).to_bytes(8, "big"))
            digest.update(prompt_bytes)
            case_count += 1
    return case_count, digest.hexdigest()


@pytest.mark.parametrize("model_name", MODEL_NAMES)
@pytest.mark.parametrize("os_name", OPERATING_SYSTEMS)
def test_all_system_prompt_paths_preserve_pre_refactor_bytes(model_name, os_name):
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    expected = baseline[json.dumps([model_name, os_name])]
    case_count, actual_sha256 = collect_rendering_digest(model_name, os_name)
    assert case_count == expected["cases"]
    assert actual_sha256 == expected["sha256"], (
        f"System prompt bytes changed for {model_name!r} on {os_name}: "
        f"{case_count} ordered cases, expected {expected['sha256']}, got {actual_sha256}"
    )
