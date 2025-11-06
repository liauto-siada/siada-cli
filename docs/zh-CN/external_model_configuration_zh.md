# 外部模型配置

用户自定义模型配置指南

## 概述

当使用 `--provider default` 时，Siada 支持从本地配置文件加载用户自定义的模型配置。这允许你配置自己的模型集合和默认模型。

## 配置文件位置

模型配置文件位于：`~/.siada-cli/models.json`

## 配置文件格式

配置文件使用 JSON 格式，包含以下字段：

```json
{
  "default_model": "模型名称",
  "models": [
    {
      "model_name": "模型名称",
      "context_window": 上下文窗口大小,
      "max_tokens": 最大输出token数（可选）,
      "supports_images": 是否支持图片（可选，默认false）,
      "supports_prompt_cache": 是否支持提示缓存（可选，默认false）,
      "supports_extra_params": ["额外参数列表"]（可选）
    }
  ]
}
```

## 配置示例

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

## 字段说明

### default_model（可选）
- **类型**：字符串
- **说明**：当用户没有通过命令行指定模型时使用的默认模型
- **示例**：`"gpt-4"`

### models（必需）
模型配置数组，每个模型包含以下字段：

#### model_name（必需）
- **类型**：字符串
- **说明**：模型的名称，支持两种格式：
  1. **标准模型名**：如 `gpt-4`、`claude-3-opus` 等，系统会自动添加协议前缀（详见[模型命名规范](#模型命名规范)）
  2. **完整格式**：`协议/模型名`，如 `anthropic/claude-3-opus`、`openai/gpt-4-turbo`
- **示例**：`"gpt-4"`, `"anthropic/claude-3-opus"`, `"deepseek/deepseek-chat"`

#### context_window（必需）
- **类型**：整数
- **说明**：模型支持的上下文窗口大小（token数）
- **示例**：`128000`, `200000`

#### max_tokens（可选）
- **类型**：整数
- **说明**：模型单次输出的最大token数
- **默认值**：如果不指定，将使用模型的默认值
- **示例**：`4096`, `8192`

#### supports_images（可选）
- **类型**：布尔值
- **说明**：模型是否支持图片输入
- **默认值**：`false`
- **示例**：`true`, `false`

#### supports_prompt_cache（可选）
- **类型**：布尔值
- **说明**：模型是否支持提示缓存功能
- **默认值**：`false`
- **示例**：`true`, `false`

#### supports_extra_params（可选）
- **类型**：字符串数组
- **说明**：模型支持的额外参数列表
- **默认值**：`null`
- **可选值**：`["reasoning_effort"]`, `["thinking_tokens"]`
- **示例**：`["reasoning_effort"]`

## 模型命名规范

模型名称支持两种格式：**标准模型名**和**完整格式**（协议/模型名）。

### 格式说明

模型名的完整格式为：`协议/模型名`

- **协议**：决定了最终访问的 API 接口类型和规范
- **模型名**：具体的模型标识符，需符合接口约束

示例：
- `anthropic/claude-3-opus` - 使用 Anthropic 原生协议访问 Claude 3 Opus
- `openai/gpt-4-turbo` - 使用 OpenAI 原生协议访问 GPT-4 Turbo
- `deepseek/deepseek-coder` - 使用 DeepSeek 原生协议访问 DeepSeek Coder

### 自动协议映射

为了简化配置，系统会自动为以下标准模型名添加协议前缀：

| 模型名前缀 | 自动映射为 | API 协议 |
|-----------|-----------|---------|
| `claude-*` | `anthropic/claude-*` | Anthropic |
| `gpt-*` | `openai/gpt-*` | OpenAI |
| `o3-*` | `openai/o3-*` | OpenAI |
| `deepseek-*` | `deepseek/deepseek-*` | DeepSeek |
| `gemini-*` | `google/gemini-*` | Google |
| `kimi-*` | `moonshotai/kimi-*` | Moonshot AI |

**查看完整实现**：[siada/provider/default/coverter.py](../../siada/provider/default/coverter.py)

### 使用说明

- 标准模型名（如 `gpt-4`）会自动映射为完整格式（`openai/gpt-4`）
- 显式指定协议的模型名（如 `anthropic/claude-3-opus`）按原样使用
- 完整配置示例请参考上文的[配置示例](#配置示例)章节

## 使用方法

### 1. 创建配置文件

首先，在 `~/.siada-cli/` 目录下创建 `models.json` 文件：

```bash
mkdir -p ~/.siada-cli
nano ~/.siada-cli/models.json
```

### 2. 配置 API 连接信息

在 `~/.siada-cli/conf.yaml` 中配置 `base_url` 和 `api_key`：

```yaml
llm_config:
  provider: default
  model: openai/gpt-4  # 可选，如果不指定将使用 models.json 中的 default_model
  base_url: https://your-api-endpoint.com/v1
  api_key: your-api-key-here
```

或者使用环境变量：

```bash
export BASE_URL=https://your-api-endpoint.com/v1
export API_KEY=your-api-key-here
```

> **💡 提示：不同协议的 base_url 配置**
> 
> - **OpenAI 兼容协议**（如 `openai/*`、`deepseek/*` 等）：需要包含 `/v1` 路径
>   - 示例：`https://api.openai.com/v1`
> 
> - **Anthropic 协议**（`anthropic/*`）：
>   - 方式1：不包含路径后缀，如 `https://api.anthropic.com`
>   - 方式2：包含完整路径，如 `https://api.anthropic.com/v1/messages`

### 3. 运行 Siada

使用 default provider：

```bash
# 使用配置文件中的默认模型
siada --provider default

# 指定特定模型
siada --provider default --model openai/gpt-4

# 或者在 conf.yaml 中配置 provider，直接运行
siada
```

## 配置优先级

配置的优先级顺序为：

1. 命令行参数（`--model`, `--provider`）
2. 配置文件 `~/.siada-cli/conf.yaml` 中的 `llm_config`
3. `models.json` 中的 `default_model`
4. 系统默认值

## 注意事项

- **配置文件格式**：确保 JSON 格式正确，可以使用在线 JSON 验证工具检查
- **模型名称**：`model_name` 必须与你的 API 提供商支持的模型名称完全一致
- **API 配置**：使用 default provider 时，必须配置 `BASE_URL` 和 `API_KEY`
- **兼容性**：配置的模型参数应该与实际 API 提供商的模型能力匹配
