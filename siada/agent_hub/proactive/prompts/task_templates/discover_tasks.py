"""
Task Discovery Instruction Template

This instruction is sent by the scheduler to ask ProactiveAgent
to discover pending tasks from recent work history.
"""

from datetime import datetime, timezone
from pathlib import Path


def get_discover_tasks_instruction() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    home = Path.home()
    events_dir = home / ".siada-cli" / "workspace" / "memory" / "events"
    task_dir = home / ".siada-cli" / "workspace" / "task"
    task_file = task_dir / f"tasks_{today}.json"
    return f"""# Task: Discover Pending Tasks

Discover actionable tasks from recent work history that may need attention.

Today's date: {today}

## Steps

1. Check `{events_dir}` for event files from today (filenames starting with `{today}`). If none exist, stop here — do nothing.
2. Read all of today's event files; extract tasks from the `predicted next tasks` field.
3. Determine the base task list:
   - If `{task_file}` exists, read it as the base.
   - Otherwise, look for the most recent file in `{task_dir}` and read it as the base (treat as empty if no file exists).
4. Merge (starting from the base task list):
   - Remove all `completed` and `cancelled` tasks.
   - Keep `in_progress` tasks unchanged (preserve their `id`).
   - For `pending` tasks: if a newly discovered task matches by title, update its description/confidence but preserve the `id`; otherwise keep as-is.
   - Append genuinely new tasks with a fresh UUID in the `id` field (use Python's `uuid.uuid4()` or generate a unique identifier).
5. Write the result to `{task_file}` using `edit`.

## Task File Schema

```json
{{
  "version": "1.0",
  "last_updated": "<ISO 8601 timestamp>",
  "tasks": [
    {{
      "id": "<uuid, preserve if task already existed>",
      "title": "Brief task name",
      "description": "Context and detail",
      "priority": "high | medium | low",
      "status": "pending | in_progress | completed | cancelled",
      "needs_confirmation": true,
      "source_memories": ["{events_dir}/{today}-10-00-slug.md"],
      "created_at": "<ISO 8601 timestamp>",
      "updated_at": "<ISO 8601 timestamp>"
    }}
  ]
}}
```

**needs_confirmation**: `true` for architectural decisions, unclear scope, or risky changes; `false` for clear TODOs and straightforward fixes

After writing, provide a brief summary of discovered and merged tasks.
"""
