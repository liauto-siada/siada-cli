# Siada CLI 用户手册

**简体中文 | [English](../USERMANUAL.md)**

本用户手册提供了 Siada CLI 的详细使用指南，帮助您充分利用这个强大的 AI 工作流工具。

## 概述

Siada CLI 是一个专业的命令行 AI 工作流工具，专为代码开发、调试和自动化任务而设计。它提供了多种智能代理，每个代理都针对特定的开发任务进行了优化。


## 配置

### 模型配置

**方法1：默认配置**
   - 系统从 `agent_config.yaml` 文件读取默认配置
   - 当前默认：模型 `claude-sonnet-4.5`，供应商 `li`

   **方法2：通过配置文件自定义**
   - 普通用户
      - 编辑配置文件 `~/.siada-cli/conf.yaml`
         ```bash
         # 1. 在用户主目录下创建配置文件
         cd ~
         mkdir -p ~/.siada-cli
         touch ~/.siada-cli/conf.yaml

         # 2. 配置文件内容示例
         llm_config:
         model: "claude-sonnet-4.5"          # 更改为您想要的模型
         provider: "li"
         ```
   - 开发者模式
      - 编辑 `agent_config.yaml` 文件中的 `llm_config` 部分：
         ```yaml
         llm_config:
         provider: "li"
         model_name: "claude-sonnet-4.5"     # 更改为您想要的模型
         ```

   **方法3：通过环境变量**
   ```bash
   # 设置模型
   export SIADA_MODEL="claude-sonnet-4.5"
   
   # 设置供应商
   export SIADA_PROVIDER="li"
   ```

   **方法4：通过命令行参数（最高优先级）**
   ```bash
   # 仅更改模型（保持供应商不变）
   siada-cli --model claude-sonnet-4.5
   
   # 同时更改模型和供应商
   siada-cli --model gpt-4.1 --provider li
   
   # 仅更改供应商（保持模型不变）
   siada-cli --provider li
   ```

   > **重要提醒：**
   > - **完整优先级**：`命令行参数` > `环境变量(SIADA_前缀)` > `配置文件(agent_config.yaml)`

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

默认值为 `6`。单次验证系统异常会自动安排下一轮续跑；连续两次验证系统错误会触发独立且更快的熔断。
后台任务结果等内部续跑不会重新激活已阻断的 Goal；用户发送新消息时才会恢复。
Goal 完成后保留最终状态、耗时和轮次，恢复会话时也会显示。
继续发送普通聊天消息时，完成的 Goal 会自动归档并移除状态栏，历史验证记录仍保留。
也可使用 `/goal clear` 提前移除，或 `/goal <目标>` 替换为新目标。
清除现有 Goal 时，`/goal clear` 会将隐藏提醒写入会话历史，告知模型不要继续旧目标。
如果历史写入失败，Goal 仍会清除并显示警告，但模型下一轮可能读不到该提醒。

需要测试 Goal 的验证重试流转时，使用环境变量启动：

```bash
SIADA_GOAL_VERIFIER_FORCE_ERROR=1 siada-cli
```

用 `/goal <目标>` 新建 Goal。每次验证都会主动抛出异常：首次异常会自动续跑，
第二次连续异常会进入 `blocked` 并停止自动续跑。已有 Goal 可能已经累计错误次数。
取消该变量并重启 CLI 后，恢复正常验证。

`/resume <id>` 和 `siada-cli --resume <id>` 会立即恢复 Goal 状态及当前 todo 列表。
仅恢复会话不会自动续跑已阻断的 Goal；发送下一条对话消息后，Goal 才会重新激活并继续验证。
内部验证提醒不会显示在 TUI 中。已清空或全部完成的 todo 列表不会从旧历史中重新恢复。

### 外部模型配置

