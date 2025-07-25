#!/usr/bin/env python
"""
MarkdownStream 实际演示脚本

这个脚本演示了 MarkdownStream 在真实场景中的使用，
模拟了 AI 助手逐步生成回复的过程。
"""

import time
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from siada.io.components.mdstream import MarkdownStream


def demo_basic_usage():
    """演示基本使用"""
    print("🔄 演示 1: 基本 MarkdownStream 使用")
    print("=" * 50)
    
    mdstream = MarkdownStream()
    
    # 模拟逐步构建内容
    content_steps = [
        "# 欢迎使用 MarkdownStream",
        "# 欢迎使用 MarkdownStream\n\n这是一个实时 Markdown 渲染工具。",
        "# 欢迎使用 MarkdownStream\n\n这是一个实时 Markdown 渲染工具。\n\n## 主要特性",
        "# 欢迎使用 MarkdownStream\n\n这是一个实时 Markdown 渲染工具。\n\n## 主要特性\n\n- 流式内容更新\n- 语法高亮\n- 实时渲染",
        "# 欢迎使用 MarkdownStream\n\n这是一个实时 Markdown 渲染工具。\n\n## 主要特性\n\n- 流式内容更新\n- 语法高亮\n- 实时渲染\n\n## 代码示例\n\n```python\nstream = MarkdownStream()\nstream.update(content)\n```"
    ]
    
    for i, content in enumerate(content_steps):
        print(f"\n📝 步骤 {i+1}: 更新内容...")
        mdstream.update(content)
        time.sleep(1.5)  # 暂停以便观察效果
    
    # 最终更新
    mdstream.update(content_steps[-1], final=True)
    print("\n✅ 基本演示完成!\n")


def demo_ai_conversation():
    """演示 AI 对话场景"""
    print("🤖 演示 2: AI 对话场景")
    print("=" * 50)
    
    mdstream = MarkdownStream()
    
    # 模拟 AI 助手回复的逐步生成
    ai_chunks = [
        "# AI 助手回复\n\n",
        "我理解您的问题。让我为您提供一个详细的解决方案。\n\n",
        "## 问题分析\n\n",
        "根据您的描述，这个问题可能涉及以下几个方面：\n\n",
        "1. **配置问题** - 检查相关配置是否正确\n",
        "2. **环境问题** - 验证运行环境\n",
        "3. **依赖问题** - 确保所有依赖都已安装\n\n",
        "## 解决步骤\n\n",
        "### 步骤 1: 检查配置\n\n",
        "```bash\n# 检查配置文件\ncat config.yaml\n```\n\n",
        "### 步骤 2: 验证环境\n\n",
        "```python\nimport sys\nprint(f\"Python 版本: {sys.version}\")\n\n# 检查关键模块\ntry:\n    import important_module\n    print(\"✅ 模块导入成功\")\nexcept ImportError as e:\n    print(f\"❌ 模块导入失败: {e}\")\n```\n\n",
        "### 步骤 3: 运行测试\n\n",
        "```bash\n# 运行基本测试\npython -m pytest tests/\n```\n\n",
        "## 预期结果\n\n",
        "完成以上步骤后，您应该能够：\n\n",
        "- ✅ 成功启动应用\n- ✅ 正常处理请求\n- ✅ 获得预期输出\n\n",
        "## 补充说明\n\n",
        "如果问题仍然存在，请检查：\n\n",
        "> **注意**: 某些环境下可能需要额外的权限设置\n\n",
        "| 问题类型 | 可能原因 | 解决方法 |\n",
        "|----------|----------|----------|\n",
        "| 权限错误 | 文件权限不足 | `chmod +x script.py` |\n",
        "| 模块错误 | 依赖缺失 | `pip install -r requirements.txt` |\n",
        "| 配置错误 | 参数不正确 | 检查配置文档 |\n\n",
        "希望这个解决方案对您有帮助！如果还有其他问题，请随时告诉我。"
    ]
    
    accumulated = ""
    for i, chunk in enumerate(ai_chunks):
        accumulated += chunk
        print(f"\n🔄 AI 思考中... ({i+1}/{len(ai_chunks)})")
        mdstream.update(accumulated)
        time.sleep(0.8)  # 模拟 AI 生成延迟
    
    # 最终更新
    mdstream.update(accumulated, final=True)
    print("\n🎉 AI 对话演示完成!\n")


