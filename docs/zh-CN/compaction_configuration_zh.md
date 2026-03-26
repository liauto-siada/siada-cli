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