如果需要配置自定义的外部模型（如私有部署的模型服务），请参阅 [外部模型配置指南](./external_model_configuration_zh.md)。该文档详细介绍了如何配置和使用外部模型，包括：
- 模型命名规范
- API 连接配置
- 协议映射说明
- 配置示例

### 一次性模型请求

会话标题、记忆文件名与摘要、浏览器技能分类与匹配、上下文压缩和图片转写，
通过 Siada 的 `ModelProviderWrapper` 发起一次 Agents SDK 模型调用。
这些辅助请求不会启动 Agent/Runner 工具循环，也不会将提示词写入主会话。
Provider 仍按模型选择 Chat Completions、Responses 或厂商专用协议。

如果需要为快速辅助请求选择独立模型，可配置 `~/.siada-cli/conf.yaml`：

```yaml
fast_llm_config:
  model: "gpt-4o-mini"
  provider: "default"
  base_url: "https://gateway.example/v1"
  api_key: "YOUR_API_KEY"
  extra_headers:
    X-Application: "siada-fast-helpers"
```

此覆盖配置必须包含 `model`。`base_url`、`api_key` 和 `extra_headers` 可省略；
default Provider 未覆盖的认证字段沿用正常运行时配置。
独立地址与 API key 覆盖需要使用 `default` Provider；其他 Provider 必须明确支持
请求局部的端点配置。认证信息和请求头仅作用于当前请求，不修改主模型配置。
连接复用并由所属运行时统一关闭，不在每次辅助调用后关闭。
未配置此节时，原有快速模型选择策略保持不变。
此覆盖只适用于 `fast_completion` 辅助调用，不改变独立的 MemoryAgent Runner 配置。

Python 集成中，`fast_completion` 和 `simple_completion` 现在返回 SDK
`ModelResponse`，而非带有 LiteLLM `choices` 的响应。可通过
`siada.provider.one_shot.extract_response_text(response)` 提取助手正文；
推理、拒绝和工具调用项不会混入正文。`one_shot_completion`、`fast_completion`
和 `simple_completion` 默认使用流式传输，但只返回最终的 `ModelResponse`，
不会返回迭代器。显式传入 `stream=False` 仍可使用非流式传输。包括自动与显式
上下文压缩在内的独立模型调用默认走流式，以减少等待完整非流式响应期间的长时间空闲。
收到 SDK 失败/不完整事件，或流结束时没有最终 SDK 响应，会报错而非返回累积的增量文本。
显式 `timeout` 仍限制整个请求（包括流消费）的总耗时；流式不能保证避免所有超时。
传输层重试仍由各 Provider 决定。

### 代理配置(开发者模式)

编辑 `agent_config.yaml` 以自定义代理行为：

```yaml
agents:
  coder:
    class: "siada.agent_hub.coder.code_gen_agent.CodeGenAgent"
    description: "通用代码开发代理"
    enabled: true

llm_config:
  provider: "li"
  model_name: "claude-sonnet-4.5"
  repo_map_tokens: 8192
  repo_map_mul_no_files: 16
  repo_verbose: true
```

### 环境变量

设置环境变量来配置行为：

