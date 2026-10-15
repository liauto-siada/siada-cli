# Log correlation and rotation

Log records include `pid`, `sessionId`, `requestId`, `agent`, and `agentRunId`.
UI and proxy logs also include a process `instanceId`. `sessionId` is the
conversation's real identifier; `requestId` identifies a user turn and is
forwarded through ACP metadata. `agentRunId` identifies one SDK agent invocation,
so parallel runs of the same agent can be distinguished. Nested and background
agents retain their source request and use their own names and run identifiers.
Startup events and work without an associated conversation use `-`.

Filter by `requestId` to follow a turn through the UI, transport, main agent,
memory agents, verifier, and sub-agents. Filter by `agentRunId` to isolate an
individual agent execution. These identifiers are diagnostic metadata and do
not change JSON-RPC request IDs or model inputs.

| Log | Default location | Rotation |
| --- | --- | --- |
| CLI | `~/.siada-cli/logs/siada_cli.log` | macOS/Linux: midnight or 10 MiB, 30 backups; Windows: 10 MiB, 30 backups |
| UI | `~/.siada-cli/ui-logs/siada-ui.log` | 10 MiB, at most 30 backups, backups older than 7 days removed |
| Chrome ACP proxy, debug mode | Configured log directory, otherwise `.acp-proxy/` in the proxy's working directory | A unique file per process, 10 MiB, 30 backups per process; files older than 7 days removed |

CLI rotation uses process-shared locks and reopens the current file after another
writer rotates it. UI writers open the current path for each append and give
backups unique names. UI cleanup preserves the active log. Proxy processes have
separate file paths. Size limits are rollover thresholds: a single record can
make a file exceed the threshold.
UI rotation does not use a cross-process lock, so multiple UI writers can exceed
the size threshold or create extra backups around a simultaneous rollover.
Unique backup paths prevent processes from overwriting each other's archives.

Set `SIADA_CLI_LOG_DIR` to override the CLI directory or `SIADA_UI_LOG_DIR` to
override the UI directory. The proxy continues to log INFO to stdout in normal
mode; file logging is enabled by its debug option. `SIADA_DEBUG=true`, `1`, or
`yes` enables CLI and UI DEBUG logs; `false` does not enable DEBUG.

Per-key input diagnostics, per-chunk ACP parsing, session updates, lifecycle deltas, token/cache status,
sub-agent content, stdin writes, and trajectory forwarding are DEBUG events.
Start, completion, state changes, warnings, and errors remain visible at INFO
or above. DEBUG mode still produces many records during streaming.
Rotation failures are reported to stderr at most once per minute per handler,
so retries do not flood diagnostics or corrupt ACP stdout.

Periodic memory analysis reads the source session identifier from the exported
Markdown header and gives the analysis a new request identifier. When an old
export lacks that header, its session identifier is `-`. Custom integrations
that invoke the agents SDK directly without Siada's logging runner need to
provide their own log scope.