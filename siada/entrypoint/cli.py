#!/usr/bin/env python3
"""
SiadaHub Command Line Tool
"""

import asyncio
import click
from importlib.metadata import version, PackageNotFoundError
from siada.services.siada_runner import SiadaRunner


def get_version():
    """Get package version information"""
    try:
        return version('siada-agenthub')
    except PackageNotFoundError:
        return 'development'


def print_version(ctx, param, value):
    """Print version information and exit"""
    if not value or ctx.resilient_parsing:
        return
    click.echo(f'siadahub, version {get_version()}')
    ctx.exit()


def load_agent_config():
    """Load agent configuration file"""
    try:
        return SiadaRunner._load_agent_config()
    except Exception as e:
        click.echo(f"Error: Failed to load configuration file: {e}", err=True)
        return {}


def register_agent_commands():
    """Register all agent commands"""
    agent_config = load_agent_config()
    
    for agent_type, config in agent_config.items():
        # Only create commands for enabled agents
        if config.get('enabled', True):
            description = config.get('description', f'Process tasks using {agent_type} agent')
            command_func = create_agent_command(agent_type)
            command_func.__name__ = agent_type
            command_func.__doc__ = description
            
            # Add click decorators
            command_func = click.argument('user_input')(command_func)
            command_func = siadahub.command()(command_func)


@click.group()
@click.option('-v', '--version', is_flag=True, expose_value=False, is_eager=True,
              callback=print_version, help='Show version information and exit')
def siadahub():
    """SiadaHub - AI Agent Command Line Tool"""
    pass


def create_agent_command(agent_type):
    """Create agent command function"""
    def agent_command(user_input):
        if not user_input:
            click.echo("Error: user_input cannot be empty", err=True)
            return
        
        try:
            result = asyncio.run(SiadaRunner.run_agent(agent_type, user_input))
            click.echo(result)
        except Exception as e:
            click.echo(f"Execution failed: {e}", err=True)
    
    return agent_command


# Register all agent commands
# IMPORTANT: Must be register before main function being called due to CLICK package requirements.
register_agent_commands()


if __name__ == '__main__':
    siadahub()
