# Bundled teardown sources

This directory vendors the interactive JavaScript/CSS sources from
[elvarofficial/teardown](https://github.com/elvarofficial/teardown), including the
kit derived from [whaleyxbt/claude-motion](https://github.com/whaleyxbt/claude-motion).
The upstream MIT license and both copyright notices are preserved in `LICENSE`.

`sources.json.gz` is a deterministic gzip archive of a JSON object with `version`
and `files` fields. Each file key is its path relative to the generated project's
`src/` directory. Source contents are unchanged; the bundled `GUIDE.md` adapts the
instructions to Chrome ACP's existing build, inline presentation and Share tools.

`manifest.json` pins the compressed archive and every original source file by
SHA-256. The loader verifies the archive before extracting sources into a private,
editable UI project. This is a fixed source resource, not an installation cache.
Normal builds and startup never fetch upstream resources or scan user skill folders.

Included source families:

- `kit/`: scene/runtime helpers, shader warmup, HUD, director and styles.
- `v8-shared/`: engine geometry, kinematics, studio and live/console references.
- `cessna-shared/`: landing-gear geometry, flight state, studio and live references.
- `strandbeest-shared/`: linkage solver, geometry, studio and live references.

Film recording executables, audio generators and recorded samples are outside
the interactive HTML toolkit. The model can use the included machine source
modules in custom pages through the same `browser_ui_build` tool.

To inspect a source snapshot without executing its code:

```bash
gzip -dc sources.json.gz | python -m json.tool
```