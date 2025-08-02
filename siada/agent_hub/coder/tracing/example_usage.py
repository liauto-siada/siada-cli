"""
LoggerTracingProcessor 使用示例

这个示例展示了如何使用 LoggerTracingProcessor 来监控 Agent 的执行过程，
包括模型调用、工具使用和 Agent 切换的详细日志。
"""

import asyncio
from typing import Any

from pydantic import BaseModel

from agents import Agent, Runner, function_tool
from agents.tracing import add_trace_processor

from siada.foundation.config import settings
from siada.provider.li.li_provider import LiProvider
from siada.agent_hub.coder.tracing import create_simple_logger, create_detailed_logger, LoggerTracingProcessor

provider = LiProvider()
model = provider.get_model(settings.Claude_4_0_SONNET)


# 定义一些示例工具
@function_tool
def search_web(query: str) -> str:
    """搜索网络信息"""
    return f"搜索结果：找到关于 '{query}' 的 5 篇相关文章"


@function_tool
def analyze_data(data: str) -> str:
    """分析数据"""
    return f"数据分析结果：{data} 的关键指标显示正向趋势"


@function_tool
def generate_report(analysis: str) -> str:
    """生成报告"""
    return f"报告已生成：基于 {analysis}，建议采取积极策略"


# 定义输出类型
class SearchResult(BaseModel):
    query: str
    results: str
    confidence: float


class AnalysisResult(BaseModel):
    summary: str
    recommendations: list[str]


# 创建 Agent（不指定 output_type，让模型自由输出）
search_agent = Agent(
    name="SearchAgent",
    instructions="你是一个搜索专家。根据用户查询搜索相关信息，然后将结果传递给分析师。",
    tools=[search_web],
    # output_type=SearchResult,  # 注释掉，不强制指定输出类型
    model=model
)

analysis_agent = Agent(
    name="AnalysisAgent", 
    instructions="你是一个数据分析师。分析搜索结果并生成深入的分析报告。",
    tools=[analyze_data, generate_report],
    # output_type=AnalysisResult,  # 注释掉，不强制指定输出类型
    model=model
)

# 设置 handoff
search_agent.handoffs = [analysis_agent]


async def example_simple_logging():
    """简单日志记录示例"""
    print("=== 简单日志记录示例 ===\n")
    
    # 注册简单的日志处理器
    add_trace_processor(create_simple_logger())
    
    # 运行 Agent
    result = await Runner.run(
        search_agent,
        input="请搜索并分析特斯拉的最新财务表现",
    )
    
    print(f"\n最终结果: {result.final_output}")


async def example_detailed_logging():
    """详细日志记录示例（包含文件输出）"""
    print("\n\n=== 详细日志记录示例 ===\n")
    
    # 注册详细的日志处理器，同时输出到文件
    add_trace_processor(create_detailed_logger())

    
    # 运行 Agent
    result = await Runner.run(
        search_agent,
        input="分析苹果公司的市场竞争力",
    )
    
    print(f"\n最终结果: {result.final_output}")
    print("详细日志已保存到 ~/.siadahub/logs/agent_trace-yyyymmdd.log 文件")



async def example_single_agent():
    """单个 Agent 示例（无 handoff）"""
    print("\n\n=== 单个 Agent 示例 ===\n")
    
    # 创建一个简单的单 Agent
    simple_agent = Agent(
        name="SimpleAgent",
        instructions="你是一个助手，可以搜索信息并直接回答用户问题。",
        tools=[search_web],
        output_type=str,
        model=model
    )
    
    # 运行单个 Agent
    result = await Runner.run(
        simple_agent,
        input="搜索人工智能的最新发展",
    )
    
    print(f"\n最终结果: {result.final_output}")


async def example_custom_configuration():
    """自定义配置示例"""
    print("\n\n=== 自定义配置示例 ===\n")

    # 创建自定义配置的日志处理器
    custom_logger = LoggerTracingProcessor(
        show_model_calls=True,
        show_tool_calls=True,
        show_handoffs=True,
        show_trace_lifecycle=True,
        show_timestamps=True,
        use_colors=True,
        output_file=None
    )
    
    add_trace_processor(custom_logger)
    
    # 运行 Agent
    result = await Runner.run(
        search_agent,
        input="快速搜索比特币价格趋势",
    )
    
    print(f"\n最终结果: {result.final_output}")


async def main():
    """主函数 - 运行所有示例"""
    print("LoggerTracingProcessor 使用示例")
    print("=" * 50)
    
    try:
        # 运行各种示例
        await example_simple_logging()
        await example_detailed_logging() 
        await example_single_agent()
        await example_custom_configuration()
        
    except Exception as e:
        print(f"示例运行出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 运行示例
    asyncio.run(main())


"""
运行这个示例的方法：

1. 基本运行：
   python examples/tracing/example_usage.py

2. 如果你想只运行特定的示例，可以修改 main() 函数，只调用你感兴趣的示例函数。

3. 输出说明：
   - 彩色输出显示不同类型的事件（模型调用、工具调用、handoff 等）
   - 增量消息显示：只显示新增的输入消息，避免重复
   - 详细的统计信息：包括执行时间、调用次数等
   - 可选的文件输出：保存完整的执行日志

4. 自定义配置：
   你可以根据需要调整 LoggerTracingProcessor 的参数：
   - show_model_calls: 控制是否显示模型调用
   - show_tool_calls: 控制是否显示工具调用  
   - show_handoffs: 控制是否显示 Agent 切换
   - use_colors: 控制是否使用彩色输出
   - output_file: 指定日志文件路径
"""
