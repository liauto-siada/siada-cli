"""
siada/services/skills/renderer.py
Skill prompt renderer - generate skills section in system prompts
"""

import logging
from pathlib import Path
from typing import Optional

from .config import MAX_DESCRIPTION_LENGTH
from .models import SkillMetadata, SkillScope, SkillUsageProfile

logger = logging.getLogger(__name__)

# Max characters of one skill description shown in the prompt. Matches the
# parse-time limit (config.MAX_DESCRIPTION_LENGTH), so this clipping is a
# defensive fallback that never triggers for loader-parsed skills.
MAX_DESCRIPTION_DISPLAY_CHARS = MAX_DESCRIPTION_LENGTH

# Total character budget for the rendered skill list, plus the dynamic variant
# used when the model context window is known (both borrowed from
# codex-rs/ext/skills/src/render.rs): 2% of the window in tokens, converted at
# ~4 chars per token; otherwise a flat 8,000 characters.
DEFAULT_SKILLS_METADATA_CHAR_BUDGET = 8_000
SKILLS_METADATA_CONTEXT_WINDOW_PERCENT = 2
APPROX_CHARS_PER_TOKEN = 4

# Built-in skills listed here remain available to slash completion but are not
# advertised to the model unless explicitly activated for the current turn.
HIDDEN_SYSTEM_SKILLS: frozenset[str] = frozenset({
    "finishing-a-development-branch",
    "receiving-code-review",
    "test-driven-development",
    "long-horizon",
    "brainstorming",
    "verification-before-completion",
    "systematic-debugging",
    "dispatching-parallel-agents",
    "executing-plans",
    "requesting-code-review",
    "subagent-driven-development",
    "design-doc-writer",
    "writing-plans",
})
LONG_HORIZON_SKILL_NAME = "long-horizon"
LONG_HORIZON_EXCLUDED_SKILL = "design-doc-writer"


# Intro variants: absolute file paths vs short paths expandable via the
# skill roots table (borrowed from codex-rs/ext/skills/src/catalog_prompt.rs).
SKILLS_INTRO_ABSOLUTE = "A skill is a set of local instructions to follow that is stored in a `SKILL.md` file. Below is the list of skills that can be used. Each entry includes a name, description, and file path so you can open the source for full instructions when using a specific skill."

SKILLS_INTRO_ALIASED = "A skill is a set of local instructions to follow that is stored in a `SKILL.md` file. Below is the list of skills that can be used. Each entry includes a name, description, and a short aliased path. When short aliased paths are used, `### Skill roots` maps aliases such as `r0` to their absolute filesystem roots. Expand the matching alias before accessing the skill."

# How-to-use variants. Both share the same rules; the aliased one adds the
# alias-expansion step. Key rules synced from the latest Codex version:
# - read the selected SKILL.md COMPLETELY (until EOF) before acting;
# - never delegate reading/interpreting skill instructions to a subagent;
# - progressive disclosure applies to selecting files, not partial reads;
# - the absolute variants never mention `### Skill roots`: that table only
#   exists in the aliased layout, so telling the model to expand an alias
#   there would dangle. Mirrors Codex, where a missing alias plan degrades
#   the whole catalog (intro + how-to) to the unaliased prompt kind.
SKILLS_HOW_TO_USE_STRICT_ABSOLUTE = """- **Discovery**: The list above is the skills available in this session (name + description + file path). Skill bodies live on disk at the listed paths.
- **Trigger rules**: If the user names a skill OR the task clearly matches a skill's description shown above, you must use that skill for that turn. Multiple mentions mean use them all. Do not carry skills across turns unless re-mentioned.
- **Missing/blocked**: If a named skill isn't in the list or the path can't be read, say so briefly and continue with the best fallback.
- **How to use a skill** (progressive disclosure):
  1) After deciding to use a skill, open and read its `SKILL.md` at the listed path completely before taking task actions. If a read is truncated or paginated, continue until EOF.
  2) When `SKILL.md` references relative paths (e.g., `scripts/foo.js`), resolve them relative to the directory containing that `SKILL.md` first, and only consider other paths if needed.
  3) If `SKILL.md` points to extra folders such as `references/`, use its routing instructions to identify the files required for the task. You must read each required instruction or reference file yourself before acting on it. Do not delegate reading, summarizing, or interpreting skill instructions to a subagent. Subagents may still perform task work when the selected skill allows it.
  4) If `scripts/` exist, prefer running or patching them instead of retyping large code blocks.
  5) If `assets/` or templates exist, reuse them instead of recreating from scratch.
- **Coordination and sequencing**:
  - If multiple skills apply, choose the minimal set that covers the request and state the order you'll use them.
  - Announce which skill(s) you're using and why (one short line). If you skip an obvious skill, say why.
- **Context hygiene**:
  - Progressive disclosure applies to selecting relevant files, not partially reading a selected instruction file. Do not load unrelated references, scripts, or assets.
  - Avoid deep reference-chasing: prefer opening only files directly linked from `SKILL.md` unless you're blocked.
  - When variants exist (frameworks, providers, domains), pick only the relevant reference file(s) and note that choice.
- **Safety and fallback**: If a skill can't be applied cleanly (missing files, unclear instructions), state the issue, pick the next-best approach, and continue."""

