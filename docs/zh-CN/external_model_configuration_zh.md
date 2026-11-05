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
前提是尚未把正文、工具事件或未知事件交给下游；思考继续实时输出，
也不会阻止重试，因此失败后可能显示另一次尝试的思考内容。
交出正文或工具事件后异常会直接传播，避免重复输出或工具调用。
空消息、空思考条目和空文本片段会与生命周期事件一起缓冲，
因此服务发版期间在这些起始事件后断连（`RemoteProtocolError`，包括
`incomplete chunked read`）仍可重试。
只输出思考后流结束、缺少最终响应事件时，也允许重试。
两次重试分别等待 1～2 秒和 2～3 秒。
上下文 admission 只执行一次，嵌套包装器共享
同一传输重试预算。直接 completion 客户端仍使用自身策略。协议路由和异常矩阵
详见 [Provider 路由与异常重试 wiki](../wiki/17_provider-routing-retries.md)。

Responses 错误日志包含有长度限制的 message/code/type/param、可用的请求与 trace ID、
模型、response ID、最后一个流事件和是否已交出输出。这些诊断记录不打印请求正文、
完整错误 body 或认证请求头。协议 `error` 和 `response.failed` 事件也按相同规则处理。

主会话在缺少最终响应、超时或连接中断后，还会最多进行两次会话续跑。续跑前读取
已保存的会话历史和已完成的工具结果，保留已经执行的操作；尚未完整生成的工具调用
不会执行，也不会复制进历史。如果本次输入尚未成功保存，恢复时保留原始输入。
连续中断超过额度仍会报错；取消操作会立即停止恢复。
如果历史已被改写，或消息格式无法确认输入是否保存，恢复也会停止，避免重复发送
保存状态不确定的输入。

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
（包括 `li` 和 `default` 供应商）对所有模型统一保留已经产生的工具结果图片。
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

#### effort_choices（可选）

- **类型**：非空数组，元素为 `"low"`、`"medium"`、`"high"`、`"xhigh"` 或 `"max"`
- **说明**：覆盖按模型家族推断的 effort 级别。`/effort` 输入提示、选择框和参数校验严格使用这些选项；从其他模型保存的 effort 会映射到允许的级别。
- **默认值**：`null`（按模型家族推断）
- **前置条件**：`supports_extra_params` 中需包含 `"reasoning_effort"`，`default_reasoning_effort` 应设为选项之一。
- **示例**：`"effort_choices": ["max"]`

## 模型命名规范

模型名称支持两种格式：**标准模型名**和**完整格式**（协议/模型名）。

### 格式说明

模型名的完整格式为：`协议/模型名`

- **协议/模型前缀**：标识 Siada 使用的模型家族或供应商路由
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
| `gpt-*` | `openai/gpt-*` | OpenAI Chat Completions；GPT-5 及以上仅支持 Responses |
| `o3-*` | `openai/o3-*` | OpenAI Chat Completions |
| `deepseek-*` | `deepseek/deepseek-*` | OpenAI 兼容 Chat Completions |
| `gemini-*` | `google/gemini-*` | Gemini 原生协议/LiteLLM |
| `kimi-*` | `moonshotai/kimi-*` | OpenAI 兼容 Chat Completions |

**查看完整实现**：[siada/provider/default/coverter.py](../../siada/provider/default/coverter.py)

### 使用说明

- 标准模型名（如 `gpt-4`）会映射为“供应商/模型”形式；OpenAI Chat Completions 请求会去掉 LiteLLM 路由前缀，只发送 endpoint 接受的模型 ID
- Claude 和 Gemini 保持现有 LiteLLM/原生路由。其他 default provider 模型必须使用支持 OpenAI Chat Completions 的 endpoint；仅指定 LiteLLM 原生协议前缀并不能保证 endpoint 兼容
- GPT-5 及更新版本使用 Responses API；其他仅支持 Responses 的别名不会发送到 Chat Completions
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
>   - 走 Chat 路由的模型必须支持 `POST /chat/completions`，配置的模型 ID 必须是该 endpoint 能识别的 ID
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

