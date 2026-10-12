# Codex GPT-6 templates adapted for Siada

These files are modified versions of OpenAI Codex's Apache-2.0 model templates
from `codex-rs/models-manager/models.json`, field
`model_messages.instructions_template`. Source checkout commit:
`2fdf047c9631c9ed01a31b62efb7891718a931a8` (2026-10-08); models catalog commit:
`d63a9b8344cfe58bc78bbe319b560378fc8756ef` (2026-10-06).

OpenAI Codex, Copyright 2025 OpenAI. The Apache-2.0 license and attribution
are reproduced in the repository's `docs/CREDITS.md` and packaged with Siada.

Each model renders its own complete template from a common composition, shared
literal sections, and explicit model differences. Preserve section order, paragraphs,
PR-description guidance where present, and per-model differences when syncing.
GPT-6.1 Sol's apology guidance and Luna's permission/test defaults are not
collapsed into Astra's template. Siada runtime instructions separately clarify
actual capabilities and explicit user/repository verification requirements.

## Composition and model differences

`composition.toml` replaces the four former `gpt-*.md` skeletons. Its
`composition.sections` list defines the section order once. Settings are merged
in this order: `defaults`, the model's optional `group`, then the model itself.
There are no recursive profile inheritance chains. All parsing and expansion use
Python's standard library; no template engine or new dependency is used.

| Profile | Differences from the common defaults |
| --- | --- |
| GPT-6 Astra | None; uses the common defaults directly. |
| GPT-6 Sol | Uses the `scannable` group, its own testing/completion rule and correction guidance, and its original extra blank line before skills. |
| GPT-6 Luna | Uses the `scannable` group, the shorter initial permission paragraph, and testing only on user request. |
| GPT-6.1 Sol | Adds its contrastive-writing wording and apology paragraph. |

The `scannable` group moves personality before permissions, changes writing
style, omits technical/PR communication, and selects its distinct authorization,
progress-update and skill-pause wording. The other profiles retain
personality after autonomy and keep the technical/PR guidance.

`shared/` owns the common section bodies: identity, personality structure,
permissions, autonomy, user collaboration and compaction, progress updates,
final-answer formatting/visualizations, tool rules, and skills. Alternative
writing styles, message authorization, test policies and skill-pause explanations
are shared named sections. Common complete sentences within differing paragraphs,
such as change reporting and precise wording, are also stored only once.

### Literal directives

- `{{include:section-name}}` inserts a shared section. A `fragments` setting can
  redirect a named slot to another section, or use `""` to omit it. Sections may
  include other sections inline or on a separate line; reference cycles fail
  with the complete reference chain.
- `{{value:setting_name}}` inserts a literal string from the merged `values`.
  These values hold actual wording/whitespace differences. They are not templates
  and are never expanded a second time.

Section names are lowercase letters/digits with hyphens, without paths or
extensions. Value names also allow underscores. Missing sections, groups or
values, malformed directives, and non-text values fail explicitly.

Parents own whitespace between included fragments. The loader removes exactly
one final newline from each shared file and otherwise preserves its bytes. The
composition joins nonempty top-level sections with two newlines and appends its
explicit suffix. Only the complete rendered template is stripped, matching the
original loader. Sol's extra blank line and all other original whitespace remain
intentional parts of the construction.

Edit common Markdown only when the change is intended for every profile that
uses it. Put genuine differences in `composition.toml` or a distinct shared
variant; do not copy whole model templates. Structural changes preserve the
rendered bytes; removing question-tool guidance is an intentional content change.

`tests/agent_hub/coder/test_gpt6_templates.py` freezes the adapted template hashes and
checks override precedence, directive failures, complete-prose duplication,
unused sections/settings and redundant overrides. The duplication boundary is
complete natural paragraphs, list rules and sentences, not arbitrary common
words or phrases. Further merging the genuinely different wording would alter
model policy or require fragmenting clauses. The full-system-prompt hash matrix
and readable snapshots track intentional content changes.

## Modifications to the upstream templates

- Identity: Codex becomes Siada.
- Communication: Codex's commentary/final channel wording becomes ordinary
  progress updates and a final response, matching Siada's message transport.
- Tools: question-tool guidance and standalone async message-tool references
  are omitted because Siada does not expose those tools. Command
  guidance uses `run_cmd`; Promise-based `functions.exec` batching becomes
  parallel tool calls where available.
- Environment: `$CODEX_HOME` becomes `$SIADA_HOME`.
- Skills: retain filesystem paths and short aliases; remove references to
  orchestrator/environment-owned skill providers and unavailable
  `skills.list`/`skills.read` tools. Siada appends its existing skills catalog
  without its old duplicate how-to block.
- Capabilities: omit the complete Apps (Connectors) and Plugins sections,
  whose tool namespaces/catalog protocols are not implemented in Siada.
  Remove unavailable automatic approval-review rejection mechanics.
- Formatting: strip trailing whitespace; do not summarize or shorten other
  corresponding sections.
