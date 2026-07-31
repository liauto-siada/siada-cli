---
name: writing-plans
description: Use when you have a spec or requirements for a multi-step task, before touching code
---

# Writing Plans

A neutral plan-writing tool. Its job: read a spec document, investigate the codebase, and produce a complete, bite-sized implementation plan.

This skill does not make design decisions, does not run code, and does not call other skills. The caller provides the spec and the output path.

<LANGUAGE-RULE>
The plan document MUST use the same language as the spec it is based on.
- Chinese spec → write the entire plan in Chinese (section headers, step descriptions, commit messages).
- English spec → write the entire plan in English.
- Code, file paths, shell commands, and identifiers remain in their natural form regardless of language.
- Do NOT switch languages mid-document.
</LANGUAGE-RULE>

## How This Skill Works

**Step 1 — Read the spec**

Read the spec document in full before writing anything. Understand the goal, architecture decisions, interfaces, and constraints.

**Step 2 — Codebase Investigation**

Before writing any plan task, investigate the code files the plan will touch:

1. Open and read every source file listed in the spec as "will be created or modified"
2. Verify that interface signatures, types, and method names in the spec match what actually exists in the codebase
3. Map out which files will be created or modified and what each is responsible for

**Investigation rules:**
- Design units with clear boundaries. Each file should have one clear responsibility.
- In existing codebases, follow established patterns. If a file you're modifying is unwieldy, a split can be included in the plan.
- Files that change together should live together — split by responsibility, not by technical layer.

Do not write any plan task based on assumptions about the code. Verify first.

If the spec covers multiple independent subsystems, check whether it should be broken into separate plans — one per subsystem. Each plan should produce working, testable software on its own.

If multiple spec files must be investigated independently, call `use_subagents` in parallel — one per spec. Aggregate before writing.

**Step 3 — Write the Plan (incrementally)**

Write the plan document to the path provided by the caller. Create the file with the header, then write one task at a time.

**Step 4 — Self-Review**

After writing all tasks, run this checklist:

1. **Spec coverage** — skim each section in the spec. Can you point to a task that implements it? Add any missing tasks.
2. **Placeholder scan** — search for any of the "No Placeholders" patterns below. Fix them all.
3. **Type consistency** — do method signatures and property names in later tasks match what was defined in earlier tasks?

Fix issues inline. Once clean, the plan is complete — return the file path to the caller.

## Plan Document Header

Every plan MUST start with this header:

```markdown
# [Feature Name] Implementation Plan

**Goal:** [One sentence describing what this builds]

**Spec:** [Path to the spec document this plan is based on]

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

---
```

## Task and Step Granularity

**Each Task** = one independently deliverable unit of work.

**Each Step** = one single action, completable in 1–5 minutes.

Forbidden step descriptions — these are plan failures:
- "Implement X" — too coarse. Break it: write test → run failing → write implementation → run passing.
- "Add error handling" — name the specific error condition and show the exact code.
- "Similar to Task N" — always repeat the full content. Tasks may be read out of order.
- "Handle edge cases" — name the specific case and show the code.
- "Write tests for the above" — without the actual test code.
- "TBD", "TODO", "fill in details"

Every step that involves code MUST include a complete code block.
Every step that runs a command MUST include the exact command and the expected output.
Every task MUST include explicit Acceptance Criteria.

## Task Structure

````markdown
### Task N: [Component Name]

**Status:** `[ ]` not started / `[x]` complete
*(Executor: update this field after the task's Acceptance Criteria all pass)*

**Goal:** [One sentence — what this task delivers and why it matters]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`
- Test: `tests/exact/path/to/test.py`

**Acceptance Criteria:**
- [ ] [Specific, verifiable condition — e.g.: `pytest tests/xxx.py` all pass]
- [ ] [Specific, verifiable condition — e.g.: calling `f(x)` returns `y` for input `z`]
- [ ] [Specific, verifiable condition — e.g.: no new lint errors introduced]

---

- [ ] **Step 1: Write the failing test**

[One sentence: what behavior this test verifies]

```python
def test_specific_behavior():
    result = function(input)
    assert result == expected
```

Run: `pytest tests/path/test.py::test_specific_behavior -v`
Expected: FAIL with "NameError" or similar — if it passes, the test is wrong. Stop and fix.

---

- [ ] **Step 2: Write minimal implementation**

[One sentence: what this code does]

```python
def function(input):
    return expected
```

---

- [ ] **Step 3: Run tests to confirm passing**

```bash
pytest tests/path/test.py::test_specific_behavior -v
```

Expected output: `PASSED`

````

## No Placeholders

Every step must contain the actual content an engineer needs. These are **plan failures**:
- "TBD", "TODO", "implement later", "fill in details"
- "Add appropriate error handling" / "add validation" / "handle edge cases" — name the specific case
- "Write tests for the above" — without the actual test code
- "Similar to Task N" — repeat the code; tasks may be read out of order
- Steps that describe what to do without showing how — code blocks required for code steps
- References to types, functions, or methods not defined anywhere in the plan

## Remember

- Exact file paths always
- Complete code in every step — if a step changes code, show the full changed code
- Exact commands with expected output
- DRY, YAGNI, TDD
