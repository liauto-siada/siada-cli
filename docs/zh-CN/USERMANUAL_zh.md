# Siada CLI 用户手册

**简体中文 | [English](../USERMANUAL.md)**

本用户手册提供了 Siada CLI 的详细使用指南，帮助您充分利用这个强大的 AI 工作流工具。

## 概述

Siada CLI 是一个专业的命令行 AI 工作流工具，专为代码开发、调试和自动化任务而设计。它提供了多种智能代理，每个代理都针对特定的开发任务进行了优化。


## 配置

### 模型配置

**方法1：默认配置**
   - 系统从 `agent_config.yaml` 文件读取默认配置
   - 当前默认：模型 `claude-sonnet-5`，供应商 `default`
   - 首次启动时选择供应商并输入 API Key，所选地址和模型保存在
     `~/.siada-cli/conf.yaml`。

   **方法2：通过配置文件自定义**
   - 普通用户
      - 编辑配置文件 `~/.siada-cli/conf.yaml`
         ```yaml
         llm_config:
           provider: "default"
           provider_id: "openai"
           model: "gpt-4o-mini"  # 使用该地址支持的模型
           base_url: "https://api.openai.com/v1"
           api_key: "YOUR_API_KEY"
         ```
   - 开发者模式
      - 编辑 `agent_config.yaml` 文件中的 `llm_config` 部分：
         ```yaml
         llm_config:
           provider: "default"
           model_name: "claude-sonnet-5"     # 更改为您想要的模型
         ```

   **方法3：通过环境变量**
   ```bash
   # 设置模型
   export SIADA_MODEL="gpt-4o-mini"
   
   # 设置供应商
   export SIADA_PROVIDER="default"

   # 当前终端会话的供应商凭据
   export BASE_URL="https://api.openai.com/v1"
   export API_KEY="YOUR_API_KEY"
   ```

   **方法4：通过命令行参数（最高优先级）**
   ```bash
   # 仅更改模型（保持供应商不变）
   siada-cli --model gpt-4o-mini
   
   # 同时更改模型和供应商
   siada-cli --model gpt-4o-mini --provider default
   
   # 仅更改供应商（保持模型不变）
   siada-cli --provider default
   ```

   > **重要提醒：**
   > - 模型和供应商优先级：命令行参数 > `SIADA_MODEL` / `SIADA_PROVIDER` >
   >   `~/.siada-cli/conf.yaml` > 内置默认值。
   > - 非空的 `BASE_URL`、`API_KEY` 覆盖对应的已存凭据，两项完整时可直接进入会话。

通过 chrome-acp 使用 Siada 时，选择模型会将其保存到
`~/.siada-cli/conf.yaml` 的 `llm_config.model`。新建会话或重启 Agent 后，
会使用保存的模型，并保留配置文件中的其他字段和注释。
如果保存失败，模型切换会报错，当前模型保持不变。

### 从已有会话派生新会话

输入 `/fork` 可从当前会话派生并切换到新会话；输入 `/fork <session_id>`
可从已保存的会话派生。`/fork <index>` 使用当前项目的 `/resume` 列表编号，
`/fork latest` 使用当前项目最近的非空会话。来源会话必须属于当前工作区。

新会话拥有独立的 ID 和存储目录，继承对话历史、压缩后的有效上下文、待办和
Goal 状态。后续消息写入新会话，原会话历史仍可通过 `/resume` 恢复。
派生读取已保存的会话状态，不复制工作区文件或正在运行的子代理进程。
该命令在终端 CLI 中提供。

### `/goal` 验证轮次上限

如果验证器没有给出可执行的 `nextAction`，或连续验证失败次数已达到上限，
`/goal` 会停止自动续跑。可在 `~/.siada-cli/conf.yaml` 中配置轮次上限：

```yaml
goal:
  max_turns: 6
```

