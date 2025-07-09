# LoggerTracingProcessor - 详细的推理过程日志记录器

这个目录包含了一个自定义的 `TracingProcessor` 实现，用于详细记录 OpenAI Agents 的执行过程。

## 功能特性

- **模型调用监控**：记录每次模型调用的输入输出，支持增量消息显示
- **工具调用跟踪**：详细记录工具函数的输入参数和返回结果
- **Agent 切换记录**：完整跟踪 handoff 过程和 Agent 间的切换
- **生命周期管理**：记录整个推理过程的开始、结束和统计信息
- **可配置输出**：支持彩色输出、内容截断、文件保存等选项

## 文件结构

```
examples/tracing/
├── __init__.py                    # 模块导入
├── logger_tracing_processor.py    # 主要实现
├── example_usage.py              # 使用示例
└── README.md                     # 说明文档
```

## 快速开始

### 1. 基本使用

```python
from agents.tracing import add_trace_processor
from examples.tracing import create_simple_logger

# 注册日志处理器
add_trace_processor(create_simple_logger())

# 正常运行你的 Agent
result = await Runner.run(agent=your_agent, input="your input")
```

### 2. 详细配置

```python
from examples.tracing.logger_tracing_processor import LoggerTracingProcessor

# 创建自定义配置的日志处理器
logger = LoggerTracingProcessor(
    show_model_calls=True,      # 显示模型调用
    show_tool_calls=True,       # 显示工具调用
    show_handoffs=True,         # 显示 Agent 切换
    show_trace_lifecycle=True,  # 显示生命周期
    max_content_length=500,     # 内容最大长度
    show_timestamps=True,       # 显示时间戳
    use_colors=True,           # 使用彩色输出
    output_file=None          # 使用默认路径 ~/.siadahub/logs/agent_trace-yyyymmdd.log
)

add_trace_processor(logger)
```

## 输出示例

运行时会看到类似以下的输出：

```
🚀 === TRACE STARTED ===
Workflow: Agent workflow
Trace ID: trace_abc123
Started: 🕐 10:30:15 
=========================

🤖 === MODEL CALL 1 ===
🕐 10:30:15 Model: gpt-4
📥 New Input Messages:
  [user]: 请搜索并分析特斯拉的最新财务表现

📤 Model Output:
  [assistant]: 我来帮您搜索特斯拉的财务信息
  🔧 Tool Call: search_web({"query": "特斯拉财务表现 2024"})

🔧 === TOOL CALL 1 ===
🕐 10:30:16 Function: search_web
📥 Input: {"query": "特斯拉财务表现 2024"}
📤 Output: "搜索结果：找到关于 '特斯拉财务表现 2024' 的 5 篇相关文章"

🔄 === HANDOFF 1 ===
🕐 10:30:17 
📤 From Agent: SearchAgent
📥 To Agent: AnalysisAgent

🤖 === MODEL CALL 2 ===
🕐 10:30:17 Model: gpt-4
📥 New Input Messages:
  [tool]: "搜索结果：找到关于 '特斯拉财务表现 2024' 的 5 篇相关文章"

📤 Model Output:
  [assistant]: 基于搜索结果，我来分析特斯拉的财务表现...

🏁 === TRACE ENDED ===
Workflow: Agent workflow
Duration: 15.3s
Model Calls: 2
Tool Calls: 1
Handoffs: 1
======================
```

## 配置选项

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `show_model_calls` | bool | True | 是否显示模型调用详情 |
| `show_tool_calls` | bool | True | 是否显示工具调用详情 |
| `show_handoffs` | bool | True | 是否显示 Agent 切换 |
| `show_trace_lifecycle` | bool | True | 是否显示 Trace 生命周期 |
| `max_content_length` | int | 500 | 内容显示的最大长度 |
| `show_timestamps` | bool | True | 是否显示时间戳 |
| `use_colors` | bool | True | 是否使用彩色输出 |
| `output_file` | str\|None | None | 可选的日志文件路径 |
| `indent_level` | int | 0 | 输出的缩进级别 |

## 预设配置

提供了三种预设配置：

### 1. 简单日志记录器
```python
from examples.tracing import create_simple_logger
add_trace_processor(create_simple_logger())
```
- 显示所有类型的事件
- 中等长度的内容显示 (300 字符)
- 彩色输出

### 2. 详细日志记录器
```python
from examples.tracing import create_detailed_logger
add_trace_processor(create_detailed_logger(output_file="trace.log"))
```
- 显示所有类型的事件
- 较长的内容显示 (1000 字符)
- 包含时间戳
- 可选文件输出

### 3. 最小化日志记录器
```python
from examples.tracing import create_minimal_logger
add_trace_processor(create_minimal_logger())
```
- 只显示模型调用和 handoff
- 较短的内容显示 (200 字符)
- 无彩色输出

## 运行示例

```bash
# 运行完整示例
python examples/tracing/example_usage.py

# 或者在项目根目录运行
python -m examples.tracing.example_usage
```

## 核心特性详解

### 增量消息显示

LoggerTracingProcessor 的一个重要特性是**增量消息显示**。在多轮对话中，它只会显示新增的消息，避免重复打印相同的历史消息。

```python
# 第一次模型调用
📥 New Input Messages:
  [user]: "请搜索特斯拉信息"

# 第二次模型调用（只显示新增的消息）
📥 New Input Messages:
  [tool]: "搜索结果：..."
```

### 多模态内容支持

支持处理包含文本、图片等多种类型的消息内容：

```python
📥 New Input Messages:
  [user]: text: 分析这张图片 | image: [image data]
```

### 统计信息

在 Trace 结束时提供完整的统计信息：

- 总执行时间
- 模型调用次数
- 工具调用次数  
- Agent 切换次数

## 与 RunHooks 的区别

| 特性 | LoggerTracingProcessor | RunHooks |
|------|----------------------|----------|
| 抽象层级 | 底层技术事件 | 高层业务事件 |
| 信息详细度 | 完整的模型输入输出 | 业务层面的摘要 |
| 配置方式 | 全局注册 | 参数传递 |
| 主要用途 | 调试和监控 | 业务逻辑扩展 |

## 注意事项

1. **性能影响**：详细的日志记录可能会影响性能，特别是在处理大量数据时
2. **敏感信息**：日志可能包含敏感信息，请谨慎处理输出文件
3. **内存使用**：长时间运行时注意内存使用，特别是启用文件输出时
4. **并发安全**：当前实现在高并发场景下可能需要额外的同步机制

## 扩展和自定义

你可以基于 `LoggerTracingProcessor` 创建自己的自定义处理器：

```python
class MyCustomProcessor(LoggerTracingProcessor):
    def _handle_generation_span(self, span, state):
        # 自定义模型调用处理逻辑
        super()._handle_generation_span(span, state)
        # 添加你的自定义逻辑
        
    def _handle_function_span(self, span, state):
        # 自定义工具调用处理逻辑
        super()._handle_function_span(span, state)
        # 添加你的自定义逻辑
```

## 故障排除

### 常见问题

1. **没有输出**：确保已正确注册 TracingProcessor
2. **颜色显示异常**：在某些终端中可能需要设置 `use_colors=False`
3. **文件写入失败**：检查文件路径权限和磁盘空间

### 调试技巧

```python
# 启用调试模式
import logging
logging.basicConfig(level=logging.DEBUG)

# 检查是否正确注册
from agents.tracing.setup import GLOBAL_TRACE_PROVIDER
print(f"已注册的处理器数量: {len(GLOBAL_TRACE_PROVIDER._multi_processor._processors)}")
