import asyncio

from siada.services.siada_runner import SiadaRunner
import logging


calendar ="""
            帮我创建一个显示公历、藏历、农历对应的网页卡片，必须是真实数据，包含：周的数据，农历节气，藏历中的各种吉日、凶日，以及吉日凶日的具体原因单次显示一个完整的月份，并可以前后查看每个月的数据。
          """
calendar_detail = """帮我创建一个显示公历、藏历、农历对应的网页卡片，必须是真实数据，包含： 周的数据，农历节气，藏历理发吉祥日。 单次显示一个完整的月份，并可以前后查看每个月的数据。 藏历理发凶吉日：《菩萨头发品》是藏历中关于理发吉凶的传统文献，指出特定日期理发会带来不同影响。根据藏历： 吉日：初三（得财富）、初四（增气色）、初五（增财）、初八（长寿）、初十（快乐）、十一（增智慧）、十三（精进）、十四（增财富）、十五（大福报）、十九（增善法）、二十三（得财）、二十六（安乐）、二十七（吉祥）。 凶日：初一（短命）、初二（多病）、初六（损气色）、初七（招闲言）、十二（患病）、十六（不吉）、十七（视力差）、十八（破财）、二十（挨饿）、二十一（传染病）、二十二（增病）、二十四（瘟疫）、二十五（眼疾）、二十八（纷争）、二十九（游魂）、三十（遇凶）。 理发后头发应妥善处理，如扔入河中（长寿）、焚烧（事业缘起）或放高山（风马兴盛），避免随意丢弃。"""
chengyu = """实现一个网页版的成语接龙小游戏"""
fruit = """实现一个网页版的水果匹配小游戏"""


async def main():
    user_input = fruit
    agent_name = "fegen"
    result = await SiadaRunner.run_agent(agent_name, user_input)
    print(result)


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.INFO)
    asyncio.run(main())