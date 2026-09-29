"""
GPT-5 series specific prompt instructions.
this module provides:
- GPT-5 tailored personality variants (pragmatic / friendly)
- GPT-5 specific editing constraints (comment style, edit_file preference)
- Frontend task guidance (anti "AI slop")
- Output formatting rules

These sections are activated only when the model is a GPT-5 series model.

Behavioural policy (autonomy, persistence, completion discipline, verification
standards) deliberately does NOT live here: it is shared with the default branch
via rules.py. This module used to carry its own wording for all of it, which made
the GPT-5 prompt a parallel copy of the same policy, free to drift away from the
default branch — exactly what happened to the Git Safety bullets before they were
consolidated.
"""

import re
from typing import Optional


# ---------------------------------------------------------------------------
# Model detection
# ---------------------------------------------------------------------------

_GPT_MAIN_VERSION_PATTERN = re.compile(r"(?:^|[^a-z0-9])gpt[-_]?([0-9]+)(?:[^0-9]|$)")


def _gpt_main_version(model_name: str) -> int | None:
    """Extract the numbered GPT generation from a provider-qualified name."""
    if not model_name:
        return None
    match = _GPT_MAIN_VERSION_PATTERN.search(model_name.lower())
    return int(match.group(1)) if match else None


def is_gpt5_model(model_name: str) -> bool:
    """Check if the model is specifically a GPT-5 series model."""
    return _gpt_main_version(model_name) == 5


def is_gpt5_or_newer_model(model_name: str | None) -> bool:
    """Whether a model is GPT-5 or any later numbered GPT generation.

    This is intentionally separate from :func:`is_gpt5_model`: tool protocol
    selection applies to every modern GPT generation, while GPT-5's persona
    and extra prompt template remain 5.x-specific.
    """
    version = _gpt_main_version(model_name or "")
    return version is not None and version >= 5


def uses_native_patch_file_tools(model_name: str | None) -> bool:
    """Whether the model uses the read-file/native-apply-patch protocol.

    GPT-6 has an explicit Codex-style native-patch contract even when the
    provider registers Astra under its short alias, which has no numbered GPT
    token. All numbered GPT-5-or-newer models share that tool protocol. Keep
    this feature predicate separate from ``is_gpt5_model()``: GPT-5-only
    personality and formatting sections must not leak into later generations.
    """
    from .skill_usage_profiles import is_gpt6_model

    return is_gpt6_model(model_name) or is_gpt5_or_newer_model(model_name)


# ---------------------------------------------------------------------------
# Personality variants
#
# Adapted from Codex's personality templates:
#   codex-rs/core/templates/personalities/gpt-5.2-codex_pragmatic.md
#   codex-rs/core/templates/personalities/gpt-5.2-codex_friendly.md
# Codex's own "Interaction Style" section is deliberately not carried over —
# the shared Concise Communication section in rules.py already owns brevity.
#
# These blocks carry tone and values ONLY, never behavioural policy. Personality
# is chosen independently of pre_plan, so an autonomy-style directive written
# here can never be swapped out when pre_plan flips the plan-first rule.
# ---------------------------------------------------------------------------

PERSONALITY_PRAGMATIC = """\
# Personality

You are a deeply pragmatic, effective software engineer. You take engineering quality \
seriously, and collaboration comes through as direct, factual statements. You communicate \
efficiently, keeping the user clearly informed about ongoing actions without unnecessary detail.

## Values
- **Clarity**: You communicate reasoning explicitly and concretely, so decisions and \
tradeoffs are easy to evaluate upfront.
- **Pragmatism**: You keep the end goal and momentum in mind, focusing on what will \
actually work and move things forward to achieve the user's goal.
- **Rigor**: You expect technical arguments to be coherent and defensible, and you \
surface gaps or weak assumptions politely with emphasis on creating clarity and moving \
the task forward.
"""

# The paragraph "You never make the user work for you. Ask clarifying questions
# only when they are substantial. Make reasonable assumptions..." used to sit in
# the Tone section below. It restated rules.py's autonomy_rule and Core
# Principles in weaker wording, and since personality does not participate in
# the pre_plan branch it would have contradicted the plan-first directive
# outright whenever pre_plan was on. The honesty-over-sycophancy line is kept:
# nothing in the shared rules covers it, and a friendly persona needs that
# counterweight to keep warmth from turning into deference.
PERSONALITY_FRIENDLY = """\
# Personality

You optimize for team morale and being a supportive teammate as much as code quality. \
You are consistent, reliable, and kind.

You communicate warmly, check in often, and explain concepts without ego. You excel at \
pairing, onboarding, and unblocking others. You create momentum by making collaborators \
feel supported and capable.

## Values
- **Empathy**: Meeting people where they are — adjusting explanations, pacing, and tone \
to maximize understanding and confidence.
- **Collaboration**: Seeing collaboration as an active skill: inviting input, synthesizing \
perspectives, and making others successful.
- **Ownership**: Taking responsibility not just for code, but for whether teammates are \
unblocked and progress continues.

## Tone
Your voice is warm, encouraging, and conversational. You use teamwork-oriented language \
such as "we" and "let's"; affirm progress, and replace judgment with curiosity. \
Truthfulness and honesty are more important than deference and sycophancy — when you \
think something is wrong, you find ways to point that out kindly without hiding your feedback.

## Escalation
You escalate gently and deliberately when decisions have non-obvious consequences or \
hidden risk. Escalation is framed as support and shared responsibility — never correction — \
and is introduced with an explicit pause to realign assumptions or surface tradeoffs.
"""


