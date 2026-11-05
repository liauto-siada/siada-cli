# 会话测试基准

[English](../SESSION_TEST_BASELINE.md)

这是一套基于当前实现、供会话／上下文重构使用的**行为测试基准**，由真实 SDK
Runner 行为测试和明确审查过的现有离线回归测试组成。基准本身不修改业务代码、不依赖模型
凭据，也不将这套会话基准宣称为整个仓库的完整测试覆盖。
以下原始快照是历史记录；最新实现状态见“默认执行入口切换验收”。

## 运行方式

使用 Python `>=3.12,<3.14` 和 Poetry 开发环境：

```bash
export REPO_ROOT="$(git rev-parse --show-toplevel)"
poetry -C "$REPO_ROOT" install --with dev

# 新增行为测试与已审查的现有回归测试。
poetry -C "$REPO_ROOT" run python "$REPO_ROOT/tests/run_session_baseline.py"

# 只运行新增测试；只列出完整选择，不执行。
poetry -C "$REPO_ROOT" run python "$REPO_ROOT/tests/run_session_baseline.py" --scope new
poetry -C "$REPO_ROOT" run python "$REPO_ROOT/tests/run_session_baseline.py" --list

# 额外参数传递给 pytest；报告保存在仓库之外。
poetry -C "$REPO_ROOT" run python "$REPO_ROOT/tests/run_session_baseline.py" \
  --junitxml=/tmp/siada-session-baseline.xml --durations=10

# 检查已知缺陷的实际失败断言；缺陷尚存时，此命令预期返回非零。
poetry -C "$REPO_ROOT" run python "$REPO_ROOT/tests/run_session_baseline.py" --scope new --runxfail
```

入口根据自身位置解析绝对测试路径，可从任意工作目录运行。默认 `--scope full`
表示完整的**会话基准选择**，不是仓库所有测试。明确的选择清单保存在
`tests/run_session_baseline.py`，不会随其他目录新增测试而悄悄扩大范围。

额外参数直接传给 pytest，不需要 `--` 分隔符：不同 Poetry 版本可能会提前解释或
移除该分隔符。

入口在导入业务模块前创建临时 `HOME`、日志和缓存目录，关闭远程模型配置拉取，
并使用 LiteLLM 内置的模型费用映射（`LITELLM_LOCAL_MODEL_COST_MAP=True`）。
pytest 插件在收集和执行阶段阻止 socket 连接；即使业务异常处理吞掉网络错误，也会
使运行失败。新增夹具使用临时会话／检查点／offload 文件、合成模型配置和响应，
关闭 tracing，并模拟 Git、UI、memory 外部边界。这里是 Python 进程内的约束，
不是限制任意子进程的操作系统沙箱。

### 模拟子 agent 压缩

完整选择包含 `test_run_subtask_compaction_simulation.py`：使用合成工具输出和预设模型服务
响应，运行真实的子任务入口、`SubTaskAgent`、流式 SDK Runner、tokenizer 和
header-summary 压缩策略。除两个单次压缩场景外，48 场景矩阵每次执行 24 轮串行或
12 轮并行工具调用，组合普通／fork 历史、三种输出规模和首次摘要成功／空响应／普通
异常／`CompactionError`。
每次模型请求检查 session 基线、最新完整工具组，以及已摘要输入和工具消息不被恢复。
另覆盖精确 token 阈值、12 次新任务的相同输入、摘要／模型调用期间取消、多次压缩后
模型失败重试、最大轮数耗尽及函数工具／原生 patch 的保留预算／历史末尾边界。两个
同时压缩的子任务另验证独立 session、重叠摘要调用及共享父上下文不变。入口模拟同时
检查调试快照和父上下文隔离。

最新工具组整体也可能超出保留预算。超大输出场景验证失败回退时历史完整，不保证下次
请求适合模型窗口；仍需限制或卸载这类输出。不评估真实模型的摘要质量。运行整个模拟
模块并显示报告：

