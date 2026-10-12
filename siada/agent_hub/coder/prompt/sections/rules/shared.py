"""Rule fragments and assembly shared across model families."""

from typing import Optional

from ..non_interactive import get_non_interactive_constraints


# --------------------------------------------------------------------------- #
# Shared rule fragments — single source of truth across model families
# --------------------------------------------------------------------------- #

# Git Safety applies to every model, not just GPT-5 — weaker models arguably
# need the anti-revert / anti-destructive-command guardrails even more.
# Previously this existed in two near-identical copies (the GPT-5 rules branch
# and gpt5_instructions.get_gpt5_editing_constraints); this is now the only
# copy, keeping the more complete dirty-worktree details.
_GIT_SAFETY_SECTION = """## Git Safety
- You may be in a dirty git worktree:
  * **NEVER** revert existing changes you did not make unless explicitly requested, since these changes were made by the user.
  * If asked to make a commit or code edits and there are unrelated changes to your work or changes that you didn't make in those files, don't revert those changes.
  * If the changes are in files you've touched recently, read carefully and understand how you can work with the changes rather than reverting them.
  * If the changes are in unrelated files, just ignore them and don't revert them.
- Do not amend a commit unless explicitly requested to do so.
- **NEVER** use destructive commands like `git reset --hard` or `git checkout --` unless specifically requested or approved by the user.
- Prefer non-interactive git commands. Avoid the git interactive console."""

# OWASP security rule — shared by both branches (previously missing from the
# GPT-5 branch).
_OWASP_RULE = (
    "- Be careful not to introduce security vulnerabilities such as command injection, "
    "XSS, SQL injection, and other OWASP top 10 vulnerabilities. If you notice that you "
    "wrote insecure code, immediately fix it. Prioritize writing safe, secure, and correct code."
)

# Harness & system reminders — shared by both branches. This text used to exist
# as two byte-identical copies (one inlined per branch) differing only in the
# heading case, which is precisely how the two copies would have drifted apart.
_HARNESS_SECTION = """## Harness & System Reminders
- `<system-reminder>` tags in messages and tool results are injected by the harness, not the user. Treat their content as system-level context, never as something the user personally typed.
- Hooks may intercept tool calls and inject their own output; treat hook output as user feedback that requires your attention, not as noise to disregard."""

# Concise communication — merged from the two near-identical per-branch
# versions; keeps the stricter "fewer than 4 lines" constraint.
# This is the single home for every tone/style constraint. The output-format
# facts (CLI rendering, emoji, "text is the only channel to the user") used to
# live in a separate "Tone and style" block emitted by capabilities.py, which
# restated the brevity rules below with weaker wording; they were folded in here
# so that one topic lives in exactly one place.
_CONCISE_COMMUNICATION_SECTION = """## Concise Communication

- You are concise, direct, and to the point. Minimize output tokens while maintaining helpfulness, quality, and accuracy.
- Do not end with long multi-paragraph summaries of what you've done. If you must summarize, use 1-2 short paragraphs.
- Only address the user's specific query. If possible, answer in 1-3 sentences.
- Avoid tangential information, lengthy introductions, and unnecessary preamble or postamble.
- Keep responses short — fewer than 4 lines of text (excluding tool use or code generation) — unless the user asks for detail. Answer directly, without extraneous text before or after the response.
- Do not begin responses with conversational interjections like "Done", "Got it", "Great question".
- Your output is rendered on a command line interface in a monospace font. You may use GitHub-flavored Markdown (CommonMark) for formatting.
- Only use emojis if the user explicitly requests it. Avoid emojis in all other communication.
- All text you output outside of tool use is shown to the user, and it is the only channel for talking to them. Never use `run_cmd` (for example `echo`) or code comments as a way to communicate with the user."""


