"""
Daily Summary Instruction Template

This instruction is sent by the scheduler to ask ProactiveAgent
to generate a summary of the most recent work day's activities.
"""

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from siada.foundation.constants import SIADA_HOME


def _find_last_work_date(events_dir: Path, today: date) -> date:
    """Return the most recent date before today that has event files."""
    if events_dir.exists():
        dates: set[date] = set()
        for f in events_dir.iterdir():
            if not f.is_file():
                continue
            parts = f.name.split("-")
            if len(parts) >= 3:
                try:
                    d = date(int(parts[0]), int(parts[1]), int(parts[2]))
                    if d < today:
                        dates.add(d)
                except ValueError:
                    pass
        if dates:
            return max(dates)
    return today - timedelta(days=1)


def _get_preferred_language() -> str:
    """Read preferred_language from conf.yaml, default to 'en'."""
    try:
        from siada.config.config_loader import load_conf
        conf = load_conf()
        return conf.preferred_language or "en"
    except Exception:
        return "en"


# Base directory for all memory-related files (events, sessions, summaries)
_MEMORY_DIR = SIADA_HOME / "workspace" / "memory"


def get_last_work_date_str() -> str:
    """Return the last work date as a string (YYYY-MM-DD).

    This is the single source of truth for determining which date the daily
    summary should cover.  Uses local time so that the generation phase and
    the IM-send phase always agree on the same date, even when they straddle
    the UTC midnight boundary.
    """
    today = datetime.now().date()
    work_date = _find_last_work_date(_MEMORY_DIR / "events", today)
    return work_date.strftime("%Y-%m-%d")


def get_daily_summary_file_path(work_date_str: Optional[str] = None) -> Path:
    """Return the expected path of the daily summary file.

    Args:
        work_date_str: Date string in YYYY-MM-DD format.  When *None*,
            :func:`get_last_work_date_str` is called to determine the date.
    """
    if work_date_str is None:
        work_date_str = get_last_work_date_str()
    return _MEMORY_DIR / "summary" / f"{work_date_str}_summary.md"


def get_daily_summary_instruction(
    preferred_language: Optional[str] = None,
    work_date_str: Optional[str] = None,
) -> str:
    events_dir = _MEMORY_DIR / "events"
    session_dir = _MEMORY_DIR / "session"

    if work_date_str is None:
        work_date_str = get_last_work_date_str()
    summary_file = get_daily_summary_file_path(work_date_str)

    lang = preferred_language or _get_preferred_language()
    if lang.startswith("zh"):
        return _instruction_zh(work_date_str, events_dir, session_dir, summary_file)
    return _instruction_en(work_date_str, events_dir, session_dir, summary_file)


# ---------------------------------------------------------------------------
# English version
# ---------------------------------------------------------------------------

def _instruction_en(work_date_str: str, events_dir: Path, session_dir: Path, summary_file: Path) -> str:
    return f"""# Task: Generate Daily Work Summary

Work date: {work_date_str}

## Data Sources

1. **Events** (primary): `{events_dir}` — files prefixed `{work_date_str}`. Already distilled with structured fields.
2. **Sessions** (fallback): `{session_dir}` — only for sessions WITHOUT a corresponding event. Process one by one.

## Steps

1. List & sort event files for `{work_date_str}` chronologically.
2. Read each event incrementally. For each event, extract:
   - `## Repository Info` → `Repository name` (the top-level grouping key)
   - The event slug (from filename) → the topic name
   - Key outcome, decisions, blockers, and predicted next tasks
3. List session files for `{work_date_str}`; skip those with a matching event.
4. Read remaining sessions incrementally; extract key facts and repo info.
5. Group all entries by repository name, then write the summary and save to `{summary_file}`.

## Output Format

```markdown
# Daily Summary - {work_date_str}

## Overview
[≤ 3 sentences: how many projects, how many items, the most important 1-3 things today]

## [Repository A]  (N items)

### Progress
- **[topic from slug]**: [≤ 1 sentence outcome]. [optional status note].
- **[topic from slug]**: ...

### Decisions
- [key technical decision made today]

### Blockers / Risks
- [blockers or risks observed]

### Next Steps
- P0: [highest priority follow-up]
- P1: [medium priority]
- P2: [lower priority]

### Sources
- HH-MM-slug
- HH-MM-slug

## [Repository B]  (M items)
...

## Tools / Environment (optional — only for entries without a real repo)
- [lightweight entry, e.g., installed a CLI tool]

## Statistics
N projects · M sessions · K items
```

## Rules

### Grouping
- Top-level grouping = `Repository name` from each event's `## Repository Info` section.
- Each repository becomes one H2 section: `## [repo name]  (N items)`.
- If a repo name is missing or unclear, group as "Uncategorized".
- Trivial entries without a real repository (e.g., installing a tool) go into "## Tools / Environment".

### Per-Repository Structure
- Within each repository H2, use up to 5 H3 sub-sections in this order:
  `### Progress` / `### Decisions` / `### Blockers / Risks` / `### Next Steps` / `### Sources`
- Omit any sub-section that has no content (except Progress and Sources which must always exist).
- NEVER create cross-project sections like "Cross-Project Decisions". Decisions/blockers belong
  to the project that drove them.

### One Event = One Bullet
- Each event file = exactly ONE bullet under its repo's `### Progress`. Format:
  `- **<topic from slug>**: <≤ 1 sentence outcome>. <optional status note>.`
- Within the same repo, merge 2+ events sharing an obvious topic into ONE bullet.
- NEVER enumerate file paths, function names, or symbol names that already live inside event files.
  The summary is a reading guide, not a changelog.

### Sources Section
- DO NOT put source citations after each bullet in Progress/Decisions/Blockers.
- All sources for a repo are aggregated in that repo's `### Sources` sub-section, listed as:
  `- HH-MM-<slug>` (one per line, time-ascending, strip the `YYYY-MM-DD-` prefix).

### Length Budget
- Total ≤ 600 words. Per repo ≤ 5 Progress bullets (merge if more).

### Other
- Prefer events over sessions; use `predicted next tasks` as authoritative next-step source.
- Process files sequentially (oldest first).
- Save to: `{summary_file}`
"""


