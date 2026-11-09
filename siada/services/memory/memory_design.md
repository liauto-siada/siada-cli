# 任务
参考OpenClaw关于记忆使用的实现方案， 在code_gen_agent执行任务的时候增加记忆检索能力， 使用MemorySearch的search方法。
重点在于agent如何与记忆工具集成

你要完全理解OpenClaw关于集成记忆检索的源代码后才可以开始写代码。 真正开始写代码之前最后先出一份详细的计划。

如果你有任何不清楚的地方可以问我。
注意保持代码简洁可读好维护。

## 实现进展

### 已完成功能 ✅

**核心实现：**
- ✅ MemoryService 类实现 (siada/services/memory/memory_service.py)
- ✅ 从 FileSession 读取会话历史
- ✅ 消息过滤和格式化（仅保存 user 和 assistant 消息，跳过命令）
- ✅ Markdown 格式化和文件存储
- ✅ 集成到 CodeGenAgent 的 run 和 run_streamed 方法

**LLM Slug 生成：**
- ✅ 使用 `siada.provider.client_factory.simple_completion` 简化接口
- ✅ 调用 LLM 分析会话内容生成描述性 slug
- ✅ 使用 context 中配置的 provider 和 model（默认 `settings.DEFAULT_MODEL`）
- ✅ 超时控制（15 秒）
- ✅ 自动降级到时间戳方案

**错误处理：**
- ✅ 完善的异常捕获，不影响主任务执行
- ✅ 使用 debug 级别记录错误
- ✅ 原子文件写入（临时文件 + 重命名）

**测试：**
- ✅ 测试脚本实现并通过 (tests/services/memory/test_memory_service.py)
- ✅ 验证消息读取、格式化、文件生成等功能

### 文件结构

```
siada/services/memory/
├── __init__.py              # 导出 MemoryService, MemoryDatabase, MemorySearch
├── memory_design.md         # 本设计文档
├── memory_service.py        # 核心服务 (434 行)
├── memory_db.py             # 数据库管理 + FTS5 索引 (323 行)
└── memory_search.py         # FTS5 搜索接口 (358 行)

siada/tools/memory/          # ✅ NEW - Agent 记忆工具
├── __init__.py              # 导出工具函数
└── memory_tool.py           # search_memory, get_memory 工具实现 (230 行)

siada/agent_hub/coder/
└── code_gen_agent.py        # 集成记忆工具到 CodeGenAgent

tests/services/memory/
├── test_memory_service.py   # MemoryService 测试
└── test_memory_fts5.py      # FTS5 功能测试

tests/tools/memory/          # ✅ NEW - 工具测试
├── __init__.py
└── test_memory_tool.py      # 记忆工具单元测试 (13 个测试用例)
```

### 核心功能说明

#### 1. 存储位置
默认：`~/.siada-cli/workspace/memory/`

#### 2. 文件命名格式
`YYYY-MM-DD-HH-MM-slug.md`

- 日期时间部分：本地时间的 YYYY-MM-DD-HH-MM 格式（精确到分钟）
- Slug 部分：
  - 优先：LLM 生成的描述性 slug（如 "api-design", "bug-fix"）
  - 降级：HHMM 格式的时间戳（如 "1234"）

#### 3. Markdown 格式

```markdown
# Session: YYYY-MM-DD HH:MM:SS UTC

- **Session ID**: <session_id>
- **Timestamp**: <iso_timestamp>

## Conversation Summary

user: <message_content>
assistant: <message_content>
...
```

### 与 OpenClaw 的差异

1. **语言**：TypeScript → Python
2. **触发机制**：`/new` 命令 → 任务完成时自动触发
3. **Session 格式**：JSONL → JSON
4. **实现范围**：仅 Markdown 存储层（不包含 SQLite 索引和搜索功能）

### 已完成扩展功能 ✅ (2024-02-13)

**SQLite FTS5 实现：**
- ✅ 数据库层实现 (siada/services/memory/memory_db.py)
- ✅ 表结构与 OpenClaw 完全一致
- ✅ 文本分块逻辑（默认 2048 字符/块）
- ✅ 自动索引：保存 markdown 时自动索引到 FTS5
- ✅ 搜索接口 (siada/services/memory/memory_search.py)
- ✅ BM25 相关性评分
- ✅ FTS5 查询构建（AND 逻辑）
- ✅ **中文分词支持**（基于 jieba，内置依赖）
  - ✅ 索引层预处理：写入 FTS5 前分词
  - ✅ 搜索层分词：查询时分词并过滤停用词
  - ✅ 自定义词典支持（预置 40+ 技术术语）
  - ✅ 中英混合查询支持
  - ✅ 默认启用，无需额外配置
