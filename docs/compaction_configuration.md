# Conversation Compaction Configuration

Siada automatically compresses older message history into an LLM summary while preserving recent conversations. CLI/TUI and IM use the same trigger, based on the current effective context window:

- **Up to and including 500,000 tokens:** reserve 60,000 tokens; trigger at `used_tokens >= max(0, context_window - 60_000)`.
- **Above 500,000 tokens:** reserve 25% of the window; trigger when usage reaches 75%. Fractional thresholds are rounded up to the next whole token.

| Effective context window | Trigger at used tokens |
|---:|---:|
| 200,000 | 140,000 |
| 500,000 | 440,000 |
| 600,000 | 450,000 |
| 1,000,000 | 750,000 |

Windows of 60,000 tokens or less reach the trigger immediately. Reaching the trigger does not guarantee compression: the selected strategy still needs compressible history and a nonempty summary.

## Request Budget and Diagnostics

For requests using the **Responses protocol**, a full local recount receives an additional **1.5× conservative buffer** after the existing estimation allowance. With the normal tokenizer's 10% safety margin, this is approximately `raw_estimate × 1.10 × 1.5 = raw_estimate × 1.65`, subject to integer rounding. The existing tokenizer and fallback methods remain unchanged. A full budget of 506,029 tokens therefore becomes 759,043, exceeding the 750,000-token trigger for a 1M window.

The buffer compensates for reasoning and encrypted payloads that local counting cannot fully represent; it is **not precise provider-side counting**. It depends on the actual counting protocol, not a GPT model-name prefix. It does not further inflate incremental additions or the server-usage baseline, which already includes cached input and response usage.

MCP server schemas are currently excluded from local estimation and request signatures. Configuring MCP servers no longer forces a full recount, but their schema changes cannot be detected by the signature. This accepted estimation limitation is logged as `mcp_schema_counting_deferred`; other signature safety checks still apply.

Structured diagnostics report the protocol, full/incremental counting mode, budget before and after buffering, reasoning-item counts and encrypted-carrier lengths, effective window and threshold rule, and compaction outcome. Request/response comparisons use cache-inclusive server input usage without adding cache twice. If compaction or subsequent hooks change the counted input, the comparison is marked unavailable rather than comparing different requests. These diagnostics record counts, lengths, and reasons, not conversation content, reasoning text, tool arguments, or credentials.

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