默认值为 `6`。连续两次验证系统错误仍会触发独立且更快的熔断。
后台任务结果等内部续跑不会重新激活已阻断的 Goal；用户发送新消息时才会恢复。
清除现有 Goal 时，`/goal clear` 会将隐藏提醒写入会话历史，告知模型不要继续旧目标。
如果历史写入失败，Goal 仍会清除并显示警告，但模型下一轮可能读不到该提醒。

### 外部模型配置

如果需要配置自定义的外部模型（如私有部署的模型服务），请参阅 [外部模型配置指南](./external_model_configuration_zh.md)。该文档详细介绍了如何配置和使用外部模型，包括：
- 模型命名规范
- API 连接配置
- 协议映射说明
- 配置示例

### Sub agent 模型配置

Sub agent 默认使用父会话的模型和 provider。若要选择其他模型，可在
`~/.siada-cli/conf.yaml` 中添加：

```yaml
sub_agent:
  enabled: true
  llm_config:
    model: "gpt-4o-mini"
```

省略 `provider` 时，sub agent 继承父会话的 provider。如果配置的 provider
在当前发行版中不可用，会依次尝试父 agent 当前使用的 provider 和 `default`。
`default` 使用你配置的 `BASE_URL` 和 `API_KEY`；可用的显式 provider 优先使用。

### 代理配置(开发者模式)

编辑 `agent_config.yaml` 以自定义代理行为：

```yaml
agents:
  coder:
    class: "siada.agent_hub.coder.code_gen_agent.CodeGenAgent"
    description: "通用代码开发代理"
    enabled: true

llm_config:
  provider: "default"
  model_name: "claude-sonnet-5"
  repo_map_tokens: 8192
  repo_map_mul_no_files: 16
  repo_verbose: true
```

### 环境变量

设置环境变量来配置行为：

```bash
# Siada 特定设置（使用 SIADA_ 前缀）
export SIADA_AGENT="coder"
export SIADA_MODEL="gpt-4o-mini"
export SIADA_THEME="dark"

# 在当前终端会话中取消环境变量
unset SIADA_MODEL
```

### Checkpoint 配置

Siada CLI 提供检查点跟踪功能，可以自动保存会话状态，并支持从开发工作流程中的先前点进行恢复。

**什么是检查点？**
- 在重要工具操作后自动拍摄会话状态快照
- 包括对话历史、修改的文件、git状态、API消息和使用统计
- 支持回滚到先前状态以及比较不同时间点的差异
- 自动清理：超过限制时保留最新的检查点

**启用检查点跟踪：**

   **方法1：命令行参数**
   ```bash
   # 启动CLI时启用检查点
   siada-cli --checkpointing --agent coder
   ```

   **方法2：环境变量**
   ```bash
   # 全局启用检查点
   export SIADA_CHECKPOINTING=true
   siada-cli --agent coder
   ```

   **方法3：配置文件**
   
   编辑 `~/.siada-cli/conf.yaml`：
   ```yaml
   checkpoint_config:
     enable: true
   ```

**检查点使用：**
- 在文件编辑和命令执行等工具操作后自动创建检查点
- 使用 `/restore <checkpoint_file>` 恢复到先前状态
- 使用 `/undo <checkpoint_file>` 撤销检查点的更改，恢复到检查点创建之前的状态
- 使用 `/compare <checkpoint_file>` 查看当前状态与检查点的差异

**存储位置：**
- 文件地址：`~/.siada-cli/data/tmp/{project_hash}/checkpoints/{session_id}/`

**最大检查点文件数：**
- 默认值：每个会话保留 50 个检查点文件
- 此限制可确保有效利用磁盘空间，同时维持足够的历史记录
- **禁用清理**：设置为 0 或负值可禁用自动清理（保留所有检查点）

**自动清理：**
- 当检查点数量超过最大限制 + 5 时，系统会自动删除最旧的 5 个检查点
- 示例：默认限制为 50，当达到 55 个文件时触发清理，删除最旧的 5 个
- **注意**：当 max_checkpoint_files 设置为 0 或负值时，自动清理功能将被禁用
- 这样可以有效管理磁盘空间，同时保留最近的工作记录

