#!/usr/bin/env python

import argparse
import os
import sys
from pathlib import Path

import configargparse
import shtab

from siada import __version__
from siada.services.siada_runner import SiadaRunner

def resolve_aiderignore_path(path_str, git_root=None):
    path = Path(path_str)
    if path.is_absolute():
        return str(path)
    elif git_root:
        return str(Path(git_root) / path)
    return str(path)


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

    group = parser.add_argument_group("Main model")

    group.add_argument(
        "--model",
        metavar="MODEL",
        default=None,
        help="Specify the model to use for the main chat",
    )

    # Add agent selection argument
    group.add_argument(
        "--agent",
        metavar="AGENT",
        choices=agent_choices,
        default="bugfix",
        help=f"Specify the agent type to use (choices: {', '.join(agent_choices)}, default: bugfix)",
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
    group = parser.add_argument_group("API Keys and settings")
    group.add_argument(
        "--set-env",
        action="append",
        metavar="ENV_VAR_NAME=value",
        help="Set an environment variable (to control API settings, can be used multiple times)",
        default=[],
    )
    group.add_argument(
        "--api-key",
        action="append",
        metavar="PROVIDER=KEY",
        help=(
            "Set an API key for a provider (eg: --api-key provider=<key> sets"
            " PROVIDER_API_KEY=<key>)"
        ),
        default=[],
    )
    group = parser.add_argument_group("Model settings")
    group.add_argument(
        "--list-models",
        "--models",
        metavar="MODEL",
        help="List known models which match the (partial) MODEL name",
    )
    
    group.add_argument(
        "--alias",
        action="append",
        metavar="ALIAS:MODEL",
        help="Add a model alias (can be used multiple times)",
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

    ##########
    group = parser.add_argument_group("Cache settings")

    group.add_argument(
        "--cache-prompts",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable caching of prompts (default: False)",
    )


    group.add_argument(
        "--cache-keepalive-pings",
        type=int,
        default=0,
        help="Number of times to ping at 5min intervals to keep prompt cache warm (default: 0)",
    )

    ##########
    group = parser.add_argument_group("Repomap settings")
    group.add_argument(
        "--map-tokens",
        type=int,
        default=None,
        help="Suggested number of tokens to use for repo map, use 0 to disable",
    )

    group.add_argument(
        "--map-refresh",
        choices=["auto", "always", "files", "manual"],
        default="auto",
        help=(
            "Control how often the repo map is refreshed. Options: auto, always, files, manual"
            " (default: auto)"
        ),
    )
    group.add_argument(
        "--map-multiplier-no-files",
        type=float,
        default=2,
        help="Multiplier for map tokens when no files are specified (default: 2)",
    )

    ##########
    group = parser.add_argument_group("Output settings")
    group.add_argument(
        "--theme",
        choices=["default", "dark", "light"],
        default=None,
        help="Select color theme: default, dark, or light (default: None, auto-detect or use individual mode flags)",
    )

    ##########
    group = parser.add_argument_group("Git settings")
    group.add_argument(
        "--git",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable/disable looking for a git repo (default: True)",
    )

    #########
    group = parser.add_argument_group("Upgrading")
    group.add_argument(
        "--just-check-update",
        action="store_true",
        help="Check for updates and return status in the exit code",
        default=False,
    )


    group.add_argument(
        "--check-update",
        action=argparse.BooleanOptionalAction,
        help="Check for new aider versions on launch",
        default=True,
    )

    group.add_argument(
        "--show-release-notes",
        action=argparse.BooleanOptionalAction,
        help="Show release notes on first run of new version (default: None, ask user)",
        default=None,
    )

    group.add_argument(
        "--install-main-branch",
        action="store_true",
        help="Install the latest version from the main branch",
        default=False,
    )
    group.add_argument(
        "--upgrade",
        "--update",
        action="store_true",
        help="Upgrade aider to the latest version from PyPI",
        default=False,
    )
    group.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show the version number and exit",
    )

    ##########
    group = parser.add_argument_group("Modes")
    group.add_argument(
        "--show-repo-map",
        action="store_true",
        help="Print the repo map and exit (debug)",
        default=False,
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
        "--chat-language",
        metavar="CHAT_LANGUAGE",
        default=None,
        help="Specify the language to use in the chat (default: None, uses system settings)",
    )
    
    group.add_argument(
        "--yes-always",
        action="store_true",
        help="Always say yes to every confirmation",
        default=None,
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
        "--suggest-shell-commands",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable/disable suggesting shell commands (default: True)",
    )

    group.add_argument(
        "--fancy-input",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable/disable fancy input with history and completion (default: True)",
    )

    group.add_argument(
        "--multiline",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable/disable multi-line input mode with Meta-Enter to submit (default: False)",
    )

    group.add_argument(
        "--notifications",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Enable/disable terminal bell notifications when LLM responses are ready (default:"
            " False)"
        ),
    )


    group.add_argument(
        "--editor",
        help="Specify which editor to use for the /editor command",
    )

    supported_shells_list = sorted(list(shtab.SUPPORTED_SHELLS))
    group.add_argument(
        "--shell-completions",
        metavar="SHELL",
        choices=supported_shells_list,
        help=(
            "Print shell completion script for the specified SHELL and exit. Supported shells:"
            f" {', '.join(supported_shells_list)}. Example: aider --shell-completions bash"
        ),
    )

    return parser