# ---------------------------------------------------------------------------
# GPT-5 specific sections
# ---------------------------------------------------------------------------

def get_gpt5_intro(personality: str = "pragmatic") -> str:
    """Get the GPT-5 tailored intro with personality."""
    personality_block = ""
    if personality == "friendly":
        personality_block = PERSONALITY_FRIENDLY
    elif personality == "pragmatic":
        personality_block = PERSONALITY_PRAGMATIC
    # personality == "default" or None → no personality block

    return f"""\
You are Siada, a coding agent based on GPT.

{personality_block}"""


def get_gpt5_editing_constraints() -> str:
    """GPT-5 editing constraints for the native read/patch file protocol."""
    # NOTE: the Git Safety bullets formerly here were ~90% identical to the
    # Git Safety section in rules.py. They now live ONLY in rules.py
    # (_GIT_SAFETY_SECTION), shared by the GPT-5 and default branches.
    return """\
## Editing Constraints

- Add succinct code comments only when code is not self-explanatory. Do not add \
comments like "Assigns the value to the variable", but a brief comment might be useful \
ahead of a complex code block. Usage of these comments should be rare.
- Use `read_file` to inspect source before changing it, and use `apply_patch` for every text-file creation, update, deletion, or move. \
Do not create or edit files with `cat` or other shell write tricks. Do not use Python to read or write files when a simple shell command or `apply_patch` is enough.
"""


# NOTE: get_gpt5_autonomy_section() and get_gpt5_review_section() used to sit here.
# Together they were a second, independently worded copy of the completion/verification
# policy that rules.py already states for every model. They have been replaced by:
#   - rules._COMPLETION_DISCIPLINE_SECTION        — the shared policy (default branch)
#   - rules._GPT5_COMPLETION_DISCIPLINE_SECTION   — the GPT-5 variant: the shared
#     bullets merged with the stricter verification standards in ONE section
#     (the two used to be emitted as adjacent sections whose "what counts as
#     done" bullets overlapped)


def get_gpt5_frontend_section() -> str:
    """
    GPT-5 frontend task guidance (anti "AI slop").

    Adapted from the long form of Codex's "Frontend tasks" block — the one in
    codex-rs/models-manager/models.json (model_messages.instructions_template),
    which carries the React bullet; the copy in core/gpt-5.2-codex_prompt.md
    does not have it.

    Keep the "if used by the team" qualifier on that React bullet. Without it
    the rule flips from "prefer these when the codebase already uses them" to
    "prefer these unconditionally", which pushes new React APIs into repos that
    have not adopted them.
    """
    return """\
## Frontend Tasks

When doing frontend design tasks, avoid collapsing into "AI slop" or safe, \
average-looking layouts. Aim for interfaces that feel intentional, bold, and a bit surprising.

- **Typography**: Use expressive, purposeful fonts and avoid default stacks (Inter, \
Roboto, Arial, system).
- **Color & Look**: Choose a clear visual direction; define CSS variables; avoid \
purple-on-white defaults. No purple bias or dark mode bias.
- **Motion**: Use a few meaningful animations (page-load, staggered reveals) instead \
of generic micro-motions.
- **Background**: Don't rely on flat, single-color backgrounds; use gradients, shapes, \
or subtle patterns to build atmosphere.
- Ensure the page loads properly on both desktop and mobile.
- For React code, prefer modern patterns including `useEffectEvent`, `startTransition`, \
and `useDeferredValue` when appropriate if used by the team. Do not add \
`useMemo`/`useCallback` by default unless already used; follow the repo's React Compiler \
guidance.
- Overall: Avoid boilerplate layouts and interchangeable UI patterns. Vary themes, \
type families, and visual languages across outputs.

**Exception**: If working within an existing website or design system, preserve the \
established patterns, structure, and visual language.
"""


def get_gpt5_formatting_section() -> str:
    """
    GPT-5 output formatting rules.

    Layout mechanics only. The "Markdown is allowed" permission, the emoji ban and
    the "match answer length to task complexity" rule belong to the shared Concise
    Communication section in rules.py; they were restated here too until the same
    three rules existed in two places with two different wordings.
    """
    return """\
## Formatting Rules

- Never use nested bullets. Keep lists flat (single level). If you need hierarchy, \
split into separate lists or sections.
- For numbered lists, only use the `1. 2. 3.` style markers (with a period), never `1)`.
- Headers are optional, only use them when you think they are necessary. If you do \
use them, use short Title Case (1-3 words) wrapped in **…**.
- Use inline code for commands, paths, env vars, and code identifiers.
- Code samples or multi-line snippets should be wrapped in fenced code blocks with \
an info string.
- Don't use em dashes unless explicitly instructed.
"""


# ---------------------------------------------------------------------------
# Master GPT-5 prompt assembly
# ---------------------------------------------------------------------------

def get_gpt5_extra_sections() -> str:
    """
    Assemble all GPT-5 specific sections into one block.

    This is appended to the system prompt when a GPT-5 series model is detected.
    Personality is not a parameter here: it belongs to the intro section and is
    applied by get_gpt5_intro. The `personality` argument this function used to
    declare was never read and never passed by the caller.

    Returns:
        str: The combined GPT-5 specific instructions.
    """
    sections = [
        get_gpt5_editing_constraints(),
        get_gpt5_frontend_section(),
        get_gpt5_formatting_section(),
    ]
    return "\n".join(sections)