### .siadaignore 配置

.siadaignore 是一个项目级配置文件，用于告知 Siada 在分析代码库时应忽略哪些文件和目录，其作用类似 .gitignore，通过模式匹配规则指定需要从Siada 的上下文和操作中排除的文件。

**注意：该文件需要手动创建**

.siadaignore 结构示例
   ```bash
   # Dependencies
   node_modules/
   **/node_modules/
   .pnp
   .pnp.js

   # Build outputs
   /build/
   /dist/
   /.next/
   /out/

   # Testing
   /coverage/

   # Environment variables
   .env
   .env.local
   .env.development.local
   .env.test.local
   .env.production.local

   # Large data files
   *.csv
   *.xlsx
   ```

.siadaignore 目录形式
   ```bash
   # .siadaignore文件必须在项目根目录下
   your-project/
   ├── .siadaignore
   ├── src/
   ├── docs/
   └── ...
   ```

### MCP 配置

Siada CLI 集成了 MCP（Model Context Protocol）服务，为 AI 代理提供扩展的工具和资源

MCP 配置加载器仅处理 JSON 配置来源，已安装插件自带的 MCP server 由插件运行时独立加载。

**MCP 配置文件 `~/.siada-cli/mcp_config.json`**

   参数说明：
   - `enabled`：控制全局/单个mcp server的开关
   - `type`：连接类型（`stdio`/`http`/`sse`）

   配置文件示例：
   ```json
   {
      "enabled": true,
      "mcpServers": {
         "filesystem": {
            "enabled": true,
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocolserver-filesystem", "./"]
         }
      }
   }
   ```

**MCP 斜杠命令**

   - `/mcp-server`：列出所有mcp服务
   - `/mcp-list`：列出所有mcp服务及提供的工具

## 使用模式

Siada CLI 支持两种使用模式，满足不同的使用场景：

交互会话使用 `siada-cli` 启动的 Node.js 终端 UI，通过 ACP 连接 Python 后端。
不再支持旧的 Rich/prompt_toolkit 交互 UI；`--prompt` 非交互执行方式保持不变。

### 非交互模式

**特点：**
- 一次性执行：执行单个任务后自动退出
- 无状态：不保留会话上下文
- 适用场景：自动化脚本、CI/CD 流水线、单次任务执行

**使用方法：**
```bash
# 使用 --prompt 参数触发非交互模式
siada-cli --agent coder --prompt "修复 auth.py 中的登录错误"

# 组合其他参数
siada-cli --agent coder --model claude-sonnet-4.5 --prompt "创建一个 REST API 端点"
```

### 交互模式

**特点：**
- 持续对话：启动后保持会话状态，可以连续对话
- 上下文记忆：AI 记住之前的对话内容
- 实时交互：支持斜杠命令、编辑器模式等高级功能
- 适用场景：探索性编程、复杂任务、需要多轮对话的开发工作

已有 API Key 配置时，输入界面可以在模型库仍于后台初始化时就绪。
启动后立即发送的第一条消息可能短暂等待初始化完成。

**使用方法：**
```bash
# 直接启动（默认为交互模式）
siada-cli --agent coder
```

**交互过程：**
```
> 创建一个用户管理 API
[AI 响应...]
> 为这个 API 添加数据验证
[AI 响应...]
> 写一些单元测试
[AI 响应...]
```

### 任务执行与阻碍

Siada 在用户请求的任务范围内执行工具，并遵守工具的权限检查。代码代理通过普通助手消息
发送进展、结果和阻碍；执行中可补充指令，也可明确要求先审阅计划再执行。
代码代理没有单独的交互提问工具或规划模式面板。

`run_subtask` 的普通、fork、后台和递归子任务均无人值守执行，无法解决的阻碍汇报给调用方代理。

### ACP 对话中的浏览器上下文

