---
name: brainstorming
description: "You MUST use this before any creative work or research work - creating features, building components, adding functionality, or modifying behavior. Explores user intent, requirements and design before implementation."
---

# Brainstorming

A neutral research and clarification tool. Its job: investigate the codebase deeply, resolve ambiguities with the user through dialogue, form a design, and write it to a document.

This skill does not make execution decisions, does not call other skills, and does not write code. The caller determines what document type to produce (index or spec) and where to save it.

<HARD-GATE>
Do not write any design document until codebase investigation is complete and all ambiguities are resolved. The document must reflect confirmed understanding, not assumptions.
</HARD-GATE>

<LANGUAGE-RULE>
Detect the language of the task description at the start.
- Chinese task → ALL outputs in Chinese (questions, design content, document text).
- English task → ALL outputs in English.
- Mixed → use the dominant language.
Language is locked for the entire session.
</LANGUAGE-RULE>

<CLARIFICATION-GATE>
Ask ONE clarifying question per message. Do NOT move to design until every ambiguity is resolved.
If a requirement can be interpreted two ways, ask — never assume.
</CLARIFICATION-GATE>

## How This Skill Works

**Step 1 — Codebase Investigation** (see protocol below, MANDATORY)

**Step 2 — Clarifying Questions**

Ask questions one at a time. Focus on: purpose, constraints, success criteria, scope boundaries.

- Before asking detailed questions, assess scope. If the task spans multiple independent subsystems, flag this first — help decompose before going deeper into any one piece.
- Prefer multiple-choice questions when possible. Open-ended is fine when the space is genuinely open.
- One question per message. If a topic needs multiple questions, break them across messages.

**Step 3 — Propose 2-3 Approaches**

Present options with trade-offs and your recommendation. Lead with the recommended option and explain why.

**Step 4 — Present the Design**

Once the design is clear, present it in sections scaled to complexity. Ask for approval after each section. Cover: architecture, components, data flow, error handling, testability.

Design for isolation and clarity:
- Each unit has one clear purpose and communicates through well-defined interfaces.
- Someone should be able to understand what a unit does without reading its internals.
- In existing codebases, follow established patterns. Fix problems that affect the work; don't refactor unrelated code.

**Step 5 — Write the Output Document**

Write the document to the path specified by the caller. Write incrementally: create the file with a header, then append one section at a time. Commit after the document is complete.

**Step 6 — Document Self-Review**

Before asking the user to review, check the document yourself:
1. **Placeholder scan** — any "TBD", "TODO", vague requirements? Fix them.
2. **Internal consistency** — do sections contradict each other?
3. **Scope check** — is this focused enough, or does it need decomposition?
4. **Ambiguity check** — can any requirement be interpreted two ways? Pick one and make it explicit.

**Step 7 — User Approves**

Present the document path and ask the user to review. Wait for explicit approval. Apply any requested changes and re-run self-review. Once approved, this skill is complete — return to the caller.

## Codebase Investigation Protocol

<HARD-GATE>
This protocol runs before any design decision. "I roughly understand it" is not sufficient.
</HARD-GATE>

**Step 1 — Map the structure**
- List top-level directories and their purpose
- Identify modules relevant to this task
- Read `README`, `ARCHITECTURE`, or equivalent docs if present

**Step 2 — Read relevant files in depth**
- Open and read every file that will be touched or depended on — do not stop at file names
- For each: understand its current responsibility, public interface, and dependencies
- Read the corresponding test files to understand expected behavior and existing coverage

**Step 3 — Identify patterns and conventions**
- Naming conventions, code style, error handling patterns
- Base classes, mixins, utilities that new code should extend or reuse

**Step 4 — Check recent history**
- Review recent commits on relevant files (if git is available)
- Note any in-progress work or TODOs that affect design choices

**Step 5 — Confirm answers to these before continuing:**
1. Which existing files will this task create, modify, or depend on?
2. What reusable patterns or utilities already exist?
3. What is the current test coverage? Where are the gaps?
4. Are there technical constraints or risks from the existing code?

**Parallel investigation:** If the task spans independent modules, call `use_subagents` — one sub-agent per module — to investigate in parallel. Aggregate summaries before continuing.

## Key Principles

- **One question at a time** — do not overwhelm
- **Multiple choice preferred** — easier to answer than open-ended
- **YAGNI ruthlessly** — remove unnecessary scope from all designs
- **Explore alternatives** — always propose 2-3 approaches
- **Incremental validation** — present design section by section, get approval before moving on