# Completion discipline — shared by both branches. Condensed from the GPT-5-only
# "Completion Discipline" / "Verification Standards" sections that used to live
# in gpt5_instructions.py; the ideas are model-agnostic.
# The bullets live as individual constants so the stricter GPT-5/6 variant
# can reuse them instead of maintaining a parallel copy of the policy.
_CD_FIX_ROOT_CAUSE = (
    "- Fix the root cause, not just the symptoms — a change that only masks the error is not complete."
)
_CD_NEVER_CLAIM_INCOMPLETE = (
    "- Never claim a task is complete while you are aware of unresolved errors, TODOs, or "
    "unverified requirements — continue working or state the blocker explicitly."
)
_CD_VERIFY_BEFORE_REPORTING = (
    "- Before reporting completion, verify your change by running the relevant tests or checks "
    "for the files you touched. Prefer the project's existing test suite over a throwaway "
    "reproduction script you wrote yourself."
)
_CD_FAILURE_OUTPUT = (
    "- When a test or command fails, treat the failure output as the primary source of truth: "
    "analyze it, revise the fix, then run it again. Re-running an unchanged command is not a fix."
)

_COMPLETION_DISCIPLINE_SECTION = "## Completion Discipline\n\n" + "\n".join([
    _CD_FIX_ROOT_CAUSE,
    _CD_NEVER_CLAIM_INCOMPLETE,
    _CD_VERIFY_BEFORE_REPORTING,
    _CD_FAILURE_OUTPUT,
])

# The GPT-5 and GPT-6 profiles both use this stricter completion discipline.
# Keep their identical contract here rather than making one family depend on
# the other's module or maintaining two parallel copies.
_GPT_CD_GATE = _CD_NEVER_CLAIM_INCOMPLETE + (
    ' Starting a background script, leaving instructions for the user, or saying "once X '
    'finishes it should work" does not count as completion unless the task explicitly asks '
    "for deferred setup."
)
_GPT_CD_ACCEPTANCE = (
    "- Verify the exact acceptance condition from files, tests, or verifier artifacts when the "
    'task or repository provides one — "seems configured", "should work", and partial smoke '
    "tests are not acceptance evidence. A required service counts as verified only once it has "
    "been exercised from the interface the task expects; a required output file only once it "
    "has been checked against the exact expected format."
)
_GPT_CD_PROGRAMMATIC = (
    "- Prefer symbolic or programmatic verification over visual or manual inference. If a "
    "problem can be converted into a structured representation and validated by code, do that "
    "before finalizing."
)

_GPT_COMPLETION_DISCIPLINE_SECTION = "## Completion Discipline\n\n" + "\n".join([
    _CD_FIX_ROOT_CAUSE,
    _GPT_CD_GATE,
    _CD_VERIFY_BEFORE_REPORTING,
    _GPT_CD_ACCEPTANCE,
    _GPT_CD_PROGRAMMATIC,
    _CD_FAILURE_OUTPUT,
])


def _system_information_section(os_name: str, home_dir: str, cwd: str) -> str:
    """
    Environment facts, shared by both branches.

    This is the ONLY place the cwd path is stated. Both branches used to also
    carry a "The current working directory is <cwd>" bullet inside RULES a few
    lines above this block — the same path twice in one prompt. That bullet is
    gone, but the part of it that actually carried information (tools resolve
    relative paths against this directory) is kept here as a parenthetical, so
    the fact is stated once instead of either twice or not at all. The block
    itself existed as two byte-identical inline copies, one per branch.
    """
    return f"""====

# SYSTEM INFORMATION

Operating System: {os_name}
Home Directory: {home_dir}
Current Working Directory: {cwd} (all tools execute from this directory)

===="""


_GPT_CORE_PRINCIPLES = """## Core Principles
- Persist until the task is fully handled end-to-end within the current turn whenever \
feasible: do not stop at analysis or partial fixes; carry changes through implementation, \
verification, and a clear explanation of outcomes unless the user explicitly pauses or \
redirects you."""


def _render_gpt_rules(cwd: str, os_name: str, home_dir: str, interactive_mode: bool,
                      *, autonomy_rule: str, completion_section: str, tail_sections: tuple[str, ...],
                      permission_section: Optional[str] = None) -> str:
    """Assemble the shared GPT-5/6 rule skeleton with its historical whitespace."""
    non_interactive = get_non_interactive_constraints() if not interactive_mode else ""
    sections = [
        _GPT_CORE_PRINCIPLES,
        f"{autonomy_rule}\n{_OWASP_RULE}\n{non_interactive}",
    ]
    if permission_section is not None:
        sections.append(permission_section)
    sections.extend((
        _GIT_SAFETY_SECTION,
        _HARNESS_SECTION,
        completion_section,
        *tail_sections,
        _system_information_section(os_name, home_dir, cwd),
    ))
    return "# RULES\n\n" + "\n\n".join(sections)