SKILLS_HOW_TO_USE_STRICT_ALIASED = """- **Discovery**: The list above is the skills available in this session (name + description + short path). Skill bodies live on disk at the listed paths after expanding the matching alias from `### Skill roots`.
- **Trigger rules**: If the user names a skill OR the task clearly matches a skill's description shown above, you must use that skill for that turn. Multiple mentions mean use them all. Do not carry skills across turns unless re-mentioned.
- **Missing/blocked**: If a named skill isn't in the list or the path can't be read, say so briefly and continue with the best fallback.
- **How to use a skill** (progressive disclosure):
  1) After deciding to use a skill, expand the listed short `path` with the matching alias from `### Skill roots`, then open and read its `SKILL.md` completely before taking task actions. If a read is truncated or paginated, continue until EOF.
  2) When `SKILL.md` references relative paths (e.g., `scripts/foo.js`), resolve them relative to the directory containing that expanded `SKILL.md` first, and only consider other paths if needed.
  3) If `SKILL.md` points to extra folders such as `references/`, use its routing instructions to identify the files required for the task. You must read each required instruction or reference file yourself before acting on it. Do not delegate reading, summarizing, or interpreting skill instructions to a subagent. Subagents may still perform task work when the selected skill allows it.
  4) If `scripts/` exist, prefer running or patching them instead of retyping large code blocks.
  5) If `assets/` or templates exist, reuse them instead of recreating from scratch.
- **Coordination and sequencing**:
  - If multiple skills apply, choose the minimal set that covers the request and state the order you'll use them.
  - Announce which skill(s) you're using and why (one short line). If you skip an obvious skill, say why.
- **Context hygiene**:
  - Progressive disclosure applies to selecting relevant files, not partially reading a selected instruction file. Do not load unrelated references, scripts, or assets.
  - Avoid deep reference-chasing: prefer opening only files directly linked from `SKILL.md` unless you're blocked.
  - When variants exist (frameworks, providers, domains), pick only the relevant reference file(s) and note that choice.
- **Safety and fallback**: If a skill can't be applied cleanly (missing files, unclear instructions), state the issue, pick the next-best approach, and continue."""