- ✅ 测试完整覆盖
  - ✅ 基础功能测试 (test_memory_fts5.py)
  - ✅ 中文搜索测试 (test_chinese_search.py)

**数据库位置：** `~/.siada-cli/workspace/memory/memory.db`


### 最新进展 ✅ (2024-02-XX)

**Agent 集成完成：**
- ✅ 记忆工具模块实现 (siada/tools/memory/memory_tool.py)
- ✅ `search_memory` 工具：搜索历史对话和会话记忆
- ✅ `get_memory` 工具：读取记忆文件的特定内容
- ✅ 集成到 CodeGenAgent 工具列表
- ✅ 配置化启用/禁用支持
- ✅ 完整测试覆盖 (tests/tools/memory/test_memory_tool.py)

**工具特性：**
- 支持中英文混合搜索
- 可配置搜索结果数量和最低评分阈值
- 安全的文件访问控制（防止路径遍历）
- 支持按行范围读取文件内容
- 优雅的错误处理和降级

**使用方式：**
Agent 在执行任务时会自动判断是否需要调用记忆工具：
- 当用户询问历史对话内容时
- 当用户提及过去的决策或偏好时
- 当需要回忆之前讨论的技术方案时

### 未来扩展计划

- [ ] 向量化语义搜索
- [ ] 混合搜索（FTS5 + 向量）
- [ ] 增量同步机制
- [ ] 文件监控和自动重建索引
- [ ] 搜索结果缓存优化
- [ ] 记忆工具使用统计和分析 



# 以下是OpenClaw 关于记忆实现方案 
其源代码根目位置在 /Users/yunan/code/open-source/openclaw

一、整体架构

OpenClaw 使用三层存储策略来保存和检索会话记忆：Markdown 文件存储、SQLite 关系数据库、以及向量数据库。三者协同工作，分别服务于人类可读、关键词搜索和语义搜索的需求。

二、Markdown 文件存储层

触发机制
当用户执行 /new 命令创建新会话时，系统自动触发记忆保存流程。

核心代码位置：
- 文件：src/hooks/bundled/session-memory/handler.ts
- 主函数：saveSessionToMemory
- 辅助函数：getRecentSessionContent

工作流程
1. 监听命令事件，过滤出 new 命令
2. 从当前会话的 JSONL 文件读取最近 N 条消息（默认 15 条，可配置）
3. 提取用户和助手的对话，过滤掉工具调用、系统消息和命令
4. 使用 LLM 为会话生成简短的描述性文件名（slug）
5. 创建 Markdown 文件，包含元数据和完整对话原文
6. 文件命名格式：YYYY-MM-DD-slug.md，保存到 workspace/memory 目录

LLM Slug 生成
代码位置：
- 文件：src/hooks/llm-slug-generator.ts
- 函数：generateSlugViaLLM

生成器调用配置的 LLM（通过 runEmbeddedPiAgent）分析对话内容前 2000 字符，返回 1-2 个单词的描述性短语，经过清理和格式化后作为文件名。如果失败则使用时间戳作为降级方案。

三、SQLite 数据库存储层

数据库管理
核心代码位置：
- 文件：src/memory/manager.ts
- 主类：MemoryIndexManager
- 关键方法：sync、indexFile、syncMemoryFiles、syncSessionFiles

数据表结构
系统创建四张主要表：

Schema 定义位置：
- 文件：src/memory/memory-schema.ts
- 函数：ensureMemoryIndexSchema

1. meta 表：存储索引元数据（模型、分块参数等）
2. files 表：记录已索引文件的路径、哈希、修改时间
3. chunks 表：存储文本分块和对应的向量
4. embedding_cache 表：缓存已生成的向量，避免重复计算

文本分块策略
代码位置：
- 文件：src/memory/internal.ts
- 函数：chunkMarkdown

系统按行读取 Markdown 内容，当累积字符数超过阈值（默认约 2048 字符，基于 512 tokens 估算）时创建一个分块。支持重叠策略保持上下文连贯性。每个分块记录起始和结束行号、文本内容和内容哈希。

索引流程
主方法： MemoryIndexManager.indexFile

流程包括：
1. 读取文件内容并调用分块函数
2. 为每个文本块生成向量（调用 embedding 提供商）
3. 删除该文件的旧索引记录
4. 插入新的分块记录到 chunks 表（包含原文和向量 JSON）
5. 如果启用向量搜索，插入到 vec0 虚拟表
6. 如果启用全文搜索，插入到 fts5 虚拟表
7. 更新 files 表记录

四、FTS5 全文搜索

启用机制
表创建位置： memory-schema.ts 中的 ensureMemoryIndexSchema 函数

系统尝试创建名为 chunks_fts 的 FTS5 虚拟表，包含 text 字段用于全文索引，其他字段标记为 UNINDEXED 仅用于返回结果。

