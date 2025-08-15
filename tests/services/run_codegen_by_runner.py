
import os
import asyncio
from siada.services.siada_runner import SiadaRunner


async def run_codegen():
    # 获取当前工作目录
    current_dir = os.getcwd()
    
    # 构建正确的文件路径
    file_path = os.path.join(current_dir, "test_data", "complex_python_file.py")
    
    # Define the user input and agent name
    user_input: str = f"请分析这个Python文件有哪些函数：{file_path}"
    agent_name: str = "coder"

    # Run the agent and get the result
    result = await SiadaRunner.run_agent(agent_name=agent_name, user_input=user_input)

    # Print the result
    print(result)


def main():
    """Main function to run the codegen test."""
    asyncio.run(run_codegen())


if __name__ == "__main__":
    main()
