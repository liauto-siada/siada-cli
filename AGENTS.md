# AGENTS.md

## Scope

This file guides coding agents working on Siada CLI. It applies throughout this
repository. Follow any more specific `AGENTS.md` in the directory being changed,
subject to higher-priority instructions and the user's requested scope.

Use only public project sources when preparing contributions. Do not read, copy,
summarize, or link private source trees or local-only operational instructions
into public code, tests, or documentation.

## Project overview

Siada CLI is a command-line AI assistant for software development, debugging,
and automation. The project has two main parts:

- A Python backend for agent orchestration, tools, model providers, and services.
- A TypeScript terminal UI built with React and `@jrichman/ink`, with Agent Client
  Protocol (ACP) support for communication with the backend.

Treat the dependency manifests, executable entry points, and nearby tests as the
source of truth when older documentation differs from the implementation.

## Repository layout

In the paths and shell commands below, `REPO_ROOT` is the absolute path to this
checkout. Set it from any directory inside the repository:

```bash
export REPO_ROOT="$(git rev-parse --show-toplevel)"
```

| Path | Responsibility |
| --- | --- |
| `${REPO_ROOT}/siada/entrypoint/` | CLI arguments, startup, and UI launcher |
| `${REPO_ROOT}/siada/acp_server/` | Standalone ACP agent and protocol handling |
| `${REPO_ROOT}/siada/agent_hub/` | Agents, prompts, hooks, and context handling |
| `${REPO_ROOT}/siada/tools/` | Tools exposed to agents |
| `${REPO_ROOT}/siada/services/` | Application services and shared workflows |
| `${REPO_ROOT}/siada/provider/` | Model-provider integrations |
| `${REPO_ROOT}/siada/config/` | Configuration handling |
| `${REPO_ROOT}/siada/models/` | Shared data models |
| `${REPO_ROOT}/siada/foundation/` | Shared runtime utilities and logging |
| `${REPO_ROOT}/siada/resources/skills/` | Bundled skill resources |
| `${REPO_ROOT}/siada_cli_ui/src/` | Terminal UI, hooks, and ACP client code |
| `${REPO_ROOT}/tests/` | Python tests, generally mirroring backend modules |
| `${REPO_ROOT}/docs/` | Public user and contributor documentation |
| `${REPO_ROOT}/chrome-acp/` | chrome-acp browser addon subproject (proxy server + Chrome extension) |

Read `${REPO_ROOT}/README.md` and `${REPO_ROOT}/docs/CONTRIBUTING.md` for project
and contribution guidance. Dependency and command definitions live in
`${REPO_ROOT}/pyproject.toml` and `${REPO_ROOT}/siada_cli_ui/package.json`.

## Environment and setup

- Use Python `>=3.12,<3.14`, as required by the Python manifest.
- Use Poetry to install dependencies and run Python commands. Do not rely on a
  globally installed Python package or CLI to validate checkout changes.
- For UI development, use npm and a maintained Node.js LTS release satisfying the
  locked dependencies. Some current UI dependencies require Node.js `>=20`, even
  though the UI package itself declares `>=18`.
- Keep `${REPO_ROOT}/poetry.lock` and
  `${REPO_ROOT}/siada_cli_ui/package-lock.json` consistent with intentional
  dependency changes. Avoid unrelated upgrades or switching package managers.

Install Python dependencies, including the development group:

```bash
poetry -C "$REPO_ROOT" install --with dev
```

Install UI dependencies when working on the terminal UI:

```bash
npm --prefix "$REPO_ROOT/siada_cli_ui" ci
```

Do not publish packages, run deployment scripts, or change global tooling as part
of ordinary development or validation.

## Running and building

Launch the application from the Poetry environment:

```bash
poetry -C "$REPO_ROOT" run siada-cli
```

The standalone ACP entry point is available for client integration work:

```bash
poetry -C "$REPO_ROOT" run siada-acp
```

These commands start application processes; they are not automated smoke tests.
Model-backed operations need user-provided configuration and may access external
services. Never assume credentials are available.

After UI source changes, compile TypeScript and regenerate the UI bundle before
checking the application through the standard launcher:

```bash
npm --prefix "$REPO_ROOT/siada_cli_ui" run build:all
```

The normal launcher prefers `${REPO_ROOT}/siada_cli_ui/bundle/siada-ui.js` over
compiled or source entry points. A stale bundle can therefore hide UI changes.
Edit source files, not generated JavaScript. Review generated changes separately
and include them only when required by the task or packaging workflow.

## Implementation conventions

- Inspect the relevant module, its callers, and nearby tests before editing.
  Make a short plan for nontrivial work and keep changes focused on the request.