对**所有模型**，主编码 Agent 会在 Git 工作区的会话首次用户请求中，将有上限的 Git 快照（分支、HEAD、工作树摘要及采集时间）作为单独的、由 `<system-reminder>` 包裹的隐藏 `input_text` 内容项追加到同一条用户消息，而不另起一条用户消息。它会写入会话的 `api_history.json`，供后续轮次和 `/resume` 复用；上下文压缩后，模型可见的 `api_messages.json` 中会刷新快照。仍兼容旧会话中的独立快照消息。非 Git 工作区或采集失败时不加入。隐藏内容项不会作为会话中途的 system 消息发送，也不会显示在聊天历史中。设置 `SIADA_GIT_SNAPSHOT=0`（或 `false` / `off`）可以单独关闭快照，不影响模型提示配置。

## GLM-5.2 及后续模型

Siada 会识别 GLM-5.2 及其后续所有版本（例如 `glm-5.2`、`glm-5.2-flash`、`glm-5.3`、`glm-6`，可带或不带 `z-ai/` 等供应商前缀）。GLM-5.1 及更早版本仍保持原有的提示词和重复工具调用提醒行为；下文的空待办清单提醒适用于所有 GLM 版本。本次 Agent 层调整不改变不同模型的推理能力或供应商配置。GLM-5.3 及后续模型仅使用 chat completions 协议。

**自有 API Key 的模型设置。** Siada 不再根据自定义模型名称推断推理能力或默认推理级别；内置的 GLM-5.3 条目仍保留各自显式声明的配置。如果希望在自定义 `models.json` 条目中使用 `/effort`，请配置 `supports_extra_params: ["reasoning_effort"]`；如果希望 Siada 使用指定的默认级别，请设置 `default_reasoning_effort`。未设置时由网关决定默认推理行为。API Key 供应商提供但没有匹配内置条目的模型也不会自动填充这些字段。

**Agent 适配。** 在这些模型上，主编码 Agent 会：

- 基于 ZCode CLI 系统提示词模板构建系统提示（产品身份替换为 Siada），同时保留 Siada 的 `edit_file` 工具、Git 安全、非交互模式下的审批规则、技能与代理目录和组合记忆；
- 在连续三次参数相同的工具调用之后，以 user 消息加入一条隐藏提醒，要求模型利用已有结果或改变做法。

GLM 专属提醒也以隐藏的 `role=user` 消息发送，不会作为会话中途的 system 消息，也不会显示在聊天历史中。GLM-5.2 及后续模型始终启用 GLM 系统提示段落和重复工具调用提醒；这两项不再有单独的关闭开关。

设置 `SIADA_TODO_EMPTY_LIST_REMINDER=0`（或 `false` / `off`）仍可关闭 GLM 全系列模型的空列表主动提醒。功能开启时，若连续至少 10 个 assistant 轮次未调用 `todo_write`（且距上次提醒也已满 10 轮），即使待办清单为空，Siada 也会提醒 GLM 模型。其他模型仅在已有待办清单时收到更新提醒；关闭此开关不会关闭已有列表的更新提醒。

## Kimi K3 及后续模型

主编码 Agent 会为 Kimi K3 及其后续所有版本使用基于 Kimi Code 的提示词，包括 `kimi-k3`、`kimi-k3.1`、`kimi-k3.5` 和 `kimi-k4`。识别不区分大小写，支持供应商前缀（`vendor-kimi-k4`、`openai/kimi-k3.5`）、下划线分隔（`kimi_k3.1`）和 `-preview` 等后缀。简写 `k3`、`k3.1`、`k3.5`、`k4` 及 `openai/k4` 等斜杠前缀形式也使用同一套提示词。配置时仍需填写 endpoint 接受的准确模型 ID；提示词识别不会把别名转换成 API 模型 ID。

Kimi K2 及更早版本继续使用通用提示词。Kimi 提示词用终端沟通和按任务选择技能的指导替换通用的“四行以内”限制及严格技能触发规则，同时保留 Siada 的 `edit_file` 工具、Git 安全、非交互模式下的审批规则、技能与代理目录和组合记忆。

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
- **兼容性**：配置的模型参数应该与实际 API 提供商的模型能力匹配。除保留的 Claude/Gemini 路径和 GPT-5 及以上 Responses 路径外，default provider 要求 endpoint 兼容 OpenAI Chat Completions；不会自动支持任意 LiteLLM 原生协议供应商
