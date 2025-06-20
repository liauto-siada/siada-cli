#!/usr/bin/env python3
"""
SiadaHub 命令行工具
"""

import asyncio
import click
from siada.services.siada_runner import SiadaRunner


@click.group()
def siadahub():
    """SiadaHub - AI Agent 命令行工具"""
    pass


@siadahub.command()
@click.argument('user_input')
def bugfix(user_input):
    """使用 bugfix agent 处理任务"""
    if not user_input:
        click.echo("错误: user_input 不能为空", err=True)
        return
    
    try:
        result = asyncio.run(SiadaRunner.run_agent("bugfix", user_input))
        click.echo(result)
    except Exception as e:
        click.echo(f"执行失败: {e}", err=True)


if __name__ == '__main__':
    siadahub()
