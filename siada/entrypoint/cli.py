#!/usr/bin/env python3
"""
SiadaHub 命令行工具
"""

import asyncio
import click
from importlib.metadata import version, PackageNotFoundError
from siada.services.siada_runner import SiadaRunner


def get_version():
    """获取包版本信息"""
    try:
        return version('siada-agenthub')
    except PackageNotFoundError:
        return 'development'


def print_version(ctx, param, value):
    """打印版本信息并退出"""
    if not value or ctx.resilient_parsing:
        return
    click.echo(f'siadahub, version {get_version()}')
    ctx.exit()


def load_agent_config():
    """加载 agent 配置文件"""
    try:
        return SiadaRunner._load_agent_config()
    except Exception as e:
        click.echo(f"错误: 加载配置文件失败: {e}", err=True)
        return {}


@click.group()
@click.option('-v', '--version', is_flag=True, expose_value=False, is_eager=True,
              callback=print_version, help='显示版本信息并退出')
def siadahub():
    """SiadaHub - AI Agent 命令行工具"""
    pass


def create_agent_command(agent_type, description):
    """创建 agent 命令的通用函数"""
    def agent_command(user_input):
        if not user_input:
            click.echo("错误: user_input 不能为空", err=True)
            return
        
        try:
            result = asyncio.run(SiadaRunner.run_agent(agent_type, user_input))
            click.echo(result)
        except Exception as e:
            click.echo(f"执行失败: {e}", err=True)
    
    return agent_command


# 从配置文件动态创建各种 agent 命令
agent_config = load_agent_config()

for agent_type, config in agent_config.items():
    # 只为启用的 agent 创建命令
    if config.get('enabled', True):
        description = config.get('description', f'使用 {agent_type} agent 处理任务')
        command_func = create_agent_command(agent_type, description)
        command_func.__name__ = agent_type
        command_func.__doc__ = description
        
        # 添加 click 装饰器
        command_func = click.argument('user_input')(command_func)
        command_func = siadahub.command()(command_func)


if __name__ == '__main__':
    siadahub()