```bash
# Siada 特定设置（使用 SIADA_ 前缀）
export SIADA_AGENT="coder"
export SIADA_MODEL="claude-sonnet-4.5"
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

MCP 配置加载器仅处理 JSON 配置来源，不注入已安装插件中的 server。
插件自带的 MCP server 由插件运行时独立加载。

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

需要像普通命令一样保留终端原生滚动历史时，可使用：

```bash
siada-cli --no-alt-screen
```

已完成的内容持续追加到终端历史。长回复生成时，已稳定的完整行也会逐步进入历史，
屏幕上的实时区域保留尚未完成的末尾。使用终端自身的滚动条或鼠标滚轮查看之前的输出，
拖选文字并使用原生复制、粘贴。缩放终端、打开选择器或切换会话不会清除或重复打印
已经输出的历史。输入框、键盘选择器和完整会话导出仍可使用。
SSH 下请使用终端粘贴（通常为 Ctrl+Shift+V 或菜单“粘贴”）。
此模式关闭备用屏幕与应用鼠标捕获，嵌套视图同样遵守这一设置。
UI 专用的 `--no-alternate-buffer` 仍使用应用消息视口并允许捕获鼠标。

默认全屏模式下，输入区固定在底部，上方独立滚动会话历史，原版 Banner 位于历史开头。
问题滚出视口顶部后悬浮在第一行，阅读其回答时保持可见；下一轮问题到达顶部时接替它。
向上滚动会切回之前的问题，回到会话开头则露出 Banner。草稿和排队中的提示不会悬浮。
按住右侧细线滚动条拖动可浏览历史，点击轨道可跳转位置。拖动时横向移出滚动条仍可继续，
松开鼠标后结束；拖到最底部会恢复跟随新回复。
鼠标滚轮或 Ctrl+↑/↓ 每次滚动历史 3 行；PgUp/PgDn 每次翻一屏
（Mac 键盘通常为 Fn+↑/↓）。SSH 下只要终端透传这组按键，Ctrl+↑/↓
也能滚动消息区，不移动输入框光标，也不切换输入历史或补全项。
Alt+↑↓ 跳转用户轮次，Ctrl+G 打开用户消息目录，Ctrl+End 或点击底部提示回到最新回复。
思考标题显示开头摘要，单行命令只显示一行。思考、Update file 和多行命令可点击展开；
其他工具直接展示。思考正文使用与用户消息相同的底色，工具详情沿用原有标题。
鼠标滚轮统一滚动会话历史。
点击顶部问题会定位到历史中的原问题全文，继续滚动即可阅读。
连续工具调用保留摘要和工具树；Update file 和多行命令保留各自的展开与收起入口。
在会话文字上按住鼠标拖选，松开后自动复制到剪贴板；拖选不会触发工具展开。
可从历史区的缩进、行尾或空白行开始拖选，起点会映射到文字边界；仅点击空白而不拖动不会复制。
单击正文只建立空起点；逐字拖选按文字边界计算，移到下一个汉字的起始位置只选中前一个字。
双击正文选词，三击选中当前逻辑行，继续拖动会按词或行扩展；Shift 点击可延伸已有选区。
纵向拖到上下边缘会自动滚动，横向拖选保持位置；鼠标滚轮会暂停自动滚动。
选择期间保留已显示的文字版本，新回复、滚动和窗口缩放不会改变已选内容；Esc 清除选区并恢复当前历史。
有选区时 Ctrl+C 复制，在系统剪贴板确认写入后清除选区；复制失败或仅通过 OSC 52 发送时保留选区。
输入文字及其下方的状态、任务和子 agent 文字同样支持拖选、双击选词和三击选行。
复制保留草稿与光标位置，自动折行按原始换行复制。输入边框、光标、占位提示、目录及导航控件不参与选择。
交互确认提示中的输入同样支持选择和复制。
等待确认输入或显示命令建议时，仍可用鼠标阅读、选择和滚动可见消息。
命令建议只遮挡其显示区域；键盘继续用于编辑或确认输入。
空白选区不会复制；复制有超时保护，关闭视图会取消未完成的复制。
本机使用系统剪贴板，不可用时尝试 OSC 52；SSH 会话即使终端识别为 Unknown，也会尝试通过 OSC 52 发送。
提示“已发送”表示复制请求已发出，是否写入剪贴板由终端支持情况和权限决定。
Ctrl+Home 回到会话开头的 Banner。
鼠标移到可点击的标题、顶部问题、目录项或回到最新回复入口时，该区域以原有灰白色调加强显示，
底部一行显示点击后的操作；移开后恢复原样。悬停反馈需要终端支持鼠标移动事件。
思考摘要和工具标题仅在实际文字所在的行、列范围响应悬停与点击；树形缩进和行尾空白不会触发。
无选区或弹窗时，Ctrl+C 停止当前执行并丢弃队列，在导航行显示提示；1 秒内再按一次退出。
其他按键取消退出提示。有草稿时第一次先清空输入，↑ 可取回完整文本及粘贴附件。
弹窗和任务详情先用 Ctrl+C 关闭，之后才进入停止或退出流程。

界面默认使用全屏缓冲区，退出后恢复之前的终端画面；会话历史在应用内浏览。
UI 可执行程序的 `--no-alternate-buffer` 参数会在主终端缓冲区重绘同样的有界布局。
空草稿时，Tab 在 Goal、Todo、Agents 之间切换，Enter 打开所选入口，Esc 返回输入框。
Agents 保持在输入框下方。Todo 是只读清单，完成后移入可展开的 `Plan completed` 消息，
不再常驻底部；Goal 完成后状态栏继续显示，耗时和轮次冻结，直到下一条普通聊天消息开始。
验证结果保留在消息中。
Goal 在 Todo 上方显示目标摘要和英文阶段描述，右侧展示当前具体状态
（`active`、`blocked`、`paused`、`complete`）、累计活动时长和验证轮次，
例如 `In progress (active · 1m 2s · 2 turns)`。窄终端优先缩短目标摘要，
空间不足时将轮次简写为 `2t`（2 轮）。验证开始时计入当前轮次，时长包含验证阶段。
目标被阻塞、暂停或完成时停止计时；恢复被阻塞的目标后接续累计时长，不计入阻塞等待时间。
中断当前轮次或退出 CLI 会自动暂停进行中的目标，暂停期间的等待不再计时；
下一条普通聊天消息会恢复目标，并保留已累计时长和连续失败次数。
旧会话根据已有的创建和最后更新时间初始化时长。
验证时原行变为 `Verifying…`，使用与 Thinking 相同的动画。
`Not achieved` 记录会说明是否自动继续，展开记录或打开 Goal 可查看原因和下一步。
新的验证记录随会话保存，恢复时可重放，包括已归档目标的结果；旧会话没有保存的
验证记录时仍恢复目标状态。`Automatic continuation stopped` 表示需发送新消息重试。
`/goal clear` 移除当前目标并显示 `Goal cleared`。
模型、effort、主题、任务、插件、会话、编辑器和状态栏选择器沿用原有操作，仅显示在底部区域，
上方会话和草稿保持。`/status` 在紧凑的底部面板中显示模型、智能体、会话 ID、工作目录和项目哈希，
按 Esc 关闭。`/effort` 会立即打开设置面板，Agent 运行时也不会进入消息队列；
选择的新级别从下一轮生效。Effort 仍使用左右键选择级别。
Tips 紧贴输入框上方：快捷键在右侧，回到底部按钮独立居中显示。
单行命令仅显示一次；Update file 和多行命令保留独立展开，其他工具直接展示。
缩略思考无常驻底色，展开正文使用与用户消息相同的底色。

### Mermaid 图表

终端回答中已闭合的 `mermaid` 或 `mmd` 代码块会显示为 Unicode 图表，支持中文
标签。支持流程图、状态图、时序图、类图和实体关系图。超宽图表会显示终端
宽度内的一段，点击图下方的 `◀`、`▶` 箭头可左右切换；旁边的数字表示当前
可见列范围和图表总宽度。每次切换保留少量重叠，方便追踪连线。代码块尚未
闭合、语法不受支持，或图表超出消息高度时，保留源码显示。

可以让 Siada 用 Mermaid 代码块回答，例如：

````markdown
```mermaid
flowchart LR
  A[收到请求] --> B[校验] --> C[返回结果]
