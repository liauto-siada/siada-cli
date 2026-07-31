"""
Task instruction: Update user profile in USER.md (proactive agent version).

Runs as a daily proactive job. Reads the most recent day's structured event files
from the events/ directory and extracts durable signals about the user's working
style, writing them to USER.md (§-separated entries, max 1375 chars).

NOTE: personal_style.md is deprecated. USER.md is the canonical user profile.
If personal_style.md exists, its content should be migrated into USER.md entries.
"""

from datetime import datetime, timezone
from pathlib import Path


def get_update_personal_style_instruction() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    home = Path.home()
    memory_dir = home / ".siada-cli" / "workspace" / "memory"
    events_dir = memory_dir / "events"
    user_profile_file = memory_dir / "USER.md"
    personal_style_file = memory_dir / "personal_style.md"
    return f"""# Task: Update User Profile (USER.md)

Update the user profile memory file based on the most recent work session events.

Today's date: {today}

───────────────────────────────────────────────────────────────
STEPS
───────────────────────────────────────────────────────────────

1. Check `{events_dir}` for event files from today (filenames starting with `{today}`).
   If none exist, stop here — do nothing.
2. Read all of today's event files to extract signals about the user's working style.
3. Read the existing `{user_profile_file}` (treat as empty if it does not exist).
4. If `{personal_style_file}` exists, read it and merge its content into USER.md
   entries as described below (migration step — only needed once per entry).
5. Identify new or stronger evidence of the user's recurring working habits,
   technical preferences, decision-making patterns, or responsibilities.
6. Write updated entries to `{user_profile_file}` using the § separator format:
   - Each entry is a concise declarative fact on its own line
   - Entries are separated by a line containing only `§`
   - Total file content must stay under 1375 characters
   - Remove low-value or outdated entries to stay within the limit

───────────────────────────────────────────────────────────────
WHAT TO CAPTURE
───────────────────────────────────────────────────────────────

  - Work Responsibilities         The user's stable role or ownership — being
                                  responsible for a project, system, team, or
                                  domain. Do NOT record one-off tasks such as
                                  fixing a specific bug or implementing a single
                                  feature request; those are work items, not
                                  responsibilities.
  - Technical Preferences         Broad, cross-context technical inclinations:
                                  architectural styles, performance philosophy,
                                  code conventions, paradigms, or tool categories
                                  the user consistently favors or avoids.
  - Work Habits                   Recurring processes the user follows regardless
                                  of the specific task at hand.
  - Communication Patterns        How the user frames requests, corrections, and
                                  clarifications.

───────────────────────────────────────────────────────────────
QUALITY RULES
───────────────────────────────────────────────────────────────

  - Only record characteristics that are durable and general
  - A pattern observed once is a signal, not yet a fact — use hedged language
    unless confirmed across sessions
  - If new evidence contradicts existing content, replace the old entry
  - Write as declarative facts in present tense ("prefers", "tends to")
  - Each entry should be 1-3 sentences maximum

───────────────────────────────────────────────────────────────
FILE FORMAT
───────────────────────────────────────────────────────────────

  User prefers concise, direct responses without lengthy preamble.
  §
  User works primarily on Python and Swift projects.
  §
  User always requests a design review before implementation on complex tasks.

If no new user profile signals are found, do nothing.
"""
