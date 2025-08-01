"""
测试 compression_tool.py 中的 _compress_context_tool 方法

这个测试文件包含了对 _compress_context_tool 方法的完整功能测试，包括：
- 成功压缩对话历史
- 边界条件处理
- 错误处理
- 真实模型调用
- 压缩结果验证和展示
"""

import pytest
import asyncio
from typing import List
from unittest.mock import Mock, patch

from siada.tools.compression_tool import _compress_context_tool
from siada.foundation.code_agent_context import CodeAgentContext
from agents.items import TResponseInputItem


class MockRunContextWrapper:
    """模拟 RunContextWrapper"""
    def __init__(self, context: CodeAgentContext):
        self.context = context


class TestCompressionTool:
    """测试 compression_tool._compress_context_tool 方法的完整功能"""

    def _create_test_message_history(self) -> List[TResponseInputItem]:
        """创建测试用的消息历史"""
        return [
            {
                "role": "user", 
                "content": "请帮我创建一个Python计算器类，需要支持基本的四则运算功能。"
            },
            {
                "role": "assistant", 
                "content": """我来帮您创建一个Python计算器类。以下是一个基本的实现：

```python
class Calculator:
    def __init__(self):
        self.history = []
    
    def add(self, a, b):
        result = a + b
        self.history.append(f"{a} + {b} = {result}")
        return result
    
    def subtract(self, a, b):
        result = a - b
        self.history.append(f"{a} - {b} = {result}")
        return result
    
    def multiply(self, a, b):
        result = a * b
        self.history.append(f"{a} * {b} = {result}")
        return result
    
    def divide(self, a, b):
        if b == 0:
            raise ValueError("Cannot divide by zero")
        result = a / b
        self.history.append(f"{a} / {b} = {result}")
        return result
```

这个计算器类包含了基本的四则运算功能，并且会记录计算历史。"""
            },
            {
                "role": "user", 
                "content": "很好！现在请添加更多的数学运算功能，比如幂运算、开方、三角函数等。"
            },
            {
                "role": "assistant", 
                "content": """好的，我来为计算器添加更多高级数学运算功能：

```python
import math

class AdvancedCalculator(Calculator):
    def power(self, base, exponent):
        result = base ** exponent
        self.history.append(f"{base} ^ {exponent} = {result}")
        return result
    
    def square_root(self, x):
        if x < 0:
            raise ValueError("Cannot calculate square root of negative number")
        result = math.sqrt(x)
        self.history.append(f"√{x} = {result}")
        return result
    
    def sin(self, x):
        result = math.sin(x)
        self.history.append(f"sin({x}) = {result}")
        return result
    
    def cos(self, x):
        result = math.cos(x)
        self.history.append(f"cos({x}) = {result}")
        return result
    
    def tan(self, x):
        result = math.tan(x)
        self.history.append(f"tan({x}) = {result}")
        return result
    
    def logarithm(self, x, base=math.e):
        if x <= 0:
            raise ValueError("Logarithm undefined for non-positive numbers")
        result = math.log(x, base)
        self.history.append(f"log_{base}({x}) = {result}")
        return result
```

现在计算器支持更多高级数学运算了！"""
            },
            {
                "role": "user", 
                "content": "现在请为这个计算器类编写完整的单元测试，确保所有功能都能正常工作。"
            },
            {
                "role": "assistant", 
                "content": """我来为计算器类编写完整的单元测试：

```python
import unittest
import math
from calculator import Calculator, AdvancedCalculator

class TestCalculator(unittest.TestCase):
    def setUp(self):
        self.calc = Calculator()
    
    def test_add(self):
        self.assertEqual(self.calc.add(2, 3), 5)
        self.assertEqual(self.calc.add(-1, 1), 0)
        self.assertEqual(self.calc.add(0.1, 0.2), 0.3)
    
    def test_subtract(self):
        self.assertEqual(self.calc.subtract(5, 3), 2)
        self.assertEqual(self.calc.subtract(0, 5), -5)
    
    def test_multiply(self):
        self.assertEqual(self.calc.multiply(3, 4), 12)
        self.assertEqual(self.calc.multiply(-2, 3), -6)
    
    def test_divide(self):
        self.assertEqual(self.calc.divide(10, 2), 5)
        with self.assertRaises(ValueError):
            self.calc.divide(5, 0)

class TestAdvancedCalculator(unittest.TestCase):
    def setUp(self):
        self.calc = AdvancedCalculator()
    
    def test_power(self):
        self.assertEqual(self.calc.power(2, 3), 8)
        self.assertEqual(self.calc.power(5, 0), 1)
    
    def test_square_root(self):
        self.assertEqual(self.calc.square_root(9), 3)
        with self.assertRaises(ValueError):
            self.calc.square_root(-1)
    
    def test_trigonometric_functions(self):
        self.assertAlmostEqual(self.calc.sin(math.pi/2), 1, places=10)
        self.assertAlmostEqual(self.calc.cos(0), 1, places=10)

if __name__ == '__main__':
    unittest.main()
```

这些测试覆盖了所有的计算器功能，包括边界条件和错误处理。"""
            },
            {
                "role": "user", 
                "content": "请优化代码性能，并添加一些实用的辅助功能，比如清除历史记录、获取最后一次计算结果等。"
            },
            {
                "role": "assistant", 
                "content": """我来优化计算器的性能并添加实用的辅助功能：

```python
import math
from typing import List, Optional, Union

class OptimizedCalculator:
    def __init__(self, max_history: int = 1000):
        self._history: List[str] = []
        self._last_result: Optional[float] = None
        self._max_history = max_history
    
    def _record_operation(self, operation: str, result: float) -> float:
        \"\"\"记录操作并管理历史记录大小\"\"\"
        self._last_result = result
        self._history.append(operation)
        
        # 限制历史记录大小以优化内存使用
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        
        return result
    
    def add(self, a: float, b: float) -> float:
        result = a + b
        return self._record_operation(f"{a} + {b} = {result}", result)
    
    def subtract(self, a: float, b: float) -> float:
        result = a - b
        return self._record_operation(f"{a} - {b} = {result}", result)
    
    def multiply(self, a: float, b: float) -> float:
        result = a * b
        return self._record_operation(f"{a} * {b} = {result}", result)
    
    def divide(self, a: float, b: float) -> float:
        if b == 0:
            raise ValueError("Cannot divide by zero")
        result = a / b
        return self._record_operation(f"{a} / {b} = {result}", result)
    
    # 辅助功能
    def get_last_result(self) -> Optional[float]:
        \"\"\"获取最后一次计算结果\"\"\"
        return self._last_result
    
    def clear_history(self) -> None:
        \"\"\"清除计算历史\"\"\"
        self._history.clear()
        self._last_result = None
    
    def get_history(self, limit: Optional[int] = None) -> List[str]:
        \"\"\"获取计算历史\"\"\"
        if limit is None:
            return self._history.copy()
        return self._history[-limit:]
    
    def memory_add(self, value: float) -> float:
        \"\"\"将值加到最后结果中\"\"\"
        if self._last_result is None:
            raise ValueError("No previous result to add to")
        return self.add(self._last_result, value)
    
    def memory_subtract(self, value: float) -> float:
        \"\"\"从最后结果中减去值\"\"\"
        if self._last_result is None:
            raise ValueError("No previous result to subtract from")
        return self.subtract(self._last_result, value)
```

这个优化版本包含了性能改进和实用功能，更适合实际使用。"""
            }
        ]

    def _create_context_with_history(self, message_history: List[TResponseInputItem]) -> MockRunContextWrapper:
        """创建包含消息历史的上下文"""
        context = CodeAgentContext(root_dir="/test/project")
        context.message_history = message_history
        return MockRunContextWrapper(context)

    @pytest.mark.asyncio
    async def test_compress_context_tool_success(self):
        """测试成功压缩对话历史"""
        print("\n" + "="*60)
        print("测试成功压缩对话历史")
        print("="*60)
        
        # 准备测试数据
        message_history = self._create_test_message_history()
        context = self._create_context_with_history(message_history)
        
        # 压缩参数
        reason = "对话历史过长，需要压缩中间的技术讨论部分以节省上下文空间"
        start_index = 1  # 从第二条消息开始压缩
        end_index = 6    # 压缩到第六条消息（不包含）
        compression_strategy = "summary"
        
        print(f"\n📋 压缩参数:")
        print(f"  - 压缩原因: {reason}")
        print(f"  - 压缩范围: 索引 {start_index} 到 {end_index} (不包含)")
        print(f"  - 压缩策略: {compression_strategy}")
        print(f"  - 总消息数: {len(message_history)}")
        
        print(f"\n📝 原始消息历史:")
        for i, msg in enumerate(message_history):
            role = msg["role"]
            content = msg["content"][:100] + "..." if len(msg["content"]) > 100 else msg["content"]
            print(f"  [{i}] {role}: {content}")
        
        print(f"\n🔄 待压缩的消息范围 (索引 {start_index}-{end_index-1}):")
        for i in range(start_index, min(end_index, len(message_history))):
            msg = message_history[i]
            role = msg["role"]
            content = msg["content"][:150] + "..." if len(msg["content"]) > 150 else msg["content"]
            print(f"  [{i}] {role}: {content}")
        
        # 执行压缩
        print(f"\n🚀 开始调用模型进行压缩...")
        result = await _compress_context_tool(
            context=context,
            reason=reason,
            start_index=start_index,
            end_index=end_index,
            compression_strategy=compression_strategy
        )
        
        # 验证结果
        print(f"\n✅ 压缩完成！结果验证:")
        assert isinstance(result, dict), "返回结果应该是字典类型"
        assert "status" in result, "结果应该包含 status 字段"
        assert "start_index" in result, "结果应该包含 start_index 字段"
        assert "end_index" in result, "结果应该包含 end_index 字段"
        assert "summary" in result, "结果应该包含 summary 字段"
        
        print(f"  - 状态码: {result['status']}")
        print(f"  - 压缩起始索引: {result['start_index']}")
        print(f"  - 压缩结束索引: {result['end_index']}")
        print(f"  - 摘要长度: {len(result['summary'])} 字符")
        
        # 验证成功状态
        assert result["status"] == 1, "压缩应该成功"
        assert result["start_index"] == start_index, "起始索引应该匹配"
        assert result["end_index"] == end_index, "结束索引应该匹配"
        assert isinstance(result["summary"], str), "摘要应该是字符串类型"
        assert len(result["summary"]) > 0, "摘要不应该为空"
        
        # 验证摘要格式
        summary = result["summary"]
        assert "[Smart Compression Summary]" in summary, "摘要应该包含标准格式标识"
        assert reason in summary, "摘要应该包含压缩原因"
        
        print(f"\n📄 压缩摘要内容:")
        print("-" * 50)
        print(summary)
        print("-" * 50)
        
        # 计算压缩效果
        original_length = sum(len(msg["content"]) for msg in message_history[start_index:end_index])
        compressed_length = len(summary)
        compression_ratio = (1 - compressed_length / original_length) * 100 if original_length > 0 else 0
        
        print(f"\n📊 压缩效果统计:")
        print(f"  - 原始内容长度: {original_length} 字符")
        print(f"  - 压缩后长度: {compressed_length} 字符")
        print(f"  - 压缩率: {compression_ratio:.1f}%")
        
        print(f"\n✅ 测试通过：成功压缩对话历史")

    @pytest.mark.asyncio
    async def test_compress_context_tool_preserve_first_message(self):
        """测试保护第一条消息的功能"""
        print("\n" + "="*60)
        print("测试保护第一条消息功能")
        print("="*60)
        
        # 准备测试数据
        message_history = self._create_test_message_history()
        context = self._create_context_with_history(message_history)
        
        # 尝试从索引0开始压缩（应该自动调整为从索引1开始）
        reason = "测试保护第一条消息的功能"
        start_index = 0  # 尝试从第一条消息开始
        end_index = 3
        
        print(f"\n📋 测试参数:")
        print(f"  - 尝试的起始索引: {start_index} (应该被自动调整为1)")
        print(f"  - 结束索引: {end_index}")
        print(f"  - 第一条消息: {message_history[0]['content'][:100]}...")
        
        # 执行压缩
        result = await _compress_context_tool(
            context=context,
            reason=reason,
            start_index=start_index,
            end_index=end_index
        )
        
        # 验证结果
        print(f"\n✅ 压缩结果:")
        print(f"  - 状态码: {result['status']}")
        print(f"  - 实际起始索引: {result['start_index']}")
        print(f"  - 结束索引: {result['end_index']}")
        
        # 验证第一条消息被保护
        assert result["start_index"] == 1, "起始索引应该被自动调整为1，保护第一条消息"
        assert result["status"] == 1, "压缩应该成功"
        
        print(f"\n✅ 测试通过：第一条消息被正确保护")

    @pytest.mark.asyncio
    async def test_compress_context_tool_invalid_range(self):
        """测试无效压缩范围的处理"""
        print("\n" + "="*60)
        print("测试无效压缩范围处理")
        print("="*60)
        
        # 准备测试数据
        message_history = self._create_test_message_history()
        context = self._create_context_with_history(message_history)
        
        # 测试无效范围：start_index >= end_index
        reason = "测试无效范围处理"
        start_index = 5
        end_index = 3  # 结束索引小于起始索引
        
        print(f"\n📋 测试参数 (无效范围):")
        print(f"  - 起始索引: {start_index}")
        print(f"  - 结束索引: {end_index}")
        print(f"  - 总消息数: {len(message_history)}")
        
        # 执行压缩
        result = await _compress_context_tool(
            context=context,
            reason=reason,
            start_index=start_index,
            end_index=end_index
        )
        
        # 验证错误处理
        print(f"\n✅ 错误处理结果:")
        print(f"  - 状态码: {result['status']}")
        print(f"  - 错误信息: {result['summary']}")
        
        assert result["status"] == 0, "应该返回失败状态"
        assert "Invalid compression range" in result["summary"], "应该包含无效范围错误信息"
        
        print(f"\n✅ 测试通过：无效范围被正确处理")

    @pytest.mark.asyncio
    async def test_compress_context_tool_empty_context(self):
        """测试空上下文的处理"""
        print("\n" + "="*60)
        print("测试空上下文处理")
        print("="*60)
        
        # 创建空上下文
        context = MockRunContextWrapper(None)
        
        # 执行压缩
        result = await _compress_context_tool(
            context=context,
            reason="测试空上下文",
            start_index=0,
            end_index=1
        )
        
        # 验证错误处理
        print(f"\n✅ 空上下文处理结果:")
        print(f"  - 状态码: {result['status']}")
        print(f"  - 错误信息: {result['summary']}")
        
        assert result["status"] == 0, "应该返回失败状态"
        assert "Unable to get context information" in result["summary"], "应该包含上下文错误信息"
        
        print(f"\n✅ 测试通过：空上下文被正确处理")

    @pytest.mark.asyncio
    async def test_compress_context_tool_single_message_range(self):
        """测试压缩单条消息"""
        print("\n" + "="*60)
        print("测试压缩单条消息")
        print("="*60)
        
        # 准备测试数据
        message_history = self._create_test_message_history()
        context = self._create_context_with_history(message_history)
        
        # 压缩单条消息
        reason = "测试压缩单条消息"
        start_index = 2
        end_index = 3  # 只压缩一条消息
        
        print(f"\n📋 测试参数 (单条消息):")
        print(f"  - 起始索引: {start_index}")
        print(f"  - 结束索引: {end_index}")
        print(f"  - 待压缩消息: {message_history[start_index]['content'][:100]}...")
        
        # 执行压缩
        result = await _compress_context_tool(
            context=context,
            reason=reason,
            start_index=start_index,
            end_index=end_index
        )
        
        # 验证结果
        print(f"\n✅ 单条消息压缩结果:")
        print(f"  - 状态码: {result['status']}")
        print(f"  - 摘要长度: {len(result['summary'])} 字符")
        
        assert result["status"] == 1, "单条消息压缩应该成功"
        assert len(result["summary"]) > 0, "摘要不应该为空"
        
        print(f"\n📄 单条消息压缩摘要:")
        print("-" * 30)
        print(result["summary"])
        print("-" * 30)
        
        print(f"\n✅ 测试通过：单条消息压缩成功")

    @pytest.mark.asyncio
    async def test_compress_context_tool_model_error_handling(self):
        """测试模型调用错误处理"""
        print("\n" + "="*60)
        print("测试模型调用错误处理")
        print("="*60)
        
        # 准备测试数据
        message_history = self._create_test_message_history()
        context = self._create_context_with_history(message_history)
        
        # 模拟模型调用失败
        with patch('siada.tools.compression_tool._compress_messages_with_model') as mock_compress:
            mock_compress.side_effect = Exception("模拟的模型调用错误")
            
            result = await _compress_context_tool(
                context=context,
                reason="测试模型错误处理",
                start_index=1,
                end_index=3
            )
            
            # 验证错误处理
            print(f"\n✅ 模型错误处理结果:")
            print(f"  - 状态码: {result['status']}")
            print(f"  - 错误信息: {result['summary']}")
            
            assert result["status"] == 0, "应该返回失败状态"
            assert "Model compression failed" in result["summary"], "应该包含模型错误信息"
            assert "模拟的模型调用错误" in result["summary"], "应该包含具体错误信息"
        
        print(f"\n✅ 测试通过：模型错误被正确处理")


if __name__ == '__main__':
    # 运行特定的测试方法来演示压缩功能
    pytest.main([__file__ + "::TestCompressionTool::test_compress_context_tool_success", "-v", "-s"])
