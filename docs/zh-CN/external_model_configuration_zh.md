# 外部模型配置

用户自定义模型配置指南

## 概述

当使用 `--provider default` 时，Siada 支持从本地配置文件加载用户自定义的模型配置。这允许你配置自己的模型集合和默认模型。

经 `ModelWrapper` 的 agent 调用会对传输超时、连接失败、LiteLLM midstream
异常和临时 OpenAI API 错误最多重试两次，采用指数退避和随机抖动。API 重试覆盖
HTTP 403/408/409/429/5xx、已识别的服务端故障/过载/超时错误码，以及未分类的
`Unknown stream error`。流中明确的非临时错误码（如参数错误、配额不足）会直接传播。
HTTP 403 认证失败共用上述重试预算；连续失败仍会在三次模型调用后抛出。
包装器不会刷新认证凭证。
重试同时覆盖创建流和消费流，
前提是尚未把正文、工具事件或未知事件交给下游；思考 delta 继续实时输出，
思考条目、片段事件也允许重试，因此失败后可能显示另一次尝试的思考内容。
交出正文或工具事件后异常会直接传播，避免重复输出或工具调用。
空消息、空思考条目和空文本片段会与生命周期事件一起缓冲，
因此服务发版期间在这些起始事件后断连（`RemoteProtocolError`，包括
`incomplete chunked read`）仍可重试；尚未交出任何事件的失败尝试会丢弃 response ID
和 item ID，思考输出后的重试会发送新的响应生命周期事件。
缓冲最多容纳 64 个空起始事件，缓冲已满时交出事件但仍允许重试。
只输出思考后流结束、缺少最终响应事件时，也允许重试。
两次重试分别等待 1～2 秒和 2～3 秒。
思考条目的完成事件会暂存到本次请求关闭重试窗口时再交出，避免 Runner 在最终
`output` 为空时补齐输出，将失败尝试的思考条目写进会话历史。
上下文 admission 只执行一次，嵌套包装器共享
同一传输重试预算。直接 completion 客户端仍使用自身策略。协议路由和异常矩阵
详见 [Provider 路由与异常重试 wiki](../wiki/17_provider-routing-retries.md)。

Responses 错误日志包含有长度限制的 message/code/type/param、可用的请求与 trace ID、
模型、response ID、最后一个流事件和是否已交出正文、工具或未知事件。这些诊断记录不打印请求正文、
完整错误 body 或认证请求头。协议 `error` 和 `response.failed` 事件也按相同规则处理。

## 使用 API Key 配置 DeepSeek

首次登录或输入 `/configure` 后，选择 **Configure API Key → DeepSeek**，
选择模型并输入 DeepSeek API Key。接口地址自动填为 `https://api.deepseek.com/v1`；
模型和凭据会保存到 `~/.siada-cli/conf.yaml`，其中 `provider: default`、
`provider_id: deepseek`。

离线预设包含 `deepseek-flash` 和 `deepseek-v4-pro`（1M 上下文）。
有 models.dev 缓存时，向导使用缓存中支持工具调用的 DeepSeek 模型；
旧缓存缺少可用的 DeepSeek 模型时使用预设。通过向导配置无需手动创建 `models.json`。

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
      "supports_extra_params": ["额外参数列表"]（可选）,
      "parallel_tool_calls": 是否支持并行工具调用（可选，默认null）
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

此能力同时控制用户附图和通过 `edit_file` 读取图片。Chat Completions 转换路径
（包括 `default` 供应商）对所有模型统一保留已经产生的工具结果图片。
转换时不检查 `supports_images`，也不依赖请求上下文，因此能力为 `false`
或缺失不会导致工具结果图片被丢弃。已保存的会话历史保持不变。

Chat Completions endpoint 需要接受 `role: tool` 消息中的图片内容。
支持用户消息中的图片并不意味着支持工具结果图片；标准 OpenAI Chat Completions
协议不支持这种格式。不兼容的 endpoint 需要另行适配消息协议。
文本模型现有的 vision bridge 行为保持不变。

#### supports_prompt_cache（可选）
- **类型**：布尔值
- **说明**：模型是否支持提示缓存功能
- **默认值**：`false`
- **示例**：`true`, `false`

#### parallel_tool_calls（可选）
- **类型**：布尔值
- **说明**：模型是否支持并行工具调用。启用后，模型可以在单次响应中同时调用多个独立的工具，提升执行效率。对于 Claude 模型，该参数会通过 prompt 级别控制并行行为；对于 OpenAI/Gemini 等模型，该参数会直接传递给 API
- **默认值**：`null`（不传递该参数）
- **推荐值**：
  - Claude、GPT、Gemini 系列：`true`
  - DeepSeek、Kimi、GLM、MiniMax 系列：`false`
