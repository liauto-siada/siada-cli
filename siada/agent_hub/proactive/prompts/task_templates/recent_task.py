"""
Task instruction: Update Recent Task memory.

Runs last in the memory pipeline. Reads the structured event from the
conversation history and updates the single recent_task.md file with
current task statuses and predicted next tasks.
"""

from datetime import datetime, timezone
from pathlib import Path


def get_recent_task_instruction() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    home = Path.home()
    memory_dir = home / ".siada-cli" / "workspace" / "memory"
    recent_task_file = memory_dir / "recent_task.md"
    max_token = 2048
    return f"""\
Your current task: Update the Recent Task memory based on the structured event you
just created.

Today's date: {today}

Review the structured event, especially the "Artifacts" and "Predicted Next Tasks"
sections. Reflect what was completed, what is now in progress, and what is coming next.

───────────────────────────────────────────────────────────────
WHAT TO TRACK
───────────────────────────────────────────────────────────────

  Completed Tasks      Tasks that are done as of this session. Include a brief
                       statement of the key outcome.

  Tasks in Progress    Tasks that were started but not finished. Include the
                       current status and the immediate next step.

  Upcoming Tasks       Tasks that are planned or highly likely to follow.
                       Source these from the structured event's "Predicted Next
                       Tasks" section and any explicit mentions in the session.

───────────────────────────────────────────────────────────────
QUALITY RULES
───────────────────────────────────────────────────────────────

  - Each task: one concise line — minimal but sufficient
  - Sort within each section in reverse chronological order
  - Retain only tasks from the last 7 days (since {today}); remove older entries
  - Keep total file length under {max_token} tokens; remove low-value or outdated entries
  - Promote tasks from "Upcoming" to "In Progress" or "Completed" as status changes
  - Remove tasks that are no longer relevant

───────────────────────────────────────────────────────────────
FILE STRUCTURE (maintain this layout)
───────────────────────────────────────────────────────────────

  # Recent Tasks

  ## Completed Tasks
  - [{today}] <task description> — <key outcome>

  ## Tasks in Progress
  - [{today}] <task description> — current status: <status>; next: <step>

  ## Upcoming Tasks
  - <task description>

───────────────────────────────────────────────────────────────
STEPS
───────────────────────────────────────────────────────────────

1. Read existing content:
     edit_file command="view" path="{recent_task_file}"

2. Update statuses, add new tasks, mark completed ones

If no task status changes are warranted, reply:
"No recent task update needed."
"""