浏览器客户端附带前置 `<browser-context>` 时，ACP 后端将它与用户原始输入分开。
同时包含页面上下文和 browser-skill 经验建议的回合，会以三个独立 user-role 输入项传给代理：
包含用户消息的 `<user_input>`、包裹页面上下文的 `<system-reminder>`，
以及单独包裹经验建议的 `<system-reminder>`。缺少的上下文项不添加，普通输入保留原有形态。

提醒标签仅标记低信任运行时上下文，不表示 system 消息角色，也不扩大授权。
上下文项随回合保存，但在历史回放中隐藏。`@文件` 扩展只处理用户消息，
不会将上下文项合并回用户输入。

## 守护进程与定时任务

### 守护进程

启动 siada-cli 时会默认在后台开启守护进程，负责主动任务分析和定时任务的调度执行。

**在非交互模式下停止和查看守护进程状态：**
```bash
# 停止守护进程
siada-cli --stop-daemon

# 查看守护进程状态
siada-cli --daemon-status
```

### 定时任务

直接用自然语言告诉 Siada 即可设置定时任务，守护进程会自动完成调度管理。

**示例：**
```
> 每天早上九点半，执行按照 xxx 文档编译代码
> 每天凌晨两点执行测试用例
```

Siada 会配置对应的定时任务并与你确认执行计划。

每次定时任务使用独立的模型 Provider，并在任务的事件循环关闭前释放异步客户端。
原生 Chat 客户端不会跨定时任务复用，也不会关闭交互会话或 IM 会话使用的 Provider。
主 Agent、递归子 Agent、模型覆盖及内置模型辅助调用，在同一运行时事件循环内共享
Provider 池，不跨循环共享。ACP、每个 IM 控制器循环、旧版 TUI，以及临时 `/btw`
或图像转写循环分别使用独立的池。原生 Chat 和默认 Responses 客户端遵循相同的
所有权规则。运行时退出时，先停止接收新任务，取消并等待剩余任务及流结束，
再在所属循环内关闭 Provider，最后关闭循环。单个 Agent 结束不会关闭兄弟任务共享的客户端。
升级后，请通过 `siada-cli --stop-daemon` 停止已有守护进程，再启动 Siada CLI，
使定时任务使用更新后的运行逻辑。

## 命令行选项

```bash
# 使用特定代理
siada-cli --agent coder
# 支持缩写
siada-cli -a coder

# 使用单个提示的非交互模式
siada-cli --prompt "修复 login.py 中的认证错误"
# 支持缩写
siada-cli -p "修复 login.py 中的认证错误"

# 使用不同模型
siada-cli --model claude-sonnet-4

# 设置颜色主题（默认 dark，旧的 auto 也直接使用 dark，不再自动检测）
siada-cli --theme dark

# 启用详细输出
siada-cli --verbose

# 列出所有可用模型
siada-cli --list-models
siada-cli --models

# 启用检查点跟踪（用于会话恢复）
siada-cli --checkpointing

# 守护进程管理（非交互模式）
siada-cli --stop-daemon     # 停止后台守护进程
siada-cli --daemon-status   # 查看守护进程状态
```

# 版本检查与更新
```bash
siada-cli --just-check-update  # 仅检查版本，不执行更新
siada-cli --upgrade            # 立即升级到最新版本  
siada-cli --check-update       # 启动时检查并提示更新（默认开启）
```

## 斜杠命令

在 CLI 中，您可以使用斜杠命令来获得额外功能：

