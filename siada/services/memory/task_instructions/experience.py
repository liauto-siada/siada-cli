"""
Task instruction: Extract Experience memories.

Runs after the structured_event task. Reads the structured event from the
conversation history (no need to re-read from disk) and extracts reusable
knowledge into categorised files under experience/.
"""

max_token = 2048
INSTRUCTION = f"""\
Your current task: Extract Experience memories from the structured event you just created.

Review the structured event — especially the "Key Insights & Notes" section and the WHY
reasoning in "Implementation Summary". Apply a strict reusability filter before writing
anything.

───────────────────────────────────────────────────────────────
THE REUSABILITY FILTER — apply this first
───────────────────────────────────────────────────────────────

Ask: "Will a future session on a DIFFERENT task in this project benefit from this?"

HIGH reusability → worth recording:
  - Rules that apply every time you work on this project (test rules, build steps,
    coding conventions, review checklist, deployment procedure)
  - Stable facts about the project that are not obvious from reading the code
    (module ownership, API contracts, configuration conventions, known constraints)
  - Cross-project patterns that apply broadly (framework usage rules,
    language-level conventions the team has adopted)

LOW reusability → do NOT record:
  - A specific bug that was fixed (the fix is in the code; recording it here adds
    no future value)
  - A one-time circular import that was resolved
  - A gotcha specific to one library version that is unlikely to recur
  - Step-by-step notes about what happened in this session (that belongs in events/)
  - Anything that would only apply if the exact same incident happened again

The higher the reusability, the better the experience.
When in doubt, do not record — a lean experience store is more valuable than a noisy one.

───────────────────────────────────────────────────────────────
WHAT QUALIFIES
───────────────────────────────────────────────────────────────

Anything that passes the reusability filter above. Typical high-value examples:

  Test rules          How to write tests in this project: which fixtures to use,
                      what must always be covered, what not to mock, file layout,
                      naming conventions, how to run the suite.

  Build & compile     How to build, lint, type-check, package, or release.
                      Commands, flags, required environment.

  Development norms   Coding style decisions, PR conventions, branch strategy,
                      commit message format, review expectations.

  Architecture facts  Module responsibilities, dependency rules, extension points,
                      where to add new features, what not to touch.

  API & config rules  How to configure the project, required env vars, schema
                      conventions, interface contracts between components.

These are examples, not an exhaustive list. Any knowledge that a future session
on a different task would genuinely benefit from is worth recording.

───────────────────────────────────────────────────────────────
WHAT NOT TO RECORD
───────────────────────────────────────────────────────────────

Skip anything that can be reconstructed from the codebase or git history without loss:
  - File/directory structure and module layout (visible via ls / tree)
  - Code patterns, class hierarchies, and function signatures (readable from source)
  - Architecture that is fully expressed in the code with no hidden rationale
  - Change history details already captured in git commits

These belong in the code, not in memory. Record only the knowledge that would be
invisible to someone reading the source — constraints, conventions, rationale, and
rules that exist only in people's heads.

───────────────────────────────────────────────────────────────
FILE NAMING — the filename is the index
───────────────────────────────────────────────────────────────

Formula:  <project-or-scope>-<specific-topic>.md

Rules:
  - Prefix with the project/repository name for project-specific knowledge
  - The topic must name what the file teaches, not just a category label
  - Lowercase hyphens only; 3–6 words total

  Good:
    siada-agenthub-test-rules.md         how to write tests in this repo
    siada-agenthub-dev-conventions.md    coding and PR norms for this repo
    siada-memory-agent-architecture.md   module layout and extension points
    myproject-build-and-release.md       how to build and ship

  Bad (category labels, not topics — avoid):
    engineering.md
    tests.md
    debugging.md
    workflows.md

  If a generic name already exists, rename it when merging: create the specific
  file, copy relevant content, delete the old file with delete_memory_file.

───────────────────────────────────────────────────────────────
QUALITY RULES
───────────────────────────────────────────────────────────────

  Macro and concise
  - If reusability is low, skip it — do not create a file
  - State each insight as an architectural or workflow-level rule, NOT an
    implementation detail or session narrative
  - One crisp, actionable sentence beats three explanatory lines
  - If you find yourself writing step-by-step notes about what happened,
    stop — that belongs in events/, not here
  - Abstract upward: capture the "what and why" as a standing principle,
    not the specific circumstance that surfaced it

  Internally consistent — no contradictions
  - Before writing, re-read the entire target file
  - Identify every existing statement that contradicts the new knowledge
  - Remove or rewrite each conflicting entry so the file is coherent end-to-end
  - The file must read as a single unified source of truth after every update;
    contradictory rules anywhere in the file are worse than no rules at all

───────────────────────────────────────────────────────────────
STEPS
───────────────────────────────────────────────────────────────
1. Determine if there is experience to accumulate.
   Most sessions produce no reusable experience — this is the normal and expected outcome.
   If nothing passes the filter, stop here and reply:
   "No experience to extract from this session."
2. Check the experience/ directory.
3. Decide whether to update an existing file or create a new one:
   - File exists — merge:
       a. Read the full file.
       b. Scan for statements that contradict the new knowledge; remove or rewrite them.
       c. Integrate the new knowledge; keep the file under {max_token} tokens,
          trimming low-value details if needed.
   - File does not exist — create it.

One session may produce experience across multiple files — repeat steps 2–3 for each.

───────────────────────────────────────────────────────────────
EXISTING EXPERIENCE FILES
───────────────────────────────────────────────────────────────

{{experience_file_list}}
"""
