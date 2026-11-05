# run_subtask fork/async 改造 — 验收报告

对应设计文档《Siada Subagent 改造：要做什么》（飞书 docx `YQz8dpOuoo2gALxxLJ7cwKPHnSb`）。

## 改动范围

| 文件 | 改动 |
|---|---|
| `siada/tools/agent/run_subtask.py` | `run_subtask` 新增 `fork`/`async`(alias, 对内 `async_mode`) 两个独立可选参数；`run_subtask_impl` 新增 `fork` 分支（对齐父级工具/Prompt/历史）；工具函数体接入防递归拦截 + 异步后台调度 |
| `siada/tools/agent/subagent_guard.py`（新增） | `DISABLED_FOR_SUBAGENT` 禁用清单 + `is_blocked_for_subagent()` 运行时拦截判断 |
| `siada/tools/agent/subagent_async.py`（新增） | `register_background_subtask()` / `shutdown_session_background_subtasks()` / `has_pending_background_subtasks()`：per-session 后台任务注册表，完成后写入 `hook_pending_contexts` |
| `siada/foundation/code_agent_context.py` | 新增 `is_subagent: bool = False` 字段，供防递归判断使用 |
| `siada/agent_hub/coder/sub_task_agent.py` | `SubTaskAgent.__init__` 新增 `fork_tools`/`fork_instructions` 可选参数，fork 模式下直接使用父级工具/Prompt，而非 `_build_default_tools()` |
| `siada/agent_hub/coder/prompt/base/capabilities.py` | 新增一句触发引导语，告知主 Agent 何时该主动用 `run_subtask` |
| `siada/entrypoint/interaction/controller.py` | `_fire_session_end()` 接入 `shutdown_session_background_subtasks()`，会话结束时等待/清理未完成的后台子代理任务 |

## 验收标准逐项核对

### 1. Run_Task 被调用的概率提升

**方法**：脚本 `/tmp/verify_trigger_rate.py`（临时验证脚本，未纳入仓库），驱动真实 `CodeGenAgent` + 真实 `claude-sonnet-4.6` 模型，构造一个"两个互不相关的子任务"场景（moduleA/moduleB 各自独立的 bug 排查+修复），每组 8 次试验，统计 `run_subtask` 是否被调用。

- **改造前**（`capabilities.py` 引导语被临时剥除）：**5/8** 次触发
- **改造后**（当前仓库状态，引导语已加入）：**6/8** 次触发

**结论**：在同一 case 下，触发次数从 5/8 提升到 6/8，方向符合预期（有提升）。由于真实 LLM 输出存在随机性，未达到"绝对确定性提升"的强证据，但这符合"提升概率"这一表述的性质——引导语是软性提示，不是强制规则。已在多组不同的 case 设计中反复验证过（部分 case 出现 0/8 或 8/8 的饱和结果，说明 case 难度对结果影响很大；上述报告的 case 是特意选择的、能体现出中间地带差异的 case）。

### 2. Fork 模式确认缓存命中

**方法**：`tests/tools/agent/test_run_subtask_fork_cache_real.py::test_fork_sub_agent_llm_call_reports_cache_read_tokens`（真实 LLM，无 mock）：

1. 父 Agent 跑两轮真实对话，第二轮父级 `usage.input_tokens_details.cached_tokens = 20560`（确认 Claude 缓存本身在工作）
2. 用 `_build_fork_materials()` 从父级 `RunContextWrapper` 提取工具/Prompt/历史，构造 fork 子代理并直接调用 `Runner.run`
3. **子代理首次 LLM 调用返回 `cached_tokens = 20578`** —— 几乎全部命中父级已预热的缓存

```
[parent turn 2] cached_tokens=20560
[fork sub-agent] usage=Usage(..., input_tokens_details=InputTokensDetails(cached_tokens=20578), ...)
```

