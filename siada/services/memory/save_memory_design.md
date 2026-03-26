# 记忆存储系统设计文档

## 一、记忆分类

记忆系统分为三个层次，形成"原始数据→衍生总结"的层级结构：

### 1. 会话级别记忆 (Session Memory)
- **用途**：记录完整的用户-AI对话内容，是所有记忆的原始数据源
- **特点**：每个会话可能包含多轮对话，记录详细的交互过程
- **存储形式**：按日期时间和主题命名的MD文件，如 `2024-01-15-14-30-实现记忆功能.md`
- **数据库标识**：`source='session'`

### 2. 个人风格记忆 (Personal Style Memory)
- **用途**：总结用户的工作方式、职责、习惯等个人特征
- **提取内容**：
  - 工作方式特点（偏好的工具、框架、代码风格）
  - 工作职责（负责的项目、团队角色）
  - 工作习惯（工作时间、沟通方式、问题解决思路）
  - 技术偏好（技术栈、开发环境）
- **存储形式**：单一文件 `personal_style.md`，持续更新
- **数据库标识**：`source='personal_style'`

### 3. 最近工作任务记忆 (Recent Task Memory)
- **用途**：追踪用户近期的主要工作任务和进展
- **提取内容**：
  - 进行中的任务（当前状态、技术方案）
  - 已完成的任务（成果总结）
  - 待处理的问题（问题描述、可能的解决方案）
- **存储形式**：单一文件 `recent_task.md`，按时间倒序更新
- **数据库标识**：`source='recent_task'`

---

## 二、现状分析

### 已实现功能
- `MemoryService.save_session_memory()` 实现了会话记忆的存储
- 支持MD文件和SQLite数据库双重持久化
- 数据库使用FTS5实现全文搜索

### 现有数据库表结构
- **`files`** 表：追踪所有索引的文件（通过 `source` 字段区分记忆类型）
- **`chunks`** 表：存储文件的分块内容（通过 `source` 字段区分记忆类型）
- **`chunks_fts`** 表：FTS5全文搜索索引
- **`meta`** 表：元数据存储

### 待实现功能
1. 个人风格记忆和工作任务记忆的智能提取和存储
2. 创建专门的记忆提取Agent（参考agents库的Agent模式）
3. 在会话保存后自动触发衍生记忆更新

---

## 三、数据存储设计

### 3.1 存储架构
记忆系统采用**双层存储架构**：

1. **文件层**：Markdown文件，便于人类阅读和编辑
2. **数据库层**：SQLite + FTS5，支持高效的全文搜索

### 3.2 数据库表设计

#### 复用现有表结构
所有记忆类型共用以下表结构，通过 `source` 字段区分，**无需新增表**：

- **`files` 表**：文件索引表
  - `path`：文件路径（主键）
  - `source`：记忆类型标识（'session' / 'personal_style' / 'recent_task'）
  - `hash`：文件内容哈希值
  - `mtime`：最后修改时间
  - `size`：文件大小

- **`chunks` 表**：文本分块表
  - `id`：分块唯一标识（主键）
  - `path`：文件路径
  - `source`：记忆类型标识
  - `start_line` / `end_line`：行号范围
  - `text`：分块文本内容
  - `embedding`：向量嵌入（预留）
  - 索引：`idx_chunks_path`、`idx_chunks_source`

- **`chunks_fts` 表**：FTS5全文搜索虚拟表
  - 对 `chunks.text` 建立全文索引
  - 支持中文分词（使用jieba）

**设计要点**：
- ✅ 通过 `source` 字段实现记忆类型隔离，便于按类型搜索
- ✅ 避免数据冗余：会话、个人风格、任务记忆共享 files/chunks 表结构
- ✅ 无需追踪历史：每次会话保存后立即触发更新，由Agent智能判断是否需要更新衍生记忆

### 3.3 数据流向与更新机制

```
用户对话结束
    ↓
save_session_memory() 保存会话记忆
    ↓ (异步触发)
update_derived_memory(session_content)
    ↓ (准备输入)
读取 personal_style.md + recent_task.md
    ↓ (构建System Prompt)
System Prompt = 当前记忆状态 + 更新标准
    ↓ (调用Agent)
Agent分析：session_content (User Input)
    ↓ (Agent决策)
判断是否需要更新？
    ↓
├─→ 需要更新个人风格
│   └─→ 调用工具：update_personal_style_memory(new_content)
│       ├─→ 写入 personal_style.md
│       └─→ 索引数据库 (source='personal_style')
│
├─→ 需要更新工作任务
│   └─→ 调用工具：update_recent_task_memory(new_content)
│       ├─→ 写入 recent_task.md
│       └─→ 索引数据库 (source='recent_task')
│
└─→ 无需更新
    └─→ 不调用任何工具
```

