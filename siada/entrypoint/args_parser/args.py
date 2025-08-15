#!/usr/bin/env python

import argparse
import os
import sys
from pathlib import Path

import configargparse
import shtab

from siada import __version__
from siada.services.siada_runner import SiadaRunner


def default_env_file(git_root):
    return os.path.join(git_root, ".env") if git_root else ".env"


def get_parser(default_config_files, git_root):
    parser = configargparse.ArgumentParser(
        description="Siada-CLI is AI pair programming in your terminal",
        add_config_file_help=True,
        default_config_files=default_config_files,
        config_file_parser_class=configargparse.YAMLConfigFileParser,
        auto_env_var_prefix="SIADA_",
    )

    # Load agent configurations from config file
    try:
        agent_configs = SiadaRunner._load_agent_config()
        # Get enabled agent types for choices
        agent_choices = [name for name, config in agent_configs.items() 
                        if config.get('enabled', False) and config.get('class')]
    except Exception as e:
        # Fallback to default if config loading fails
        agent_configs = {}
        agent_choices = ['bugfix', 'coder', 'fegen', 'bugreproduce']
        print(f"Warning: Failed to load agent config, using defaults: {e}")

    ##########
    group = parser.add_argument_group("agent config")

    group.add_argument(
        "--agent",
        "-a",
        metavar="AGENT",
        choices=agent_choices,
        default="coder",
        help=f"Specify the agent type to use (choices: {', '.join(agent_choices)}, default: coder)",
    )

    # Generate individual agent command arguments
    for agent_name in agent_choices:
        agent_config = agent_configs.get(agent_name, {})
        description = agent_config.get('description', f'{agent_name.title()} agent')

        group.add_argument(
            f"--{agent_name}",
            action="store_const",
            dest="agent",
            const=agent_name,
            help=f"Use {description}",
        )

    ##########
    group = parser.add_argument_group("prompt config")
    group.add_argument(
        "--prompt",
        "-p",
        metavar="PROMPT",
        default=None,
        help="Specify the prompt, if provided, it will be activated for the no interaction mode",
    )

    ##########
    group = parser.add_argument_group("API Keys and settings")
    group.add_argument(
        "--env-file",
        metavar="ENV_FILE",
        default=default_env_file(git_root),
        help="Specify the .env file to load (default: .env in git root)",
    ).complete = shtab.FILE

    group.add_argument(
        "--set-env",
        action="append",
        metavar="ENV_VAR_NAME=value",
        help="Set an environment variable (to control API settings, can be used multiple times)",
        default=[],
    )

    group = parser.add_argument_group("Model settings")

    group.add_argument(
        "--model",
        metavar="MODEL",
        default=None,
        help="Specify the model to use for the main chat",
    )

    group.add_argument(
        "--list-models",
        "--models",
        action="store_true",
        help="List all available models",
    )

    group.add_argument(
        "--reasoning-effort",
        type=str,
        help="Set the reasoning_effort API parameter (default: not set)",
    )
    group.add_argument(
        "--thinking-tokens",
        type=str,
        help=(
            "Set the thinking token budget for models that support it. Use 0 to disable. (default:"
            " not set)"
        ),
    )

    group.add_argument(
        "--provider",
        choices=["openrouter", "li"],
        default=None,
        help="Specify the provider to use for the main chat (choices: openrouter, li, default: li)",
        metavar="PROVIDER",
    )

    group = parser.add_argument_group("Output settings")
    group.add_argument(
        "--theme",
        choices=["default", "dark", "light"],
        default="dark",
        help="Select color theme: default, dark, or light (default: None, auto-detect or use individual mode flags)",
    )

    group.add_argument(
        "--pretty",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable/disable pretty, colorized output (default: True)",
    )

    group.add_argument(
        "--fancy-input",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable/disable fancy input (default: True)",
    )

    group = parser.add_argument_group("Upgrading")
    group.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show the version number and exit",
    )

    ######
    group = parser.add_argument_group("Other settings")

    group.add_argument(
        "--vim",
        action="store_true",
        help="Use VI editing mode in the terminal (default: False)",
        default=False,
    )
    group.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
        default=False,
    )

    group.add_argument(
        "--encoding",
        default="utf-8",
        help="Specify the encoding for input and output (default: utf-8)",
    )

    group.add_argument(
        "--editor",
        help="Specify which editor to use for the /editor command",
    )

    group.add_argument(
        "--disable-console-output",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Disable console output for debugging (default: True)",
    )

    return parser