SKILLS_HOW_TO_USE_GPT6_ABSOLUTE = """A skill is a set of instructions stored in a `SKILL.md` file. The skills available to you in this session are
listed above under `### Available skills`, each with a name, description, and file path. Open that path to read
the skill before relying on it.

The user's instructions take precedence over guidelines provided in a skill. If explicit user instructions
conflict with a skill's instructions, prioritize the user's instructions.

The first time in a conversation that you decide to apply a skill, tell the user in one short sentence which
skill you are using and why.

If a skill causes you to ask the user for permission or confirmation, pause, or leave requested work
unfinished, name the skill and quote the specific instruction you are following, and explain how it applies.
Distinguish what the skill explicitly requires from your own interpretation of it. If a skill does not
explicitly require approval, continue within the scope the user has already authorized instead of asking for
confirmation based on an inferred requirement.

If your current task would benefit from a skill without the user naming one, use reasonable judgement to apply
it. Do not pick up a skill based only on keyword overlap, superficial relevance, or the mere fact that a skill
exists. Do not carry a skill across turns unless the user names it again or it stays relevant to the work you
are doing.

To use a skill, open and read the `SKILL.md` at its listed path. When it references a relative path, resolve
that path against the directory containing the `SKILL.md`. Avoid reading the same skill twice in one session."""

SKILLS_HOW_TO_USE_GPT6_ALIASED = """A skill is a set of instructions stored in a `SKILL.md` file. The skills available to you in this session are
listed above under `### Available skills`, each with a name, description, and short path. Expand a short path
using the matching alias in `### Skill roots` before reading the skill.

The user's instructions take precedence over guidelines provided in a skill. If explicit user instructions
conflict with a skill's instructions, prioritize the user's instructions.

The first time in a conversation that you decide to apply a skill, tell the user in one short sentence which
skill you are using and why.

If a skill causes you to ask the user for permission or confirmation, pause, or leave requested work
unfinished, name the skill and quote the specific instruction you are following, and explain how it applies.
Distinguish what the skill explicitly requires from your own interpretation of it. If a skill does not
explicitly require approval, continue within the scope the user has already authorized instead of asking for
confirmation based on an inferred requirement.

If your current task would benefit from a skill without the user naming one, use reasonable judgement to apply
it. Do not pick up a skill based only on keyword overlap, superficial relevance, or the mere fact that a skill
exists. Do not carry a skill across turns unless the user names it again or it stays relevant to the work you
are doing.

To use a skill, expand its listed short path with the matching alias in `### Skill roots`, then open and read
the `SKILL.md`. When it references a relative path, resolve that path against the directory containing the
`SKILL.md`. Avoid reading the same skill twice in one session."""

# The instructions originated from the Astra template, but apply to every
# GPT-6 variant. Keep the old names as compatibility aliases for callers that
# adopted them before the profile scope was widened.
SKILLS_HOW_TO_USE_ASTRA_ABSOLUTE = SKILLS_HOW_TO_USE_GPT6_ABSOLUTE
SKILLS_HOW_TO_USE_ASTRA_ALIASED = SKILLS_HOW_TO_USE_GPT6_ALIASED

# Preserve historical imports and strict-profile bytes for existing callers.
SKILLS_HOW_TO_USE_ABSOLUTE = SKILLS_HOW_TO_USE_STRICT_ABSOLUTE
SKILLS_HOW_TO_USE_ALIASED = SKILLS_HOW_TO_USE_STRICT_ALIASED


def select_how_to_use(profile: SkillUsageProfile, *, aliased: bool) -> str:
    """Return fixed instructions for one model profile and path layout."""
    variants = {
        (SkillUsageProfile.STRICT, False): SKILLS_HOW_TO_USE_STRICT_ABSOLUTE,
        (SkillUsageProfile.STRICT, True): SKILLS_HOW_TO_USE_STRICT_ALIASED,
        (SkillUsageProfile.GPT6, False): SKILLS_HOW_TO_USE_GPT6_ABSOLUTE,
        (SkillUsageProfile.GPT6, True): SKILLS_HOW_TO_USE_GPT6_ALIASED,
    }
    return variants[(profile, aliased)]


# Skills section template
SKILLS_SECTION_TEMPLATE = """## Skills

{intro}

{roots_section}### Available skills

{skill_list}

### How to use skills

{how_to_use}"""


# Hint when no skills available
NO_SKILLS_TEMPLATE = """## Skills

No skills are currently available in this session. """