- Preserve existing user changes. Do not revert unrelated work, perform broad
  refactors, or reformat whole files merely to adjust a small behavior.
- Follow surrounding naming, imports, error handling, and module organization.
  Prefer existing helpers and dependencies over parallel abstractions.
- Python: use four-space indentation, descriptive `snake_case` functions and
  variables, `PascalCase` classes, and type annotations for new interfaces.
- TypeScript/React: follow nearby components and hooks. Preserve ESM conventions,
  including `.js` extensions in relative imports where already used. Use
  `@jrichman/ink` rather than introducing a different Ink package.
- Write new comments and docstrings in English. Explain intent and non-obvious
  constraints instead of narrating the code.
- Keep agent behavior, tool execution, service logic, and UI presentation in their
  existing layers. Do not put backend business logic into UI components.
- Preserve async cancellation, subprocess cleanup, and resource ownership. Avoid
  blocking work in async paths and do not silently swallow errors.
- When changing ACP messages or shared configuration, check both Python and
  TypeScript consumers and add coverage for compatibility and error cases.
- Keep ACP stdout reserved for protocol traffic. Use the existing logging
  facilities for diagnostics instead of adding arbitrary prints to transports.
- Do not add a formatter, linter, framework, or dependency unless the task needs
  it. Report unavailable or misconfigured checks rather than silently skipping
  them or inventing a new project-wide toolchain.

## Testing and validation

Start with the smallest relevant test selection. For example, the ACP stdio tests
can be run without launching the interactive application:

```bash
poetry -C "$REPO_ROOT" run python -m pytest "$REPO_ROOT/tests/acp_server/test_stdio.py" -q
```

For a broader Python selection, after reviewing the test prerequisites:

```bash
poetry -C "$REPO_ROOT" run python -m pytest "$REPO_ROOT/tests" -m "not integration" -q
```

The integration marker is a selection aid, not a guarantee of offline execution.
Inspect the selected tests before running them. Do not run live model calls,
external-service tests, or costly benchmarks without explicit authorization.

For UI changes, run tests in non-watch mode and check TypeScript without emitting
build artifacts:

```bash
npm --prefix "$REPO_ROOT/siada_cli_ui" test -- --run
npm --prefix "$REPO_ROOT/siada_cli_ui" run build -- --noEmit
```

- Put Python tests under `${REPO_ROOT}/tests/`, following the module layout where
  practical. Use `test_*.py` files and `test_*` function names. The project uses
  pytest and pytest-asyncio; follow nearby fixture and async-test patterns.
- Add UI tests alongside related tests under
  `${REPO_ROOT}/siada_cli_ui/src/` or `${REPO_ROOT}/siada_cli_ui/tests/`, using the
  existing Vitest conventions and `*.test.ts` or `*.test.tsx` naming.
- Add regression coverage for bug fixes. Test observable behavior, failure paths,
  and relevant boundary cases rather than only implementation details.
- Keep unit tests deterministic. Mock model APIs, network services, and subprocess
  boundaries; use temporary directories instead of real user state.
- Distinguish new failures from pre-existing failures. Report exact commands and
  results, including missing dependencies or environment limitations. Do not
  claim a check passed if it was not run.

## Security and open-source boundaries

- Public changes must not depend on private packages, unpublished services,
  company-specific deployment procedures, or access to private repositories.
- Never commit credentials, tokens, cookies, private keys, proprietary hostnames,
  personal data, or machine-specific absolute paths.
- Use synthetic fixtures and sanitized examples. Do not copy real conversations,
  runtime logs, authentication state, or production data into tests or docs.
- Do not inspect or expose local secrets just to make tests pass. Use mocks or
  report the missing configuration instead.
- Preserve permission checks and user-consent boundaries around file writes,
  shell execution, browser automation, and external integrations.
- Respect `${REPO_ROOT}/.gitignore`. Do not include caches, dependency directories,
  local environment files, logs, or unrelated build output in a contribution.
- Preserve existing license and attribution notices. Follow the contribution
  requirements in `${REPO_ROOT}/docs/CONTRIBUTING.md`.

## Completion checklist

Before handing off a change:

1. Review the diff for correctness, scope, accidental data exposure, and generated
   files. Check whitespace with `git -C "$REPO_ROOT" diff --check`.
2. Run the relevant tests and build checks, or clearly document why they could
   not run. For documentation-only changes, verify paths, commands, and examples.
3. Update relevant public documentation when changing user-visible behavior.
   Keep existing English and Chinese documentation consistent where affected.
4. Check dependency manifests and lockfiles if dependencies changed. Do not
   modify versions or licensing as an unrelated cleanup.
5. Summarize the changes, validation performed, and any remaining limitations.
