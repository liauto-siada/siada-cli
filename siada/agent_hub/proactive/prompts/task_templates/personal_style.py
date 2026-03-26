"""
Task instruction: Update Personal Style memory (proactive agent version).

Runs as a daily proactive job. Reads the most recent day's structured event files
from the events/ directory and extracts signals about the user's working style into
the single personal_style.md file.
"""

from datetime import datetime, timezone
from pathlib import Path


def get_update_personal_style_instruction() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    home = Path.home()
    events_dir = home / ".siada-cli" / "workspace" / "memory" / "events"
    personal_style_file = home / ".siada-cli" / "workspace" / "memory" / "personal_style.md"
    return f"""# Task: Update Personal Style

Update the personal style memory file based on the most recent work session events.

Today's date: {today}

───────────────────────────────────────────────────────────────
STEPS
───────────────────────────────────────────────────────────────

1. Check `{events_dir}` for event files from today (filenames starting with `{today}`).
   If none exist, stop here — do nothing.
2. Read all of today's event files to extract signals about the user's working style.
3. Read the existing `{personal_style_file}` (treat as empty if it does not exist).
4. Identify new or stronger evidence of the user's recurring working habits,
   technical preferences, decision-making patterns, or responsibilities.
5. Merge and write the updated content back to `{personal_style_file}`.

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
                                  the user consistently favors or avoids. Do NOT
                                  record a choice made only to solve a specific
                                  problem; ask whether the same preference would
                                  apply in a different project or context before
                                  recording it.
  - Work Habits                   Recurring processes the user follows regardless
                                  of the specific task at hand (e.g. always
                                  requires a design review before coding, always
                                  writes tests alongside implementation)
  - Documentation Standards       What the user expects in docs and comments.
  - Communication Patterns        How the user frames requests, corrections, and
                                  clarifications.

───────────────────────────────────────────────────────────────
QUALITY RULES
───────────────────────────────────────────────────────────────

  - Only record characteristics that are durable and general — they must apply
    across different tasks, projects, or contexts, not just the current session
  - Before recording any signal, ask: "Would this still be true in an unrelated
    project?" If the answer is "probably not", discard it
  - A pattern observed once is a signal, not yet a fact — use hedged language
    unless confirmed across sessions
  - If new evidence contradicts existing content, replace the old entry
  - Keep total file length under 2048 tokens; remove low-value or outdated entries
  - Write in present tense ("prefers", "always requires", "tends to")

───────────────────────────────────────────────────────────────
FILE STRUCTURE (maintain this layout)
───────────────────────────────────────────────────────────────

  # Personal Style

  ## Work Responsibilities
  ## Technical Preferences
  ## Work Habits
  ## Documentation Standards
  ## Communication Patterns

If no new personal style signals are found, do nothing.
"""