def _to_posix(path: "Path | str") -> str:
    """Render a path with forward slashes for cross-platform consistency.

    Uses the platform-aware pathlib API instead of a blind string replace:
    on Windows the separators are converted, while on POSIX a backslash is a
    legal filename character and is therefore left untouched. Forward slashes
    also keep the rendered paths free of backslashes, which the model would
    otherwise have to re-escape when echoing them into tool-call JSON.
    """
    return Path(path).as_posix()


def _flatten_skill_roots(
    skill_roots: Optional[dict[SkillScope, "Path | list[Path]"]],
) -> list[Path]:
    """
    Flatten configured skill roots into a deterministic ordered list.

    Ordering is a pure function of the configuration (never of discovery or
    dict-insertion order), so the rendered prompt stays byte-identical across
    builds and preserves model prompt-cache hits:
    - scopes iterate by SkillScope value (lower value = higher priority first);
    - within a scope, the configured list order is preserved;
    - duplicates after resolve() are dropped, keeping the first occurrence.
    """
    if not skill_roots:
        return []

    ordered: list[Path] = []
    seen: set[str] = set()
    for scope in sorted(skill_roots.keys()):
        scope_paths = skill_roots[scope]
        candidates = list(scope_paths) if isinstance(scope_paths, (list, tuple)) else [scope_paths]
        for root in candidates:
            resolved = Path(root).resolve()
            key = str(resolved)
            if key not in seen:
                seen.add(key)
                ordered.append(resolved)
    return ordered


def _match_root(skill_path: Path, roots: list[Path]) -> Optional[Path]:
    """Return the longest configured root that contains skill_path."""
    best: Optional[Path] = None
    for root in roots:
        if skill_path.is_relative_to(root) and (best is None or len(root.parts) > len(best.parts)):
            best = root
    return best


def _clip_description(desc: str, limit: int) -> str:
    """Clip a description to at most `limit` display characters.

    A limit <= 0 (or an empty description) yields "" so the caller can omit
    the description entirely. Truncated text ends with "..." inside the limit,
    so the displayed length is exactly min(len(desc), limit) - monotonically
    non-decreasing in the limit, which the budget binary search relies on.
    """
    if limit <= 0 or not desc:
        return ""
    if len(desc) <= limit:
        return desc
    if limit <= 3:
        return desc[:limit]
    return desc[: limit - 3] + "..."


def _format_entry_line(name: str, desc: str, path_str: str, desc_limit: int) -> str:
    """Format one skill list line; desc_limit=0 renders name + path only."""
    clipped = _clip_description(desc, desc_limit)
    if not clipped:
        return f"- {name}: (file: {path_str})"
    return f"- {name}: {clipped} (file: {path_str})"


def format_skill_entry(
    skill: SkillMetadata,
    display_path: Optional[str] = None,
    max_display_len: int = MAX_DESCRIPTION_DISPLAY_CHARS,
) -> str:
    """
    Format single skill entry as one compact line.

    Args:
        skill: Skill metadata
        display_path: Path shown to the model (aliased short path or absolute
            path). Defaults to the skill's absolute path.
        max_display_len: Max characters shown for the description. Defaults to
            MAX_DESCRIPTION_DISPLAY_CHARS (aligned with the parse-time limit).

    Returns:
        Formatted string, e.g. "- name: description (file: r0/name/SKILL.md)"
    """
    path_str = display_path if display_path is not None else _to_posix(skill.path)
    return _format_entry_line(skill.name, skill.description, path_str, max_display_len)