# ---------------------------------------------------------------------------
# Localized variant (English content)
# ---------------------------------------------------------------------------

def _instruction_zh(work_date_str: str, events_dir: Path, session_dir: Path, summary_file: Path) -> str:
    return f"""# Task: Generate Daily Work Summary

Work date: {work_date_str}

## Data Sources

1. **Events** (primary): `{events_dir}` — files prefixed `{work_date_str}`. Already distilled with structured fields.
2. **Sessions** (fallback): `{session_dir}` — only for sessions WITHOUT a corresponding event. Process one by one.

## Steps

1. List & sort event files for `{work_date_str}` chronologically.
2. Read each event incrementally. For each event, extract:
   - `## Repository Info` → `Repository name` (the top-level grouping key)
   - The event slug (from filename) → the topic name
   - Key outcome, decisions, blockers, and predicted next tasks
3. List session files for `{work_date_str}`; skip those with a matching event.
4. Read remaining sessions incrementally; extract key facts and repo info.
5. Group all entries by repository name, then write the summary and save to `{summary_file}`.

## Output Format

```markdown
# Daily Summary - {work_date_str}

## Overview
[≤ 3 sentences: how many projects, how many items, the most important 1-3 things today]

## [Repository A]  (N items)

### Progress
- **[topic from slug]**: [≤ 1 sentence outcome]. [optional status note].
- **[topic from slug]**: ...

### Decisions
- [key technical decision made today]

### Blockers / Risks
- [blockers or risks observed]

### Next Steps
- P0: [highest priority follow-up]
- P1: [medium priority]
- P2: [lower priority]

### Sources
- HH-MM-slug
- HH-MM-slug

## [Repository B]  (M items)
...

## Tools / Environment (optional — only for entries without a real repo)
- [lightweight entry, e.g., installed a CLI tool]

## Statistics
N projects · M sessions · K items
```

## Rules

### Grouping
- Top-level grouping = `Repository name` from each event's `## Repository Info` section.
- Each repository becomes one H2 section: `## [repo name]  (N items)`.
- If a repo name is missing or unclear, group as "Uncategorized".
- Trivial entries without a real repository (e.g., installing a tool) go into "## Tools / Environment".

### Per-Repository Structure
- Within each repository H2, use up to 5 H3 sub-sections in this order:
  `### Progress` / `### Decisions` / `### Blockers / Risks` / `### Next Steps` / `### Sources`
- Omit any sub-section that has no content (except Progress and Sources which must always exist).
- NEVER create cross-project sections like "Cross-Project Decisions". Decisions/blockers belong
  to the project that drove them.

### One Event = One Bullet
- Each event file = exactly ONE bullet under its repo's `### Progress`. Format:
  `- **<topic from slug>**: <≤ 1 sentence outcome>. <optional status note>.`
- Within the same repo, merge 2+ events sharing an obvious topic into ONE bullet.
- NEVER enumerate file paths, function names, or symbol names that already live inside event files.
  The summary is a reading guide, not a changelog.

### Sources Section
- DO NOT put source citations after each bullet in Progress/Decisions/Blockers.
- All sources for a repo are aggregated in that repo's `### Sources` sub-section, listed as:
  `- HH-MM-<slug>` (one per line, time-ascending, strip the `YYYY-MM-DD-` prefix).

### Length Budget
- Total ≤ 600 words. Per repo ≤ 5 Progress bullets (merge if more).

### Other
- Prefer events over sessions; use `predicted next tasks` as authoritative next-step source.
- Process files sequentially (oldest first).
- Save to: `{summary_file}`
"""
