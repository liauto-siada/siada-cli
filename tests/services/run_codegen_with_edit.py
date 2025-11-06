import os
import asyncio
from siada.services.siada_runner import SiadaRunner


async def run_codegen():
    # 获取当前工作目录
    current_dir = os.getcwd()

    # 构建正确的文件路径
    file_path = os.path.join(current_dir, "test_data", "test.py")

    # Define the user input and agent name
    user_input: str = f"编辑此文件，打印hello world：{file_path}"
    agent_name: str = "coder"

    # Run the agent and get the streaming result
    result = await SiadaRunner.run_agent(
        agent_name=agent_name, 
        user_input=user_input, 
        stream=True
    )

    # Consume the stream events
    print("开始接收流式输出...\n")
    print("=" * 80)
    
    event_count = 0
    async for event in result.stream_events():
        event_count += 1
        # 打印每个流式事件
        print(f"\n[事件 #{event_count}]")
        print(f"事件类型: {type(event).__name__}")
        print(f"事件内容: {event}")
        print("-" * 80)

    # 获取最终结果
    print("\n" + "=" * 80)
    print("流式输出完成！")
    print(f"总共接收到 {event_count} 个事件")
    print("=" * 80)
    print("\n最终输出:")
    print(result.final_output)


def main():
    """Main function to run the codegen test."""
    asyncio.run(run_codegen())


if __name__ == "__main__":
    main()
