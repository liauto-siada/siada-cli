# Conversation Compaction Configuration

When the model's context window has 60,000 tokens or fewer remaining, Siada automatically compresses the message history by generating an LLM summary to replace older messages while preserving recent conversations. The trigger is `used_tokens >= context_window - 60_000`, using the current effective context window. For a 200,000-token window, compaction starts at 140,000 used tokens; for a 1,000,000-token window, it starts at 940,000. Windows of 60,000 tokens or less reach the trigger immediately; the selected strategy still needs compressible history.

The budget includes instructions, tool definitions and the history replayed to
the selected model. After a response is saved successfully, its reported total
usage can anchor the saved prefix; subsequent requests count only the added
history. Cache-hit and cache-write figures do not reduce the context budget.
Changed instructions, tools, model routing or restored history invalidate that
anchor, so the next request estimates the complete input again.

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