def render_skills_section(
    skills: list[SkillMetadata],
    include_empty_hint: bool = False,
    skill_roots: Optional[dict[SkillScope, "Path | list[Path]"]] = None,
    context_window: Optional[int] = None,
    activated_skill_names: Optional[set[str]] = None,
    usage_profile: SkillUsageProfile = SkillUsageProfile.STRICT,
) -> Optional[str]:
    """
    Render skills prompt section.

    Args:
        skills: Skill metadata list
        include_empty_hint: Whether to include hint when no skills available
        skill_roots: Configured roots (same mapping used at load time). When
            provided, skills under a shared root render with a short aliased
            path and a `### Skill roots` table maps each alias to its absolute
            root. Skills matching no root keep their absolute path. When None,
            all entries render absolute paths.
        context_window: Model context window in tokens, used to size the skill
            list budget (2% of the window). When None, a flat fallback budget
            of DEFAULT_SKILLS_METADATA_CHAR_BUDGET characters applies.
        activated_skill_names: Skill names explicitly activated for this turn.
            Hidden system skills in this set are included in the catalog.
        usage_profile: Usage instructions paired with the catalog. Defaults to
            STRICT so all existing model prompts retain their current text.

    Returns:
        Rendered prompt section, None if no skills and include_empty_hint=False

    Note:
        Output is deterministic: roots are ordered by scope priority then
        configuration order, skills sort by (name, path), and the budget is a
        pure function of `context_window`. Given the same skill set and the
        same arguments, repeated renders are byte-identical so model prompt
        caches keep hitting.
    """
    activated = {name.lower() for name in (activated_skill_names or set())}
    hidden_system_skills = {name.lower() for name in HIDDEN_SYSTEM_SKILLS}
    if LONG_HORIZON_SKILL_NAME in activated:
        activated.update(hidden_system_skills - {LONG_HORIZON_EXCLUDED_SKILL})
    skills = [
        skill
        for skill in skills
        if skill.scope != SkillScope.SYSTEM
        or skill.name.lower() not in hidden_system_skills
        or skill.name.lower() in activated
    ]
    if not skills:
        return NO_SKILLS_TEMPLATE if include_empty_hint else None

    # Sort by name (path as tiebreak) for a stable, cache-friendly order
    sorted_skills = sorted(skills, key=lambda s: (s.name.lower(), _to_posix(s.path)))

    # Resolve once: loader already resolves, but stay robust for direct callers
    prepared = [(skill, Path(skill.path).resolve()) for skill in sorted_skills]

    # Match each skill to its longest containing root; roots used by at least
    # one skill get an alias in deterministic configuration order (r0, r1, ...)
    roots = _flatten_skill_roots(skill_roots)
    matched = [_match_root(path, roots) for _, path in prepared]
    alias_by_root: dict[str, str] = {}
    for root in roots:
        if any(m == root for m in matched):
            alias_by_root[str(root)] = f"r{len(alias_by_root)}"

    entries: list[tuple[str, str, str]] = []  # (name, description, display_path)
    for (skill, path), root in zip(prepared, matched):
        if root is not None and str(root) in alias_by_root:
            alias = alias_by_root[str(root)]
            relative = _to_posix(path.relative_to(root))
            display_path = f"{alias}/{relative}"
        else:
            display_path = _to_posix(path)
        entries.append((skill.name, skill.description, display_path))
    skill_list = _render_skill_list_within_budget(
        entries, _resolve_skills_char_budget(context_window)
    )

    if alias_by_root:
        # Render roots posix-style too: the entry paths above already use
        # forward slashes, and keeping the table consistent avoids handing the
        # model backslashes it would have to re-escape in tool-call JSON.
        root_lines = "\n".join(
            f"- `{alias}` = `{_to_posix(root)}`" for root, alias in alias_by_root.items()
        )
        roots_section = f"### Skill roots\n\n{root_lines}\n\n"
        intro = SKILLS_INTRO_ALIASED
        how_to_use = select_how_to_use(usage_profile, aliased=True)
    else:
        roots_section = ""
        intro = SKILLS_INTRO_ABSOLUTE
        how_to_use = select_how_to_use(usage_profile, aliased=False)

    return SKILLS_SECTION_TEMPLATE.format(
        intro=intro,
        roots_section=roots_section,
        skill_list=skill_list,
        how_to_use=how_to_use,
    )


