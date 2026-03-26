---
name: long-horizon-task-design
description: Generate a technical design document for a complex task before execution. Load this Skill when the agent has judged the task to be complex (multi-module changes, significant information gaps, or ambiguous requirements). Do not load it for simple tasks.
metadata:
  short-description: Generate technical design document for complex tasks
---

# Long-Horizon Task Design Document Generation

This Skill guides you through producing a technical design document that fully specifies a complex task, obtaining user confirmation, and then handing off to the execution phase.

Work through the steps below in order. Do not skip any step.

> **Language rule**: The generated design document must be written in the **same language as the user's instruction**. If the user wrote in Chinese, the document (including all section headings, content, and step titles) must be in Chinese. If in English, in English. The structure and field names defined in the template are guides — translate them to match the user's language when generating.

---

## Step 1 — Collect Context

Before writing anything, read the codebase:

- Read all source files, existing design docs, READMEs, and configuration relevant to the task
- Understand the current architecture, data flow, and module boundaries
- Identify the full impact scope of the requested changes

Do not ask the user anything at this stage.

---

## Step 2 — Identify Information Gaps and Ask (If Necessary)

After reading, decide whether you have enough information to write a correct design.

**Only ask when all of the following are true:**
1. The information **cannot be inferred** from the codebase or existing documents
2. Without it, the design would be **materially wrong**, not just slightly different

**How to ask:**
- Batch every necessary question into **one single message** — never drip single questions across multiple turns
- For each question, state **why you need it**: _"I need to know X because without it I cannot determine Y"_

**Never ask about:**
- Naming conventions, code style, log levels, or any detail you can reasonably assume
- Anything already answerable by reading the codebase

If you have no blocking gaps, skip directly to Step 3.

---

## Step 3 — Generate the Design Document

Read the template at `design-doc-template.md` (same directory as this file) for the required structure and field descriptions.

Save the generated document to: `design_docs/<task-slug>.md`

- `task-slug` is derived from the task title in lowercase hyphen format (e.g., `add-user-auth`, `refactor-cache-layer`)
- Create the `design_docs/` directory if it does not exist

### Document structure requirements

The document must include a **table of contents** immediately after the title. The TOC must reflect the actual headings in the document: top-level sections (`##`) as first-level list items, and `###` sub-headings (e.g., Technical Design sub-sections, each Implementation Step) as indented second-level items. See `design-doc-template.md` for the format.

The document must contain exactly three top-level sections:

1. **Requirements Summary and Goals** — background, functionality, and goal
2. **Technical Design** — module breakdown, interface design, data flow, and key decisions with rationale. Omit a sub-section only if it is genuinely not applicable.
3. **Implementation Steps** — the detailed execution plan for the technical design

### Step format requirements

Each implementation step must satisfy all of the following:

- **Scope**: bounded to what a **single sub-agent can execute independently** — one module, one file group, or one clearly delimited concern. Do not bundle unrelated changes into one step.
- **Granularity**: steps must be roughly uniform in scope and effort. No single step should be disproportionately complex compared to the others — if a step is too heavy, split it; if a step is trivially small, merge it with a closely related one.
- **Complexity**: each individual step must contain **no more than five change points** (a change point is any distinct file edit, configuration update, or code addition the executor must make). If a step exceeds this limit, split it into smaller steps.
- **Status tag**: every step starts as `[ ] Not started`; completed steps are marked `[x] Done`.
- **Acceptance criterion**: how to verify the step is done correctly — a test case, a command to run, or a concrete checklist. Vague criteria like "works correctly" are not acceptable.

---

## Step 4 — Self-Check

After generating the document, run all three checks below. **Fix any failure before proceeding.** After fixing, re-run all three checks.

| Check | Pass Criteria |
|-------|---------------|
| **No contradictions** | Every section describes the same concept/behaviour consistently. No section contradicts another. |
| **No critical gaps** | The implementation steps fully cover the technical design. No piece of the design is left without a corresponding step. |
| **No unresolved items** | The document contains no open items: no "TBD", "TODO", "to be confirmed", "待定", "需确认", or any other placeholder. |

---

## Step 5 — Present Summary and Wait for Confirmation

Show the user a **summary only** — do not paste the full document. Use this format:

```
Design document ready.

Goal: <one sentence>

Technical approach: <2–3 sentences covering the key design decisions>

Implementation steps:
1. <step 1 title>
2. <step 2 title>
... (N steps total)

Full document: design_docs/<task-slug>.md

Please confirm to proceed, or tell me what to change.
```

Wait for the user's response:

- **User confirms** → inform the user that execution will now begin and proceed to load the `long-horizon-task-execute` Skill with the design document path as input
- **User requests changes** → edit the document per feedback, re-run Step 4 self-check, then show the summary again (Step 5)
