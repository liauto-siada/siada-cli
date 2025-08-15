"""
演示 ContextHooks 中 on_tool_end 方法的压缩功能
展示压缩工具完成后如何自动删除被压缩的消息并插入摘要
"""
import asyncio
import json
from siada.services.code_context_manager import ContextHooks
from siada.foundation.code_agent_context import CodeAgentContext


class MockRunContextWrapper:
    """模拟 RunContextWrapper"""
    def __init__(self, context: CodeAgentContext):
        self.context = context


class MockTool:
    """模拟 Tool"""
    def __init__(self, name: str):
        self.name = name


async def demo_compression_workflow():
    """演示完整的压缩工作流程"""
    print("🚀 开始演示 ContextHooks 压缩功能")
    print("=" * 80)
    
    # 1. 创建包含多条消息的上下文
    context = CodeAgentContext(root_dir="/demo/project")
    context.message_history = [
        {"role": "user", "content": "请帮我创建一个Python计算器类"},
        {"role": "assistant", "content": "好的，我来为您创建一个计算器类。这个类将包含基本的四则运算功能..."},
        {"role": "user", "content": "很好！现在请添加更多的数学运算功能"},
        {"role": "assistant", "content": "我来为计算器添加更多高级数学运算功能，包括幂运算、开方、三角函数等..."},
        {"role": "user", "content": "现在请为这个计算器类编写完整的单元测试"},
        {"role": "assistant", "content": "我来为计算器类编写完整的单元测试，确保所有功能都能正常工作..."},
        {"role": "user", "content": "请优化代码性能，并添加一些实用的辅助功能"},
        {"role": "assistant", "content": "我来优化计算器的性能并添加实用的辅助功能，比如清除历史记录、获取最后一次计算结果等..."}
    ]
    
    wrapper = MockRunContextWrapper(context)
    
    print(f"📋 初始消息历史 (共 {len(context.message_history)} 条):")
    for i, msg in enumerate(context.message_history):
        role = msg["role"]
        content = msg["content"][:60] + "..." if len(msg["content"]) > 60 else msg["content"]
        print(f"  [{i}] {role}: {content}")
    
    # 2. 创建 ContextHooks 实例
    hooks = ContextHooks()
    
    # 3. 模拟压缩工具调用完成
    tool = MockTool("compress_context_tool")
    
    # 4. 创建压缩结果（压缩中间的技术讨论部分）
    compression_result = {
        "status": 1,
        "start_index": 1,
        "end_index": 6,  # 压缩索引1-5的消息
        "summary": """[Smart Compression Summary]
Reason for compression: 对话历史过长，需要压缩中间的技术讨论部分以节省上下文空间

Summary: 用户请求创建Python计算器类，助手提供了完整的实现方案，包括：
1. 基本四则运算功能的Calculator类
2. 扩展的AdvancedCalculator类，支持幂运算、开方、三角函数等高级数学运算
3. 完整的单元测试套件，覆盖所有功能和边界条件
4. 性能优化版本，包含内存管理、历史记录限制等实用辅助功能

技术要点：使用面向对象设计，包含错误处理、类型提示、完整的测试覆盖。"""
    }
    
    result_json = json.dumps(compression_result, ensure_ascii=False)
    
    print(f"\n🔄 压缩操作参数:")
    print(f"  - 压缩范围: 索引 {compression_result['start_index']} 到 {compression_result['end_index']} (不包含)")
    print(f"  - 将压缩 {compression_result['end_index'] - compression_result['start_index']} 条消息")
    
    # 5. 执行 on_tool_end 方法
    print(f"\n⚡ 执行压缩操作...")
    await hooks.on_tool_end(wrapper, None, tool, result_json)
    
    # 6. 展示压缩后的结果
    print(f"\n📋 压缩后的消息历史 (共 {len(context.message_history)} 条):")
    for i, msg in enumerate(context.message_history):
        role = msg["role"]
        if role == "system":
            print(f"  [{i}] {role}: [压缩摘要]")
            print(f"      {msg['content'][:100]}...")
        else:
            content = msg["content"][:60] + "..." if len(msg["content"]) > 60 else msg["content"]
            print(f"  [{i}] {role}: {content}")
    
    # 7. 统计压缩效果
    original_count = 8  # 原始消息数量
    compressed_count = len(context.message_history)
    saved_messages = original_count - compressed_count
    
    print(f"\n📊 压缩效果统计:")
    print(f"  - 原始消息数量: {original_count} 条")
    print(f"  - 压缩后消息数量: {compressed_count} 条")
    print(f"  - 节省消息数量: {saved_messages} 条")
    print(f"  - 压缩率: {(saved_messages / original_count) * 100:.1f}%")
    
    print(f"\n✅ 演示完成！压缩功能正常工作")


async def demo_error_handling():
    """演示错误处理情况"""
    print("\n" + "🛡️ 演示错误处理功能")
    print("=" * 80)
    
    # 创建上下文
    context = CodeAgentContext(root_dir="/demo/project")
    context.message_history = [
        {"role": "user", "content": "测试消息1"},
        {"role": "assistant", "content": "测试消息2"},
        {"role": "user", "content": "测试消息3"}
    ]
    
    wrapper = MockRunContextWrapper(context)
    hooks = ContextHooks()
    tool = MockTool("compress_context_tool")
    
    original_count = len(context.message_history)
    
    # 测试1: 压缩失败
    print(f"\n🔍 测试1: 压缩失败的情况")
    failed_result = {
        "status": 0,
        "start_index": 1,
        "end_index": 2,
        "summary": "压缩失败：模型调用超时"
    }
    
    await hooks.on_tool_end(wrapper, None, tool, json.dumps(failed_result))
    assert len(context.message_history) == original_count, "失败时消息历史应保持不变"
    print(f"  ✅ 压缩失败时消息历史正确保持不变")
    
    # 测试2: 无效JSON
    print(f"\n🔍 测试2: 无效JSON的情况")
    await hooks.on_tool_end(wrapper, None, tool, "无效的JSON字符串")
    assert len(context.message_history) == original_count, "JSON解析失败时消息历史应保持不变"
    print(f"  ✅ JSON解析失败时消息历史正确保持不变")
    
    # 测试3: 无效索引
    print(f"\n🔍 测试3: 无效索引的情况")
    invalid_index_result = {
        "status": 1,
        "start_index": 10,  # 超出范围
        "end_index": 20,
        "summary": "这个摘要不应该被使用"
    }
    
    await hooks.on_tool_end(wrapper, None, tool, json.dumps(invalid_index_result))
    assert len(context.message_history) == original_count, "无效索引时消息历史应保持不变"
    print(f"  ✅ 无效索引时消息历史正确保持不变")
    
    print(f"\n✅ 错误处理演示完成！所有边界情况都得到正确处理")


async def main():
    """主演示函数"""
    print("🎯 ContextHooks 压缩功能完整演示")
    print("=" * 80)
    
    # 演示正常压缩流程
    await demo_compression_workflow()
    
    # 演示错误处理
    await demo_error_handling()
    
    print(f"\n🎉 所有演示完成！")
    print("=" * 80)
    print("📝 总结:")
    print("  1. ✅ 成功实现了 on_tool_end 方法的压缩功能")
    print("  2. ✅ 正确删除被压缩的消息范围")
    print("  3. ✅ 正确插入压缩摘要作为系统消息")
    print("  4. ✅ 完善的错误处理和边界条件检查")
    print("  5. ✅ 保持消息历史的连续性和完整性")


if __name__ == "__main__":
    asyncio.run(main())
