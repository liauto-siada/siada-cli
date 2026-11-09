# DeepSeek Harness 提示词迁移

来源为 `deepseek-ai/deepseek-harness` 的 `dsh@0.2.1-rc.2`，对应提交
`687f282e8625c6b8d11ff58211a90524be2e4317`（2026-10-17）。CLI 包
`apps/cli/package.json` 声明版本为 `0.2.1-rc.2`。

该版本通过系统提示词注册表按顺序拼接身份、部署 persona 和工具使用指引，
并没有 GPT-6 那样单独的长篇行为模板。本目录保留实际可迁移的原文，
不把测试场景自定义 persona 当作产品默认提示词。

## 原文对应关系

| 本地模板 | 上游来源 | 适配内容 |
| --- | --- | --- |
| `system.md` | `packages/core/system-prompt/src/index.ts`、`packages/bundle/web-app/presets/standard.patch.yml` | 将 Harness 身份改为 Siada，保留 coding agent 句式，插入实际模型名称。 |
| `system.md` 的命令、读取、编辑和搜索段落 | `packages/shell/tool-bash/src/index.ts`、`packages/fs/tool-fs/src/read.ts`、`edit.ts`、`packages/fs/tool-fs-search/src/grep.ts` | 使用 Siada 的 `run_cmd`、`edit_file`、`regex_search_files`，参数改为 `command` 和 `view_range`。保留可适用的句子与段落顺序。 |
| `skills.md` | `packages/skill/tool-skill/src/index.ts` 的 `renderCatalogMessage()` | 保留命中技能后先加载、加载所有适用技能、不能从摘要推断指令的措辞；技能加载改为读取 `SKILL.md`，路径使用 Siada 的别名表。 |
| `delegation.md` | `packages/subagent/tool-subagent/src/index.ts` | 将 `subagent` / `subagent_fork` 改为 `run_subtask`，保留独立委派在同一消息中启动并继续有用工作的原句结构。 |
| `web-search.md`、`web-search-only.md` | `packages/web/tool-web/src/search.ts` | 按实际工具集选择是否推荐 `web_fetch`；仅搜索时原文保留，两者可用时将获取“全文”改为获取“更多细节”，避免承诺 Siada 未返回的内容。 |
| `web-fetch.md` | `packages/web/tool-web/src/fetch.ts` | 首段原文保留；追加 Siada 的条件参数说明、分析与预览边界及失败结果的证据限制。 |

模型名称采用调用方选定的名称，不将 provider 前缀或版本后缀改写为其他模型。
DeepSeek 检测使用独立词边界，支持大小写、provider 前缀及 slash/underscore
限定形式；编号 GPT 模型不会被误判为 DeepSeek。现有 DeepSeek 型号均走此路径。

## 联网工具适配

以下为 Siada 本地适配，不属于上游原文，不增加主动联网调用倾向：

- `web_search` 每次接收一个字符串 `query`，不是上游的 `queries` 数组；
  返回标题、URL、可选摘要及站点和发布时间信息，不返回页面全文。
  搜索参数已经由工具 schema 和描述提供，模板不重复上游的调用协议。
- `web_fetch` 的内置服务实现要求 `url` 和 `prompt`，返回根据 prompt 生成的
  分析结果；公开版回退实现接收 `url` 和 `output_format`，返回提取的内容。
  回退实现的部分工具描述示例使用 `format`，但实际 schema 中的参数名为
  `output_format`。模板明确以本次工具 schema 为准，不混用两种实现的参数。
- 当前两种抓取观察对象的字符串输出都将正文限制为前 200 个字符的预览；
  公开版提取内容本身也有长度截断。不能把预览或分析结果当作完整网页原文，
  也不能根据失败结果推断页面内容。本次仅调整提示词，不修改工具及结果序列化。

## 运行时拼接

`assembly/deepseek.py` 复用 `assembly/markdown_template.py`，在模板后保留
Siada 的能力清单、Git 安全、系统提醒、OWASP 安全规则、环境、语言、技能路径别名、
可用 agent 清单及带边界的 Combined Memory。动态值只替换一次，不重新解释其中
的 `${...}` 或 shell 表达式；不存在的模板变量会显式报错。

