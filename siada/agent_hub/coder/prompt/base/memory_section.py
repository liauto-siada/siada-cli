from pathlib import Path


def get_memory_section() -> str:
    """
    Return the memory section for the system prompt.

    Uses progressive disclosure: a unified usage hint appears at the top, followed
    by each memory category with a brief description and file list.

    Returns:
        str: Memory section text, or empty string if no memory files exist.
    """
    memory_dir = Path.home() / ".siada-cli" / "workspace" / "memory"
    sections = []

    # --- User habits (personal style) ---
    personal_style_file = memory_dir / "personal_style.md"
    if personal_style_file.exists():
        sections.append(f"""\
### USER'S RECENT WORK HABITS

Personal work style, preferences, and communication habits.

- {personal_style_file}""")

    # --- Experience files ---
    experience_dir = memory_dir / "experience"
    if experience_dir.is_dir():
        experience_files = sorted(experience_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]
        if experience_files:
            file_list = "\n".join(f"- {p}" for p in experience_files)
            sections.append(f"""\
### LONG-TERM EXPERIENCE

Reusable knowledge from past sessions: engineering rules, test conventions, architecture facts, design patterns, etc.

{file_list}""")

    # --- Recent structured events ---
    events_dir = memory_dir / "events"
    if events_dir.is_dir():
        event_files = sorted(events_dir.glob("*.md"), reverse=True)[:10]
        if event_files:
            file_list = "\n".join(f"- {p}" for p in event_files)
            sections.append(f"""\
### RECENT SESSION EVENTS

Structured summaries of the 10 most recent work sessions, newest first. Each captures
background, implementation decisions, artifacts produced, and predicted next tasks.

{file_list}""")

    if not sections:
        return ""

    body = "\n\n".join(sections)
    return f"""\
====
Memory

{body}

### Memory Usage Instructions
- **Memory Discovery**: The list above shows the user memories that may be used in the current session (personal style, experience, session event history). Memory files are located at the paths indicated in the list.
- **Memory Trigger**: If the user explicitly requests to retrieve memories, or the task content clearly matches a memory name listed above, read the corresponding memory content.
- **How to Use Memories**:
  1. Do not load all memories; only read memory files relevant to the current task.
  2. After reading, if the memory content is indeed related to the current task, use it as auxiliary information to complete the task.
  3. If the memory content clearly conflicts with the user’s current instruction, follow the user’s instruction as the authoritative source.

===="""