```bash
poetry -C "$REPO_ROOT" run python "$REPO_ROOT/tests/run_session_baseline.py" \
  -k test_run_subtask_compaction_simulation -s
```

2026-10-13 完整重复运行五次，每次 88 个模拟用例全部通过。长链矩阵累计覆盖
240 个场景、4,560 轮模型调用、7,200 次工具调用、3,375 次成功压缩（每个场景
5–24 次）。这是确定性调度的重复验证，不是随机化模型服务测试。合并离线选择
（包含额外的子任务 fork／显示／守卫回归）通过 883 个用例，保留 3 个既有 legacy
xfail，没有意外网络连接尝试。

### 共享压缩修改的主流程验证

`test_shared_compaction_main_flow.py` 在临时 prepared 主会话中使用真实 tokenizer 和
压缩策略，仅替换模型服务响应及 UI／memory 外部边界。204 个用例覆盖自动／手动压缩、
流式／非流式 SDK、串行／并行工具、函数／原生 patch、chat／native 请求载荷、保留预算
裁剪、失败恢复及 IM 按轮裁剪策略。每次请求都与已提交的有效上下文对照，压缩删除的
工具消息不得恢复，完整历史不得因压缩改变；显式验证 assistant 开头的保留尾部，
而不是只从 user 开头的正常历史推断安全性。

共享配对修复方法默认仍要求 user 起始，只有 header-summary 的保留尾部裁剪关闭此
约束，因为组装时会在尾部之前加入 user 摘要。IM 摘要输入裁剪仍使用原默认契约。
与公开 Git 原实现的 36 组差分验证中，32 组结果不变；4 组最新工具组能放进预算且
尾部由 assistant 开头的场景，从裁剪报错变为保留完整最新工具组，属于预期修复。

2026-10-13，204 个主流程用例全部通过（35.27s）。合并受网络约束的离线选择
（包含额外的子任务 fork／显示／守卫回归）通过 1,087 个用例，恰好保留 3 个既有
legacy G01/G12/G14 xfail（60.76s），没有意外网络连接尝试。这是已审查的测试选择，
不是整个仓库的全部测试。

这没有解决所有超预算情况：user 开头的尾部可能删掉全部工具组，assistant 开头的
尾部则可能被裁空、导致压缩失败。入口在失败时保留原上下文，但它仍可能超过模型
窗口。这些确定性离线测试不评估真实摘要质量，也不保证所有 provider 消息排列。

```bash
poetry -C "$REPO_ROOT" run python "$REPO_ROOT/tests/run_session_baseline.py" \
  --scope new -k test_shared_compaction_main_flow
```

### 已验证快照

2026-10-12 基于父 revision `4cb28f42ae7556354126f3f1fc1396152e871b84` 和本轮尚未
提交的测试／文档新增进行验证。环境为 Python 3.12.2、pytest 8.4.2、
pytest-asyncio 1.3.0、openai-agents 0.22.3、openai 3.0.0、pydantic 2.13.5、
filelock 3.20.3。

| 选择 | 结果 | Pytest 耗时 | 退出码 |
| --- | --- | --- | --- |
| `--scope new` | 74 passed、19 xfailed | 1.42s | 0 |
| 默认完整选择 | 531 passed、19 xfailed | 2.81s | 0 |
| `--scope new --runxfail` | 74 passed、19 failed | 1.39s | 1（预期） |

选择包含一个新增目录和 34 个已审查的现有测试文件（457 个现有用例）。正常运行没有
出现受拦截的意外连接尝试。独立故障注入验证了收集阶段及严格 xfail 夹具中吞掉连接
错误仍返回退出码 1，也检查了导入时 home／日志路径与临时 HOME 清理。报告保留在
仓库之外；源码或依赖变更后应重新记录快照。

### 存储基础实现阶段