普通 DeepSeek 模型继续使用复合 `edit_file` 工具，不切换为 GPT-6 的
`read_file` / `apply_patch` 工具协议。关闭子 agent 后，委派提示和 agent 清单
一起移除。联网段落依据本次运行的实际工具名称输出；工具集未知时不猜测可用性。
DeepSeek 不拼接公共能力清单中的主动委派措辞；系统委派段落保留上游原文。
`run_subtask` 继续沿用 Siada 公共工具说明，仅移除额外的主动调用段落；
角色、参数和返回说明保持不变，递归子 agent 使用同样的工具措辞。
不追加 DeepSeek 专属的 fork 身份说明，不修改现有 fork 输入与继承行为。
工具描述和 fork 身份说明的统一适配留待后续覆盖所有模型。
非交互模式保留 Siada 的授权边界和无法提问时的阻塞说明。
读取大文件时保留 Siada 工具的截断例外：`[FILE TRUNCATED: ...]` 表示字节截断，
不能继续通过 `view_range` 翻页，必须按工具返回指引改用搜索或局部 shell 读取。

没有移植的上游机制包括独立 `read` / `write` / `edit` / `glob` 工具、
`fs-observation-policy`、`[exit code: N]` 标记、`job_output` / `job_kill`、
workflow、goal 的 Harness 专有控制协议、plan-mode 和问答工具、`present` 文件卡片，
以及 Web GUI / 源码 checkout 专属上下文。这些机制与 Siada 的实际工具或运行方式
不同，不能只复制提示词就宣称支持。

## 子 agent 实现差异（未移植）

以下为实现对照，不代表本次移植了这些机制；当前仅移除 DeepSeek 的额外主动调用措辞。

| 设计点 | DeepSeek Harness `dsh@0.2.1-rc.2` | Siada 现有实现 |
| --- | --- | --- |
| 工具入口 | 普通 `subagent` 与 `subagent_fork` 分别绑定 spawn / fork provider。 | 合并为 `run_subtask(instruction, agent, fork, async)`；工具参数、执行回调和审批检查保持不变。 |
| 独立角色 | 普通子 agent 默认继承父级 preset 的配置，但不继承会话；部署可通过允许列表开放 `agent_preset` 选择。fork 不支持独立 preset。 | 不指定 `agent` 时使用通用 SubTaskAgent；指定时读取用户定义角色，并叠加无人值守规则、工具限制、预加载技能、MCP、effort 和 model。指定角色会忽略 `fork`，不是同时继承父 prompt 与独立角色。 |
| fork 历史 | 捕获截至最后一个 `turn/end` 的已完成轮次，明确排除进行中轮次。 | 从 FileSession 复制当前有效上下文，不按 `turn/end` 切片；说明为快照而非后续会话同步，不承诺排除当前轮次。 |
| fork 身份 | 新子 agent 作用域继承 preset 配置；委派身份与父 agent 返回说明使用运行时上下文或任务消息，不额外改变系统提示词前缀。 | 继承父系统提示词和实际工具列表，子任务输入保持原样；专属身份与返回说明未移植，留待后续统一处理。 |
| 返回与继续通信 | 工具立即返回持久子 agent id；进程内子 agent 可用 `send_message` 报告结果并接受后续消息。 | 默认等待最终结果；`async=True` 返回后台任务 id，角色 `background: true` 强制后台。结果由运行时注入，不宣称支持 `send_message` 或按 id 续聊。 |
| 模型与目录 | 工具可按配置开放 provider / model / effort 和 `cwd` 参数。 | 工具没有这些直接参数；模型取子 agent 配置或角色定义，工作目录沿用父 context。 |
| 递归与权限 | provider 能力、深度限制及子作用域权限由 Harness 校验。 | 保留 Siada 的总开关、递归开关、深度与并发限制和 `is_subagent` 运行时检查；不照搬上游“任何需要审批的操作都会自动拒绝”的保证。 |

## 回归检查与许可

`tests/agent_hub/coder/test_deepseek_prompt.py` 固定迁移模板和最终提示词的
SHA-256，覆盖模型路由、两种交互模式、可选章节、工具可用性、一次替换和
CodeGenAgent 的实际提示词交付。公共字节兼容测试继续保护其他模型原有输出。
联网回归还核对实际抓取工具 schema、模型可见的预览及失败结果；验证不调用联网工具。

上游采用 MIT 许可。原始版权声明为 `Copyright (c) 2026 DeepSeek`，
版权与许可声明保留在仓库的 `docs/CREDITS.md`，并随 Siada 包分发。
