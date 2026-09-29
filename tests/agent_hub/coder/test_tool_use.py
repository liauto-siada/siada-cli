"""Tests for the coder prompt optimization.

Covers:
- The TOOL USE prompt section was removed together with the tool_use.py helper
  module: tool-call guidance lives in the tool descriptions themselves, so the
  system prompt no longer carries a dedicated section (main and sub agents).
- All in-production models declare parallel_tool_calls=True.
- The removed specialized agents (bug_fix / fe_gen / bug_reproduce /
  deep_research / test / browser / card / select / bug_fix_triage) are no
  longer registered or importable; the card-only cca tool package is gone too.
- rules.py convergence: Git Safety / OWASP / Concise Communication shared by
  both branches; default branch gained the behavior clauses and Completion
  Discipline; GPT-5 editing constraints reference real tool names.
- pre_plan no longer conflicts with the GPT-5 "implement directly" wording.
"""
import importlib

import pytest
import yaml

from siada.agent_hub.coder.prompt.base.gpt5_instructions import (
    get_gpt5_editing_constraints,
    get_gpt5_extra_sections,
)
from siada.agent_hub.coder.prompt.base import rules as rules_module
from siada.agent_hub.coder.prompt.base.rules import get_rules_section
from siada.agent_hub.coder.prompt import code_gen_prompt, issue_review_prompt
from siada.models.model_base_config import get_model_config


# --------------------------------------------------------------------------- #
# TOOL USE section — removed from prompts and from the package
# --------------------------------------------------------------------------- #

def test_tool_use_module_removed():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("siada.agent_hub.coder.prompt.base.tool_use")


def test_prompts_have_no_tool_use_section():
    prompts = [
        code_gen_prompt.get_system_prompt("/cwd", model_name="claude-sonnet-5"),
        code_gen_prompt.get_system_prompt("/cwd", model_name="gpt-5.4"),
        issue_review_prompt.get_system_prompt("/cwd"),
    ]
    for prompt in prompts:
        assert "TOOL USE" not in prompt
        # Parallel-call guidance now lives in the tool descriptions, not the
        # system prompt.
        assert "parallel tool calls" not in prompt


def test_sub_task_agent_prompt_has_no_tool_use_section():
    from siada.agent_hub.coder.sub_task_agent import _build_subtask_instructions

    class _Ctx:
        root_dir = "/cwd"

    class _RunContext:
        context = _Ctx()

    prompt = _build_subtask_instructions(_RunContext(), agent=None)
    assert "TOOL USE" not in prompt
    assert "parallelize" not in prompt


# --------------------------------------------------------------------------- #
# Model configs — every in-production model supports parallel tool calls
# --------------------------------------------------------------------------- #

def test_kimi_models_parallel_tool_calls_enabled():
    # Kimi K2.6 was retired from the local catalog; cover the current K3
    # entry instead of accidentally relying on a stale remote catalog.
    for model_name in ("kimi-k3",):
        config = get_model_config(model_name)
        assert config is not None
        assert config.parallel_tool_calls is True, model_name


# --------------------------------------------------------------------------- #
# Removed specialized agents — no registration, not importable
# --------------------------------------------------------------------------- #

def test_removed_agents_not_in_agent_config():
    with open("agent_config.yaml", "r", encoding="utf-8") as f:
        agents = yaml.safe_load(f).get("agents", {})
    for removed in ("bugfix", "fegen", "bugreproduce", "test", "deepresearch", "browser", "card"):
        assert removed not in agents, f"{removed} should no longer be registered"


def test_removed_agent_modules_not_importable():
    removed_modules = [
        "siada.agent_hub.coder.bug_fix_agent",
        "siada.agent_hub.coder.fe_gen_agent",
        "siada.agent_hub.coder.bug_reproduce_agent",
        "siada.agent_hub.coder.deep_research_agent",
        "siada.agent_hub.coder.test_agent",
        "siada.agent_hub.coder.browser_agent",
        "siada.agent_hub.coder.card_agent",
        "siada.agent_hub.coder.select_agent",
        "siada.agent_hub.coder.bug_fix_triage_agent",
        "siada.agent_hub.coder.prompt.fe_gen_prompt",
        "siada.agent_hub.coder.prompt.bug_reproduce_prompt",
        "siada.agent_hub.coder.prompt.test_prompt",
        "siada.agent_hub.coder.prompt.deep_research_prompt",
        "siada.agent_hub.coder.prompt.browser_system_prompt",
        "siada.agent_hub.coder.prompt.card_prompt",
        "siada.agent_hub.coder.prompt.bug_prompt.bug_fix_prompt",
        # Card-agent-only tool package: no importers remain, fully removed.
        "siada.tools.cca",
        "siada.tools.cca.card_gen",
        "siada.tools.cca.compile_card",
        "siada.tools.cca.zip_project",
        "siada.tools.cca.get_cca_resource",
    ]
    for module_name in removed_modules:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module_name)


# --------------------------------------------------------------------------- #
# rules.py — branch convergence
# --------------------------------------------------------------------------- #

