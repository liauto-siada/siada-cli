"""
Web Content Analysis Agent Test Module

Test implementation for web content analysis functionality
"""
import os
from dataclasses import dataclass

from agents import RunContextWrapper, RunResult, RunResultStreaming, Runner, RunConfig, add_trace_processor

from siada.foundation.code_agent_context import CodeAgentContext
from siada.agent_hub.siada_agent import SiadaAgent
from siada.tools.web import web_crawl
from siada.foundation.config import settings
from siada.provider.li.li_provider import LiProvider
from siada.agent_hub.coder.tracing import create_detailed_logger
import logging

logging.getLogger().setLevel(logging.INFO)


@dataclass
class WebAnalysisOutput:
    url: str
    title: str
    main_content_summary: str
    key_topics: list[str]
    content_type: str
    analysis_result: str


class TestWebAnalysisAgent(SiadaAgent[CodeAgentContext]):
    """
    Test Web Content Analysis Agent

    Test agent implementation for web content analysis functionality
    """

    def __init__(self, *args, **kwargs):
        # Use default model provided by SiadaProvider
        provider = LiProvider()
        model = provider.get_model("claude-sonnet-4")

        # Use default value if name parameter is not passed
        if 'name' not in kwargs:
            kwargs['name'] = "TestWebAnalysisAgent"

        # Use default value if tools parameter is not passed
        if 'tools' not in kwargs:
            kwargs['tools'] = [web_crawl]

        # Use default value if model parameter is not passed
        if 'model' not in kwargs:
            kwargs['model'] = model

        # Set up web analysis related instructions and tools
        super().__init__(
            *args,
            **kwargs
        )

    async def get_system_prompt(self, run_context: RunContextWrapper[CodeAgentContext]) -> str | None:
        return """You are a test web content analysis assistant. Your main tasks are:

1. Receive web URLs provided by users for testing purposes
2. Use the web_crawl tool to fetch web content (supports text, markdown, json, html formats)
3. Analyze the main content of the webpage for testing, including:
   - Web page title and basic information
   - Main content summary
   - Key themes and topics
   - Content type (news, blog, product page, documentation, etc.)
   - Test analysis results

This is a test implementation for validating web content analysis functionality.

When analyzing, please pay attention to:
- Extract core information and key points
- Identify content themes and categories
- Summarize the value and highlights of the content
- Provide clear, structured test analysis reports"""

    async def get_context(self) -> CodeAgentContext:
        current_working_dir = os.getcwd()
        context = CodeAgentContext(root_dir=current_working_dir)
        return context

    async def run(self, user_input: str, context: CodeAgentContext) -> RunResult:
        """
        Execute web content analysis test task

        Args:
            user_input: User input containing the web URL to analyze and analysis requirements
            context: Context object for providing contextual information
        Returns:
            Test analysis results including web content analysis report, execution rounds, etc.
        """

        config = RunConfig(tracing_disabled=False)
        # add_trace_processor(create_detailed_logger())

        result = await Runner.run(
            starting_agent=self,
            input=user_input,
            max_turns=settings.MAX_TURNS,
            run_config=config,
            context=context
        )

        return result

    async def run_streamed(self, user_input: str, context: CodeAgentContext) -> RunResultStreaming:
        """
        Execute web content analysis test task (streaming output)

        Args:
            user_input: User input containing the web URL to analyze and analysis requirements
            context: Context object for providing contextual information
        Returns:
            Streaming test analysis results including web content analysis report, execution rounds, etc.
        """

        config = RunConfig(tracing_disabled=False)
        add_trace_processor(create_detailed_logger())

        result = Runner.run_streamed(
            starting_agent=self,
            input=user_input,
            max_turns=settings.MAX_TURNS,
            run_config=config,
            context=context
        )

        return result


async def main():
    """运行 web analysis agent 测试"""
    print("=== 测试 TestWebAnalysisAgent ===")
    
    try:
        # 创建 agent 实例
        agent = TestWebAnalysisAgent()
        print(f"✓ Agent 创建成功: {agent.name}")
        
        # 获取 context
        context = await agent.get_context()
        print(f"✓ Context 创建成功: {context.root_dir}")
        
        # 测试 agent 运行
        print("\n开始测试 agent 运行...")
        test_url = "https://blog.csdn.net/coderroad/article/details/149356472?spm=1000.2115.3001.10509"
        user_input = f"请分析这个网页的内容: {test_url}"
        
        print(f"输入: {user_input}")
        print("=" * 50)
        
        # 运行 agent
        try:
            result = await agent.run(user_input, context)
            
            print("\n=== Agent 运行结果 ===")
            print(f"最终消息:")
            print(result)
            print("✓ Agent 运行完成")
            
        except Exception as run_error:
            print(f"✗ Agent 运行失败: {str(run_error)}")
            import traceback
            traceback.print_exc()
        
    except Exception as e:
        print(f"✗ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
