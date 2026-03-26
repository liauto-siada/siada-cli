"""
Daily Summary Instruction Template

This instruction is sent by the scheduler to ask ProactiveAgent
to generate a summary of the most recent work day's activities.
"""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path


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


def get_daily_summary_instruction() -> str:
    today = datetime.now(timezone.utc).date()
    home = Path.home()
    events_dir = home / ".siada-cli" / "workspace" / "memory" / "events"
    session_dir = home / ".siada-cli" / "workspace" / "memory" / "session"

    work_date = _find_last_work_date(events_dir, today)
    work_date_str = work_date.strftime("%Y-%m-%d")
    summary_file = home / ".siada-cli" / "workspace" / "memory" / "summary" / f"{work_date_str}_summary.md"
    return f"""# Task: Generate Daily Work Summary

Analyze the most recent work day's structured events and session history to create a comprehensive daily summary.

Work date: {work_date_str}

## Data Sources

1. **Structured Events** (primary): `{events_dir}` directory
   - **Scope**: Event files for {work_date_str} only (filter by date prefix `{work_date_str}`)
   - **Advantage**: Already distilled — contains background, implementation summary, deliverables, predicted next tasks, repository info, and key insights fields; much higher information density than raw sessions
2. **Raw Sessions** (fallback): `{session_dir}` directory
   - **Scope**: Session files for {work_date_str} that do NOT have a corresponding event file
   - **Note**: Only read session files when no structured event exists for that session. There may be multiple session files. To avoid context overflow, read and summarize them one by one incrementally.

## Your Objectives

1. **Identify Work Day Activities**
   - What features were worked on
   - What bugs were fixed
   - What discussions took place
   - What decisions were made
   - What problems were encountered
   - Which code repository do these tasks belong to, and what is the working directory.

2. **Highlight Key Accomplishments**
   - Completed features or tasks
   - Resolved issues
   - Important milestones reached
   - User satisfaction (if explicitly mentioned or can be inferred from context)

3. **Note Pending Items**
   - Work started but not finished (use `predicted next tasks` field from events as the authoritative source)
   - Issues discovered but not resolved
   - Questions raised but not answered


## Execution Steps

1. List event files for {work_date_str} from `{events_dir}` directory (filenames starting with `{work_date_str}`)
2. **Sort by time**: Sort event files by timestamp in chronological order (oldest first)
3. **Read and summarize incrementally**: Process each event file one by one; extract all structured fields
4. List session files for {work_date_str} from `{session_dir}`; skip any session that already has a corresponding event (matched by date-time prefix)
5. For remaining sessions without events, read and extract key facts incrementally
6. Aggregate all findings into final daily summary
7. Save the summary to `{summary_file}`

## Output Format

Generate a markdown file with the following structure:

```markdown
# Daily Work Summary - {work_date_str}

## Session Summaries

### Session: [session-filename-1]
**Facts:**
- [Key facts from this session]

**Tasks:**
- [Task name] - Status: [completed/in-progress/blocked] - User Satisfaction: [satisfied/neutral/unsatisfied/unknown]

**Notes:**
- [Other relevant observations]

---

### Session: [session-filename-2]
**Facts:**
- [Key facts from this session]

**Tasks:**
- [Task name] - Status: [completed/in-progress/blocked] - User Satisfaction: [satisfied/neutral/unsatisfied/unknown]

**Notes:**
- [Other relevant observations]

---

## Overall Summary

### Accomplishments
- [Aggregated completed work items with session sources]

### In Progress
- [Aggregated ongoing work items with session sources]

### Discussions & Decisions
- [Key discussions and decisions with session sources]

### Challenges & Blockers
- [Issues or blockers encountered with session sources]

### Next Steps
- [Planned follow-up actions]

## Statistics
- Total sessions: [N]
- Completed tasks: [N]
- In-progress tasks: [N]
- Blocked tasks: [N]
```

## Important Notes

- **Each summary item must cite its source** (event or session filename)
- **Prefer events over sessions**: Structured events are already distilled — always use them as the primary source; fall back to raw sessions only when no event exists
- **For task-related content**: Always include completion status; use `predicted next tasks` from events as the authoritative next-step source
- **User satisfaction**: Include if explicitly mentioned or can be reasonably inferred from user feedback in the session
- **Time-ordered processing**: Always process files in chronological order (oldest first) based on filename timestamp
- **Incremental processing**: Don't load all files at once - process them sequentially to manage context length
- **Save location**: `{summary_file}`

After generating the summary, save it to the specified location and inform the user.
"""
