

import asyncio
from siada.services.siada_runner import SiadaRunner


input="""生成一个日历卡片， 带农历公历，礼拜信息，节假日信息， 适用于手机尺寸
"""

async def run_fegen():
    # 获取当前工作目录
    current_dir = '/Users/yunan/code/test/test_ai_siada'

    # Define the user input and agent name
    agent_name: str = "fegen"

    # Run the agent and get the result
    result = await SiadaRunner.run_agent(agent_name=agent_name, user_input=input, workspace=current_dir)

    # Print the result
    print(result)


def main():
    """Main function to run the codegen test."""
    asyncio.run(run_fegen())


if __name__ == "__main__":
    main()