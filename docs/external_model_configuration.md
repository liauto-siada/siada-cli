# External Model Configuration

User-Defined Model Configuration Guide

## Overview

When using `--provider default`, Siada supports loading user-defined model configurations from a local configuration file. This allows you to configure your own model collection and default model.

Agent calls through `ModelWrapper` retry transport timeouts, connection failures,
LiteLLM midstream failures, and transient OpenAI API errors up to twice, with
exponential backoff and jitter. API retries cover HTTP 403/408/409/429/5xx, recognized
server/overload/timeout error codes, and an unclassified `Unknown stream error`.
HTTP 403 authentication failures share this retry budget; persistent failures
still propagate after three model calls. The wrapper does not refresh credentials.
Explicit non-transient stream error codes, such as invalid input or insufficient
quota, are propagated.
This covers stream creation and consumption until answer text, tool events, or
unknown events reach the caller. Thinking remains visible in real time and does
not stop retries; thinking from another attempt may appear after a failure.
Once answer or tool output is exposed, the error propagates to avoid duplicating
it. Empty message/reasoning items and empty text
parts are buffered along with lifecycle events, so a deployment disconnect
(`RemoteProtocolError`, including `incomplete chunked read`) during these start
events can still retry. Reasoning-only streams that end without a final response
can also retry. Retry delays are 1–2 seconds and 2–3 seconds.
Context admission runs once; nested wrappers
share one transport retry budget. Direct completion clients retain their own
retry policies. See the [provider routing and retry wiki](wiki/17_provider-routing-retries.md)
for the protocol routes and exception matrix.

Responses error logs include bounded error message/code/type/param fields,
available request and trace IDs, model, response ID, last stream event, and whether
output has been exposed. Request bodies, full error bodies, and authentication
headers are excluded from these diagnostic records. Protocol `error` and
`response.failed` events follow the same retry rules as SDK exceptions.

The main conversation also allows up to two session continuations after a missing
final response, timeout, or connection interruption. It reads saved conversation
history and completed tool results before continuing, so completed operations are
preserved. Unfinished tool calls are not executed or copied into history. If the
new input was not admitted, recovery retains the original input. Persistent
interruptions still report an error; cancellation stops recovery immediately.
Recovery also stops if saved history was rewritten or an unsupported message
shape prevents verifying input admission, rather than resending uncertain input.

## Configure DeepSeek with an API Key

On first sign-in or through `/configure`, select **Configure API Key → DeepSeek**,
choose a model, and enter your DeepSeek API key. The base URL is prefilled as
`https://api.deepseek.com/v1`; the selected model and credentials are saved in
`~/.siada-cli/conf.yaml` with `provider: default` and `provider_id: deepseek`.

The offline preset includes `deepseek-flash` and `deepseek-v4-pro` (1M context).
When a models.dev cache is available, the wizard uses its current tool-capable
DeepSeek models; an older cache without usable DeepSeek entries uses the preset.
You do not need to create `models.json` to use this wizard.

## Configuration File Location

The model configuration file is located at: `~/.siada-cli/models.json`

## Configuration File Format

The configuration file uses JSON format and contains the following fields:

```json
{
  "default_model": "model_name",
  "models": [
    {
      "model_name": "model_name",
      "context_window": context_window_size,
      "max_tokens": max_output_tokens (optional),
      "supports_images": whether_supports_images (optional, default false),
      "supports_prompt_cache": whether_supports_prompt_cache (optional, default false),
      "supports_extra_params": ["extra_params_list"] (optional),
      "parallel_tool_calls": whether_supports_parallel_tool_calls (optional, default null)
    }
  ]
}
```

## Configuration Example

```json
{
  "default_model": "openai/gpt-4",
  "models": [
    {
      "model_name": "openai/gpt-4",
      "context_window": 128000,
      "max_tokens": 4096,
      "supports_images": true,
      "supports_prompt_cache": false,
      "supports_extra_params": [],
      "parallel_tool_calls": true
    },
    {
      "model_name": "openai/gpt-3.5-turbo",
      "context_window": 16385,
      "max_tokens": 4096,
      "supports_images": false,
      "supports_prompt_cache": false,
      "supports_extra_params": [],
      "parallel_tool_calls": true
    },
    {
      "model_name": "anthropic/claude-3-opus",
      "context_window": 200000,
      "max_tokens": 4096,
      "supports_images": true,
      "supports_prompt_cache": true,
      "supports_extra_params": [],
      "parallel_tool_calls": true
    },
    {
      "model_name": "deepseek/deepseek-chat",
      "context_window": 128000,
      "max_tokens": 8192,
      "supports_images": false,
      "supports_prompt_cache": false,
      "supports_extra_params": [],
      "parallel_tool_calls": false
    }
  ]
}
```