def demo_code_explanation():
    """演示代码解释场景"""
    print("💻 演示 3: 代码解释场景")
    print("=" * 50)
    
    mdstream = MarkdownStream()
    
    # 模拟代码解释的逐步生成
    explanation_parts = [
        "# 代码解释\n\n",
        "让我来解释这段 Python 代码的工作原理：\n\n",
        "```python\ndef fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)\n```\n\n",
        "## 函数分析\n\n",
        "这是一个实现斐波那契数列的递归函数：\n\n",
        "### 基础情况\n\n",
        "```python\nif n <= 1:\n    return n\n```\n\n",
        "- 当 `n` 为 0 或 1 时，直接返回 `n`\n",
        "- 这是递归的终止条件\n\n",
        "### 递归情况\n\n",
        "```python\nreturn fibonacci(n-1) + fibonacci(n-2)\n```\n\n",
        "- 对于其他情况，返回前两个数的和\n",
        "- 这体现了斐波那契数列的定义\n\n",
        "## 执行示例\n\n",
        "让我们看看 `fibonacci(4)` 的执行过程：\n\n",
        "```\nfibonacci(4)\n├── fibonacci(3)\n│   ├── fibonacci(2)\n│   │   ├── fibonacci(1) → 1\n│   │   └── fibonacci(0) → 0\n│   │   └── 结果: 1\n│   └── fibonacci(1) → 1\n│   └── 结果: 2\n└── fibonacci(2)\n    ├── fibonacci(1) → 1\n    └── fibonacci(0) → 0\n    └── 结果: 1\n└── 最终结果: 3\n```\n\n",
        "## 性能注意事项\n\n",
        "> ⚠️ **警告**: 这个实现有指数时间复杂度 O(2^n)\n\n",
        "对于大的 `n` 值，这个函数会非常慢。更好的实现：\n\n",
        "```python\ndef fibonacci_optimized(n, memo={}):\n    if n in memo:\n        return memo[n]\n    if n <= 1:\n        return n\n    memo[n] = fibonacci_optimized(n-1, memo) + fibonacci_optimized(n-2, memo)\n    return memo[n]\n```\n\n",
        "## 总结\n\n",
        "- ✅ 简洁优雅的递归实现\n",
        "- ❌ 性能较差，不适合大数\n",
        "- 💡 可以使用备忘录技术优化\n\n"
    ]
    
    accumulated = ""
    for i, part in enumerate(explanation_parts):
        accumulated += part
        print(f"\n📖 正在解释... ({i+1}/{len(explanation_parts)})")
        mdstream.update(accumulated)
        time.sleep(1.0)
    
    # 最终更新
    mdstream.update(accumulated, final=True)
    print("\n📚 代码解释演示完成!\n")