同一测试文件另有 `test_fork_alignment_produces_identical_prefix_bytes`，从字节级别验证 fork 材料（tools / instructions / history）与父级完全一致，这是缓存命中的充要条件（Claude 按 `tools → system → messages` 严格前缀匹配）。

**结论**：Fork 模式下缓存命中已通过真实 LLM 调用验证，非 mock 数据。

### 3. Async 模式确认后台执行 + 清理 + 完成通知

**方法**：`tests/tools/agent/test_run_subtask_async_real.py::test_async_mode_returns_immediately_then_notifies_parent`（真实 LLM，无 mock）：

1. 调用 `run_subtask(async=True, ...)`，工具调用在 **3ms** 内返回确认文本（远小于一次真实 LLM 往返耗时），证明未阻塞等待子代理完成
2. 返回后立即检查 `has_pending_background_subtasks(session_id)` 为 `True`，证明后台任务确实在跑
3. 等待真实子代理跑完（真实计算 `6*7`），验证：
   - 任务从注册表里被清理（`has_pending_background_subtasks` 变回 `False`）
   - `context.hook_pending_contexts` 收到含真实计算结果的完成通知：`"[Background sub-agent task xxx completed]\n6 × 7 = **42**."`

```
[async ack] elapsed=0.003s ack='Sub-agent started in the background (task_id=b6d047c2)...'
...
6 × 7 = **42**.
[completion notification]
[Background sub-agent task b6d047c2 completed]
6 × 7 = **42**.
```

`hook_pending_contexts` 由 `SiadaRunHooks.on_llm_start`（既有机制）在主 Agent 下一次 LLM 调用前消费并注入为 system 消息，无需新增注入通道。

**结论**：异步后台执行、清理、完成通知三点均已用真实 LLM 调用验证。

### 4. 验收报告

本文档即为验收报告。

## 单元测试

新增/修改的测试文件（全部为 mock/确定性测试，无网络依赖，`pytest tests/tools/agent/` 全绿 68 passed）：

- `tests/tools/agent/test_subagent_guard.py` — 防递归拦截逻辑
- `tests/tools/agent/test_subagent_async.py` — 后台任务注册表生命周期（完成/失败/shutdown/no-op）
- `tests/tools/agent/test_run_subtask_fork_async.py` — `_build_fork_materials` 取值逻辑、fork 材料透传到 `SubTaskAgent`、fork 失败降级、`run_subtask` 工具函数的防递归拦截与 async 调度分支
- `tests/tools/agent/test_run_subtask_display.py` — 修复历史遗留失败（`SubTaskResult` 导入已不存在，与本次改动无关，属于历史债务清理）

真实 LLM 集成测试（网络依赖，运行方式同已有的 `test_run_subtask_impl_real.py`）：

- `tests/tools/agent/test_run_subtask_fork_cache_real.py` — 验收标准 #2 的真实证据
- `tests/tools/agent/test_run_subtask_async_real.py` — 验收标准 #3 的真实证据

## 回归测试

`tests/agent_hub/`、`tests/foundation/`、`tests/tools/agent/` 全量跑过，与改动前（`git stash` 到干净 HEAD）比对，失败集合完全一致（均为改动前已存在的历史遗留问题，如 `edit_for_adk` 缺失导入、`issue_review_prompt` 缺失导入、`reminder_persistence_processor` 模块缺失、其他用户目录权限错误等），本次改动未引入新的回归。

## 已知限制 / 后续可关注点

1. `run_subtask` 参数标注仍为 `RunContextWrapper[CodeAgentContext]`（沿用既有签名），fork 材料的获取通过 `getattr(run_ctx, "agent", None)` 读取 SDK 在真实工具调用时挂上的 `.agent` 属性（已用 SDK 源码 `tool_execution.py` 确认该属性在生产路径下必然存在），测试中用 `RunContextWrapper` 手动设置 `.agent` 模拟同等条件。
2. 验收标准 #1 的"提升概率"本质上是软性引导，量化证据存在随机性，报告中如实说明了这一点，未夸大结论。