- **示例**：`true`, `false`

#### supports_extra_params（可选）
- **类型**：字符串数组
- **说明**：模型支持的额外参数列表
- **默认值**：`null`
- **可选值**：`["reasoning_effort"]`, `["thinking_tokens"]`
- **示例**：`["reasoning_effort"]`

#### default_thinking_tokens（可选）
- **类型**：整数
- **说明**：设置后，模型启动时将自动开启推理/思考模式，无需通过命令行参数手动开启。数值本身**不会**作为 token 预算发送——推理深度仅由 `reasoning_effort` 控制（见下），本配置只作为"开启思考"的信号
- **默认值**：`null`（不开启推理）
- **特殊值**：
  - `-1`：自适应推理模式（adaptive thinking），适用于 Claude 4.6+ 等支持自适应推理的模型
  - 正整数（如 `1024`）：开启思考，推理深度使用模型/网关的默认值
- **前置条件**：`supports_extra_params` 中需包含 `"thinking_tokens"`
- **示例**：`-1`（自适应模式）, `1024`（默认深度思考）

#### default_reasoning_effort（可选）
- **类型**：字符串
- **说明**：模型默认的推理努力级别。设置后，模型启动时将自动使用指定的推理努力等级
- **默认值**：`null`（不设置推理努力级别）
- **可选值**：`"low"`、`"medium"`、`"high"`
- **前置条件**：`supports_extra_params` 中需包含 `"reasoning_effort"`
- **示例**：`"low"`

## 模型命名规范

模型名称支持两种格式：**标准模型名**和**完整格式**（协议/模型名）。

### 格式说明

模型名的完整格式为：`协议/模型名`

- **协议/模型前缀**：标识 Siada 使用的模型家族或供应商路由
- **模型名**：具体的模型标识符，需符合接口约束

示例：
- `anthropic/claude-3-opus` - 使用 Anthropic 原生协议访问 Claude 3 Opus
- `openai/gpt-4-turbo` - 使用 OpenAI Chat Completions 访问 GPT-4 Turbo
- `deepseek/deepseek-coder` - 使用兼容 OpenAI 的端点访问 DeepSeek Coder

### 自动协议映射

为了简化配置，系统会自动为以下标准模型名添加协议前缀：

| 模型名前缀 | 自动映射为 | API 协议 |
|-----------|-----------|---------|
| `claude-*` | `anthropic/claude-*` | Anthropic |
| `gpt-*` | `openai/gpt-*` | OpenAI Chat Completions；GPT-5 及以上使用 Responses |
| `o3-*` | `openai/o3-*` | OpenAI Chat Completions |
| `deepseek-*` | `deepseek/deepseek-*` | 兼容 OpenAI 的 Chat Completions |
| `gemini-*` | `google/gemini-*` | Gemini 原生协议/LiteLLM |
| `kimi-*` | `moonshotai/kimi-*` | 兼容 OpenAI 的 Chat Completions |

**查看完整实现**：[siada/provider/default/coverter.py](../../siada/provider/default/coverter.py)

### 使用说明