- `!<命令>` - 在不切换模式的情况下直接执行单条 shell 命令
- `/model` - 显示模型选择器或切换模型（`/model <model_name>`）
- `/editor` 或 `/edit` - 打开编辑器进行多行输入
- `/init [--force]` - 分析项目并创建定制的 `SIADA.md` 文件
- `/compact` - 压缩会话上下文；终端在压缩状态下方显示消息数量变化和移除数量。执行中显示压缩状态，结束后恢复模型推理状态。
- `/restore <checkpoint_file>` - 从检查点文件恢复会话状态（需要启用检查点跟踪）
- `/undo <checkpoint_file>` - 撤销检查点所做的更改，恢复到检查点创建之前的状态（需要启用检查点跟踪）
- `/compare <checkpoint_file>` - 将当前状态与检查点文件进行比较以查看差异
- `/context-file-refresh` - 刷新 `SIADA.md` 和 `AGENTS.md` 上下文文件，并显示内容概览
- `/rule-status` - 显示发现的 `siada_rule.md` 层级文件和相关配置
- `/status` - 显示当前会话状态（模型、Agent、会话ID和工作空间）
- `/lang` - 查看当前语言配置
  - `/lang zh` - 切换中文
  - `/lang en` - 切换英文
- `/exit` - 退出应用程序

### 执行 Shell 命令

在提示符中使用 `!` 前缀执行单条系统命令：

```bash
> !ls -la
> !git status
> !npm run dev
```

命令执行结束后，提示符返回对话模式。用于持续 shell 模式的 `/shell` 命令在当前版本中已停用。

### 语言配置

**coder agent** 在**交互模式**下支持使用斜杠命令切换语言

```bash
# 默认语言为英文
# 显示当前语言
/lang

# 切换当前会话语言为中文
/lang zh
/lang zh-CN

# 切换当前会话语言为英文
/lang en
```

## 代理类型

### 代码生成代理 (`--agent coder` / `-a coder` / `--coder`)
通用代码开发代理，用于创建新功能、修复缺陷、重构代码以及在各种编程语言中实现功能（包括前端开发任务）。

### 自定义代理（`.agents/agents/`）
除内置代理类型外，你还可以在 `.agents/agents/`（或 `~/.siada-cli/agents/`）下用 Markdown 文件定义自己的命名子代理。每个定义自带系统提示词，并支持 `tools`、`skills`、`mcpServers`、`background`、`effort` 配置，主代理通过 `run_subtask` 把任务派给它。文件格式、字段说明、优先级规则与示例见 [自定义代理指南](./USER_AGENTS_zh.md)。

每次 `run_subtask` 执行使用独立的内存上下文，并可在上下文增长时进行压缩。
后续 SDK 保存不会重新加入压缩掉的原始任务输入；内容相同的消息会保留，
包括继承（`fork`）历史中的重复消息。

## 示例

### 激活虚拟环境（仅开发者模式需要）
首先，进入 siada-cli 项目目录并激活虚拟环境：

```bash
# 进入项目目录
cd ~/path/to/siada-cli

# 激活虚拟环境（推荐方法）
source $(poetry env info --path)/bin/activate

# 或者使用 Poetry 运行（无需激活环境）
# poetry run siada-cli
```

### 使用示例

激活环境后，您可以选择交互模式或非交互模式与 AI 代理进行交互。

**交互模式（默认）：**

```bash
# 进入项目目录
cd my-project/

# 启动交互模式
siada-cli --agent coder

# 然后您可以在交互界面中输入提示
> 使用 FastAPI 创建一个带有用户认证的 REST API 服务器
# AI 会响应并可以继续对话...
> 为这个 API 添加日志记录功能
```

**非交互模式（一次性执行）：**

```bash
# 直接执行单个任务并退出（默认使用 coder agent）
siada-cli --prompt "创建一个用户注册 API"

# 指定特定代理执行任务
siada-cli --agent coder --prompt "修复 login.py 中的认证错误"
siada-cli --agent coder --prompt "使用 React 和 Tailwind CSS 创建一个响应式导航栏组件"
```

**退出虚拟环境（仅开发者模式需要）：**

```bash
# 使用完毕后退出虚拟环境
deactivate
```

## 常见任务

### 调试和修复代码问题

```text
> 分析这个错误消息并建议修复方案：[粘贴错误]
```

```text
> 帮我重现这个在高负载期间出现的间歇性错误
```

### 代码生成和开发

```text
> 为此服务中的数据库查询实现缓存层
```

```text
> 将这个单体函数重构为更小、更易维护的部分
```