第一阶段为 FileSession 增加完整历史专用接口、版本化上下文接口、版本校验替换、
保守的显式旧格式迁移、共享 ownership／存储锁及可恢复的多文件事务。
**尚未切换默认模型读取入口**：`get_items()` 和现有请求链路仍沿用旧契约。
旧写入会使准备中的上下文失效，而不是留下可被误用的过期快照。
仅历史初始化需要明确批准；旧快照边界非法或新格式文件损坏时直接报错，不回退完整历史。

`test_versioned_storage.py` 新增 30 个离线用例，覆盖显式准备、空／仅摘要快照迁移、
未发送增量、身份／边界错误、不可变替换、版本冲突、路由保留、写入失败、
中断事务恢复（包含真实子进程异常退出）及非法事务日志。
持久化的真实遥测 hook 测试验证原始工具历史、注入项筛选、原计数口径，
以及替换不产生新增消息事件；没有验证完整压缩流程或真实外部上报。

G11、G15、G16、G17 的期望断言已通过，移除对应 xfail。
该阶段**仍有 15 个严格 xfail 用例**；最新清单见下文。
并发追加夹具改为在锁获取之前观察竞争，避免在新的共享锁内部人为制造双读取死锁。

旧多文件操作的事务目前保留完整文件撤销数据；仅运行期替换只记录上下文文件。
这会增加本地 I/O，尚未进行性能基准验证。在该历史阶段，默认入口切换、SDK 消息身份接入、
完整状态／resume／checkpoint 迁移及删除消息镜像仍是后续阶段，不属于当时已完成能力。

2026-10-12 在与原快照相同的 Poetry／依赖环境中验证，业务改动尚未提交：

| 选择 | 结果 | Pytest 耗时 | 退出码 |
| --- | --- | --- | --- |
| `--scope new` | 108 passed、15 xfailed | 2.70s | 0 |
| 默认完整选择 | 565 passed、15 xfailed | 4.78s | 0 |
| `--scope new --runxfail` | 108 passed、15 failed | 2.79s | 1（预期） |

这些结果包含原先审查的全部 457 个现有用例及新增目录的 123 个用例。
报告仍保存在仓库之外。
审计失败与 15 个严格 xfail 的用例身份完全一致，没有夹具错误。

### 显式请求桥接与已准备的消费路径

后续增量阶段提供用于显式准备会话的 `EffectiveContextSession`，通过持久化消息身份，
将 SDK 输入／结果及过滤后 hook 追加内容接入版本化上下文和完整原生历史。
压缩后重复的 SDK 保存不会复活已丢弃上下文。UI／ACP 回放和现有遥测明确读取完整历史；
上下文替换不产生新增消息事件。

已准备会话的 verifier、memory、侧问和 resume 使用版本化上下文，保留空和仅摘要视图；
损坏或失效时不回退历史。Resume 在修改活跃会话前校验存储身份，并跳过旧快照 tracking；
旧版仅状态恢复保持兼容。Checkpoint 等待 SDK 工具结果持久化后，在同一锁内捕获两个
持久化视图，不再在 `on_tool_end` 读取消息状态镜像。并行捕获使用不同文件名。

已准备会话的 checkpoint 恢复保留消息接入凭证，递增活跃恢复代际，拒绝旧 SDK 请求
迟到的保存，同时不阻断正常压缩。项目回滚快照可补偿普通的 Git 部分失败以及存储提交／
flush 失败；补偿失败会明确报错。这**不代表 Git 和会话存储之间具备崩溃原子性**。
并行工具捕获观察的是已完成的 SDK 批次，不是逐个工具的独立项目状态。

**在该历史阶段，默认激活仍然关闭。** 可变的 workspace 缓存消费方仍需协调 session 身份，涉及 goal
hooks、slash commands、会话中断、后台通知排出、遥测上下文查找和只读侧问分支。
完整 todo／goal／计数器／通知／usage 状态恢复、跨 Git／存储崩溃恢复以及删除旧镜像尚未
完成。15 个严格 xfail 仍描述旧请求链路；显式准备路径的测试不能作为直接移除它们的依据。

