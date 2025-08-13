"""
测试SiadaRunner的流式功能
"""
import asyncio
import pytest
from siada.services.siada_runner import SiadaRunner
from agents import RunResult, RunResultStreaming


class TestStreamRunner:
    """测试SiadaRunner的流式功能"""

    @pytest.mark.asyncio
    async def test_run_agent_normal_mode(self):
        """测试普通模式运行Agent"""
        user_input = "Generate a simple test card"
        agent_name = "test"
        
        result = await SiadaRunner.run_agent(agent_name, user_input, stream=False)
        
        # 验证返回的是RunResult类型
        assert isinstance(result, RunResult)
        print(f"普通模式结果类型: {type(result)}")

    @pytest.mark.asyncio
    async def test_run_agent_stream_mode(self):
        """测试流式模式运行Agent"""
        user_input = "Generate a simple test card"
        agent_name = "test"
        
        result = await SiadaRunner.run_agent(agent_name, user_input, stream=True)
        
        # 验证返回的是RunResultStreaming类型
        assert isinstance(result, RunResultStreaming)
        print(f"流式模式结果类型: {type(result)}")

    @pytest.mark.asyncio
    async def test_run_agent_with_workspace(self):
        """测试带工作空间的Agent运行"""
        user_input = "Generate a simple test card"
        agent_name = "test"
        workspace = "/tmp/test_workspace"
        
        # 测试普通模式
        result_normal = await SiadaRunner.run_agent(agent_name, user_input, workspace=workspace, stream=False)
        assert isinstance(result_normal, RunResult)
        
        # 测试流式模式
        result_stream = await SiadaRunner.run_agent(agent_name, user_input, workspace=workspace, stream=True)
        assert isinstance(result_stream, RunResultStreaming)

    @pytest.mark.asyncio
    async def test_run_agent_default_stream_false(self):
        """测试默认情况下stream参数为False"""
        user_input = "Generate a simple test card"
        agent_name = "test"
        
        # 不传递stream参数，应该默认为False
        result = await SiadaRunner.run_agent(agent_name, user_input)
        
        # 验证返回的是RunResult类型（非流式）
        assert isinstance(result, RunResult)


async def main():
    """手动测试函数"""
    print("开始测试SiadaRunner流式功能...")
    
    user_input = "Generate a Weibo trending card"
    agent_name = "test"
    
    try:
        # 测试普通模式
        print("\n=== 测试普通模式 ===")
        result_normal = await SiadaRunner.run_agent(agent_name, user_input, stream=False)
        print(f"普通模式结果类型: {type(result_normal)}")
        print(f"普通模式结果: {result_normal}")
        
        # 测试流式模式
        print("\n=== 测试流式模式 ===")
        result_stream = await SiadaRunner.run_agent(agent_name, user_input, stream=True)
        print(f"流式模式结果类型: {type(result_stream)}")
        print(f"流式模式结果: {result_stream}")
        
        # 测试默认模式（应该是普通模式）
        print("\n=== 测试默认模式 ===")
        result_default = await SiadaRunner.run_agent(agent_name, user_input)
        print(f"默认模式结果类型: {type(result_default)}")
        print(f"默认模式结果: {result_default}")
        
        print("\n✅ 所有测试完成！")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
