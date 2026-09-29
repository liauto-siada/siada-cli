---
title: Supported Agents
description: AI agents that work with the chrome-acp proxy.
---

`chrome-acp` works with any [ACP-compatible agent](https://agentclientprotocol.com/get-started/agents) — the proxy takes an agent command and runs it as a subprocess. In a Siada CLI installation that command is **`siada-cli --acp`**.

---

## siada-cli (Default)

Siada CLI's browser add-on always runs Siada's own ACP entry point, so the side panel is a normal Siada session (memory, skills, MCP servers, tools) with browser control on top.

```bash
# Install once: this is the proxy that Siada CLI spawns for you
siada-browser setup /path/to/siada-agenthub/chrome-acp
# or: siada-cli --browser-setup /path/to/siada-agenthub/chrome-acp

# Start / restart / inspect it
siada-browser start
siada-browser status
```

**Requirements:** a working Siada CLI configuration (model provider, API keys) — the browser add-on adds nothing extra.

**Features:** everything Siada CLI can do, plus the [browser tools](/guides/browser-tools/).

---

## Using Another Agent

The proxy is agent-agnostic: pass any command that speaks ACP over stdin/stdout, for example `acp-proxy <agent-command> -- <agent-args>`. Two things to keep in mind:

- Stop the Siada-managed proxy first if you want to bind the same port: `siada-browser stop`
- A proxy you launch yourself prints its own token and URLs; the extension connects to `ws://localhost:<port>/ws` (or `wss://` with `--https`) plus that token

The examples below use the proxy that `siada-browser setup` installed; substitute `packages/proxy-server/dist/cli/bin.js` if you are running straight from a checkout.

---

## Claude Code

Anthropic's agentic coding tool, driven through its ACP adapter.

```bash
# Install the agent (the proxy is already installed)
npm install -g @anthropic-ai/claude-code @zed-industries/claude-code-acp

# Run the proxy with it
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --no-auth claude-code-acp
```

**Requirements:** `ANTHROPIC_API_KEY` environment variable

**Features:** Image support, Model selection, Extended thinking

---

## Codex CLI

OpenAI's coding agent.

```bash
# Install
npm install -g @openai/codex @zed-industries/codex-acp

# Run
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --no-auth codex-acp
```

**Requirements:** `OPENAI_API_KEY` environment variable

---

## OpenCode

Open-source terminal AI assistant with multi-provider support.

```bash
# Install
curl -fsSL https://opencode.ai/install | bash

# Run
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --no-auth opencode -- acp
```

---

## Gemini CLI

Google's AI agent with a generous free tier.

```bash
# Install
npm install -g @google/gemini-cli

# Run
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --no-auth gemini -- --experimental-acp
```

**Requirements:** `GOOGLE_API_KEY` or Google Cloud credentials

---

## Qwen Code

Free coding agent using Qwen models (no API key required).

```bash
# Install
npm install -g @qwen-code/qwen-code@latest

# Run
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --no-auth qwen -- --acp
```

---

## Augment Code

AI coding agent by Augment.

```bash
# Install
npm install -g @augmentcode/auggie

# Run
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --no-auth auggie -- --acp
```

---

## Agent Capabilities

Agents can declare their capabilities when creating a session. `chrome-acp` supports:

### Image Support

Agents can accept images in prompts:

```typescript
promptCapabilities: {
  image: true  // Enables image attachment button
}
```

When enabled, users can:
- Attach images via button or drag-and-drop
- Paste screenshots from clipboard
- Images are compressed to <2MB and sent as base64

### Model Selection

Agents can expose multiple models:

```typescript
modelState: {
  availableModels: [
    { id: "claude-3-opus", displayName: "Claude 3 Opus" },
    { id: "claude-3-sonnet", displayName: "Claude 3 Sonnet" }
  ],
  currentModelId: "claude-3-sonnet"
}
```

When available, a model selector appears in the chat input footer.

### Extended Thinking

Some agents support "thinking" or "reasoning" modes where they show their thought process:

```typescript
{ sessionUpdate: "agent_thought_chunk", content: { type: "text", text: "..." } }
```

Thought chunks are displayed in a collapsible "Thinking" section.

---

## Custom Agents

Any ACP-capable command works with `chrome-acp`:

```bash
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --no-auth /path/to/your/agent
```

### Requirements

Your agent must:
1. Accept communication via **stdin/stdout**
2. Implement the **ACP protocol** (NDJSON messages)
3. Handle session lifecycle (`new_session`, `prompt`, etc.)

### Minimal Protocol

```jsonl
← {"request":"new_session","requestId":"1"}
→ {"requestId":"1","sessionId":"abc123","promptCapabilities":{"image":false}}
← {"request":"prompt","requestId":"2","sessionId":"abc123","content":[{"type":"text","text":"Hello"}]}
→ {"requestId":"2","sessionUpdate":"agent_message_chunk","content":{"type":"text","text":"Hi there!"}}
→ {"requestId":"2","promptComplete":{"stopReason":"end_turn"}}
```

### Adding Browser Tools

To use browser tools, your agent must support MCP and connect to:
```
http://localhost:9315/mcp
```

See [Architecture](/reference/architecture/) for MCP protocol details.

---

## Troubleshooting

### Agent doesn't start

```bash
# Check the proxy state and where the agent failed
siada-browser status
tail -n 50 ~/.siada-cli/browser/acp-proxy.log

# Test the agent directly
siada-cli --acp

# Check if it accepts stdin
echo '{"request":"new_session","requestId":"1"}' | siada-cli --acp
```

### Missing API key

```
Error: ANTHROPIC_API_KEY not set
```

Set the required environment variable:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Agent crashes immediately

Enable debug mode to see detailed logs:
```bash
node ~/.siada-cli/browser/proxy/dist/cli/bin.js --debug --no-auth claude-code-acp
```

Check logs in `.acp-proxy/` in the working directory, and the proxy's own log at `~/.siada-cli/browser/acp-proxy.log`.