**关键特点**：
- **实时触发**：每次会话保存后立即触发
- **智能判断**：Agent通过LLM能力自主判断是否需要更新
- **工具驱动**：更新操作通过工具调用完成，职责分离清晰
- **并发执行**：使用asyncio后台任务，不阻塞主流程

### 3.4 文件输出位置
- `~/.siada-cli/workspace/memory/personal_style.md` - 个人风格记忆
- `~/.siada-cli/workspace/memory/recent_task.md` - 工作任务记忆
- `~/.siada-cli/workspace/memory/{date}-{slug}.md` - 会话记忆
- `~/.siada-cli/workspace/memory/memory.db` - SQLite数据库

---

## 四、实现步骤

### 步骤一：创建记忆提取Agent (memory_agent.py) ✅

**状态**: 已完成
**完成时间**: 2024-01-15

**目标**：使用LLM智能判断是否需要更新记忆，并通过工具调用完成更新

#### 1.1 定义System Prompt构建函数
**函数：`build_memory_extraction_prompt(personal_style_content, recent_task_content)`**
- 参数：
  - `personal_style_content`：当前 personal_style.md 的内容（可能为空）
  - `recent_task_content`：当前 recent_task.md 的内容（可能为空）
- 返回：动态构建的system prompt，包含：
  
**Prompt结构**：
```
你是记忆管理助手，负责维护用户的个人风格记忆和工作任务记忆。

## 当前记忆状态

### 个人风格记忆（personal_style.md）
{personal_style_content 或 "暂无"}

### 最近工作任务记忆（recent_task.md）
{recent_task_content 或 "暂无"}

## 你的任务
分析用户刚完成的对话内容，判断是否需要更新上述记忆：

### 个人风格记忆更新标准
- 包含：工作方式特点、工作职责、工作习惯、技术偏好
- 只提取明确的、可验证的信息，
- 与现有内容去重， 要进一步整理和压缩
- 使用Markdown格式，按以下结构组织：
  - 工作方式特点
  - 工作职责
  - 工作习惯
  - 技术偏好
- 个人风格记忆总长度低于 4096 tokens  

### 工作任务记忆更新标准
- 包含：具体任务、任务状态、技术方案、问题和解决方案
- 保留最近7天的任务
- 按时间倒序排列
- 使用Markdown格式，按以下结构组织：
  - 已完成的任务
  - 进行中的任务
  - 即将开始的任务
- 工作任务记忆总长度低于 4096 tokens 

## 如何更新
- 如果对话包含新的个人风格信息，调用 update_personal_style_memory(content) 工具
- 如果对话包含新的工作任务信息，调用 update_recent_task_memory(content) 工具
- 如果都没有新信息，不调用任何工具

## 注意事项
- 判断要严格：纯技术讨论、问答、闲聊不算新信息
- 更新要完整：调用工具时传入完整的更新后的记忆内容
- 格式要规范：使用清晰的Markdown格式
```

#### 1.2 实现Agent单例模式
**函数：`get_memory_extraction_agent(context)`**
- 使用全局变量 `_GLOBAL_MEMORY_EXTRACTION_AGENT` 实现单例
- 参考agents库模式创建Agent实例
- 配置模型：通过 ModelProviderWrapper 获取
- **不设置固定的system prompt**（每次调用时动态传入）
- 注册工具函数（使用 @function_tool 装饰器）
- 配置 RunConfig（max_turns=5, tool_call_policy="auto"）

#### 1.3 定义工具函数（供Agent调用）
**工具1：`update_personal_style_memory(content: str)`**
- 功能：更新个人风格记忆
- 参数：更新后的完整记忆内容（Markdown格式）
- 操作：
  - 写入 `~/.siada-cli/workspace/memory/personal_style.md`
  - 调用 `db.index_file()` 重新索引（source='personal_style'）
- 返回："个人风格记忆已更新"

**工具2：`update_recent_task_memory(content: str)`**
- 功能：更新最近工作任务记忆
- 参数：更新后的完整记忆内容（Markdown格式）
- 操作：
  - 写入 `~/.siada-cli/workspace/memory/recent_task.md`
  - 调用 `db.index_file()` 重新索引（source='recent_task'）
- 返回："工作任务记忆已更新"

