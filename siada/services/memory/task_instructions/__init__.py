"""
Memory task instructions.

Each module defines one task instruction (prompt) for a specific memory type.
The system prompt is defined in system_prompt.py.

Memory generation order:
  1. structured_event  - must run first; output feeds all subsequent tasks
  2. experience        - extract reusable knowledge from event context
  3. personal_style    - update user style profile from event context
  4. recent_task       - update task tracking from event context

To add a new memory type:
  1. Create a new file <type>.py with a INSTRUCTION template string
  2. Add it to the task list in memory_agent._build_task_list()
"""