```
````

### 工作目录

默认情况下，Siada CLI 将执行 `siada-cli` 命令时所在的目录作为工作目录，
交互模式和非交互模式均遵循这一规则。在 Git 仓库的子目录启动时，不会自动
切换到仓库根目录；现有 `.env` 加载逻辑仍会查找 Git 根目录。

```bash
cd ./my-project/src
siada-cli
```

需要使用其他目录时，可以通过 `--workspace` 或其简写 `-w` 显式指定（相对路径
基于启动目录解析），也可以设置 `SIADA_WORKSPACE` 环境变量。命令行参数的优先级
高于环境变量。

目录参数是可选的：`siada-cli -w`（或 `siada-cli --workspace`）明确使用当前目录，
即使设置了 `SIADA_WORKSPACE` 也不会使用该环境变量中的目录。提供目录参数时，
仍然使用指定的目录。

```bash
siada-cli -w
siada-cli -w --prompt "检查当前目录"
siada-cli --workspace ./my-project
siada-cli -w ./my-project
siada-cli --workspace ./my-project --prompt "检查项目"
```

会话与其工作目录关联。恢复此前在仓库根目录创建的会话时，请从该根目录启动，
或通过 `--workspace` 显式选择它。

### 非交互模式

**特点：**
- 一次性执行：执行单个任务后自动退出
- 与交互模式使用相同的流式执行和回合策略，包括自动恢复及重试检查
- 显示中间执行进度和最终答案；详细 Trace 同时记录到 `~/.siada-cli/logs/` 下
  按天生成的 `agent_trace-YYYYMMDD.log` 和 `subtask_trace-YYYYMMDD.log` 文件
- 执行 Goal 时，打印开始或继续执行、每轮验证、验证结果、完成、阻塞及暂停状态，
  并展示耗时、验证反馈、下一步建议和可用的 token 用量。轮次指 Goal 验证次数，
  不是工具调用次数；即使 stdout 重定向到文件或管道，也会及时刷新进度输出。
- 使用 `--prompt "/goal <目标>"` 会先创建 Goal 再开始执行，并立即打印开始状态。
  验证在 Agent 的当前轮次结束后才启动；此前中断会打印暂停状态，不会产生验证结果。
- 保留会话历史，支持通过 `--resume` 继续执行
- 始终关闭检查点，即使命令行选项或配置文件启用了检查点
- 不提供交互输入循环、斜杠命令界面或执行中追加用户输入
- Shell 命令不会读取启动终端的输入，即使从终端启动 Siada 也一样。需要确认或输入
  的命令应使用非交互参数，或通过管道、重定向提供输入。
- 执行失败时返回非零退出码（中断时为 `130`）
- 恢复的目标在验证后变为 blocked 时，会明确报告目标未完成并返回退出码 `1`，
  即使模型已经生成了答案
- 适用场景：自动化脚本、CI/CD 流水线、单次任务执行

**使用方法：**
```bash
# 使用 --prompt 参数触发非交互模式
siada-cli --agent coder --prompt "修复 auth.py 中的登录错误"

