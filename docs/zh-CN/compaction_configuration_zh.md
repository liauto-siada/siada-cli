# 会话压缩配置

当对话 token 数达到模型上下文窗口的 70% 时，Siada 会自动压缩历史消息，通过 LLM 生成摘要替换旧消息，保留近期对话。

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
