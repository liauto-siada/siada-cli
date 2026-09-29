# 自定义 Agent（`.agents/agents/`）

**简体中文 | [English](../USER_AGENTS.md)**

自定义 Agent 让你用 Markdown 文件定义自己的专用子 Agent。主 Agent 会在系统提示词里看到它们，并通过 `run_subtask` 工具把一件边界清晰的任务派给它——每个命名 Agent 都自带系统提示词、工具集、技能、MCP 服务器、后台偏好、推理强度与模型。

## 目录

- [概述](#概述)
- [快速开始](#快速开始)
- [定义文件放在哪里](#定义文件放在哪里)
- [定义文件格式](#定义文件格式)
- [字段说明](#字段说明)
  - [`name` 与 `description`](#name-与-description)
  - [`tools`](#tools)
  - [`skills`](#skills)
  - [`mcpServers`](#mcpservers)
  - [`background`](#background)
  - [`effort`](#effort)
  - [`model`](#model)
- [运行时会发生什么](#运行时会发生什么)
- [优先级与去重](#优先级与去重)
- [示例](#示例)
- [与 Claude Code Agent 文件的兼容性](#与-claude-code-agent-文件的兼容性)
- [故障排查](#故障排查)
- [相关文档](#相关文档)

## 概述

自定义 Agent 可以理解为 Skill 的"子 Agent 版"：

| | Skill（`SKILL.md`） | 自定义 Agent（`agents/*.md`） |
|---|---|---|
| 用途 | Agent 读取的可复用指令 | 一个带独立提示词与配置的命名子 Agent |
| 消费方 | 主 Agent（系统提示词中的技能目录） | `run_subtask(agent="<名字>")` |
| 额外配置 | — | `tools`、`skills`、`mcpServers`、`background`、`effort`、`model` |

定义文件在**每次构建提示词、每次 spawn 时**都会从磁盘重新读取，因此新增或修改定义在下一轮对话即可生效，无需重启。

## 快速开始

1. 在项目中创建目录与定义文件：

   ```bash
   mkdir -p .agents/agents
   ```

   ```markdown
   <!-- .agents/agents/code-reviewer.md -->
   ---
   name: code-reviewer
   description: 审查代码改动中的缺陷、风格与安全问题。在完成一次实现后使用。
   tools: [read_file, regex_search_files, run_cmd]
   skills: [wiki]
   effort: high
   ---

   你是一名严谨的代码审查者。每条发现都要给出文件、行号、问题原因和具体修复建议。
   不要自己改代码——只报告发现。
   ```

2. 启动（或继续使用）`siada-cli`，主 Agent 就会在提示词里看到这个 Agent：

   ```
   AGENT TYPES
   ...
   Available agents (name — description):
   - `code-reviewer` — 审查代码改动中的缺陷、风格与安全问题。在完成一次实现后使用。
   ```

3. 提出与描述匹配的任务，例如"实现 X，然后让 code-reviewer 审查这次改动"。主 Agent 会以
   `agent: "code-reviewer"` 调用 `run_subtask`，并把子 Agent 的摘要汇报给你。

## 定义文件放在哪里

每个根目录都是一个 `agents/` 目录；定义文件是 `.md` 文件，可以放在子目录中（递归发现）。

| 作用域 | 目录（优先级由低到高） |
|--------|------------------------|
| 仓库级 | `<项目>/.claude/agents/` → `<项目>/.siada/agents/` → `<项目>/.agents/agents/` → `<项目>/.siada-cli/agents/` |
| 用户级 | `~/.claude/agents/` → `~/.agents/agents/` → `~/.siada-cli/agents/` |

仓库级作用域以 Agent 的工作目录为基准解析。推荐使用 `.agents/agents/`；`.siada-cli/agents/` 是 Siada 的规范位置，`.claude/agents/` 用于兼容 Claude Code。

## 定义文件格式

定义是带 YAML frontmatter 的 Markdown 文件：

```markdown
---
name: researcher
description: 在网络上调研某个主题并返回带出处的摘要。
tools: [web_search, web_fetch, read_file]
mcpServers:
  - lark
background: true
effort: medium
---

这里是系统提示词。像给同事交底一样写清楚：这个 Agent 负责什么、应该怎么做事、
最终答案必须包含什么。
```

- **frontmatter** 配置这个 Agent；
- **正文** 会追加到子 Agent 的标准指令之后（无人值守规则始终在最前面，正文紧随其后）。

frontmatter 的轻微书写瑕疵会被容忍：例如 `description` 里含未加引号的 `": "`（第三方 Agent 包常见写法），定义依然会加载，而不是直接失败。

## 字段说明

### `name` 与 `description`

两者都是**必填**。缺任何一个该文件都会加载失败并记录一条加载错误（同目录的其它定义不受影响）。

- `name`（最长 64 字符）：Agent 的标识名。`run_subtask` 解析 `agent="<名字>"` 时**不区分大小写**。
- `description`（最长 1024 字符）：何时使用该 Agent。这段文字会进入主 Agent 看到的 `AGENT TYPES` 段，所以请写成触发条件（"当……时使用"），而不是宣传语。

### `tools`

限定子 Agent 的工具集，支持三种写法：

```yaml
tools: [read_file, regex_search_files, run_cmd]   # YAML 列表
tools: read_file, regex_search_files, run_cmd     # 逗号分隔字符串
tools: ['*']                                      # 全部默认工具
```

语义：

- **省略** → 使用默认子 Agent 工具集，不做裁剪。
- **`['*']`** → 等同于省略。
- **给出列表** → 只保留列出的工具。
- 未知名字会被丢弃并在日志里打 warning。
- 如果一个都没匹配上，会退回默认工具集——定义永远不会产出一个"没有工具"的 Agent。

默认子 Agent 工具集（随模型族变化）：

| 工具 | 说明 |
|------|------|
| `read_file` + `apply_patch` | 原生 patch 模型（GPT-5 及更新、Astra） |
| `edit_file` | 其它所有模型 |
| `regex_search_files`、`run_cmd`、`list_code_definition_names` | 始终存在 |
| `web_search`、`web_fetch` | 开启 web 工具时 |
| `run_powershell` | 可用时 |
| `run_subtask` | 仅在 `sub_agent.allow_recursive_subagents` 开启时 |

`read_file`、`edit_file`、`apply_patch` 被视为一组：写了其中任意一个，就会保留当前模型实际提供的文件工具，因此同一份定义可以跨模型使用。

Claude Code 的工具名同样可用，会自动映射（`Read`→`read_file`、`Bash`→`run_cmd`、`Grep`/`Glob`→`regex_search_files`、`Task`→`run_subtask`、`TodoWrite`→`todo_write`、`WebSearch`/`WebFetch`→`web_search`/`web_fetch`、`Write`/`Edit`→`edit_file`）。

### `skills`

需要**预加载**的技能名列表。spawn 时会读取这些技能的 `SKILL.md` 正文，内联到子 Agent 提示词的 `## Preloaded Skills` 段，子 Agent 无需自己去发现和读取。

```yaml
skills: [wiki, open-source-release]
```

- 技能解析复用主 Agent 的同一套加载器，`.agents/skills/`、`.siada-cli/skills/`、插件技能都可引用。
- 未知技能名会打 warning 后跳过；技能文件读取失败也只跳过该技能，都不会阻断 spawn。
- 子 Agent 仍然会收到技能目录提示，可以按需读取其它技能。

### `mcpServers`

只在**该次运行**内挂载给子 Agent 的 MCP 服务器。

```yaml
mcpServers:
  - lark                                            # 按名字引用已配置的服务器
  - browser: {url: "https://example.test/mcp"}      # 内联定义
  - notes: {command: "npx", args: ["-y", "notes-mcp"]}
```

- **按名字**引用你 MCP 配置中的服务器（`~/.siada-cli/mcp_config.json`、项目 `.mcp.json` 等）。如果该服务器在会话中已连接，直接复用连接；若只是"配置存在但未连接"，则为本次运行连接。
- **内联定义**会为本次运行创建并连接，运行结束后清理；定义中的环境变量（`${VAR}`）会被解析。
- 配置里 `enabled: false` 的服务器会被跳过。
- 既不在配置中、也不是内联定义的名字会打 warning 后跳过。
- 与主 Agent 一致：会重命名可能覆盖 Siada 原生工具名的 MCP 工具。

### `background`

```yaml
background: true
```

`true` 表示该 Agent 的**每一次** spawn 都走后台任务：主 Agent 立即拿到 `task_id`，摘要稍后以通知形式返回。适合耗时且独立的工作（审计、大规模检索、批量重构）。

- 该设置优先于调用方：即使模型传了 `async: false`，`background: true` 的 Agent 仍然在后台运行。
- `false` 或省略（默认）则由调用方决定。

### `effort`

为该 Agent 的运行指定推理强度：

```yaml
effort: high
```

- 合法取值：`low`、`medium`、`high`、`xhigh`、`max`。
- 该档位会按**实际生效的子 Agent 模型**做映射（就近取档，距离相同取更强）。例如 GLM-5.3 只接受 `low`/`high`/`max`，`medium` 会变成 `high`。
- 只作用于子 Agent 的这一次运行：你当前会话的 `/effort` 设置不会被改动。
- 非法值会被忽略并打 warning（改用模型自身默认档位）。
- `effort` 通常与 `conf.yaml` 中的 `sub_agent.llm_config`（为子 Agent 指定独立模型）搭配使用——或配合下面按 Agent 指定的 [`model`](#model)。

### `model`

让该 Agent 运行在指定模型上：

```yaml
model: gpt-6-luna
```

- 取值需要是模型目录里的模型名（即 `/model` 里可选的模型）。
- 它优先于 `conf.yaml` 中配置的子 Agent 模型（`sub_agent.llm_config.model`）；不写该字段时按上述配置解析——都没有配置时使用父会话自身的模型。
- provider 始终沿用这次 spawn 本来会用的那个（`conf.yaml` 里设了 `sub_agent.llm_config.provider` 就用它，否则用父级的），因此换模型不会换网关。
- `inherit`（Claude Code 的"与主 Agent 使用相同模型"）等同于"未配置"：按上面的默认解析生效。
- 未知的模型名（拼写错误、或已更名的旧名）会被忽略并在日志中打 warning；本次运行继续使用已配置的子 Agent 模型。
- [`effort`](#effort) 会按这个模型的可用档位做映射。

## 运行时会发生什么

1. 主 Agent 的系统提示词中会多出一段 `AGENT TYPES`，按 `名字 — 描述` 列出所有可用 Agent（没有任何定义时该段整体省略；`sub_agent.enabled: false` 关闭子 Agent 功能时同样省略，默认行为完全不变）。
2. 当任务与某条描述匹配时，主 Agent 以 `agent: "<名字>"` 调用 `run_subtask`。
3. Siada 加载定义并逐项应用：正文追加到子 Agent 的标准指令之后，`tools` → 裁剪后的工具集，`skills` → 预加载指令，`mcpServers` → 本次运行连接的服务器，`model` → 本次运行的模型，`effort` → 本次运行的模型设置，`background` → 后台执行。
4. 子 Agent 依然是无人值守的：不能向你提问，结束时必须给出摘要。
5. 未知的 Agent 名字不算错误——工具会返回当前可用 Agent 列表，让模型自行纠正。

几点说明：

- 指定了 Agent 时 `fork: true` 会被忽略：命名 Agent 自带提示词与工具，而 fork 存在的意义是复用父会话的提示词缓存前缀，两者冲突。
- 自定义 Agent 只配置**子 Agent** 的运行，不影响主 Agent 自身的提示词、工具与模型。
- 与其它子 Agent 一样，运行过程显示在子 Agent 详情视图中，不会内联在主对话里。

## 优先级与去重

同名定义相遇时：

- **同一作用域内**：上表中靠后的目录胜出（`.siada-cli/agents/` > `.agents/agents/` > `.claude/agents/`）。
- **跨作用域**：用户级定义（`~/.siada-cli/agents/` 等）优先于仓库级定义。

因此你可以保留个人版本，同时项目自带一份团队版本。

## 示例

**只读的审查者，绝不改代码：**

```markdown
---
name: code-reviewer
description: 审查代码改动中的缺陷、风格与安全问题。在完成一次实现后使用。
tools: [read_file, regex_search_files, run_cmd]
effort: high
---

你是一名严谨的代码审查者。每条发现按 `路径:行号 — 问题 — 建议修复` 输出，不要修改文件。
```

**带 web 与 MCP 能力的后台调研 Agent：**

```markdown
---
name: researcher
description: 在网络上调研主题并返回带出处的摘要。用于外部方案对比与最佳实践调研。
tools: ['*']
mcpServers: [lark]
background: true
---

你使用网络搜索与可用的 MCP 工具开展调研。摘要中的每条结论都必须标注 URL 或工具结果出处。
```

**总是套用项目技能的 Agent：**

```markdown
---
name: release-notes
description: 把一段提交区间整理成面向用户的发版说明。准备发版时使用。
skills: [lark-workflow-release-announcement]
---

你为最终用户撰写发版说明：按主题归类、丢弃内部重构、用非技术语言表述。
```

## 与 Claude Code Agent 文件的兼容性

为 Claude Code 的 `.claude/agents/` 写的文件通常可直接使用：

- 搜索的目录一致（仓库与主目录下的 `.claude/agents/`）。
- `name`、`description`、`tools`、`skills`、`mcpServers`、`background`、`effort`、`model` 字段名与语义相同（`model` 需要填 Siada 模型目录中的模型名；`inherit` 也能识别）。
- 常见 Claude Code 工具名会自动映射为 Siada 工具名（见 [`tools`](#tools)）。
- 不支持的 Claude Code 字段（`permissionMode`、`hooks`、`maxTurns`、`memory`、`isolation` 等）会被忽略，不会导致定义失效。对只存在于 Claude Code 的模型别名（`sonnet`、`opus`、`haiku`），请改用 Siada 的模型名——见 [`model`](#model)。

## 故障排查

| 现象 | 可能原因与处理 |
|------|----------------|
| `AGENT TYPES` 里看不到这个 Agent | `name` 或 `description` 缺失/不是字符串；查看 `siada_cli.log` 中的解析告警。 |
| 报 `Unknown agent 'x'. Available agents: …` | 名字拼写错误，或定义不在搜索目录内。 |
| Agent 运行了但工具比预期少 | `tools` 中有未知名字（日志有 warning）。改用 [`tools`](#tools) 表中的名字，或写 `['*']`。 |
| 指定的 skill 被忽略 | 技能名解析不到；检查告警以及技能 `SKILL.md` 中的 `name` 字段。 |
| Agent 里没有 MCP 工具 | `mcpServers` 条目既未配置也非内联定义（有日志），或服务器连接失败（有日志）——连接失败不会阻断运行。 |
| 实际 effort 与写法不一致 | 属正常：档位会按实际生效模型做就近映射。 |
| 写了 `model:` 但 Agent 仍用默认子 Agent 模型 | 模型名不在模型目录中（拼写错误或已更名）——日志里有 "not a known model; ignoring the override" 告警。请改用 `/model` 中可选的模型名。 |
| 修改定义后没有生效 | 定义每轮都会重新加载——请确认改的是[优先级规则](#优先级与去重)中胜出的那个文件。 |

## 相关文档

- [用户手册](./USERMANUAL_zh.md)
- [Skills 系统文档](./SKILLS_zh.md)
- [MCP 配置](./USERMANUAL_zh.md#mcp-配置)
- [外部模型配置](./external_model_configuration_zh.md)