# 组合其他参数
siada-cli --agent coder --model claude-sonnet-4.5 --prompt "创建一个 REST API 端点"

# 启动带自动验证和续跑的 Goal 执行
siada-cli --agent coder --prompt "/goal 修复失败的测试"
```

### 交互模式

**特点：**
- 持续对话：启动后保持会话状态，可以连续对话
- 上下文记忆：AI 记住之前的对话内容
- 实时交互：支持斜杠命令、编辑器模式等高级功能
- 适用场景：探索性编程、复杂任务、需要多轮对话的开发工作

**使用方法：**
```bash
# 直接启动（默认为交互模式）
siada-cli --agent coder

# 打开交互式 UI，并自动提交第一条消息
siada-cli "你好"
siada-cli --agent coder "检查这个项目"

# 初始消息也会走正常的斜杠命令处理
siada-cli "/goal 修复失败的测试"
```

初始消息会在 UI 连接完成、启动登录或会话选择结束后提交一次，之后界面保持
打开，可以继续对话。通过 `--resume SESSION_ID "继续任务"` 可在已有会话中
提交初始消息。包含空格的消息需要加引号；以 `-` 开头的消息使用
`-- "消息"`。位置参数消息不能与 `--prompt`/`-p` 同时使用，后者仍选择非交互执行。

**交互过程：**
```
> 创建一个用户管理 API
[AI 响应...]
> 为这个 API 添加数据验证
[AI 响应...]
> 写一些单元测试
[AI 响应...]
```

### 终端原生历史

使用 `siada-cli --no-alt-screen` 启动，输出会持续追加到终端原生历史，
可用终端自身的滚动条、文字选择和鼠标操作。该模式关闭备用屏幕和鼠标捕获。

要默认启用，在 `~/.siada-cli/conf.yaml` 中添加：

```yaml
ui:
  no_alt_screen: true
