# 会话压缩配置

当模型上下文窗口剩余不超过 60,000 tokens 时，Siada 会自动压缩历史消息，通过 LLM 生成摘要替换旧消息，保留近期对话。触发条件为 `已用 tokens >= 上下文窗口 - 60_000`，使用当前实际生效的上下文窗口。例如，200,000 tokens 窗口在已用 140,000 tokens 时触发，1,000,000 tokens 窗口在已用 940,000 tokens 时触发。窗口不超过 60,000 tokens 时会立即达到触发条件，是否实际压缩仍取决于所选策略是否有可压缩的历史。

预算包含指令、工具定义和向当前模型回放的历史。响应成功保存后，可以使用服务端报告的总 usage 作为已保存历史的基线，后续请求只估算新增历史。缓存命中和缓存写入不会减少上下文预算。指令、工具、模型路由或恢复后的历史发生变化时，该基线会失效，下一次请求重新估算完整输入。

## 配置方式

编辑 `~/.siada-cli/conf.yaml`：

```yaml
# 压缩策略（可选，不设置则自动选择）
compaction_strategy: null
```

## 可选值

| 策略 | 说明 | 默认适用 |
|---|---|---|
| `header_summary` | 保留首轮对话 + LLM 摘要 + 最近 30% 消息 | CLI / TUI 模式 |
| `turn_prune_summary` | 三层管线：轮次裁剪 → 工具结果截断 → LLM 摘要，保留最近 3 轮对话 | IM 模式（飞书） |

不配置时，系统根据会话模式自动选择：CLI/TUI 用 `header_summary`，IM 用 `turn_prune_summary`。

## 示例

强制 CLI 模式使用 IM 策略：

```yaml
compaction_strategy: "turn_prune_summary"
```

## 压缩模型

摘要默认使用主模型。可通过环境变量 `SIADA_COMPACT_MODEL` 指定同一 provider
和端点提供的其他模型。

使用 `default` provider 时，无 provider 前缀的自定义模型 ID 通过配置的
OpenAI 兼容端点（`BASE_URL` 和 `API_KEY`）调用。带 provider 前缀的模型 ID
保留显式路由；OpenRouter 端点使用 OpenRouter 路由。