def demo_performance_test():
    """演示性能测试"""
    print("⚡ 演示 4: 性能测试")
    print("=" * 50)
    
    mdstream = MarkdownStream()
    
    print("🔄 生成大量内容进行性能测试...")
    
    # 生成大量内容
    large_content = "# 性能测试报告\n\n"
    large_content += "这是一个包含大量内容的 Markdown 文档，用于测试 MarkdownStream 的性能。\n\n"
    
    for i in range(50):
        large_content += f"## 第 {i+1} 节\n\n"
        large_content += f"这是第 {i+1} 节的内容。" * 5 + "\n\n"
        large_content += f"```python\n"
        large_content += f"def section_{i+1}():\n"
        large_content += f"    \"\"\"第 {i+1} 节的示例代码\"\"\"\n"
        large_content += f"    data = ['item_{j}' for j in range(10)]\n"
        large_content += f"    return {{k: v for k, v in enumerate(data)}}\n"
        large_content += f"```\n\n"
        large_content += f"| 项目 | 值 |\n|------|----|\n"
        for j in range(3):
            large_content += f"| 参数 {j+1} | 值 {i*3+j+1} |\n"
        large_content += "\n"
    
    start_time = time.time()
    
    # 分块更新大内容
    chunks = [large_content[:i*1000] for i in range(1, len(large_content)//1000 + 1)]
    chunks.append(large_content)  # 完整内容
    
    for i, chunk in enumerate(chunks[::5]):  # 每5个块更新一次，减少演示时间
        print(f"📊 更新进度: {i+1}/{len(chunks[::5])} ({len(chunk)} 字符)")
        mdstream.update(chunk)
        time.sleep(0.2)
    
    mdstream.update(large_content, final=True)
    
    end_time = time.time()
    print(f"\n⏱️ 性能测试完成! 总用时: {end_time - start_time:.2f} 秒")
    print(f"📊 处理内容: {len(large_content)} 字符\n")


def demo_thinking_answer_format():
    """演示包含 thinking 和 answer 格式的内容"""
    print("🧠 演示 5: Thinking + Answer 格式")
    print("=" * 50)
    
    mdstream = MarkdownStream()
    
    # 完整的 thinking + answer 格式内容
    thinking_answer_content = """► **ANSWER**

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

## 📋 项目组件对比

| 组件类型 | 功能范围 | 应用场景 |
|----------|----------|----------|
| 🤖 **Agent Hub** | 智能代理管理 | AI 辅助编程 |
| 🧪 **Benchmark** | 性能评估 | 代码质量测试 |
| 🛠️ **Tools** | 实用工具集 | 开发效率提升 |
| ⚙️ **Foundation** | 基础设施 | 系统配置管理 |

## 💻 核心功能展示

```python
# Siada Agent 示例使用
from siada.agent_hub import SiadaAgent
from siada.tools.coder import edit, search, run_cmd

class MyAgent(SiadaAgent):
    def __init__(self):
        super().__init__(
            name="智能编程助手",
            tools=[edit, search, run_cmd],
            model="claude-sonnet-4"
        )
    
    async def solve_problem(self, user_input: str):
        # 智能分析用户需求
        context = await self.get_context()
        
        # 执行解决方案
        result = await self.run(user_input, context)
        
        return result

# 使用示例
agent = MyAgent()
result = await agent.solve_problem("帮我优化这段代码")
print(f"解决方案: {result}")
```

> **核心特性**: Thinking + Answer 格式完美支持 ✅

---

**演示完成** - MarkdownStream 支持完整的 AI 交互格式！🎉
"""
    
    # 分步展示内容
    parts = [
        "► **ANSWER**\n\n<thinking>",
        thinking_answer_content.split('</thinking>')[0] + '</thinking>',
        thinking_answer_content.split('</thinking>')[1].split('## 📋')[0],
        thinking_answer_content.split('## 📋')[1].split('## 💻')[0],
        thinking_answer_content.split('## 💻')[1]
    ]
    
    accumulated = ""
    for i, part in enumerate(parts):
        if i == 0:
            accumulated = part
        elif i == 1:
            accumulated = part
        else:
            accumulated += ("## 📋" if i == 2 else ("## 💻" if i == 3 else "")) + part
        
        print(f"\n🔄 展示部分 {i+1}: {'思考过程' if i <= 1 else '回答内容' if i == 2 else '项目结构' if i == 3 else '代码示例'}")
        mdstream.update(accumulated)
        time.sleep(1.2)
    
    # 最终更新
    mdstream.update(thinking_answer_content, final=True)
    print("\n🧠 Thinking + Answer 格式演示完成!\n")


def main():
    """主演示函数"""
    print("🎯 MarkdownStream 功能全面演示")
    print("=" * 60)
    print("这个演示将展示 MarkdownStream 在各种场景下的使用效果")
    print("请注意观察内容的实时渲染效果！\n")
    
    demos = [
        ("基本使用", demo_basic_usage),
        ("AI 对话场景", demo_ai_conversation),
        ("代码解释场景", demo_code_explanation),
        ("性能测试", demo_performance_test),
        ("Thinking + Answer 格式", demo_thinking_answer_format)
    ]
    
    for i, (name, demo_func) in enumerate(demos, 1):
        print(f"\n🎬 准备运行演示 {i}: {name}")
        input("按 Enter 键开始...")
        
        try:
            demo_func()
        except KeyboardInterrupt:
            print("\n\n⏹️ 演示被用户中断")
            break
        except Exception as e:
            print(f"\n❌ 演示出错: {e}")
        
        if i < len(demos):
            print("=" * 60)
    
    print("\n🎉 所有演示完成！")
    print("感谢您体验 MarkdownStream 的功能！")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 演示结束，再见！")
    except Exception as e:
        print(f"\n💥 程序出错: {e}")
        sys.exit(1) 