```

若已有 `ui` 段，将字段加到该段中。使用不带引号的 YAML 布尔值。
默认值为 `false`；命令行 `--no-alt-screen` 始终启用该模式。
修改后重新启动 CLI 即可生效，无需重启守护进程。

### 复制和粘贴

粘贴文字时可使用终端菜单“粘贴”（Linux/Windows 常用 Ctrl+Shift+V，macOS 使用
Cmd+V）。通过 SSH 运行时同样适用，因为文字由终端发送给 Siada。长文本会显示为
占位符，提交时自动展开。

Ctrl+V 主动读取 UI 所在机器的剪贴板，支持文字和图片。Windows 和 WSL 使用
Windows 剪贴板。Linux、macOS 和 Windows 的文字读取与复制优先使用随安装包
提供的原生后端，Linux 用户无需为文字粘贴安装 `wl-paste` 或 `xclip`。
仍需能够访问桌面剪贴板；Wayland 需要支持 data-control 协议或启用 XWayland。
图片读取也优先使用随安装包提供的原生后端，保留真实尺寸并编码成 PNG；
Linux 原生图片读取支持 X11/XWayland，原有平台工具作为回退。
WSL 通过 PowerShell 读取 Windows 剪贴板，SSH 下会提示使用终端粘贴。
读取失败会在输入框下方显示提示。

Ctrl+B 复制当前输入内容，并展开粘贴文字占位符。本地桌面使用系统剪贴板；
SSH/tmux 下通过终端请求复制，本地复制失败也会尝试终端。终端需允许 OSC 52
剪贴板写入，或 tmux 支持剪贴板转发。“已请求终端复制”表示请求已发送，
并不表示已确认写入剪贴板。

鼠标中键将剪贴板中的图片或文字粘贴到当前激活的输入框，读取与 Ctrl+V 相同的
剪贴板；单行输入框只粘贴文字。无需先选中文字，粘贴不会自动发送消息。
终端需要向 Siada 转发鼠标事件，带修饰键的中键操作保留终端行为。
复制仍可使用鼠标选区及 Ctrl+C。

有选中文字时，在对应消息区或输入区域右键复制。确认写入剪贴板后清除选区；
复制失败或终端尚未确认时保留选区，可再次右键或按 Ctrl+C 重试，阅读位置保持不变。
没有选区时，本地 Linux、macOS 和 Windows 会话中的普通右键将文字粘贴到当前
可编辑输入框。SSH 和已识别的 VS Code 终端请使用终端菜单“粘贴”。
剪贴板读取期间，如果输入文字、收到终端粘贴、切换会话或离开输入框，会丢弃本次
读取结果。Siada 忽略带修饰键的右键；使用终端的鼠标绕过操作（通常为 Shift+右键）
打开原生菜单。

### 导出会话

使用 `/export [文件名]` 将完整会话保存为工作目录下的 `.txt` 文件。
导出沿用当前 TUI 的布局、终端宽度、语言、工具分组和折叠状态，包括单独展开的
消息块。Markdown、代码、表格和文件 diff 与对话视图使用相同的渲染。
文本文件保留排版和符号，不包含终端颜色及交互控件。

### 自主执行

Hook 反馈会单独显示，例如 `Hook · PreToolUse · 提示`。工具调用被 hook
拦截或回合被中止时，分别标为「已拦截」和「已中止」。紧凑模式也会保留这些
提示，导出会话时会保留 hook 事件名称和状态。

Siada 默认在用户请求的任务范围内直接执行工具（YOLO 模式）。代码代理不提供交互提问
工具或提问面板，工作进展和结果通过普通助手消息发送；执行过程中可以发送补充指令。

`run_subtask` 的普通、fork、后台和递归子任务均为无人值守执行，
无法解决的阻碍会汇报给调用方代理。

### ACP 对话中的浏览器上下文

浏览器客户端附带前置 `<browser-context>` 时，ACP 后端会将它与用户的原始输入分开。
同时包含页面上下文和 browser-skill 经验建议的回合，会以三个独立的 user-role 输入 item
传给代理：只包含用户消息的 `<user_input>`、包裹页面上下文的 `<system-reminder>`，
以及单独包裹经验建议的 `<system-reminder>`。缺少的上下文 item 不会添加；普通输入
保留原来的形态。

提醒标签仅标记低信任运行时上下文，不表示 system 消息角色，也不扩大授权。
两个上下文 item 会随回合保存，但在会话历史回放时隐藏。`@文件` 扩展只处理用户消息，
不会将上下文 item 再合并回用户输入。

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

- `/shell` - 切换到 shell 模式执行系统命令（输入 `exit` 或 `quit` 退出 shell 模式）
- `!<命令>` - 在不切换模式的情况下直接执行单条 shell 命令
- `/model` - 显示模型选择器或切换模型（`/model <model_name>`）
- `/editor` 或 `/edit` - 打开编辑器进行多行输入
- `/init [--force]` - 分析项目并创建定制的 siada.md 文件
- `/compact` - 压缩会话上下文；终端界面在压缩状态下方以树状分支展示消息数量变化和移除数量。压缩动画仅在压缩期间显示，结束后恢复模型推理状态。
- `/restore <checkpoint_file>` - 从检查点文件恢复会话状态（需要启用检查点跟踪）
- `/undo <checkpoint_file>` - 撤销检查点所做的更改，恢复到检查点创建之前的状态（需要启用检查点跟踪）
- `/compare <checkpoint_file>` - 将当前状态与检查点文件进行比较以查看差异
- `/memory-refresh` - 从 siada.md 文件刷新用户内存内容
- `/memory-status` - 显示当前用户内存状态（文件信息、大小、加载状态）
- `/status` - 显示当前会话状态（模型、Agent、会话ID和工作空间）
- `/lang` - 查看当前语言配置
  - `/lang zh` - 切换中文
  - `/lang en` - 切换英文
- `/exit` - 退出应用程序

在终端 UI 中，`/status` 和 `/help` 可以在 Agent 响应期间执行，不会打断
响应或进入模型输入。`/clear`、`/model` 等修改会话的命令会等待当前轮结束。

### Shell 模式使用说明

Siada CLI 提供两种方式执行系统命令：

#### 方式一：使用 `/shell` 切换到 shell 模式
切换到持续的 shell 模式，在此模式下可以连续执行多个系统命令：

```bash
> /shell
# 进入 shell 模式后可以执行多个命令
ls -la
cd my-project
npm install
git status
# 使用 exit 或 quit 退出 shell 模式
exit
```

#### 方式二：使用 `!` 前缀直接执行命令
在交互模式下直接执行单个系统命令，无需切换模式：

```bash
> !ls -la
> !git status
> !npm run dev
```

两种方式的区别：
- **`/shell`**：适合需要连续执行多个系统命令的场景，一次切换持续使用
- **`!<命令>`**：适合偶尔执行单个系统命令的场景，执行完立即返回 AI 对话模式

### 语言配置

终端界面默认使用英文。输入 `/language` 打开 English / 中文选择面板，也可使用
`/language en` 或 `/language zh-CN` 直接切换。选择立即生效，并以 `language` 字段
保存至 `~/.siada-cli/ui-config.json`，下次启动时沿用。命令名、模型名和用户内容保留原文。

`/lang` 单独控制 AI 回答的语言：

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

每次 `run_subtask` 执行使用独立的内存上下文，并可在上下文增长时进行压缩。后续 SDK 保存不会把压缩掉的原始任务输入重新加入；内容相同的消息不会被合并，包括继承（`fork`）历史中的重复消息。

使用 GPT-6 及以上模型（含 `astra` 别名）时，系统提示词要求仅在你或适用的
`SIADA.md`／`AGENTS.md`／技能指令明确要求子代理、委派或代理并行工作时，
才进行委派。例如：“让 reviewer 代理审查这次 diff。”
任务与代理描述匹配本身不构成委派要求。

## 示例

### 激活虚拟环境（仅开发者模式需要）
首先，进入 siada-agenthub 项目目录并激活虚拟环境：

```bash
# 进入项目目录
cd ~/path/to/siada-agenthub

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

