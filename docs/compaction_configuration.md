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

## Compaction Model

Summaries use the main model by default. Set `SIADA_COMPACT_MODEL` to use a
different model available through the same provider and endpoint.

With the `default` provider, bare custom model IDs use the configured
OpenAI-compatible endpoint (`BASE_URL` and `API_KEY`). Provider-prefixed model
IDs retain their explicit routing; OpenRouter endpoints use OpenRouter routing.