def test_git_safety_and_owasp_in_both_branches():
    gpt5_rules = get_rules_section("/cwd", "Darwin", "/home", model_name="gpt-5.4")
    default_rules = get_rules_section("/cwd", "Darwin", "/home", model_name="claude-sonnet-5")
    for rules in (gpt5_rules, default_rules):
        assert "## Git Safety" in rules
        assert "NEVER** revert existing changes you did not make" in rules
        assert "git reset --hard" in rules
        assert "OWASP" in rules
        # Merged concise section, keeping the stricter 4-line constraint.
        assert "## Concise Communication" in rules
        assert "fewer than 4 lines" in rules


def test_default_branch_new_clauses():
    default_rules = get_rules_section("/cwd", "Darwin", "/home", model_name="claude-sonnet-5")
    assert "If the user asks a simple question without any coding context, answer it directly without using any tools." in default_rules
    assert "Do not claim you will perform an action without actually performing it in the same turn." in default_rules
    assert "## Completion Discipline" in default_rules


def test_default_completion_discipline_byte_identical():
    # Pin the default branch's Completion Discipline section to its exact
    # 4-bullet text. The bullets are shared constants also used by the GPT-5
    # merged variant, so this test is the guard that an edit intended for
    # GPT-5 never silently changes the default branch.
    expected = (
        "## Completion Discipline\n\n"
        "- Fix the root cause, not just the symptoms — a change that only masks the error is not complete.\n"
        "- Never claim a task is complete while you are aware of unresolved errors, TODOs, or unverified requirements — continue working or state the blocker explicitly.\n"
        "- Before reporting completion, verify your change by running the relevant tests or checks for the files you touched. Prefer the project's existing test suite over a throwaway reproduction script you wrote yourself.\n"
        "- When a test or command fails, treat the failure output as the primary source of truth: analyze it, revise the fix, then run it again. Re-running an unchanged command is not a fix."
    )
    assert rules_module._COMPLETION_DISCIPLINE_SECTION == expected
    default_rules = get_rules_section("/cwd", "Darwin", "/home", model_name="claude-sonnet-5")
    assert expected in default_rules


def test_gpt5_pre_plan_mutual_exclusion():
    normal = get_rules_section("/cwd", "Darwin", "/home", model_name="gpt-5.4", pre_plan=False)
    pre_plan = get_rules_section("/cwd", "Darwin", "/home", model_name="gpt-5.4", pre_plan=True)
    assert "go ahead and actually implement" in normal
    assert "go ahead and actually implement" not in pre_plan
    assert "design plan" in pre_plan


def test_gpt5_completion_discipline_merged_single_section():
    gpt5_rules = get_rules_section("/cwd", "Darwin", "/home", model_name="gpt-5.4")
    default_rules = get_rules_section("/cwd", "Darwin", "/home", model_name="claude-sonnet-5")
    # GPT-5 folds the former Verification Standards section into one
    # Completion Discipline section — no second adjacent header.
    assert gpt5_rules.count("## Completion Discipline") == 1
    assert "## Verification Standards" not in gpt5_rules
    # Nothing dropped: the merged gate bullet carries the "does not count as
    # completion" examples, and the acceptance criteria survive.
    assert "does not count as completion unless the task explicitly asks for deferred setup." in gpt5_rules
    assert "partial smoke tests are not acceptance evidence" in gpt5_rules
    assert "exercised from the interface the task expects" in gpt5_rules
    assert "Prefer symbolic or programmatic verification" in gpt5_rules
    # The default branch keeps the shared section untouched (no GPT-5 increments).
    assert "## Verification Standards" not in default_rules
    assert "deferred setup" not in default_rules


# --------------------------------------------------------------------------- #
# gpt5_instructions.py — tool names and cleanups
# --------------------------------------------------------------------------- #

def test_gpt5_editing_constraints_reference_real_tool():
    constraints = get_gpt5_editing_constraints()
    assert "read_file" in constraints
    assert "apply_patch" in constraints
    assert "cat" in constraints
    assert "simple shell command" in constraints
    assert "edit_file" not in constraints
    assert "str_replace" not in constraints
    assert "replace_in_file" not in constraints
    assert "write_to_file" not in constraints
    # Git Safety was single-sourced into rules.py.
    assert "git worktree" not in constraints


def test_gpt5_extra_sections_no_empty_general_header():
    sections = get_gpt5_extra_sections()
    assert "# General" not in sections


# --------------------------------------------------------------------------- #
# Scenario prompts — thinking-tag residue removed
# --------------------------------------------------------------------------- #

def test_code_gen_prompt_has_no_thinking_tag_residue():
    for model_name in ("claude-sonnet-5", "gpt-5.4"):
        prompt = code_gen_prompt.get_system_prompt("/cwd", model_name=model_name)
        assert "thinking tag" not in prompt
        assert "<thinking>" not in prompt
        assert "one tool per message" not in prompt


def test_code_gen_prompt_gpt5_pre_plan_has_no_conflict():
    prompt = code_gen_prompt.get_system_prompt("/cwd", pre_plan=True, model_name="gpt-5.4")
    assert "modifies or creates files" in prompt
    # The implement-directly directive must not coexist with pre_plan.
    assert "Go ahead and implement rather than proposing" not in prompt
    assert "go ahead and actually implement" not in prompt


def test_issue_review_prompt_has_no_thinking_tag_residue():
    prompt = issue_review_prompt.get_system_prompt("/cwd")
    assert "<thinking>" not in prompt
    assert "one tool per message" not in prompt
