def get_long_horizon_section() -> str:
    """
    Return the long-horizon task handling section for the CodeGenAgent system prompt.

    Covers:
    - Complexity judgment rules (design doc 3.3)
    - Skill loading triggers
    - run_subtask tool usage constraint
    """
    return """## Complex Task Handling

### Complexity Judgment

Immediately after receiving a task — before doing anything else — assess whether the task is **complex**. No user approval is needed for this judgment.

Mark as COMPLEX if:
    - Task is not fully specified
    - Any ambiguity exists
    - Requires multiple steps(normally > 50 steps) to complete
    - Involves debugging, design, or integration

If the task is complex, load the `using-superpowers` Skill Firstly.

If the task is straightforward, proceed normally without mentioning this judgment at all.

### Skill Loading Triggers

| Situation | Action |
|-----------|--------|
| Task judged as complex | Load `using-superpowers` Skill and follow its workflow |
| User explicitly requests superpowers | Load `using-superpowers` Skill immediately |"""
