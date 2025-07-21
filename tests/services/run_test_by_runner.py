
import asyncio
from siada.services.siada_runner import SiadaRunner


async def run_test():
    # 获取当前工作目录
    current_dir = '/Users/yunan/code/test/test_ai'

    # Define the user input and agent name
    agent_name: str = "test"

    test_input = "Test the email validity verification function"

    # Run the agent and get the result
    result = await SiadaRunner.run_agent(agent_name=agent_name, user_input=test_input, workspace=current_dir)

    # Print the result
    print(result)


def main():
    """Main function to run the codegen test."""
    asyncio.run(run_test())


if __name__ == "__main__":
    main()


