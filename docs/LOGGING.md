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
| UI | `~/.siada-cli/logs/ui/siada-ui.log` | 10 MiB, at most 30 backups, backups older than 7 days removed |
| Chrome ACP proxy, INFO and DEBUG | `~/.siada-cli/logs/proxy/acp-proxy-<time>-<pid>-<uuid>.log` | 10 MiB, 30 backups per process; files older than 7 days removed, live process logs protected |
| Proxy bootstrap diagnostics | `~/.siada-cli/logs/proxy/acp-proxy-launch.log` | Checked on each launch: 10 MiB, 3 backups |

CLI rotation uses process-shared locks and reopens the current file after another
writer rotates it. UI writers open the current path for each append and give
backups unique names. UI cleanup preserves the active log. Proxy processes have
separate file paths. Size limits are rollover thresholds: a single record can
make a file exceed the threshold.
UI rotation does not use a cross-process lock, so multiple UI writers can exceed
the size threshold or create extra backups around a simultaneous rollover.
Unique backup paths prevent processes from overwriting each other's archives.

`SIADA_CLI_LOG_DIR` relocates the shared root, including its `ui/` and `proxy/`
subdirectories. `SIADA_UI_LOG_DIR` and `SIADA_PROXY_LOG_DIR` override individual
component directories. Launchers pass the resolved root to child processes,
including when the CLI falls back to another writable directory.

Normal mode writes INFO and higher levels. The proxy's `--debug` option adds
DEBUG records. `SIADA_DEBUG=true`, `1`, or `yes` enables CLI and UI DEBUG logs;
`false`, `0`, and `no` do not enable DEBUG. UI `--log-level debug` also works.
When managed by Siada, proxy stdout/stderr after logger initialization use the
rotating runtime log. Connection banners and QR codes are shown on foreground
launches. The bootstrap file captures failures before initialization.
Existing processes retain their old paths until restarted; existing archives
are preserved.

Per-key input diagnostics, per-chunk ACP parsing, session updates, lifecycle deltas, token/cache status,
sub-agent content, stdin writes, partial JSON buffering, screen-clear traces,
cache status, and trajectory forwarding are DEBUG events.
Start, completion, state changes, warnings, and errors remain visible at INFO
or above. DEBUG mode still produces many records during streaming.
Persistent high-memory warnings are limited to one every five minutes per UI
instance; memory checks still run every 30 seconds. Repeated missing-message
content diagnostics are limited to one per minute.
Backend stderr is recorded by the adapter; UI event listeners do not duplicate it.
Rotation failures are reported to stderr at most once per minute per handler,
so retries do not flood diagnostics or corrupt ACP stdout.

Periodic memory analysis reads the source session identifier from the exported
Markdown header and gives the analysis a new request identifier. When an old
export lacks that header, its session identifier is `-`. Custom integrations
that invoke the agents SDK directly without Siada's logging runner need to
provide their own log scope.

Each `run_subtask` execution writes its transcript and accounting to
`~/.siada-cli/data/tmp/<project-hash>/sessions/<root-session-id>/subagents/<agent-id>.log`.
This includes normal, named, forked, background and recursive sub-agents with
an active root session, even when SDK tracing or recursion is disabled.
Each completed model request records its sequence number, effective model,
input/output/cache-read/cache-write/total tokens, estimated cost in CNY, and
`Duration` in seconds. Token counts follow Siada's normalized provider usage.
Request duration covers the model call, including transport retries and backoff;
tool execution between requests is excluded. Continuation requests after an
empty reasoning-only response are recorded separately.
`SDK Reported Requests` preserves the request count returned by the SDK, which
can include multiple retry attempts in one model call. Explicit cache-write
tokens take precedence when positive; otherwise the existing inference applies.

The final `SUB-AGENT USAGE SUMMARY` includes cumulative tokens, known cost,
summed model request duration, and elapsed sub-agent duration (including tools).
Missing usage, unconfigured pricing and interrupted requests report unavailable
cost, with a count in the summary. Costs use the existing model pricing settings
and are estimates, not provider invoices. Failed transport attempts without
returned usage cannot be included in the estimated cost.
Files retain full dates in timestamps and stay at the same path across midnight.
The shared daily subtask trace remains
available; existing log files are not backfilled.