搜索实现
代码位置：
- 文件：src/memory/manager-search.ts
- 函数：searchKeyword
- 辅助函数：buildFtsQuery（在 src/memory/hybrid.ts）

关键词搜索构建 FTS5 查询语法，执行 MATCH 查询，使用 BM25 算法计算相关性分数，返回匹配的文本块及其上下文信息。

五、向量化与语义搜索

向量生成
Embedding 提供商管理：
- 文件：src/memory/embeddings.ts
- 函数：createEmbeddingProvider

系统支持三种 embedding 提供商：OpenAI、Gemini、本地模型。根据配置选择提供商，调用其 API 将文本转换为向量。

批处理逻辑：
- 主方法：MemoryIndexManager.embedChunksInBatches
- 批量方法：embedChunksWithBatch、embedBatchWithRetry

系统优先使用缓存的向量，对于未缓存的文本批量调用 embedding API。支持重试机制和错误处理，遇到问题可降级到备用提供商。

sqlite-vec 扩展
加载位置：
- 文件：src/memory/sqlite-vec.ts
- 函数：loadSqliteVecExtension
- 调用位置：MemoryIndexManager.loadVectorExtension

系统动态加载 sqlite-vec 扩展，创建 chunks_vec 虚拟表存储向量的二进制表示。表结构包含 id 和 embedding 两列，embedding 使用 float 数组的 blob 格式。

向量搜索
代码位置：
- 文件：src/memory/manager-search.ts
- 函数：searchVector

搜索流程：
1. 将查询文本转换为向量
2. 使用 sqlite-vec 的相似度函数查询最近邻
3. JOIN chunks 表获取对应的原文
4. 计算余弦相似度作为相关性分数
5. 返回排序后的结果

六、混合搜索

代码位置：
- 文件：src/memory/hybrid.ts
- 函数：mergeHybridResults、bm25RankToScore

系统同时执行向量搜索和关键词搜索，对两组结果进行加权合并。向量搜索分数和 BM25 分数分别乘以配置的权重，相同文本块的分数相加，最后按总分排序返回。默认配置为向量搜索权重较高。

七、增量同步机制

文件监控
主方法： MemoryIndexManager.ensureWatcher

系统使用 chokidar 库监控 memory 目录的文件变化，检测到修改后延迟触发同步。避免频繁的重建索引操作。

会话增量更新
代码位置：
- 监听器注册：ensureSessionListener
- 增量处理：updateSessionDelta、processSessionDeltaBatch

系统监听会话文件的实时更新事件，记录每个文件的已索引大小，仅处理新增的内容。通过读取文件末尾的增量字节，统计新增消息数量，达到阈值后触发增量索引。

定时同步
方法： MemoryIndexManager.ensureIntervalSync

可配置定时任务（默认每隔若干分钟）自动执行全量同步，确保所有变更被索引。

八、数据内容说明

存储的都是完整原文
- Markdown 文件：存储可配置数量（默认 15 条）的完整对话
- chunks 表的 text 列：存储分块后的完整原文
- FTS5 表：存储相同的完整原文用于全文索引
- embedding 列：以 JSON 数组格式存储向量
- chunks_vec 表：仅存储向量的二进制表示

无压缩或总结
整个流程中没有使用 LLM 对内容进行压缩或摘要。LLM 仅用于生成文件名。所有文本保持原始形态，仅进行分块处理以适应 embedding 模型的输入限制。

九、配置与扩展

配置解析
代码位置：
- 文件：src/agents/memory-search.ts
- 函数：resolveMemorySearchConfig

解析用户配置，包括存储路径、embedding 提供商、分块参数、搜索权重、同步策略等。

Hook 配置
位置： src/hooks/config.ts 中的 resolveHookConfig

session-memory hook 支持配置保存的消息数量，通过读取 hooks 配置的 messages 参数实现。

批处理支持
文件：
- OpenAI Batch：src/memory/batch-openai.ts（函数 runOpenAiEmbeddingBatches）
- Gemini Batch：src/memory/batch-gemini.ts（函数 runGeminiEmbeddingBatches）

对于大量文本，系统支持使用提供商的批处理 API 降低成本和提高效率。创建批处理作业，轮询状态，失败时降级到常规 API。

十、搜索统一接口

代码位置：
- 文件：src/memory/manager.ts
- 主方法：MemoryIndexManager.search

搜索接口自动选择最优策略：
- 如果向量和 FTS 都可用且配置启用混合搜索，执行混合搜索
- 否则优先使用向量搜索
- 向量不可用时降级到关键词搜索
- 都不可用时返回空结果

返回结果包含匹配的文本片段、文件路径、行号范围、相关性分数等信息，供 AI 助手引用和回答用户问题。