def _resolve_skills_char_budget(context_window: Optional[int]) -> int:
    """Total character budget for the rendered skill list.

    With a known context window: 2% of it in tokens, converted at ~4 chars per
    token (mirrors codex-rs/ext/skills/src/render.rs). Otherwise a flat
    DEFAULT_SKILLS_METADATA_CHAR_BUDGET characters.
    """
    if context_window is not None and context_window > 0:
        token_budget = max(1, context_window * SKILLS_METADATA_CONTEXT_WINDOW_PERCENT // 100)
        return token_budget * APPROX_CHARS_PER_TOKEN
    return DEFAULT_SKILLS_METADATA_CHAR_BUDGET


def _skill_list_cost(entries: list[tuple[str, str, str]], desc_limit: int) -> int:
    """Total rendered characters of the skill list, newlines included."""
    return sum(len(_format_entry_line(n, d, p, desc_limit)) + 1 for n, d, p in entries)


def _fit_description_limit(entries: list[tuple[str, str, str]], budget: int) -> int:
    """Largest uniform per-description display limit that fits the budget.

    Returns MAX_DESCRIPTION_DISPLAY_CHARS when everything fits unclipped, 0
    when only description-less lines fit, and -1 when even those exceed the
    budget. Displayed description length is monotonically non-decreasing in
    the limit, so binary search converges to the optimum.
    """
    if _skill_list_cost(entries, MAX_DESCRIPTION_DISPLAY_CHARS) <= budget:
        return MAX_DESCRIPTION_DISPLAY_CHARS
    best, lo, hi = -1, 0, MAX_DESCRIPTION_DISPLAY_CHARS
    while lo <= hi:
        mid = (lo + hi) // 2
        if _skill_list_cost(entries, mid) <= budget:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _render_skill_list_within_budget(
    entries: list[tuple[str, str, str]], budget: int
) -> str:
    """Render skill list lines, degrading gracefully when over budget.

    Degradation order (borrowed from codex-rs/ext/skills/src/render.rs): clip
    every description to a uniform limit -> drop all descriptions -> omit
    trailing entries with a "(+N more skills)" trailer.
    """
    limit = _fit_description_limit(entries, budget)

    if limit >= 0:
        if limit == 0:
            logger.warning(
                "Skills prompt budget (%d chars) exceeded: all skill descriptions "
                "were removed; only names and paths are shown.",
                budget,
            )
        elif limit < MAX_DESCRIPTION_DISPLAY_CHARS and any(
            len(desc) > limit for _, desc, _ in entries
        ):
            logger.warning(
                "Skill descriptions were shortened to at most %d chars to fit the "
                "%d-char skills prompt budget. Disable unused skills to leave more "
                "room for the rest.",
                limit,
                budget,
            )
        return "\n".join(_format_entry_line(n, d, p, limit) for n, d, p in entries)

    # Even name+path lines exceed the budget: keep the longest fitting prefix.
    kept: list[str] = []
    for name, desc, path_str in entries:
        candidate = kept + [_format_entry_line(name, desc, path_str, 0)]
        remaining = len(entries) - len(candidate)
        trailer = f"(+{remaining} more skills)" if remaining else ""
        cost = sum(len(line) + 1 for line in candidate)
        if trailer:
            cost += len(trailer) + 1
        if cost > budget:
            break
        kept = candidate
    omitted = len(entries) - len(kept)
    logger.warning(
        "Skills prompt budget (%d chars) exceeded: %d skill(s) omitted from the prompt list.",
        budget,
        omitted,
    )
    kept.append(f"(+{omitted} more skills)")
    return "\n".join(kept)


def render_skill_summary(skills: list[SkillMetadata]) -> str:
    """
    Render skills brief summary (for logs or status display)

    Args:
        skills: Skill metadata list

    Returns:
        Brief summary string
    """
    if not skills:
        return "No skills loaded"

    names = [skill.name for skill in skills]
    return f"Loaded {len(skills)} skill(s): {', '.join(names)}"