- 标准模型名（如 `gpt-4`）会映射为“供应商/模型”形式；OpenAI Chat Completions 请求会去掉 LiteLLM 路由前缀，只发送端点接受的模型 ID。
- Claude 和 Gemini 保留原有 LiteLLM/原生路由。其他 default provider 模型必须使用支持 OpenAI Chat Completions 的端点；仅填写 LiteLLM 原生协议前缀并不能保证兼容。
- GPT-5 及后续版本使用 Responses API；其他仅支持 Responses 的别名也不会发到 Chat Completions。
- Responses 请求固定使用 `store: false`，回放完整的已保存历史。启用推理时，`reasoning.context` 统一为 `all_turns`，并请求用于回放的加密推理内容。调用方设置不能启用服务端存储，也不能把推理回放限制为当前轮次。
- 完整配置示例请参考上文的[配置示例](#配置示例)章节

## 使用方法

### 1. 创建配置文件

首先，在 `~/.siada-cli/` 目录下创建 `models.json` 文件：

```bash
mkdir -p ~/.siada-cli
nano ~/.siada-cli/models.json
```

### 2. 配置 API 连接信息

在 Siada UI 中运行 `/configure`，选择供应商、模型并输入 API Key。
可以重复运行该命令来更新 Key 或切换供应商，无需重启。
提交过程中也可以按 Esc 取消配置。

每次配置只接收一条回复。后台仍在等待选择时，Esc 可以取消；
已经接受的提交不会因随后按 Esc 而撤销。
重复和过期的回复会被忽略，避免影响后续命令。

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
>   - Chat 路由的模型必须支持 `POST /chat/completions`；模型 ID 必须是该端点接受的 ID
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

## Git 快照（所有模型）

主编码 Agent 会为所有模型在 Git 工作区的首次用户请求中，追加一项有界的 Git 快照，
包含分支、HEAD、工作树摘要及采集时间。快照以 `<system-reminder>` 包裹的隐藏
`input_text` 内容项保存到同一条用户消息中，并写入会话的 `api_history.json`。
后续轮次和 `/resume` 会复用快照，压缩后在模型使用的已准备上下文
`api_message.json` 中刷新；旧会话迁移前使用 `api_messages.json`。
仍兼容旧会话中的独立快照消息。非 Git 工作区或采集失败时不添加快照。
快照是上下文数据，不扩大授权，不作为会话中途的 system 消息发送，也不显示在聊天历史中。
设置 `SIADA_GIT_SNAPSHOT=0`（或 `false` / `off`）可关闭快照。

## GLM-5.2 及后续模型

Siada 识别 GLM-5.2 及后续版本，例如 `glm-5.2`、`glm-5.2-flash`、`glm-5.3`、
`glm-6`，也支持带供应商前缀的名称。GLM-5.1 及更早版本保留原有提示词和重复工具调用行为。
这些提示词适配不改变模型的推理能力或供应商设置。GLM-5.3 及后续版本使用 Chat Completions。

自定义模型名不会自动推断推理支持或默认努力级别；内置 GLM-5.3 条目保留显式配置。
自定义 `models.json` 条目可通过 `supports_extra_params: ["reasoning_effort"]` 启用
`/effort`，通过 `default_reasoning_effort` 指定默认级别。未显式指定时由网关决定默认
推理行为。API Key 供应商提供、但没有匹配内置条目的模型也不会自动填充这些设置。

主编码 Agent 在 GLM-5.2 及后续模型上基于 ZCode CLI 系统提示词模板构建系统提示
（产品身份替换为 Siada），同时保留 Siada 的 `edit_file` 工具、Git 安全、非交互模式下
的审批规则、技能与代理目录和组合记忆。连续三次调用同一工具且参数相同后，会加入一条
隐藏 user-role 提醒，要求使用已有结果或改变做法。GLM 提示词和重复调用提醒没有单独的
关闭开关。

GLM 全系列模型连续至少十个 assistant 轮次未调用 `todo_write` 时，还可收到空列表提醒，
两次提醒至少相隔十轮。设置 `SIADA_TODO_EMPTY_LIST_REMINDER=0`（或 `false` / `off`）
可关闭空列表提醒。其他模型仅在已有待办清单时收到提醒；该开关不关闭已有清单的提醒。
提醒是隐藏运行时上下文，不是 system-role 消息，也不扩大授权。

## Kimi K3 及后续模型

主编码 Agent 为 Kimi K3 及后续版本使用基于 Kimi Code 的提示词，包括 `kimi-k3`、
`kimi-k3.1`、`kimi-k3.5` 和 `kimi-k4`。识别不区分大小写，支持供应商前缀
（`vendor-kimi-k4`、`openai/kimi-k3.5`）、下划线（`kimi_k3.1`）及 `-preview` 等后缀。
简写 `k3`、`k3.1`、`k3.5`、`k4` 和 `openai/k4` 等斜杠前缀形式也会选择同一套提示词。
仍需填写端点接受的准确模型 ID；提示词识别不会把别名重写成 API 模型 ID。

Kimi K2 及更早版本保留通用提示词。Kimi 提示词使用终端沟通和按任务选择技能的指导，
替代通用的四行回复限制及严格技能触发段落；仍保留 Siada 的 `edit_file` 工具、Git 安全、
权限边界、非交互模式的阻碍报告、技能与代理目录及组合记忆。

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
- **兼容性**：模型参数必须与端点能力匹配。除 Claude/Gemini 和 GPT-5 及以上的 Responses 路由外，default provider 要求端点兼容 OpenAI Chat Completions；不会自动支持任意 LiteLLM 原生协议供应商。
