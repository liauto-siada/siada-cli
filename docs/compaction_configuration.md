# Conversation Compaction Configuration

When the conversation token count reaches 70% of the model's context window, Siada automatically compresses the message history by generating an LLM summary to replace older messages while preserving recent conversations.

## Configuration

Edit `~/.siada-cli/conf.yaml`:

```yaml
# Compaction strategy (optional, auto-detected if not set)
compaction_strategy: null
```

## Available Strategies

| Strategy | Description | Default For |
|---|---|---|
| `header_summary` | Keeps first user-assistant pair + LLM summary + recent 30% messages | CLI / TUI mode |
| `turn_prune_summary` | Three-layer pipeline: turn pruning → tool result truncation → LLM summary, keeps last 3 turns | IM mode (Feishu) |

When not configured, the system auto-selects based on session mode: CLI/TUI uses `header_summary`, IM uses `turn_prune_summary`.

## Example

Force IM strategy in CLI mode:

```yaml
compaction_strategy: "turn_prune_summary"
```