**重新打开浏览器侧边栏：**

关闭 Siada 侧边栏后，Agent 和会话保留五分钟。在同一个浏览器窗口内重新打开，
会复用 Agent 并恢复对话历史。超过保留期后，下次打开会启动新 Agent 并恢复已保存的历史。
点击 **Disconnect** 会立即释放 Agent。关闭侧栏会取消正在执行的请求和待确认的权限，
并停止实时画面；保留期用于让 Agent 在重开时继续可用。

**模型 API 错误：**
- 检查您的网络连接

**模型调用了不可用的工具：**

Siada 会把工具错误和当前可用的工具名称返回给模型，并在同一次 Agent 执行中
继续处理，包括调用不可用的 `apply_patch` 的情况。不存在的工具不会执行，
已经完成的工具调用也不会重放。如果模型持续选择不可用的工具，仍受正常轮次上限约束。
恢复后保存的工具历史仍可在切换到 Chat Completions 模型，或使用该协议模型压缩上下文时重放。

**Connection prematurely closed DURING response：**

上游连接在模型流式响应过程中关闭。如果还未交出正文或工具事件，Siada
会按指数退避自动重试，最多两次，包括网关以 `stream_error` 报告断流的情况。
重试期间，已经显示的推理内容可能保留。

如果已经出现正文或工具事件，会话可从已保存的历史和已完成的工具结果继续，
最多恢复两次，未完成的工具调用会被丢弃。无法校验已保存历史、存储失败或
用户取消请求时，会停止恢复。

**恢复旧会话时上下文快照无法校验：**

- 旧版可能保存与完整历史不再匹配的快照边界，例如超长工具输出被截断后。这是本地兼容问题，不是模型 API 故障。
- 快照边界可验证时，Siada 保留快照并补齐尚未纳入的历史尾部。边界无法验证或快照缺失时，Siada 自动从完整原生历史重建上下文，无需用户确认。模型请求前仍会经过正常工具输出过滤，并按配置执行自动压缩。
- 重建可能重新带回此前被压缩流程移出有效上下文的内容。原始历史及已有的旧版 `api_messages.json` 会保留；边界降级会在日志中记录为 `action=rebuild_from_history`。
- 会话文件损坏、身份不匹配或存储失败仍会停止恢复。人工修复前请备份会话目录，不要删除快照或猜测 `last_index`。

**模型响应未完整结束：**

模型流结束时缺少最终响应事件，已经显示部分文字时也可能发生。
Siada 使用上述自动重试和历史恢复策略。如果恢复失败，手动重试前请检查
已显示的内容和工具执行结果。
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
