# Coding System Prompt Layout

`code_gen_prompt.py` is the coding agent's stable entry point. It selects one
profile and collects runtime facts. Default and GPT-5 profiles keep the
historical section builder. GPT-6 uses `assembly/codex.py`: a complete per-model
template first, followed by capabilities, runtime instructions, environment,
language, the skills catalog, available agents, and memory. The old GPT-6 intro
and rule helpers remain available for compatibility imports but are not used
by the main GPT-6 prompt path.

Kimi K3 and later use `assembly/kimi.py` and a Kimi Code-based Markdown template in
`models/kimi_k3/templates/system.md`. Its communication, tool use, coding,
risk, delivery, context management, environment, and project information
sections follow Kimi Code's template. Runtime facts and the available tools
are adapted to Siada; the existing `edit_file` tool remains in use.

GLM-5.2 and later use `assembly/glm.py` and the ZCode-based Markdown template
in `models/glm/templates/system.md`. GLM and Kimi share the one-pass renderer
in `assembly/markdown_template.py`, while keeping their own template content.
Siada supplies the runtime facts, tool capabilities, safety rules, catalogs,
and framed memory. See the repository's `NOTICE` and `docs/CREDITS.md` for
upstream attribution and adaptation details.

| Directory | Responsibility |
| --- | --- |
| `selection/` | Model-name feature predicates, prompt-family selection, and skill usage profiles. File-tool support is separate from prompt family. |
| `models/default/`, `models/gpt5/`, `models/gpt6/`, `models/glm/`, `models/kimi_k3/` | Family-specific content. GPT-6's `templates/composition.toml` defines a common section order, defaults and model overrides; Kimi K3 and later use one template with explicit runtime substitutions. |
| `sections/` | Shared capabilities, objectives, language, memory framing, and mode guidance. `sections/rules/` owns shared rules and family dispatch. |
| `assembly/` | Render preselected sections into the final string; no model-name classification on the main path. |
| `base/` | Thin imports for older callers; do not put new prompt content here. The deprecated `memory_section.py` is an empty compatibility stub. |

Keep existing sections byte-identical during structural refactors: the
`tests/agent_hub/coder/test_prompt_byte_compatibility.py` SHA-256 matrix and
synthetic `.snap` files protect the final prompt, whitespace included. New
model families belong in `models/` plus the `selection/` and rule dispatch
tables, not in `base/`.

GPT-6 templates and their Codex provenance/adaptations are documented in
[`models/gpt6/templates/README.md`](models/gpt6/templates/README.md). GPT-6.1 Sol,
GPT-6 Sol, and GPT-6 Luna retain their individual upstream wording; Astra,
its shorthand alias, and unrecognized GPT-6 variants use the Astra template.
The skills catalog is appended without a second skills usage block.
The four former GPT-6 Markdown skeletons are replaced by one composition with
explicit differences. No model prose, section order or whitespace is normalized.
Shared-section and model-setting audits prevent duplicated prose and unused or
redundant configuration from accumulating again.

Interactive question tools are not part of the coding agent's tool surface.
GPT-6 templates omit their question-tool guidance; the remaining per-model
instructions retain their existing wording.

Kimi detection compares the numeric major version and selects `KIMI_K3` for
K3 and later, including `kimi-k3.1`, `kimi-k3.5`, `kimi-k4`, and future versions.
Names are case-insensitive and accept provider-qualified forms, underscore
separators, and preview suffixes. Short names such as `k3`, `k3.1`, `k3.5`,
`k4`, and `openai/k4` also select this template. Kimi K2 and older keep the
default profile; partial names and conflicting numbered GPT names do not
select the Kimi template. The Kimi prompt replaces
the generic four-line response limit and strict skill usage block with Kimi
Code's terminal communication and relevant-skill guidance. It retains Siada's
Git safety, hook handling, non-interactive approval blockers, skills path aliases,
subagent switch, and framed combined memory. Dynamic values are substituted
once and are never interpreted as template syntax.
