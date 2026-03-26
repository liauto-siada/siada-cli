"""
LiMateModel 流式模式测试

直接测试 LiMateModel 的流式响应模式，实时显示每个chunk。

使用方法:
    cd tests/agent_hub/a2a/hello_world
    python test_stream.py
"""

import asyncio
import time

from google.adk.models.llm_request import LlmRequest
from google.genai import types
from siada.provider.adk_provider import LiMateModel


async def main():
    print("\n" + "=" * 70)
    print(" LiMateModel 流式模式测试")
    print("=" * 70)
    
    # 创建模型
    model = LiMateModel(model="claude-sonnet-4.5")
    
    # 测试用例（中文）
    test_cases = [
        "请用一句话解释什么是量子计算",
        "Python和Java的主要区别是什么？",
        "请推荐3本适合编程初学者的书",
    ]
    
    for i, question in enumerate(test_cases, 1):
        print(f"\n{'='*70}")
        print(f" 测试 {i}/{len(test_cases)}")
        print(f"{'='*70}")
        print(f"问题: {question}")
        print(f"\n开始流式输出...")
        print(f"{'─'*70}")
        
        # 构建请求
        request = LlmRequest(
            model="claude-sonnet-4.5",
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part(text=question)]
                )
            ],
            config=types.GenerateContentConfig()
        )
        
        # 流式调用
        start_time = time.time()
        chunk_count = 0
        full_response = ""
        partial_count = 0
        
        print("💬 实时输出: ", end="", flush=True)
        
        async for response in model.generate_content_async(request, stream=True):
            chunk_count += 1
            
            if response.content and response.content.parts:
                text = response.content.parts[0].text
                full_response += text
                
                if response.partial:
                    partial_count += 1
                    # 实时打印每个chunk（模拟打字效果）
                    print(text, end="", flush=True)
                else:
                    # Final chunk
                    if text:
                        print(text, end="", flush=True)
                    print()  # 换行
        
        elapsed = time.time() - start_time
        
        print(f"{'─'*70}")
        print(f"\n📊 统计信息:")
        print(f"   总chunks: {chunk_count}")
        print(f"   Partial chunks: {partial_count}")
        print(f"   Final chunks: {chunk_count - partial_count}")
        print(f"   响应时间: {elapsed:.2f}秒")
        print(f"   总长度: {len(full_response)} 字符")
        print(f"   平均chunk长度: {len(full_response) / chunk_count:.1f} 字符")
        
        if i < len(test_cases):
            print(f"\n{'─'*70}")
            input("按回车继续下一个测试...")
    
    print(f"\n{'='*70}")
    print(" ✅ 所有测试完成")
    print(f"{'='*70}")
    print("\n💡 观察要点:")
    print("  1. 日志中应显示: chat_complete_stream called")
    print("  2. 每个问题有多个chunks（通常10-30个）")
    print("  3. Partial chunks: Partial=True")
    print("  4. Final chunk: Partial=False")
    print("  5. 响应内容逐字逐句显示（打字机效果）")
    print("\n🎯 流式的优势:")
    print("  - 用户体验更好：立即看到响应开始")
    print("  - 感知延迟更低：不用等待完整响应")
    print("  - 适合长文本：逐步显示，不会长时间无响应")


if __name__ == '__main__':
    asyncio.run(main())
