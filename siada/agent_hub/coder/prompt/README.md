# Coding System Prompt Layout

`code_gen_prompt.py` is the coding agent's stable entry point. It selects one
profile, collects runtime facts into `SystemPromptContext`, and calls the
renderer registry in `assembly/system.py`. Default and GPT-5 profiles keep the
historical section builder. GPT-6 uses `assembly/codex.py`: a complete per-model
template first, followed by capabilities, runtime instructions, environment,
language, the skills catalog, available agents, and memory. The old GPT-6 intro
and rule helpers remain available for compatibility imports but are not used
by the main GPT-6 prompt path.

Kimi K3 and later use `assembly/kimi.py` and a Kimi Code-based Markdown template in
`models/kimi_k3/templates/system.md`. Its communication, tool use, coding,
risk, delivery, context management, environment, and project information
sections follow Kimi Code's template. Runtime facts and the available tools
are adapted to Siada; the existing `edit_file` tool remains in use.

GLM-5.2 and later use `assembly/glm.py` and a ZCode-based Markdown template in
`models/glm/templates/system.md`. The template copies the ZCode CLI system
prompt (identity, harness, communication, environment, and context-management
sections) with the identity renamed to Siada and runtime facts substituted at
render time. The full-template families (Kimi, GLM, DeepSeek) render through
`assembly/markdown_template.py`, which owns the shared substitution logic:
Siada's capabilities, runtime instructions (Git safety, harness notices, OWASP,
non-interactive approval blockers), language, skills and agent catalogs, and
the framed combined memory follow the template text.

| Directory | Responsibility |
| --- | --- |
| `selection/` | Model-name feature predicates, prompt-family selection, and skill usage profiles. File-tool support is separate from prompt family. |
| `models/default/`, `models/gpt5/`, `models/gpt6/`, `models/glm/`, `models/kimi_k3/`, `models/deepseek/` | Family-specific content. GPT-6's `templates/composition.toml` defines a common section order, defaults and model overrides; Kimi K3, GLM-5.2+, and DeepSeek use Markdown templates with explicit runtime substitutions. |
| `sections/` | Shared capabilities, objectives, language, memory framing, and mode guidance. `sections/rules/` owns shared rules and family dispatch. |
| `assembly/` | Render preselected sections into the final string; no model-name classification on the main path. |
| `base/` | Thin imports for older callers; do not put new prompt content here. The deprecated `memory_section.py` is an empty compatibility stub. |

Keep existing sections byte-identical during structural refactors: the
`tests/agent_hub/coder/test_prompt_byte_compatibility.py` SHA-256 matrix and
synthetic `.snap` files protect the final prompt, whitespace included. New
model families belong in `models/` plus the `selection/` and rule dispatch
tables, not in `base/`.

## 统一渲染机制

所有模型的 system prompt 都经过 `assembly/template.py` 的一次性变量替换。
`assembly/system.py` 统一选择渲染器并添加 GPT-6 及后续版本已有的委派尾段；
`assembly/legacy.py` 负责 Default/GPT-5 的内容选择，模型模板和原文保持独立。
公共运行时指引、技能清单提取和记忆章节由 `assembly/fragments.py` 生成，
可选章节的判空、首尾裁剪和分隔符由公共渲染函数处理。

统一的是机制，不是输出格式：历史路径保留原有 `====`、清单空白和尾部换行；
GPT-6 保留不带边界的记忆章节；Markdown 家族保留各自模板中的章节位置。
运行时值只替换一次，其中的 `${...}`、`$$` 等文本不会再次展开。

`tests/agent_hub/coder/test_system_prompt_rendering.py` 使用重构前冻结的
SHA-256 基线，覆盖 56,160 组完整输出：全部六个家族、GPT-6 四个模板、模型别名、
未来 GPT 回退、三种操作系统、交互和子 agent 开关、联网工具组合及可选章节边界。
每组提示词按字节长度和原始 UTF-8 内容依次计入摘要；基线不在测试中自动更新。

GPT-6 templates and their source provenance/adaptations are documented in
[`models/gpt6/templates/README.md`](models/gpt6/templates/README.md). GPT-6.1 Terra
uses the Astra-equivalent base with its additional Default-mode execution
preference. GPT-6.1 Sol, GPT-6 Sol, and GPT-6 Luna retain their individual upstream
wording; Astra, its shorthand alias, and unrecognized GPT-6 variants use the Astra template.
The skills catalog is appended without a second skills usage block.
The four former GPT-6 Markdown skeletons are replaced by one composition with
explicit differences. No model prose, section order or whitespace is normalized.
Shared-section and model-setting audits prevent duplicated prose and unused or
redundant configuration from accumulating again.

Interactive question tools are not part of the coding agent's tool surface.
GPT-6 templates omit their question-tool guidance; the remaining per-model
instructions retain their existing wording.

Kimi detection compares the numeric major version and selects `KIMI_K3` for
K3 and later, including `kimi-k3.1`, `kimi-k3.5`, `kimi-k4`, and future versions.
Names are case-insensitive and accept provider-qualified forms, underscore
separators, and preview suffixes. Short names such as `k3`, `k3.1`, `k3.5`,
`k4`, and `openai/k4` also select this template. Kimi K2 and older keep the
default profile; partial names and conflicting numbered GPT names do not
select the Kimi template. The Kimi prompt replaces
the generic four-line response limit and strict skill usage block with Kimi
Code's terminal communication and relevant-skill guidance. It retains Siada's
Git safety, hook handling, non-interactive approval blockers, skills path aliases,
subagent switch, and framed combined memory. Dynamic values are substituted
once and are never interpreted as template syntax.

GLM detection selects the `GLM` family for GLM-5.2 and every later generation,
including provider-prefixed and `-flash` variants; GLM-5.1 and older keep the
default profile. The GLM prompt replaces the generic section builder with the
ZCode CLI system prompt: its identity, harness, communication, environment, and
context-management text is copied from ZCode (`zai-org/ZCode`, commit
`29628c9`) with the product identity renamed to Siada. ZCode's git-status
snapshot is not copied because Siada already injects one as runtime context;
Siada's capabilities, Git safety, non-interactive approval blockers, skills
path aliases, subagent switch, and framed combined memory are retained the same
way as in the Kimi prompt. The repeated-tool reminder for GLM models is a
runtime hook and is independent of this prompt change.

## DeepSeek 提示词

DeepSeek 模型使用 `assembly/deepseek.py` 和
`models/deepseek/templates/` 中的独立模板，来源为 DeepSeek Harness
`dsh@0.2.1-rc.2`。迁移保留上游身份句式、读取/编辑/搜索、技能加载、委派及联网
安全指引；只适配 Siada 的身份、实际工具名与参数。DeepSeek 仍使用 `edit_file`，
不沿用 GPT-6 的原生补丁工具。联网段落根据实际可用工具输出，关闭子 agent 后
同时移除委派段落和 agent 清单。

该路径复用 `assembly/markdown_template.py` 的一次性替换与运行时章节拼接，
新增可选的家族模板值及技能措辞，不改变 Kimi、GLM 或 GPT 系列已有提示词字节。
模型选择位于 `selection/`，原文位于 `models/deepseek/`，拼接位于 `assembly/`。
版本、原文路径、适配及省略项见
[`models/deepseek/templates/README.md`](models/deepseek/templates/README.md)。
