# 原生 Gemini Model

当前 checkout 提供 `siada.provider.gemini.GeminiModel`，通过 Google 官方
`google-genai` SDK 实现 Agents `Model`。原生 Gemini 请求不经过 LiteLLM 桥接。
现有 `default` 和 `li` provider 的原生 Gemini 路由会选择该 Model，其他模型路由不变。

支持任意连字符前缀的 `xxx-gemini` 或 `xxx-gemini-*` 派生名称，例如
`google-gemini-3.5-flash`、`my-team-gemini-3.5-flash`。原生请求会去掉别名前缀，
使用 `gemini-3.5-flash` 作为模型 ID。匹配忽略大小写，模型 ID 本身的大小写保持不变。
OpenRouter 优先：当 default provider 当前生效的 `BASE_URL` 指向 OpenRouter 时，
这些名称仍走 OpenRouter 兼容路由，不切换到原生 Gemini。显式 `openrouter/...`
路由和现有 endpoint 校验不变。

## default provider 配置

设置 `GEMINI_API_KEY` 或 `GOOGLE_API_KEY`，`API_KEY` 保留为后备配置。
如果 `BASE_URL` 已指向 OpenAI Chat 服务，使用 `GEMINI_BASE_URL` 指定原生
Gemini endpoint；该地址可以带 `/v1beta` 前缀，不能指向 `/chat/completions`。

OpenRouter 保留兼容路由，不属于原生签名无损保证范围；需要完整 Part 回放时应使用
原生 endpoint。Li 路由复用现有鉴权和路由规则，但实际网关透传仍需单独实测。

## 直接注入与资源关闭

可以使用 `GeminiModel("gemini-3.5-flash", client=client)` 注入官方
`genai.Client`。该客户端由调用方拥有，所有请求结束后先
`await client.aio.aclose()`，再 `client.close()`。
完整调用示例见 [英文说明](../gemini_native_model.md#explicit-model-and-client-ownership)。

不传 client 或 transport 时，Model 拥有默认 transport，结束时调用
`await model.close()`。通过应用 provider 创建的 Model 借用 provider 的连接；
应在运行时退出时关闭 provider，不逐个关闭 Model。异步连接不能跨 event loop 复用。

## 历史与支持边界

未压缩的回放必须保存完整 SDK input items，包括不透明的 provider 元数据。
provider 负责恢复文本、思考和工具调用的原始签名片段，agents 框架仅处理标准 SDK
items。不要用展示文本重建保留的 item，也不要修改其已签名文本或工具参数。
原生签名回放要求 Gemini model、provider、backend 不变；其他模型可以消费标准历史，
包括用于生成摘要，但不会使用 Gemini 私有元数据。

从其他模型切换到 Gemini 时，可以复用没有 Gemini 封装的已完成 SDK 函数调用历史。
每次调用需要唯一、非空的 `call_id`、JSON 对象格式的参数，以及对应的文本结果。
适配器会为这些导入的调用提供 Google 文档允许的
`skip_thought_signature_validator` 标记。已有原生 `apply_patch` 和 custom tool
历史也可以通过函数调用代理导入。

兼容转换发生在请求组装时，原始存储历史保持完整。相邻的无签名调用和结果会整理为
完整调用组后接完整结果组，支持交错的并行调用记录；assistant 或 reasoning 消息
可以分隔已完成的步骤。这种兼容方式跳过签名校验，不能恢复旧模型的思考状态，也不能
还原已丢失的原始 Part 与响应组边界。已有 Gemini 签名仍原样回放，原生封装的版本、
来源、签名视图异常或不完整的并行工具组会在发送请求前报错。详见 Google 的
[思考签名迁移 FAQ](https://ai.google.dev/gemini-api/docs/generate-content/thought-signatures?hl=zh-cn)。

工具由 Runner 执行，Google automatic function calling 明确禁用。
首期支持无 namespace 的函数工具、完整函数调用、文本工具结果、文本/思考输出、
用户文本/图片和 JSON 输出 schema；不支持 hosted tools、流式 partial function
arguments、生成图片/音频和服务端 Responses 会话状态。

温度、top-p、输出 token、tool choice、timeout 使用普通 `ModelSettings`。
原生参数通过 `extra_body` 或 `extra_args` 使用官方 `GenerateContentConfig`
字段，例如 `thinking_config`；不能通过它们覆盖工具、历史、凭据或 HTTP options。
Gemini 3 和 4 的 `ModelSettings.reasoning.effort` 映射为 thinking level，旧模型使用
原生 thinking 配置。`effort="none"` 发送零 thinking budget，能否关闭思考取决于
Google 模型；需要思考文本时设置 `reasoning.summary`。

Gemini 与其他模型使用同一套已配置的压缩策略，包括 header 摘要、近期边界保留和
完整工具组裁剪。压缩可以移除较早的 items；每个保留的 item 自带其原始签名片段，
provider 在会话重载或 checkpoint 恢复后还原片段顺序和并行调用分组。已有签名的
Part 绝不会被校验绕过标记替代。预算采用近似 UTF-8 字节估算，不是 Google
tokenizer，实际 usage 仍用于校准。Generation span 仅记录模型分类和 usage，
telemetry 去除 provider 元数据；会话文件仍应按敏感数据管理。
