import os
import asyncio
from siada.services.siada_runner import SiadaRunner
from siada.session.session_manager import RunningSessionManager
from siada.entrypoint.interaction.running_config import RunningConfig
from siada.io.io import InputOutput
from siada.models.model_run_config import ModelRunConfig


async def run_codegen():
    # 获取当前工作目录
    # current_dir = os.getcwd()

    # 构建正确的文件路径
    # file_path = os.path.join(current_dir, "test_data", "complex_python_file.py")

    current_dir = '/Users/yunan/code/copilot/agent-web'

    # Define the user input and agent name
    user_input: str = f"""创建一个shell脚本， 打印三遍：你好北京"""
    agent_name: str = "coder"

    # 创建 RunningSession
    # 方式1: 使用默认配置创建 session（简单快速）
    # session = RunningSessionManager.get_default_session()

    # 方式2: 自定义配置创建 session（推荐，更完整的演示）
    llm_config = ModelRunConfig.get_default_config()
    io = InputOutput()

    siada_config = RunningConfig(
        llm_config=llm_config,
        io=io,
        workspace=current_dir,
        agent_name=agent_name,
        console_output=True,  # 控制台输出日志
        interactive=False,  # 非交互模式
    )

    session = RunningSessionManager.create_session(siada_config)

    print(f"Session ID: {session.session_id}")
    print(f"Session workspace: {session.siada_config.workspace}")
    print("-" * 80)

    # Run the agent and get the result
    # 传入 session 参数，这样可以：
    # 1. 保存会话历史到文件系统
    # 2. 支持 checkpoint 功能（代码检查点，可以回退）
    # 3. 支持用户记忆（user_memory）和规则记忆（rule_memory）
    # 4. 支持更多配置选项
    result = await SiadaRunner.run_agent(
        agent_name=agent_name,
        user_input=user_input,
        workspace=current_dir,
        session=session  # 传入 session 参数
    )

    # Print the result
    print("\n" + "=" * 80)
    print("Result:")
    print(result)


def main():
    """Main function to run the codegen test."""
    asyncio.run(run_codegen())


if __name__ == "__main__":
    main()