2026-10-12 在同一 Poetry 环境中验证，没有调用真实模型或出现受拦截的意外网络连接：

| 选择 | 结果 | Pytest 耗时 | 退出码 |
| --- | --- | --- | --- |
| 默认完整选择（最终复跑） | 653 passed、15 xfailed | 6.50s | 0 |
| 聚焦 effective／prepared 测试 | 78 passed、132 deselected、1 xfailed | 2.19s | 0 |
| 额外 verifier／侧问／memory 测试 | 40 passed、211 deselected | 0.47s | 0 |
| ControllerUI 测试 | 22 passed、211 deselected | 0.73s | 0 |
| `--scope new --runxfail` | 196 passed、15 failed | 4.91s | 1（预期） |

该阶段新增目录有 211 个用例。额外选择包含 `tests/services/goal/test_verifier.py`、
`tests/services/test_btw_deny_guardrail.py` 和 `tests/services/memory/memory_update/`
下的 `test_snapshot_view.py`／`test_updater.py`，不属于默认基准清单。
中间出现的 6 个旧版仅状态 resume 失败已修复，没有新增 xfail 或弱化已准备路径的校验断言。

最终报告审计确认 15 个普通断言失败与旧链路严格 xfail 的用例身份完全一致，没有夹具错误。
41 个修改／新增 Python 文件均可解析和编译；已检查跟踪及新增文件的空白、末尾换行、
中英文链接和缺口清单。依赖清单与锁文件未改动。
这些结果验证的是显式准备路径的阶段成果，不代表当时尚未完成的默认切换。

### 默认执行入口切换验收

默认流式／非流式 `SiadaAgent` 执行边界现已安装 `EffectiveContextSession`。
已准备的 `get_items()` 读取单数 `api_message.json`；SDK 输入、回复、工具结果和
过滤后追加内容通过事务接入有效上下文及完整原生 UI／遥测历史。每次请求读取权威上下文，
合法空／仅摘要视图不会回退；压缩不复活旧消息、不改写展示历史。保留自定义 RunConfig
设置，但拒绝自定义会话输入回调／读取设置，因为接入边界由桥接层统一拥有。

新空会话自动准备；已有仅历史会话仍需明确批准
`migrate_legacy_context(allow_history_only=True)`，有效旧快照可保守迁移。
损坏或无法对齐的数据直接报错，不从 UI 历史重建运行输入。
已准备会话拒绝旧快照／tracking 写入；迁移本身不会删除旧文件。

可变 context 缓存和查询绑定会话身份。版本化 `runtime_state.json` 单独保存 todos、
提醒计数、待提交／已投递通知、请求回执和实际响应用量，不与 token 预算混用。
Goal、ownership、子任务索引保持原有存储职责。Resume 支持合法空状态、恢复标题／
工作区，不重复投递已消费工作。Checkpoint 捕获工具结果持久化后的批次与结构化状态，
回滚保留真实 usage／投递回执，并隔离旧运行的迟到保存。
临时真实 Git 测试验证了项目恢复前、中、后及提交前 worker 异常退出后的日志补偿；
补偿失败保留日志供重试。这是可恢复补偿，不是 Git 与会话文件同时可见或断电验证；
并行工具仍共享已完成批次边界。

2026-10-12 在相同父 revision、Poetry／依赖环境中验证，业务改动尚未提交：

| 选择 | 结果 | Pytest 耗时 | 退出码 |
| --- | --- | --- | --- |
| `--scope new` | 244 passed、3 xfailed | 9.30s | 0 |
| 默认完整选择 | 701 passed、3 xfailed | 11.19s | 0 |
| 最终审计后的完整复跑 | 701 passed、3 xfailed | 10.39s | 0 |
| 扩展消费者（额外 20 个模块） | 305 passed、247 deselected | 5.79s | 0 |
| 真实用户子代理 Runner／MCP stdio | 7 passed、247 deselected | 1.30s | 0 |
| `--scope new --runxfail` | 244 passed、3 failed | 9.43s | 1（预期） |

