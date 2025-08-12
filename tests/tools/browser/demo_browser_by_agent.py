

import asyncio
from siada.services.siada_runner import SiadaRunner


# input="""生成一个日历卡片， 带农历公历，礼拜信息，节假日信息， 适用于手机尺寸
# """

# input = "打开这个网页， 并总结网页的内容 https://www.huxiu.com/article/4668429.html"
input = "打开www.baidu.com, 在搜索框输入'GPT5的最新消息'， 然后点击搜索按钮，获取搜索结果的标题和链接。"
#input = "打开www.baidu.com, 告诉我搜索框的中心在图片中的坐标位置"

async def run_browser():
    # 获取当前工作目录
    current_dir = '/Users/yunan/code/test/test_ai_siada'

    # Define the user input and agent name
    agent_name: str = "browser"

    # Run the agent and get the result
    result = await SiadaRunner.run_agent(agent_name=agent_name, user_input=input, workspace=current_dir)

    # Print the result
    print(result)


def main():
    """Main function to run the codegen test."""
    asyncio.run(run_browser())


if __name__ == "__main__":
    main()