### 前端开发

```text
> 创建一个带有侧边栏导航的响应式仪表板布局
```

```text
> 为用户注册表单添加表单验证
```

## 故障排除

并行请求排查时，请参阅[日志关联与轮转](LOGGING_zh.md)，了解日志位置、
来源标识、DEBUG 设置和轮转规则。

### 常见问题

**命令找不到 (command not found)：**
如果直接运行 `siada-cli` 提示命令找不到：
- 在开发者模式中是正常现象，因为命令安装在虚拟环境中
- 参考示例激活虚拟环境

通过 `uv tool` 安装的命令，可运行 `uv tool update-shell` 配置 PATH。
运行安装脚本后，请打开新终端使 PATH 配置生效。
浏览器配套组件的安装命令是 `siada-browser setup`，也可使用 `siada-cli --browser-setup`。
如果 setup 提示 HTTP 404，请更新 Siada 后重试。使用自定义下载源时，可运行
`siada-browser setup --base-url <发布目录>`，或
`siada-cli --browser-setup --browser-base-url <发布目录>`。

**模型 API 错误：**
- 检查您的网络连接

**模型响应未完整结束：**

模型流结束时缺少最终响应事件，已经显示部分文字时也可能发生。
如果只收到生命周期事件，Siada 最多重试两次；一旦交出正文、推理或工具事件，
就报告失败并停止重放。手动重试前请检查已显示的内容和工具执行结果。
错误提示显示真实日志路径，通常为 `~/.siada-cli/logs/errors.log`，
可通过 `SIADA_CLI_LOG_DIR` 修改目录。诊断日志包含模型、response ID、
最后事件以及是否已经交出内容。

**安装问题：**
- 确保您安装了 Python 3.12+
- 使用官方安装方法安装 Poetry
- 尝试删除 `poetry.lock` 并重新运行 `poetry install`

**代理无法工作：**
- 检查代理在 `agent_config.yaml` 中是否启用
- 验证代理类路径是否正确
- 使用 `--verbose` 标志查看详细输出

**DOCX 转换报 `FileConversionException` / `UnicodeDecodeError`：**

`openhands-aci 0.3.3` 与 `markdownify 1.x` 一起安装时，含链接或图片的 DOCX
可能转换失败。最终显示的 UTF-8 错误可能掩盖前面的转换错误。
Siada 已将 `markdownify` 约束到兼容版本。开发环境请使用仓库提交的锁文件
运行 `poetry install`，然后重启 Siada 并重新读取文档。

**Markdown 文件编辑显示：**

完成的 Markdown 字符串替换在折叠、展开和恢复会话时均显示为逐行 diff，保留正文中的代码块和空行。流式编辑结束前仍使用工具文本视图。旧版未加代码围栏的显示文本若包含无法确定边界的 `with:` 分隔行，则保留文本视图，不猜测 diff。

`edit_file` 在替换和插入文本时保留原文件的 LF/CRLF 换行。新增文本沿用文件中第一个换行符；没有换行符时使用 LF。未修改行保留各自的换行符，插入操作保留原文件权限，`create` 创建文件时保留传入内容的换行符。

**补丁上下文不匹配（`Invalid Context` / `Invalid EOF Context`）：**

原生补丁失败时会返回恢复建议：

- 旧文本及上下文必须匹配当前文件中的完整行，匹配器不会理解 JSON 字段或行内片段。
- 重新读取目标区域，再按当前原文生成补丁；不要复制阅读输出的行号和截断标记，
  也不要原样重试失败的补丁。
- 定位时容忍行首/行尾空白及常见 Unicode 标点或特殊空格差异，保留未修改的原文。
  字段值变化和不同 JSON 排版不视为等价。
- 每项原生操作在写入前校验；整批操作不是事务，失败不会回滚已成功的操作，
  SDK 仍可能尝试后续操作。重试前检查每项结果及当前文件。

有关更详细的故障排除，请检查日志并使用 `--verbose` 标志获取额外的调试信息。