新增目录含 247 个用例；默认回归清单仍是 34 个文件／457 个用例。
审计恰好失败于 G01／G12／G14 的原期望断言，没有夹具错误；全部选择没有受拦截的意外
连接尝试。未放宽守卫、未新增 xfail。扩展回归更新了过时的 Git PATH／惰性初始化断言，
补齐具体会话 ID／Goal 夹具。快照测试仅模拟无关的 Lark daemon 工具发现，不替代 Git
快照行为。用户子代理测试使用真实 Runner、合成响应和临时本地 MCP stdio 子进程，
不调用真实服务。[英文对应章节](../SESSION_TEST_BASELINE.md#default-execution-cutover-acceptance)
记录完整的 20 模块复现命令；用户子代理命令如下，同样使用离线守卫：

```bash
poetry -C "$REPO_ROOT" run python "$REPO_ROOT/tests/run_session_baseline.py" --scope new \
  "$REPO_ROOT/tests/tools/agent/test_user_agent_end_to_end.py" \
  -k test_user_agent_end_to_end --junitxml=/tmp/siada-cutover-verified-user-e2e.xml
```

补齐新增文件末尾换行后，使用默认 launcher 及
`--junitxml=/tmp/siada-cutover-post-audit-full.xml` 完整复跑，未改变业务逻辑。
68 个修改／新增 Python 文件均可解析和编译，未生成编译产物；最终检查了跟踪／新增
文件空白、文档路径／链接／锚点、Shell 语法、双语缺口清单及扩展模块复现命令。
两个跟踪文件保留父 revision 已有的无末尾换行状态，全部新增文件有末尾换行；
依赖清单／锁文件和 TypeScript UI 均未改动。

**验收范围：** 默认执行入口切换通过已审查的离线选择，不表示设计的每项要求均已完成。
`session_file`、`from_file(api_history.json)`、会话发现／展示加载及旧消息类仍是兼容面。
直接使用未准备 Runner／快照的旧链路保留三个缺口；已准备／默认路径的对应测试通过。
物理删除兼容 API／镜像类和设计要求的单个全状态生命周期组合场景仍属后续工作。
未运行全仓测试、交互启动、真实模型／服务、生产恢复、性能／断电测试或 TypeScript UI
构建；未修改 TypeScript 源码、依赖清单或锁文件。

## 上下文与记忆来源日志

INFO 日志分别标识执行模式与运行／review 输入来源。可以筛选普通 CLI 日志
（或对应的 daemon 日志）：

```bash
LOG_FILE="${SIADA_CLI_LOG_DIR:-$HOME/.siada-cli/logs}/siada_cli.log"
grep -E '\[effective-context\]|\[memory-source\]' "$LOG_FILE"
```

| 标记／字段 | 含义 |
| --- | --- |
| `[effective-context][run] mode=prepared bridge=enabled` | 已配置新的每轮 bridge；`filter=default` 或 `custom` 标识其输入过滤器。 |
| `[effective-context][run] mode=passthrough bridge=disabled` | 非 FileSession 存储保留原配置，不一定代表旧过滤器。 |
| `[effective-context][filter] mode=legacy` | 正在执行旧的 `context_capture_filter` 链路。 |
| `[effective-context][read] mode=prepared source=api_message.json` | 成功读取版本化上下文，包含 `version` 与 `items`；空上下文仍合法。 |
| `[effective-context][read] mode=legacy` | 旧格式读取，来源为 `api_history.json`、`api_messages.json` 或 `api_messages.json+delta`。 |
| `[effective-context][request] stage=filter_committed` | bridge 已提交过滤后的输入，包含 admission ID、请求序号、版本及消息数量；不代表过滤后 hook 准入完成或模型响应成功。 |
| `[memory-source][read] source=runtime_items` | memory 读取 FileSession 运行上下文，可按 session ID 关联 `[effective-context][read]` 确认实际存储来源；适配器来源为 `in_memory_snapshot`、`effective_adapter` 或 `items_adapter`。 |
| `[memory-source][export]` | 关联 session ID 与导出的 Markdown 文件名，并记录消息数量及长度截断情况。 |
| `[memory-source][review] trigger=pre_compaction source=in_memory_snapshot` | review 使用本次压缩之前的独立快照，其中可能已经包含此前压缩产生的摘要。 |
| `[memory-source][analyze]` / `[memory-source][review] trigger=periodic source=session_markdown` | 分析链路与后续 review 读取同一份导出的 Markdown，以文件名标识；不重读当前 JSON，也不推断该文件最初的导出来源。 |

review 调用前记录 `status=starting`；没有可用文本消息时记录 `status=skipped` 及原因。
原有结果日志继续描述阶段完成情况；开始日志不保证提取成功或记忆写入成功。
这些诊断不会新增会话正文、工具输出或绝对工作区路径。已准备上下文读取失败仍直接抛错，
不会回退完整历史。

## 覆盖矩阵

| 领域 | 新增行为测试 | 已审查的现有回归测试 |
| --- | --- | --- |
| 主 Runner | 首轮与后续轮次、流式／非流式、工具调用／结果、累计与最近响应 usage、输入／回复不重复 | 流式事件转换、原生工具展示 |
| 历史与上下文 | 请求前快照时序、快照加未发送尾部、工具循环中压缩且展示历史完整、快照写入失败 | 压缩策略、原生 patch／工具配对、并行边界、goal 重新注入、超大输出 offload |
| Resume | 真实 FileSession 切换、保留锚点的压缩输入、todo 顺序／所有字段、goal 状态／所有字段／审计历史 | 恢复跟踪修复、前端 goal／子代理状态推送 |
| 提醒与通知 | todo 提醒持久化且不重复、排队用户输入、过滤器后临时通知、失败／重试 | todo／重复工具提醒阈值、多模态排队输入限制 |
| 检查点 | 真实 JSON 捕获、hook 时刻的工具结果／usage、旧格式可选字段、成功恢复及 Git／快照失败补偿 | 现有会话同步持久化回归 |
| 父子任务 | 未完成任务递归树、已完成日志／结果、pending 状态一次消费、完成／失败路由和唤醒隔离 | 后台任务取消／关闭、持久化、递归、子代理真实 Runner 压缩 |
| 会话状态 | metadata／source／ownership 保留、message／run 标识与终态、详细 usage 序列化、缓存维度、每轮 skill 状态 | 展示／分类、telemetry 角色、切换模型的推理配置 |
| 存储边界 | 单实例并发追加、原子替换失败、回调失败、注入／原生消息标识、缺失／损坏快照 | 现有文件会话／同步测试 |
| 基准入口 | 清单校验、成功／异常环境恢复、吞掉网络异常时的失败约束 | 不引入新框架或依赖 |

旧链路行为夹具使用真实 `context_capture_filter`、`ContextTrackProcessor`、`FileSession`
以及 `agents.Runner.run`／`run_streamed`。恢复和检查点测试使用真实服务实现。
主夹具中的 token 计算和压缩输出为确定性替身；真实压缩策略由现有回归测试独立覆盖。
交互式启动、真实模型供应商、生产 Git 回滚、memory 调度及 React 终端 UI 不属于本套选择。

## 当前行为与期望不变量

通过项包含对现有行为的刻意记录：

- `api_messages.json` 在模型回复前保存，并非完整 UI 历史。有效上下文由快照加其后的
  原生历史增量组成。
- 会话 usage 保存最近一次模型响应；SDK run usage 累计本轮所有请求。
- 消息遥测保持完整 UI 历史来源，不改读压缩后的有效上下文，也不使用 UI 渲染后裁剪
  的文本；保留当前格式化、角色映射、注入项筛选及完整历史计数口径。
- `hook_pending_contexts` 通知目前只影响一次请求，不会持久化。这是当前行为，
  不是重构必须保留消息丢失的契约。
- 固定 SDK 版本的流式路径将模型侧 `CancelledError` 结束为无输出的完成结果；
  调用方取消另有测试，确保两种 API 都传播取消并关闭模型协程。

已知缺口使用 `pytest.mark.xfail(strict=True, raises=AssertionError)` 表达期望行为。
其他异常类型仍正常失败；修复后会触发 `XPASS(strict)` 失败，需移除对应标记。
不能把新回归改为 xfail，也不能把没有新增 xfail 当作功能完整的证明。

以上行为描述限定于旧链路夹具，不是已准备／默认执行契约；默认切换回归单独记录。

### 可执行的已知缺口清单

| 编号 | 当前缺口／期望不变量 |
| --- | --- |
| G01（仅旧链路） | 未准备 Runner 请求失败丢失后置通知；已准备／默认重试测试通过。 |
| G02（已修复） | 同工作区、同代理的不同会话不共享可变缓存上下文。 |
| G03（已修复） | 没有 todo 历史及显式空列表均清除旧 pending／context todos。 |
| G04（已修复） | 全部完成时已清空的 todos，resume 后仍为空。 |
| G05（已修复） | 无 goal 的恢复清除缓存旧 goal。 |
| G06（已修复） | 恢复实际 usage 详情，与请求 token 预算分离。 |
| G07（已修复） | 提醒计数器具有结构化持久化恢复状态。 |
| G08（已修复） | 重复 resume 不重复追加未完成任务通知。 |
| G09（已修复） | 已保存标题恢复到 SessionState。 |
| G10（已修复） | 跨工作区 resume 重新绑定工作区与存储。 |
| G11（已修复） | limit=0 返回空列表；拒绝负数限制。 |
| G12（仅旧链路） | 未准备空旧快照回退历史；已准备／默认空上下文保持为空。 |
| G13（已修复） | 清空历史同时清除有效上下文与旧计数。 |
| G14（仅旧链路） | 未准备仅摘要快照恢复无法对齐；已准备／默认仅摘要恢复测试通过。 |
| G15（已修复） | metadata 写入失败会回滚历史与签名。 |
| G16（已修复） | 共享锁及元数据合并保留交错写入的 ownership。 |
| G17（已修复） | 独立 FileSession 实例串行提交追加事务。 |
| G18（已修复） | 检查点保存结构化 todo／goal／计数器／通知状态快照。 |

原清单共 18 类缺口、19 个预期失败用例，G03 包含两种变体。
其中 15 类已修复，仅直接旧链路剩余 G01／G12／G14 三个严格预期失败用例。
G16／G17 使用受控交错，
而非概率性竞争；未来更改锁机制时，应更新夹具以验证新的事务边界，避免在新锁内部
人为制造死锁。

## 基准记录与后续维护

比较重构时，应同时记录源码 revision、依赖版本、完整命令、通过／xfail 数量和耗时，
并保留 JUnit 报告。耗时仅用于观察，不是延迟性能门禁；替身 token 计数不代表计费
准确性。未测量时不声明覆盖率百分比。

每次修改后：

1. 先跑新增测试，再用新进程跑完整会话选择。
2. 对照清单检查失败；修复新失败，只有对应期望不变量真正通过后才移除 xfail。
3. 有意修复缺口时，同时更新与新行为冲突的旧行为测试。
4. 消息格式、新状态字段变更时补齐兼容、旧格式和损坏数据测试；同步维护中英文清单。
5. 脱敏报告保存在仓库之外，不提交真实会话、凭据、日志或机器专属路径作为夹具。
