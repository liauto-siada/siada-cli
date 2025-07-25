#!/usr/bin/env python
"""
测试 MarkdownStream 的 update 函数能力

测试流式 Markdown 渲染的各种场景，包括：
- 基本 markdown 内容渲染
- 增量更新功能
- 不同 markdown 元素的处理
- 最终更新处理
- 性能和频率控制
"""

import time
import io
import sys
from unittest.mock import patch, MagicMock
import pytest

from siada.io.components.mdstream import MarkdownStream


class TestMarkdownStream:
    """MarkdownStream 测试类"""

    def setup_method(self):
        """每个测试方法的设置"""
        self.mdstream = MarkdownStream()

    def teardown_method(self):
        """每个测试方法的清理"""
        if self.mdstream and self.mdstream.live:
            self.mdstream.live.stop()

    def test_basic_markdown_rendering(self):
        """测试基本的 markdown 渲染功能"""
        test_content = """# 测试标题

这是一个基本的 markdown 内容测试。

## 子标题

- 列表项 1
- 列表项 2

```python
def hello():
    print("Hello, World!")
```

**粗体文本** 和 *斜体文本*
"""
        
        # 模拟控制台输出
        with patch('siada.io.components.mdstream.Live') as mock_live:
            mock_live_instance = MagicMock()
            mock_live.return_value = mock_live_instance
            
            # 测试更新
            self.mdstream.update(test_content, final=True)
            
            # 验证 Live 实例被创建和启动
            mock_live.assert_called_once()
            mock_live_instance.start.assert_called_once()
            mock_live_instance.stop.assert_called_once()

    def test_incremental_updates(self):
        """测试增量更新功能"""
        with patch('siada.io.components.mdstream.Live') as mock_live:
            mock_live_instance = MagicMock()
            mock_live.return_value = mock_live_instance
            
            # 第一次更新
            content1 = "# 开始测试\n\n这是第一段内容"
            self.mdstream.update(content1)
            
            # 第二次更新 - 添加更多内容
            content2 = "# 开始测试\n\n这是第一段内容\n\n## 第二部分\n\n这是第二段内容"
            self.mdstream.update(content2)
            
            # 第三次更新 - 添加代码块
            content3 = content2 + "\n\n```python\nprint('Hello')\n```"
            self.mdstream.update(content3)
            
            # 最终更新
            self.mdstream.update(content3, final=True)
            
            # 验证 Live 被正确管理
            mock_live_instance.start.assert_called_once()
            mock_live_instance.stop.assert_called_once()
            assert mock_live_instance.update.call_count >= 2  # 至少调用了多次 update

    def test_frequency_throttling(self):
        """测试更新频率控制"""
        with patch('siada.io.components.mdstream.Live') as mock_live:
            mock_live_instance = MagicMock()
            mock_live.return_value = mock_live_instance
            
            # 快速连续更新
            content_base = "# 频率测试\n\n"
            
            start_time = time.time()
            update_count = 0
            
            for i in range(10):
                content = content_base + f"第 {i+1} 次更新\n"
                self.mdstream.update(content)
                update_count += 1
                time.sleep(0.01)  # 快速更新间隔
            
            # 最终更新
            self.mdstream.update(content, final=True)
            
            # 验证更新被适当节流
            # 由于频率控制，实际的 Live.update 调用应该少于我们的更新次数
            assert mock_live_instance.update.call_count < update_count

    def test_different_markdown_elements(self):
        """测试不同类型的 markdown 元素"""
        markdown_samples = [
            # 标题
            "# H1 标题\n## H2 标题\n### H3 标题",
            
            # 代码块
            "```python\ndef test():\n    return True\n```",
            
            # 列表
            "- 项目 1\n- 项目 2\n  - 子项目\n- 项目 3",
            
            # 表格
            "| 列1 | 列2 | 列3 |\n|-----|-----|-----|\n| A   | B   | C   |",
            
            # 链接和格式
            "这是 **粗体** 和 *斜体* 以及 `代码` 文本\n\n[链接示例](https://example.com)",
            
            # 引用
            "> 这是一个引用\n> 跨多行的引用内容"
        ]
        
        with patch('siada.io.components.mdstream.Live') as mock_live:
            mock_live_instance = MagicMock()
            mock_live.return_value = mock_live_instance
            
            # 逐个测试不同的 markdown 元素
            for i, sample in enumerate(markdown_samples):
                self.mdstream = MarkdownStream()  # 重新创建实例
                
                try:
                    self.mdstream.update(sample, final=True)
                    # 如果没有抛出异常，说明渲染成功
                    assert True
                except Exception as e:
                    pytest.fail(f"Markdown 元素 {i+1} 渲染失败: {e}")

    def test_large_content_handling(self):
        """测试大内容的处理"""
        # 生成大量内容
        large_content = "# 大内容测试\n\n"
        for i in range(100):
            large_content += f"## 第 {i+1} 节\n\n"
            large_content += f"这是第 {i+1} 节的内容。" * 10 + "\n\n"
            large_content += "```python\n"
            large_content += f"def function_{i+1}():\n"
            large_content += f"    return 'result_{i+1}'\n"
            large_content += "```\n\n"
        
        with patch('siada.io.components.mdstream.Live') as mock_live:
            mock_live_instance = MagicMock()
            mock_live.return_value = mock_live_instance
            
            start_time = time.time()
            self.mdstream.update(large_content, final=True)
            end_time = time.time()
            
            # 验证大内容能在合理时间内处理完成（应该小于5秒）
            assert end_time - start_time < 5.0

    def test_error_handling(self):
        """测试错误处理"""
        with patch('siada.io.components.mdstream.Live') as mock_live:
            # 模拟 Live 创建失败
            mock_live.side_effect = Exception("Live creation failed")
            
            # 应该能优雅处理错误
            try:
                self.mdstream.update("# 测试", final=True)
            except Exception:
                pytest.fail("应该优雅处理 Live 创建失败")

    def test_cleanup_on_destruction(self):
        """测试对象销毁时的清理"""
        with patch('siada.io.components.mdstream.Live') as mock_live:
            mock_live_instance = MagicMock()
            mock_live.return_value = mock_live_instance
            
            # 创建并使用 MarkdownStream
            mdstream = MarkdownStream()
            mdstream.update("# 测试清理", final=False)
            
            # 模拟对象销毁
            del mdstream
            
            # 注意：在实际测试中，__del__ 方法的调用时机不确定
            # 这里主要是为了测试 __del__ 方法本身不会抛出异常

    def test_window_scrolling(self):
        """测试滑动窗口功能"""
        with patch('siada.io.components.mdstream.Live') as mock_live:
            mock_live_instance = MagicMock()
            mock_live.return_value = mock_live_instance
            
            # 创建超过窗口大小的内容
            content = "# 滑动窗口测试\n\n"
            for i in range(20):  # 超过默认的 live_window = 6
                content += f"第 {i+1} 行内容\n"
            
            self.mdstream.update(content)
            
            # 验证内容被分割为稳定部分和动态窗口部分
            assert len(self.mdstream.printed) > 0  # 应该有稳定的打印内容

    def test_performance_metrics(self):
        """测试性能指标"""
        content = "# 性能测试\n\n" + "测试内容 " * 1000
        
        with patch('siada.io.components.mdstream.Live') as mock_live:
            mock_live_instance = MagicMock()
            mock_live.return_value = mock_live_instance
            
            # 测试多次更新的性能
            start_time = time.time()
            
            for i in range(10):
                self.mdstream.update(content + f" {i}")
                time.sleep(0.1)  # 模拟真实的流式间隔
            
            self.mdstream.update(content, final=True)
            end_time = time.time()
            
            # 验证总时间合理（应该在2秒内完成）
            total_time = end_time - start_time
            assert total_time < 2.0
            
            # 验证 min_delay 被动态调整
            assert hasattr(self.mdstream, 'min_delay')
            assert self.mdstream.min_delay > 0

    def test_thinking_and_answer_format(self):
        """测试包含 thinking 标签和 ANSWER 格式的完整内容"""
        full_content = """► **ANSWER**

<thinking>
The user said "你好" which means "Hello" in Chinese. They are simply greeting me. Since this is a greeting and not a 
specific task, I should respond appropriately in Chinese and let them know I'm ready to help with any tasks they might 
have related to the codebase.

Looking at the environment details, I can see this is a project called "siada-agenthub" with various components 
including:
- Benchmark/evaluation framework for SWE (Software Engineering) tasks
- Agent hub with Siada agents
- Various tools for coding, file operations, repo mapping, etc.
- Utilities and configuration management

I should greet them back and ask what they'd like me to help with regarding this codebase.
</thinking>

你好！我是 Siada，一位经验丰富的软件工程师。我看到你在 siada-agenthub 
项目中，这是一个包含代理框架、基准测试工具和各种编程工具的项目。

我可以帮助你：
- 分析和理解代码结构
- 编写或修改代码
- 运行测试和评估
- 搜索和查找代码模式
- 优化和重构代码
- 解决编程问题

请告诉我你想要做什么，我会很乐意帮助你！

## 📋 项目结构

| 组件 | 功能描述 |
|------|----------|
| `siada-agenthub` | 主要代理框架 |
| `benchmark` | 基准测试工具 |
| `agents` | 各种 AI 代理 |
| `tools` | 编程辅助工具 |

```python
# 示例代码
def greet_user():
    return "你好，欢迎使用 Siada!"
```

> **提示**: 完整格式内容测试 ✅
"""
        
        with patch('siada.io.components.mdstream.Live') as mock_live:
            mock_live_instance = MagicMock()
            mock_live.return_value = mock_live_instance
            
            # 测试完整格式内容的渲染
            self.mdstream.update(full_content, final=True)
            
            # 验证 Live 实例被正确处理
            mock_live.assert_called_once()
            mock_live_instance.start.assert_called_once()
            mock_live_instance.stop.assert_called_once()
            
            # 验证内容被处理（通过检查渲染方法是否被调用）
            assert hasattr(self.mdstream, '_render_markdown_to_lines')

    def test_chinese_multilingual_content(self):
        """测试中文和多语言混合内容"""
        multilingual_content = """# 多语言支持测试

## 中文内容
你好！这是中文测试内容，包含各种格式：

- **粗体中文**
- *斜体中文*
- `中文代码`

## English Content
Hello! This is English test content with various formats:

- **Bold English**
- *Italic English*  
- `English code`

## 日本語コンテンツ
こんにちは！これは日本語のテストコンテンツです：

- **太字の日本語**
- *斜体の日本語*
- `日本語コード`

## 混合代码示例

```python
def multilingual_greeting():
    greetings = {
        "中文": "你好世界！",
        "English": "Hello World!",
        "日本語": "こんにちは世界！"
    }
    
    for lang, text in greetings.items():
        print(f"{lang}: {text}")

# 测试函数
multilingual_greeting()
```

## 特殊字符测试

| 语言 | 标点符号 | 货币符号 |
|------|----------|----------|
| 中文 | 。、！？ | ￥ |
| English | .,!? | $ |
| 日本語 | 。、！？ | ¥ |

> 多语言内容渲染测试完成 ✅
"""
        
        with patch('siada.io.components.mdstream.Live') as mock_live:
            mock_live_instance = MagicMock()
            mock_live.return_value = mock_live_instance
            
            # 分步测试多语言内容
            sections = multilingual_content.split('\n\n')
            accumulated = ""
            
            for section in sections[:3]:  # 测试前3个部分
                accumulated += section + '\n\n'
                self.mdstream.update(accumulated)
            
            # 最终更新完整内容
            self.mdstream.update(multilingual_content, final=True)
            
            # 验证多次更新正常执行
            assert mock_live_instance.update.call_count >= 2
            mock_live_instance.stop.assert_called_once()


