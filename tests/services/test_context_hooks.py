"""
测试 ContextHooks 中的 on_tool_end 方法
验证压缩工具完成后正确删除被压缩的消息并插入摘要
"""
import pytest
import json
from unittest.mock import Mock

from siada.services.code_context_manager import ContextHooks
from siada.foundation.code_agent_context import CodeAgentContext
from agents import RunContextWrapper
from agents.tool import Tool


class MockRunContextWrapper:
    """模拟 RunContextWrapper"""
    def __init__(self, context: CodeAgentContext):
        self.context = context


class MockTool:
    """模拟 Tool"""
    def __init__(self, name: str):
        self.name = name


class TestContextHooks:
    """测试 ContextHooks 的 on_tool_end 方法"""

    def _create_test_message_history(self):
        """创建测试用的消息历史"""
        return [
            {"role": "user", "content": "第一条消息 - 应该被保留"},
            {"role": "assistant", "content": "第二条消息 - 将被压缩"},
            {"role": "user", "content": "第三条消息 - 将被压缩"},
            {"role": "assistant", "content": "第四条消息 - 将被压缩"},
            {"role": "user", "content": "第五条消息 - 应该被保留"},
            {"role": "assistant", "content": "第六条消息 - 应该被保留"}
        ]

    def _create_compression_result(self, status=1, start_index=1, end_index=4, summary="压缩摘要"):
        """创建压缩工具的返回结果"""
        return {
            "status": status,
            "start_index": start_index,
            "end_index": end_index,
            "summary": summary
        }

    @pytest.mark.asyncio
    async def test_on_tool_end_successful_compression(self):
        """测试成功的压缩操作"""
        print("\n" + "="*60)
        print("测试成功的压缩操作")
        print("="*60)
        
        # 准备测试数据
        context = CodeAgentContext(root_dir="/test/project")
        context.message_history = self._create_test_message_history()
        wrapper = MockRunContextWrapper(context)
        
        # 创建 ContextHooks 实例
        hooks = ContextHooks()
        
        # 创建模拟工具
        tool = MockTool("compress_context_tool")
        
        # 创建压缩结果
        compression_result = self._create_compression_result(
            status=1,
            start_index=1,
            end_index=4,
            summary="[Smart Compression Summary]\n这是一个测试压缩摘要，包含了被压缩消息的核心内容。"
        )
        result_json = json.dumps(compression_result)
        
        print(f"\n📋 压缩前的消息历史 (共 {len(context.message_history)} 条):")
        for i, msg in enumerate(context.message_history):
            print(f"  [{i}] {msg['role']}: {msg['content']}")
        
        print(f"\n🔄 压缩参数:")
        print(f"  - 起始索引: {compression_result['start_index']}")
        print(f"  - 结束索引: {compression_result['end_index']}")
        print(f"  - 摘要: {compression_result['summary']}")
        
        # 执行 on_tool_end
        await hooks.on_tool_end(wrapper, None, tool, result_json)
        
        # 验证结果
        print(f"\n📋 压缩后的消息历史 (共 {len(context.message_history)} 条):")
        for i, msg in enumerate(context.message_history):
            print(f"  [{i}] {msg['role']}: {msg['content']}")
        
        # 验证消息数量变化
        expected_length = 6 - 3 + 1  # 原始6条 - 删除3条 + 插入1条摘要 = 4条
        assert len(context.message_history) == expected_length, f"消息数量应该是 {expected_length}"
        
        # 验证第一条消息被保留
        assert context.message_history[0]["content"] == "第一条消息 - 应该被保留"
        
        # 验证摘要被插入到正确位置
        assert context.message_history[1]["role"] == "system"
        assert "测试压缩摘要" in context.message_history[1]["content"]
        
        # 验证后续消息被保留
        assert context.message_history[2]["content"] == "第五条消息 - 应该被保留"
        assert context.message_history[3]["content"] == "第六条消息 - 应该被保留"
        
        print(f"\n✅ 测试通过：成功压缩并替换消息")

    @pytest.mark.asyncio
    async def test_on_tool_end_compression_failure(self):
        """测试压缩失败的情况"""
        print("\n" + "="*60)
        print("测试压缩失败的情况")
        print("="*60)
        
        # 准备测试数据
        context = CodeAgentContext(root_dir="/test/project")
        context.message_history = self._create_test_message_history()
        wrapper = MockRunContextWrapper(context)
        original_length = len(context.message_history)
        
        # 创建 ContextHooks 实例
        hooks = ContextHooks()
        
        # 创建模拟工具
        tool = MockTool("compress_context_tool")
        
        # 创建失败的压缩结果
        compression_result = self._create_compression_result(
            status=0,  # 失败状态
            start_index=1,
            end_index=4,
            summary="压缩失败：模型调用错误"
        )
        result_json = json.dumps(compression_result)
        
        print(f"\n📋 压缩前的消息历史 (共 {len(context.message_history)} 条):")
        for i, msg in enumerate(context.message_history):
            print(f"  [{i}] {msg['role']}: {msg['content'][:50]}...")
        
        # 执行 on_tool_end
        await hooks.on_tool_end(wrapper, None, tool, result_json)
        
        # 验证消息历史没有被修改
        assert len(context.message_history) == original_length, "失败时消息历史不应该被修改"
        assert context.message_history[1]["content"] == "第二条消息 - 将被压缩", "原始消息应该被保留"
        
        print(f"\n✅ 测试通过：压缩失败时消息历史保持不变")

    @pytest.mark.asyncio
    async def test_on_tool_end_invalid_indices(self):
        """测试无效索引的情况"""
        print("\n" + "="*60)
        print("测试无效索引的情况")
        print("="*60)
        
        # 准备测试数据
        context = CodeAgentContext(root_dir="/test/project")
        context.message_history = self._create_test_message_history()
        wrapper = MockRunContextWrapper(context)
        original_length = len(context.message_history)
        
        # 创建 ContextHooks 实例
        hooks = ContextHooks()
        
        # 创建模拟工具
        tool = MockTool("compress_context_tool")
        
        # 创建无效索引的压缩结果
        compression_result = self._create_compression_result(
            status=1,
            start_index=5,  # 无效的起始索引
            end_index=10,   # 超出范围的结束索引
            summary="这个摘要不应该被使用"
        )
        result_json = json.dumps(compression_result)
        
        print(f"\n📋 测试无效索引: start_index={compression_result['start_index']}, end_index={compression_result['end_index']}")
        print(f"消息历史长度: {len(context.message_history)}")
        
        # 执行 on_tool_end
        await hooks.on_tool_end(wrapper, None, tool, result_json)
        
        # 验证消息历史没有被修改
        assert len(context.message_history) == original_length, "无效索引时消息历史不应该被修改"
        
        print(f"\n✅ 测试通过：无效索引时消息历史保持不变")

    @pytest.mark.asyncio
    async def test_on_tool_end_invalid_json(self):
        """测试无效JSON的情况"""
        print("\n" + "="*60)
        print("测试无效JSON的情况")
        print("="*60)
        
        # 准备测试数据
        context = CodeAgentContext(root_dir="/test/project")
        context.message_history = self._create_test_message_history()
        wrapper = MockRunContextWrapper(context)
        original_length = len(context.message_history)
        
        # 创建 ContextHooks 实例
        hooks = ContextHooks()
        
        # 创建模拟工具
        tool = MockTool("compress_context_tool")
        
        # 无效的JSON字符串
        invalid_json = "这不是一个有效的JSON字符串"
        
        print(f"\n📋 测试无效JSON: {invalid_json}")
        
        # 执行 on_tool_end
        await hooks.on_tool_end(wrapper, None, tool, invalid_json)
        
        # 验证消息历史没有被修改
        assert len(context.message_history) == original_length, "JSON解析失败时消息历史不应该被修改"
        
        print(f"\n✅ 测试通过：JSON解析失败时消息历史保持不变")

    @pytest.mark.asyncio
    async def test_on_tool_end_non_compression_tool(self):
        """测试非压缩工具的情况"""
        print("\n" + "="*60)
        print("测试非压缩工具的情况")
        print("="*60)
        
        # 准备测试数据
        context = CodeAgentContext(root_dir="/test/project")
        context.message_history = self._create_test_message_history()
        wrapper = MockRunContextWrapper(context)
        original_length = len(context.message_history)
        
        # 创建 ContextHooks 实例
        hooks = ContextHooks()
        
        # 创建非压缩工具
        tool = MockTool("other_tool")
        
        # 任意结果
        result = "这是其他工具的结果"
        
        print(f"\n📋 测试工具: {tool.name}")
        
        # 执行 on_tool_end
        await hooks.on_tool_end(wrapper, None, tool, result)
        
        # 验证消息历史没有被修改
        assert len(context.message_history) == original_length, "非压缩工具时消息历史不应该被修改"
        
        print(f"\n✅ 测试通过：非压缩工具时消息历史保持不变")

    @pytest.mark.asyncio
    async def test_on_tool_end_empty_context(self):
        """测试空上下文的情况"""
        print("\n" + "="*60)
        print("测试空上下文的情况")
        print("="*60)
        
        # 创建空上下文
        wrapper = MockRunContextWrapper(None)
        
        # 创建 ContextHooks 实例
        hooks = ContextHooks()
        
        # 创建模拟工具
        tool = MockTool("compress_context_tool")
        
        # 创建压缩结果
        compression_result = self._create_compression_result()
        result_json = json.dumps(compression_result)
        
        print(f"\n📋 测试空上下文")
        
        # 执行 on_tool_end（应该不会抛出异常）
        await hooks.on_tool_end(wrapper, None, tool, result_json)
        
        print(f"\n✅ 测试通过：空上下文时方法正常执行")


if __name__ == '__main__':
    # 运行所有测试
    pytest.main([__file__, "-v", "-s"])