## Field Descriptions

### default_model (Optional)
- **Type**: String
- **Description**: The default model to use when the user does not specify a model via command line
- **Example**: `"gpt-4"`

### models (Required)
An array of model configurations, each model contains the following fields:

#### model_name (Required)
- **Type**: String
- **Description**: The name of the model, supports two formats:
  1. **Standard model name**: Such as `gpt-4`, `claude-3-opus`, etc. The system will automatically add the protocol prefix (see [Model Naming Convention](#model-naming-convention))
  2. **Full format**: `protocol/model_name`, such as `anthropic/claude-3-opus`, `openai/gpt-4-turbo`
- **Example**: `"gpt-4"`, `"anthropic/claude-3-opus"`, `"deepseek/deepseek-chat"`

#### context_window (Required)
- **Type**: Integer
- **Description**: The context window size supported by the model (in tokens)
- **Example**: `128000`, `200000`

#### max_tokens (Optional)
- **Type**: Integer
- **Description**: Maximum number of tokens for a single output
- **Default**: If not specified, the model's default value will be used
- **Example**: `4096`, `8192`

#### supports_images (Optional)
- **Type**: Boolean
- **Description**: Whether the model supports image input
- **Default**: `false`
- **Example**: `true`, `false`

This capability controls both user-attached images and image reads through
`edit_file`. For Chat Completions conversions, including the `li` and `default`
providers, already-produced tool-result images are always preserved for every
model. Conversion does not check `supports_images` or require request context,
so a false or missing capability cannot discard images from tool results.
The stored history is unchanged.

The Chat Completions endpoint must accept image content in `role: tool`
messages. Supporting images in user messages alone does not ensure
support for tool-result images; the standard OpenAI Chat Completions protocol
does not support them. An incompatible endpoint needs a separate message-protocol
adaptation. Existing vision-bridge behavior for text-only models is unchanged.

#### supports_prompt_cache (Optional)
- **Type**: Boolean
- **Description**: Whether the model supports prompt caching
- **Default**: `false`
- **Example**: `true`, `false`

#### parallel_tool_calls (Optional)
- **Type**: Boolean
- **Description**: Whether the model supports parallel tool calls. When enabled, the model can invoke multiple independent tools simultaneously in a single response, improving execution efficiency. For Claude models, this parameter controls parallel behavior via prompt-level instructions; for OpenAI/Gemini models, this parameter is passed directly to the API
- **Default**: `null` (parameter not passed)
- **Recommended Values**:
  - Claude, GPT, Gemini series: `true`
  - DeepSeek, Kimi, GLM, MiniMax series: `false`
- **Example**: `true`, `false`

#### supports_extra_params (Optional)
- **Type**: String Array
- **Description**: List of extra parameters supported by the model
- **Default**: `null`
- **Possible Values**: `["reasoning_effort"]`, `["thinking_tokens"]`
- **Example**: `["reasoning_effort"]`

#### default_thinking_tokens (Optional)
- **Type**: Integer
- **Description**: Enables thinking/reasoning mode on startup without requiring command-line arguments. The value itself is NOT sent as a token budget — reasoning depth is controlled solely by `reasoning_effort` (see below); this setting only signals "thinking on"
- **Default**: `null` (thinking not enabled)
- **Special Values**:
  - `-1`: Adaptive thinking mode, suitable for Claude 4.6+ and other models supporting adaptive reasoning
  - Positive integer (e.g., `1024`): Thinking enabled with the model/gateway's default reasoning depth
- **Prerequisite**: `supports_extra_params` must include `"thinking_tokens"`
- **Example**: `-1` (adaptive mode), `1024` (default-depth thinking)

#### default_reasoning_effort (Optional)
- **Type**: String
- **Description**: Default reasoning effort level for the model. When set, the model will automatically use the specified reasoning effort level on startup
- **Default**: `null` (reasoning effort level not set)
- **Possible Values**: `"low"`, `"medium"`, `"high"`
- **Prerequisite**: `supports_extra_params` must include `"reasoning_effort"`
- **Example**: `"low"`

#### effort_choices (Optional)

- **Type**: Non-empty array of `"low"`, `"medium"`, `"high"`, `"xhigh"`, or `"max"`
- **Description**: Overrides the inferred model-family effort levels. `/effort` input hints, the selector and validation use exactly these choices. A persisted effort from another model maps to an allowed level.
- **Default**: `null` (use model-family inference)
- **Prerequisite**: `supports_extra_params` must include `"reasoning_effort"`. Set `default_reasoning_effort` to one of the choices.
- **Example**: `"effort_choices": ["max"]`

## Model Naming Convention

Model names support two formats: **Standard model name** and **Full format** (protocol/model_name).

### Format Description

The full format of a model name is: `protocol/model_name`

- **Protocol/model prefix**: Identifies the model family or provider route used by Siada
- **Model name**: Specific model identifier, must comply with interface constraints

Examples:
- `anthropic/claude-3-opus` - Access Claude 3 Opus using Anthropic native protocol
- `openai/gpt-4-turbo` - Access GPT-4 Turbo using OpenAI native protocol
- `deepseek/deepseek-coder` - Access DeepSeek Coder using DeepSeek native protocol

### Automatic Protocol Mapping

To simplify configuration, the system automatically adds protocol prefixes for the following standard model names:

| Model Name Prefix | Automatically Mapped To | API Protocol |
|-------------------|-------------------------|--------------|
| `claude-*` | `anthropic/claude-*` | Anthropic |
| `gpt-*` | `openai/gpt-*` | OpenAI Chat Completions, except GPT-5+ Responses-only models |
| `o3-*` | `openai/o3-*` | OpenAI Chat Completions |
| `deepseek-*` | `deepseek/deepseek-*` | OpenAI-compatible Chat Completions |
| `gemini-*` | `google/gemini-*` | Gemini native/LiteLLM |
| `kimi-*` | `moonshotai/kimi-*` | OpenAI-compatible Chat Completions |

**View Full Implementation**: [siada/provider/default/coverter.py](../siada/provider/default/coverter.py)

### Usage Notes

- Standard model names (such as `gpt-4`) are mapped to a provider/model form; OpenAI Chat Completions requests send the endpoint's model ID without the LiteLLM routing prefix
- Claude and Gemini keep their existing LiteLLM/native routes. Other default-provider models must use an endpoint that accepts OpenAI Chat Completions; a LiteLLM-native protocol prefix alone does not make an endpoint compatible
- GPT-5 and newer use the Responses API. Other Responses-only aliases are not sent to Chat Completions
- For complete configuration examples, please refer to the [Configuration Example](#configuration-example) section above

## Usage Guide

### 1. Create Configuration File

First, create the `models.json` file in the `~/.siada-cli/` directory:

```bash
mkdir -p ~/.siada-cli
nano ~/.siada-cli/models.json
```

### 2. Configure API Connection

In the Siada UI, run `/configure` to choose a provider, model and API key.
You can repeat the command to update the key or switch providers without
restarting. Press Esc while submitting to cancel the configuration.

Each configuration accepts one reply. Esc cancels while the backend is still
waiting for a choice; it does not undo an already accepted submission.
Duplicate and expired replies are ignored so they cannot affect later commands.

Configure `base_url` and `api_key` in `~/.siada-cli/conf.yaml`:

```yaml
llm_config:
  provider: default
  model: openai/gpt-4  # Optional, will use default_model from models.json if not specified
  base_url: https://your-api-endpoint.com/v1
  api_key: your-api-key-here
```

Or use environment variables:

```bash
export BASE_URL=https://your-api-endpoint.com/v1
export API_KEY=your-api-key-here
```

> **💡 Tip: base_url Configuration for Different Protocols**
> 
> - **OpenAI-compatible protocols** (such as `openai/*`, `deepseek/*` etc.): Must include `/v1` path
>   - Example: `https://api.openai.com/v1`
>   - Chat-routed models must accept `POST /chat/completions`; the configured model ID must be the ID accepted by that endpoint
> 
> - **Anthropic protocol** (`anthropic/*`):
>   - Option 1: Without path suffix, e.g., `https://api.anthropic.com`
>   - Option 2: With full path, e.g., `https://api.anthropic.com/v1/messages`

### 3. Run Siada

Using the default provider:

```bash
# Use default model from configuration file
siada --provider default

# Specify a specific model
siada --provider default --model openai/gpt-4

# Or configure provider in conf.yaml and run directly
siada
```

## Git Snapshot (All Models)

For **all models**, the main coding agent appends a bounded Git snapshot (branch, HEAD, worktree summary and capture time) as a hidden `<system-reminder>`-wrapped `input_text` content part on the first user request in a Git workspace, rather than creating another user message. It is stored in the session's `api_history.json`, reused on subsequent turns and after `/resume`, and refreshed in the model-visible `api_messages.json` after context compaction. Older sessions with a standalone snapshot message remain supported. If the workspace is not a Git repository or capture fails, no snapshot is added. The hidden content part is never sent as a mid-conversation system message or shown in chat history. Set `SIADA_GIT_SNAPSHOT=0` (or `false` / `off`) to disable it independently of the model prompt.

## GLM-5.2 and Later

Siada recognizes GLM-5.2 and every later generation (for example `glm-5.2`, `glm-5.2-flash`, `glm-5.3`, `glm-6`, with or without a provider prefix such as `z-ai/`). GLM-5.1 and older keep the previous prompt and repeated-tool behavior; the empty todo-list reminder below applies to all GLM generations. This agent-level change does not alter model-specific reasoning capabilities or provider settings. Only the chat-completions protocol is used for GLM-5.3-and-later models.

**Own-key model settings.** Siada does not infer reasoning capabilities or effort defaults from a custom model's name. Built-in GLM-5.3 entries retain their explicit settings. For a custom `models.json` entry, configure `supports_extra_params: ["reasoning_effort"]` if you want to use `/effort`, and set `default_reasoning_effort` if you want Siada to use a configured default level; otherwise, the gateway determines the default reasoning behavior. API-key provider entries with no matching built-in model also leave these fields unset.

**Agent adaptations.** For the main coding agent on these models, Siada:

- builds the system prompt from the ZCode CLI system prompt template (identity renamed to Siada), while preserving Siada's `edit_file` tools, Git safety, non-interactive approval rules, skill and agent catalogs, and combined memory;
- adds one hidden reminder as a user message after three consecutive, identical tool calls, asking the model to use the results or change its approach.

The GLM reminder is also a hidden `role=user` message; it is never sent as a mid-conversation system message or shown in chat history. The GLM prompt profile and repeated-tool reminder are enabled whenever the model is GLM-5.2 or later; they have no separate opt-out switches.

`SIADA_TODO_EMPTY_LIST_REMINDER=0` (or `false` / `off`) turns off the proactive empty-list reminder for GLM models of any generation. When enabled, after at least 10 assistant turns without `todo_write` (and 10 turns since the previous reminder), Siada also reminds a GLM model when its todo list is still empty. Other models only receive reminders for existing todo lists. Turning off this switch does not disable reminders for existing lists.

## Kimi K3 and Later

The main coding agent uses a Kimi Code-based prompt for Kimi K3 and every later generation, including `kimi-k3`, `kimi-k3.1`, `kimi-k3.5`, and `kimi-k4`. Detection is case-insensitive and accepts provider prefixes (`vendor-kimi-k4`, `openai/kimi-k3.5`), underscore separators (`kimi_k3.1`), and suffixes such as `-preview`. Short aliases `k3`, `k3.1`, `k3.5`, and `k4`, including slash-qualified forms such as `openai/k4`, select the same prompt. Configure the exact model ID accepted by your endpoint; prompt recognition does not translate aliases into API model IDs.

Kimi K2 and older retain the generic prompt. The Kimi prompt replaces the generic four-line response limit and strict skill usage block with terminal communication and relevant-skill guidance, while preserving Siada's `edit_file` tools, Git safety, non-interactive approval rules, skill and agent catalogs, and combined memory.

## Configuration Priority

The configuration priority order is:

1. Command line arguments (`--model`, `--provider`)
2. `llm_config` in configuration file `~/.siada-cli/conf.yaml`
3. `default_model` in `models.json`
4. System defaults

## Important Notes

- **Configuration File Format**: Ensure the JSON format is correct, you can use online JSON validators to check
- **Model Names**: `model_name` must exactly match the model names supported by your API provider
- **API Configuration**: When using the default provider, you must configure `BASE_URL` and `API_KEY`
- **Compatibility**: The configured model parameters should match the actual capabilities of the API provider's models. Except for the retained Claude/Gemini and GPT-5+ Responses paths, the default provider requires an OpenAI Chat Completions-compatible endpoint; arbitrary LiteLLM-native providers are not automatically supported