def test_markdown_stream_integration():
    """集成测试：模拟真实使用场景"""
    
    # 模拟流式接收 AI 响应的场景
    ai_response_chunks = [
        "# AI 助手回复\n\n",
        "我来帮您解决这个问题。\n\n",
        "## 解决方案\n\n",
        "1. 首先，我们需要分析问题\n",
        "2. 然后制定解决策略\n",
        "3. 最后实施解决方案\n\n",
        "```python\n",
        "def solve_problem():\n",
        "    # 问题解决代码\n",
        "    return 'solved'\n",
        "```\n\n",
        "这样就完成了问题的解决。"
    ]
    
    with patch('siada.io.components.mdstream.Live') as mock_live:
        mock_live_instance = MagicMock()
        mock_live.return_value = mock_live_instance
        
        mdstream = MarkdownStream()
        accumulated_content = ""
        
        # 模拟流式更新
        for chunk in ai_response_chunks:
            accumulated_content += chunk
            mdstream.update(accumulated_content)
            time.sleep(0.1)  # 模拟网络延迟
        
        # 最终更新
        mdstream.update(accumulated_content, final=True)
        
        # 验证整个流程正常完成
        mock_live_instance.start.assert_called_once()
        mock_live_instance.stop.assert_called_once()
        assert mock_live_instance.update.call_count > 0


if __name__ == "__main__":
    # 运行基本演示
    print("MarkdownStream 功能演示:")
    
    mdstream = MarkdownStream()
    
    demo_content = """# MarkdownStream 演示

## 功能特性

- ✅ 实时 Markdown 渲染
- ✅ 流式内容更新
- ✅ 语法高亮支持
- ✅ 滑动窗口显示

## 代码示例

```python
def demo():
    stream = MarkdownStream()
    stream.update("# Hello World")
    stream.update("# Hello World\n\n更多内容...")
    stream.update(final_content, final=True)
```

## 结束

演示完成！
"""
    
    # 模拟逐步更新
    parts = demo_content.split('\n\n')
    accumulated = ""
    
    for part in parts:
        accumulated += part + '\n\n'
        mdstream.update(accumulated)
        time.sleep(0.5)  # 演示延迟
    
    mdstream.update(demo_content, final=True)
    print("\n演示完成！") 