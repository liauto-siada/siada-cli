"""
Task instruction: Generate a Structured Event.

This is always the first task in the memory pipeline. Its output is stored in
events/ and used as the primary source for all subsequent memory tasks.
"""
max_token = 2048
INSTRUCTION = f"""\
Your current task: Generate a Structured Event from the session conversation above.

A Structured Event is a high-density semantic summary of one session. It serves as the
authoritative source for all higher-level memories (experience, personal style, recent
tasks). Accuracy and completeness here directly determines the quality of everything
downstream.

───────────────────────────────────────────────────────────────
STEP 0: VALUE ASSESSMENT — Should this session be saved?
───────────────────────────────────────────────────────────────

Not all sessions are worth saving. Before generating a structured event, evaluate
whether this session contains valuable information worth preserving.

SAVE if the session includes any of:
  ✓ Technical implementation or code changes
  ✓ Design decisions with reasoning
  ✓ Problem-solving with concrete solutions
  ✓ Configuration or architectural changes
  ✓ Debugging insights or root cause analysis
  ✓ Reusable patterns or lessons learned
  ✓ Specific technical questions with definitive answers

SKIP if the session is primarily:
  ✗ Simple greetings or small talk without technical content
  ✗ Vague or exploratory discussions without conclusions
  ✗ Questions that were left unanswered or unresolved
  ✗ Pure clarification requests without implementation
  ✗ Meta-conversations about how to use the system
  ✗ Conversations where the user decided not to proceed

If you determine this session should be SKIPPED:
  1. Output exactly: "SKIP_EVENT: <brief reason>"
  2. Stop — do not generate the 7 sections below

If the session has value, proceed to generate the full structured event.

───────────────────────────────────────────────────────────────
OUTPUT FORMAT — 7 required sections
───────────────────────────────────────────────────────────────

## Background
What problem this session was solving. What triggered it. The technical state before
the session began.

## Implementation Summary
The key steps taken and decisions made. For each significant decision, explain:
  - WHAT was decided
  - WHY this option was chosen over the alternatives
  - What trade-offs were accepted
Do not just describe what happened — capture the reasoning behind it.

## Artifacts
Concrete outputs produced by this session:
  - New files created (with paths)
  - Existing files modified (with paths and a brief description of changes)
  - Design documents, configuration changes, schema changes, etc.

## Predicted Next Tasks
Based on the artifacts produced and items left unresolved, list the most likely
follow-up tasks in order of probability. Be specific — name modules, files, or
features where possible.

## Repository Info
  - Repository name
  - Working directory path
  - Key files changed

## Key Insights & Notes
OPEN FIELD. Capture anything valuable that does not fit the sections above:
  - Failed attempts and their root causes (why they didn't work)
  - Unexpected discoveries or surprising findings
  - Reusable patterns or lessons that emerged
  - Technical debt or fragility observed
  - Anything that, if forgotten, would cause future confusion or repeated mistakes

## Source Session Path
The path to the original session file that is the source of this content.
Format: session/YYYY-MM-DD-HH-MM-slug.md (relative to the memory directory)

───────────────────────────────────────────────────────────────
WHAT NOT TO RECORD
───────────────────────────────────────────────────────────────

Omit anything that can be trivially reconstructed by reading the codebase or git history:
  - File/directory structure and module layout (visible via ls / tree)
  - Code patterns, class hierarchies, function signatures (readable from source)
  - Commit-level change details (covered by git log / git diff)
  - Architecture that is fully expressed in the code itself with no hidden rationale

Record the WHY and CONTEXT that code alone cannot reveal — decisions, trade-offs,
constraints, and reasoning that would be lost if only the diff were preserved.

───────────────────────────────────────────────────────────────
FILE NAMING
───────────────────────────────────────────────────────────────

  events/YYYY-MM-DD-HH-MM-<slug>.md

  The slug must be self-describing enough to act as an index entry — someone
  scanning a directory listing should immediately know what this session was about.

  Slug rules:
  - Lowercase, hyphen-separated
  - Include the repository or project name when the work is project-specific
  - Include the module, feature, or component name
  - Include the action verb or change type (refactor, add, fix, redesign, migrate…)
  - 3–6 words; lean toward more words over vague brevity

  Good examples:
    siada-memory-agent-prompt-refactor
    siada-agenthub-circular-import-fix
    siada-experience-file-naming-redesign
    myproject-auth-service-jwt-migration

  Bad examples (too vague — avoid):
    memory-update
    fix-bug
    refactor

───────────────────────────────────────────────────────────────
STEPS
───────────────────────────────────────────────────────────────
1. Evaluate session value (STEP 0 above). If SKIP, output "SKIP_EVENT: <reason>" and stop.
2. Check the events/ directory.
3. Decide whether to update an existing event file or create a new one.
   - **Prioritize updating existing event files.** Highly relevant events may be merged into a single one, and this practice is strongly encouraged. The current event file may be renamed if necessary. This is to prevent excessive fragmentation of information caused by the overly rapid proliferation of event files.
4. Compose the structured event covering all 7 sections
   - The session file content has already been provided above — do not re-read it
   - Keep the file under {max_token} tokens; trim low-value details if needed

───────────────────────────────────────────────────────────────
EXISTING EVENT FILES
───────────────────────────────────────────────────────────────

{{events_file_list}}
"""