#### 1.4 实现Agent调用包装函数
**异步函数：`analyze_and_update_memory(context, session_content, personal_style_content, recent_task_content)`**
- 参数：
  - `context`：代码Agent上下文
  - `session_content`：当前会话的完整内容（字符串）
  - `personal_style_content`：现有个人风格记忆内容
  - `recent_task_content`：现有工作任务记忆内容
- 流程：
  1. 获取Agent实例
  2. 动态构建system prompt（调用 build_memory_extraction_prompt）
  3. 将会话内容作为user message
  4. 运行Agent（使用 Runner 类）
  5. Agent自动判断并可能调用工具
- 返回：Agent的执行结果（包含工具调用信息）

---

### 步骤二：扩展MemoryService (memory_service.py) ✅

**状态**: 已完成
**完成时间**: 2024-01-15

**目标**：在会话保存后自动触发衍生记忆更新

#### 2.1 添加辅助方法
**方法：`_read_memory_file(memory_type: str) -> str`**
- 功能：读取指定类型的记忆文件
- 参数：'personal_style' 或 'recent_task'
- 返回：文件内容，如不存在返回空字符串

**方法：`_format_session_content(messages: List[Dict]) -> str`**
- 功能：将消息列表格式化为易读的文本
- 参数：消息列表（已在 save_session_memory 中获取）
- 返回：格式化的会话内容字符串

#### 2.2 添加核心更新方法
**异步方法：`update_derived_memory(session_content: str)`**
- 功能：根据当前会话内容更新衍生记忆
- 参数：当前会话的格式化内容（不是文件路径！）
- 流程：
  1. 读取现有的两个记忆文件内容
     - `personal_style_content = self._read_memory_file('personal_style')`
     - `recent_task_content = self._read_memory_file('recent_task')`
  2. 获取上下文（CodeAgentContext）
  3. 调用 `analyze_and_update_memory(context, session_content, personal_style_content, recent_task_content)`
  4. Agent内部会判断并调用工具完成更新（工具直接写文件+索引）
  5. 记录日志
- 注意：所有更新操作都由Agent的工具完成，此方法只负责协调

#### 2.3 扩展现有会话保存方法
**修改方法：`save_session_memory(file_session, auto_update_derived=True)`**
- 在现有实现中修改：
  1. 在格式化Markdown内容后，保存 `all_messages` 变量（已有）
  2. 在写入文件成功后，如果 `auto_update_derived=True`：
     - 调用 `session_content = self._format_session_content(all_messages)`
     - 使用 `asyncio.create_task(self.update_derived_memory(session_content))` 创建后台任务
  3. 继续后续流程（索引等）
- 保持现有功能不变

---

## 五、实现总结

### 实现状态
✅ 所有步骤已完成

### 完成的功能

#### 1. 记忆提取Agent (memory_agent.py)
- ✅ 动态System Prompt构建 (`build_memory_extraction_prompt`)
- ✅ Agent单例模式 (`get_memory_extraction_agent`)
- ✅ 工具函数实现:
  - `update_personal_style_memory`: 更新个人风格记忆
  - `update_recent_task_memory`: 更新工作任务记忆
- ✅ Agent调用包装 (`analyze_and_update_memory`)

#### 2. MemoryService扩展 (memory_service.py)
- ✅ 辅助方法实现:
  - `_read_memory_file`: 读取记忆文件
  - `_format_session_content`: 格式化会话内容
- ✅ 核心更新方法 (`update_derived_memory`)
- ✅ 会话保存方法扩展 (`save_session_memory`):
  - 新增 `auto_update_derived` 参数
  - 使用 `asyncio.create_task` 异步触发更新
  - 修正会话记忆的source标识为'session'

### 架构特点

1. **智能判断**: Agent通过LLM能力自主判断是否需要更新记忆
2. **工具驱动**: 更新操作通过function_tool完成,职责清晰
3. **异步执行**: 使用asyncio后台任务,不阻塞主流程
4. **单例模式**: Agent实例全局复用,提高效率
5. **双层存储**: 
   - 文件层: Markdown格式,便于人类阅读
   - 数据库层: SQLite + FTS5,支持高效搜索

### 数据流向

```
用户对话 → save_session_memory() → 保存会话MD文件
                ↓
            索引数据库 (source='session')
                ↓
            触发 update_derived_memory() (异步后台任务)
                ↓
            读取现有记忆 → 调用Agent分析
                ↓
            Agent判断 → 可能调用工具
                ↓
        工具更新文件 + 重新索引数据库
        (source='personal_style' / 'recent_task')
```
