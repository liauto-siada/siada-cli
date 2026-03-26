"""
LiMateModel 非流式模式测试

直接测试 LiMateModel 的非流式响应模式。

使用方法:
    cd tests/agent_hub/a2a/hello_world
    python test_non_stream.py
"""

import asyncio
import time

from google.adk.models.llm_request import LlmRequest
from google.genai import types
from siada.provider.adk_provider import LiMateModel


async def main():
    print("\n" + "=" * 70)
    print(" LiMateModel 非流式模式测试")
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
        print(f"\n等待响应...")
        
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
        
        # 非流式调用
        start_time = time.time()
        response_count = 0
        full_response = ""
        
        async for response in model.generate_content_async(request, stream=False):
            response_count += 1
            
            if response.content and response.content.parts:
                text = response.content.parts[0].text
                full_response += text
                
                print(f"\n{'─'*70}")
                print(f"响应 #{response_count}:")
                print(f"{'─'*70}")
                print(f"Partial: {response.partial}")
                print(f"长度: {len(text)} 字符")
                print(f"\n内容:")
                print(text)
                print(f"{'─'*70}")
        
        elapsed = time.time() - start_time
        
        print(f"\n📊 统计信息:")
        print(f"   总响应数: {response_count}")
        print(f"   响应时间: {elapsed:.2f}秒")
        print(f"   总长度: {len(full_response)} 字符")
        
        if i < len(test_cases):
            print(f"\n{'─'*70}")
            input("按回车继续下一个测试...")
    
    print(f"\n{'='*70}")
    print(" ✅ 所有测试完成")
    print(f"{'='*70}")
    print("\n💡 观察要点:")
    print("  1. 日志中应显示: chat_complete called")
    print("  2. 每个问题只有1个完整响应")
    print("  3. Partial 始终为 False")
    print("  4. 响应内容一次性返回")


if __name__ == '__main__':
    asyncio.run(main())
