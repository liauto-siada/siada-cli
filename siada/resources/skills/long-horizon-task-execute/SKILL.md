---
name: long-horizon-task-execute
description: Execute a complex task step-by-step using the confirmed design document. Load this Skill after the user has confirmed the design document produced by the long-horizon-task-design Skill. Input is the design document path.
metadata:
  short-description: Execute complex task step-by-step per design document
---

# Long-Horizon Task Execution

This Skill drives the step-by-step execution of a complex task whose design document has been confirmed by the user. You receive the design document path as input. Work through the steps below in order.

---

## Step 1 — Read the Design Document and Extract Steps

Read the full design document at the provided path. Locate the "Implementation Steps" section and extract every step with its current status.

Step status is indicated by the prefix on the **Status** field:

| Prefix | Meaning |
|--------|---------|
| `[ ]`  | Not started |
| `[x]`  | Done |

---

## Step 2 — Display the Execution Plan

Before executing anything, show the user the full step list in this format:

```
## Execution Plan

[ ] Step 1: <title>
[ ] Step 2: <title>
[x] Step 3: <title>  (done)
...

Progress: <N done> / <total> completed
```

Map each step's current status prefix to the display above. Do not wait for user confirmation — begin executing immediately after displaying.

**Resuming an interrupted task**: if some steps are already marked `[x]`, display the current state and explain which step you are resuming from.

---

## Step 3 — Execute Steps in a Loop

Repeat the following cycle for each step that is not yet done (`[ ]`), in document order:

### 3.1 Decide execution mode

Assess whether this step is complex enough to run in a sub-agent:

- **Use `run_subtask`** if the step involves significant exploration, cross-module changes, or multiple interdependent edits that benefit from an isolated context window.
- **Execute directly** if the step is straightforward — e.g., a single-file edit, a configuration change, or a simple addition with no unknowns.

No hard threshold applies; use your judgment. State your decision in one line before proceeding.

### 3.2 Direct execution path

If you chose to execute directly, complete the step yourself using available tools. When done, proceed to 3.5.

### 3.3 run_subtask path — pre-execution research

Before assembling the instruction, read the source files and design document sections relevant to this step. Produce a brief research summary covering

### 3.4 run_subtask path — assemble and call

Use this template to build the `instruction` argument:

```
Context:
- Working directory: <absolute path of the current working directory>
- Design document: <absolute path to the design document>

Research summary:
<findings from 3.3: key patterns, interfaces, dependencies, constraints>

Previous step result:
<the structured summary written back from the most recently completed step>
(If this is the first step, write: "N/A — this is the first step.")

Your task:
Implement step <N>: <step title>
```

Call `run_subtask` with this instruction string.

### 3.5 Handle the result

Treat the outcome as either **success** or **failure**:

**Success** (direct execution completed, or `run_subtask` returned `status == "completed"`)
1. In the design document, change the step's Status prefix from `[ ]` to `[x]`
2. Append a structured "Result" sub-field on the step entry: list files changed and key decisions made
3. Save the document
4. Display the updated Execution Plan (same format as Step 2)
5. Continue to the next not-started step

**Failure** (direct execution failed, or `run_subtask` returned `"failed"` or `"blocked"`)
1. The step status in the document remains `[ ]` — do not modify it
2. Report to the user: the step title, what went wrong, and (if from `run_subtask`) the `blockers` content
3. Ask the user for instructions
4. Wait for the user's response before proceeding

---

## Step 4 — Finish

When all steps are marked `[x]`, output a completion summary to the user:

```
Task complete.

Steps executed: <N>
<brief summary of what was accomplished overall>
```
