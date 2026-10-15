# 日志关联与轮转

日志包含 `pid`、`sessionId`、`requestId`、`agent` 和 `agentRunId`；
UI 和代理还包含进程的 `instanceId`。`sessionId` 是真实会话 ID，
`requestId` 标识一次用户请求，通过 ACP 元数据传递。
`agentRunId` 标识一次 SDK agent 执行，可以区分同名 agent 的并行运行。
子 agent 和后台 agent 保留来源请求，使用自己的名称和执行 ID。
启动阶段或没有关联会话的工作使用 `-`。

按 `requestId` 筛选，可以关联 UI、传输、主 agent、memory agent、
验证 agent 和子 agent；按 `agentRunId` 筛选，可以查看单次 agent 执行。
这些字段只用于诊断，不改变 JSON-RPC 请求 ID，也不会进入模型输入。

| 日志 | 默认位置 | 轮转规则 |
| --- | --- | --- |
| CLI | `~/.siada-cli/logs/siada_cli.log` | macOS/Linux：午夜或 10 MiB，保留 30 个备份；Windows：10 MiB，保留 30 个备份 |
| UI | `~/.siada-cli/logs/ui/siada-ui.log` | 10 MiB，最多 30 个备份，删除超过 7 天的备份 |
| Chrome ACP 代理，INFO 和 DEBUG | `~/.siada-cli/logs/proxy/acp-proxy-<时间>-<pid>-<uuid>.log` | 10 MiB，每进程 30 个备份；清理超过 7 天的文件，保护存活进程的日志 |
| 代理启动诊断 | `~/.siada-cli/logs/proxy/acp-proxy-launch.log` | 每次启动检查：10 MiB，3 个备份 |

CLI 使用跨进程文件锁协调轮转，并在其他进程轮转后重新打开当前文件。
UI 每次追加都打开当前路径，备份名称保证唯一，清理时保留活动日志。
代理各进程使用不同的文件路径。大小是轮转阈值，单条日志可能使文件超过阈值。
UI 轮转没有跨进程锁；多个 UI 同时写入时，可能超过大小阈值或在同时轮转时
产生额外备份。唯一备份路径避免不同进程覆盖彼此的备份。

`SIADA_CLI_LOG_DIR` 统一覆盖日志根目录，包括 `ui/` 和 `proxy/` 子目录；
`SIADA_UI_LOG_DIR` 和 `SIADA_PROXY_LOG_DIR` 单独覆盖组件目录。启动器会把实际
解析到的根目录传给子进程，包括 CLI 使用可写目录回退的情况。

默认记录 INFO 及更高等级。代理 `--debug` 增加 DEBUG 日志。
`SIADA_DEBUG=true`、`1` 或 `yes` 开启 CLI 与 UI 的 DEBUG 日志；
`false`、`0`、`no` 不会开启，UI 的 `--log-level debug` 也可开启。
Siada 托管启动的代理，在 logger 初始化后将 stdout/stderr 送入轮转日志；
连接 banner 和二维码只在前台启动时展示。启动诊断文件记录初始化前的错误。
已运行的进程在重启后使用新路径，已有归档保留。

逐次按键诊断、逐片 ACP 解析、会话更新、生命周期增量、token/cache 状态、子 agent 内容、
stdin 写入及轨迹转发改为 DEBUG。开始、完成、状态变化、告警和错误保留
INFO 或更高等级。开启 DEBUG 后，流式输出仍会产生较多日志。
未完整到达的 JSON 缓冲诊断、清屏事件和缓存状态也只在 DEBUG 打印。
持续高内存告警每个 UI 实例最多每 5 分钟打印一次，内存仍每 30 秒检查；
内容增量缺少消息对象的重复诊断最多每分钟打印一次。
后端 stderr 由适配器统一记录，UI 事件监听器不再重复写入同一条告警。
轮转失败的诊断每个 handler 每分钟最多向 stderr 输出一次，
避免重试刷屏或污染 ACP stdout。

定时记忆分析从导出的 Markdown 头部读取来源会话 ID，并生成新的请求 ID。
旧导出缺少该头部时，会话 ID 为 `-`。自定义集成如果直接调用 agents SDK，
没有经过 Siada 的日志 runner，需要自行设置日志上下文。