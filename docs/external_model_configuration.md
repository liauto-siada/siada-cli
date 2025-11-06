# External Model Configuration

User-Defined Model Configuration Guide

## Overview

When using `--provider default`, Siada supports loading user-defined model configurations from a local configuration file. This allows you to configure your own model collection and default model.

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
      "supports_extra_params": ["extra_params_list"] (optional)
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
      "supports_extra_params": []
    },
    {
      "model_name": "openai/gpt-3.5-turbo",
      "context_window": 16385,
      "max_tokens": 4096,
      "supports_images": false,
      "supports_prompt_cache": false,
      "supports_extra_params": []
    },
    {
      "model_name": "anthropic/claude-3-opus",
      "context_window": 200000,
      "max_tokens": 4096,
      "supports_images": true,
      "supports_prompt_cache": true,
      "supports_extra_params": []
    },
    {
      "model_name": "deepseek/deepseek-chat",
      "context_window": 128000,
      "max_tokens": 8192,
      "supports_images": false,
      "supports_prompt_cache": false,
      "supports_extra_params": []
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

#### supports_prompt_cache (Optional)
- **Type**: Boolean
- **Description**: Whether the model supports prompt caching
- **Default**: `false`
- **Example**: `true`, `false`

#### supports_extra_params (Optional)
- **Type**: String Array
- **Description**: List of extra parameters supported by the model
- **Default**: `null`
- **Possible Values**: `["reasoning_effort"]`, `["thinking_tokens"]`
- **Example**: `["reasoning_effort"]`

## Model Naming Convention

Model names support two formats: **Standard model name** and **Full format** (protocol/model_name).

### Format Description

The full format of a model name is: `protocol/model_name`

- **Protocol**: Determines the API interface type and specification to be accessed
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
| `gpt-*` | `openai/gpt-*` | OpenAI |
| `o3-*` | `openai/o3-*` | OpenAI |
| `deepseek-*` | `deepseek/deepseek-*` | DeepSeek |
| `gemini-*` | `google/gemini-*` | Google |
| `kimi-*` | `moonshotai/kimi-*` | Moonshot AI |

**View Full Implementation**: [siada/provider/default/coverter.py](../siada/provider/default/coverter.py)

### Usage Notes

- Standard model names (such as `gpt-4`) will be automatically mapped to full format (`openai/gpt-4`)
- Model names with explicitly specified protocols (such as `anthropic/claude-3-opus`) are used as-is
- For complete configuration examples, please refer to the [Configuration Example](#configuration-example) section above

## Usage Guide

### 1. Create Configuration File

First, create the `models.json` file in the `~/.siada-cli/` directory:

```bash
mkdir -p ~/.siada-cli
nano ~/.siada-cli/models.json
```

### 2. Configure API Connection

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
- **Compatibility**: The configured model parameters should match the actual capabilities of the API provider's models
