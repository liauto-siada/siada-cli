#!/usr/bin/env python

import argparse
import os
from pathlib import Path
from typing import Dict
import configargparse
import shtab
import yaml
import siada
from siada import __version__
from siada.io.io import InputOutput



def _load_agent_config() -> Dict[str, Dict]:
    """
    Load Agent configuration from configuration file

    Returns:
        Dict[str, Dict]: Agent configuration dictionary
    """
    # Get the configuration file path in the project root directory
    current_dir = Path(__file__).parent.parent.parent.parent  # Go back to project root directory
    config_path = current_dir / "agent_config.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"Agent configuration file not found: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    return config.get('agents', {})

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
        agent_configs = _load_agent_config()
        # Get enabled agent types for choices
        agent_choices = [name for name, config in agent_configs.items() 
                        if config.get('enabled', False) and config.get('class')]
    except Exception as e:
        # Fallback to default if config loading fails
        agent_configs = {}
        agent_choices = ['bugfix', 'coder', 'fegen', 'bugreproduce']
        print(f"Warning: Failed to load agent config, using defaults: {e}")
        # Add IO to print errors for sending ACP messages
        try:
            io = InputOutput.get_instance()
            if io:
                io.print_error(f"Warning: Failed to load agent config, using defaults: {e}")
        except:
            pass
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

    group.add_argument(
        "--resume",
        metavar="SESSION_ID",
        nargs='?',
        const='',
        default=None,
        help="Resume a previous session. Use --resume <session_id> to resume a specific session, "
             "or --resume alone to show the session browser (interactive mode) or resume the latest "
             "session (non-interactive mode).",
    )

    group.add_argument(
        "--resume-list",
        action="store_true",
        default=False,
        help="List all sessions for the current workspace and exit.",
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
        "--thinking",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable or disable thinking/reasoning for models that support it (default: enabled for models that support it)",
    )
    
    group.add_argument(
        "--parallel-tool-calls",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable or disable parallel tool calls for models that support it (default: enabled for models that support it)",
    )

    group.add_argument(
        "--provider",
        choices=["openrouter", "li", "default"],
        default=None,
        help="Specify the provider to use for the main chat (choices: openrouter, li, default: li)",
        metavar="PROVIDER",
    )

    group = parser.add_argument_group("Output settings")
    group.add_argument(
        "--theme",
        choices=["auto", "dark", "light"],
        default="auto",
        help="Select color theme: auto (auto-detect system theme), dark, or light (default: auto)",
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

    group.add_argument(
        "--banner",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable/disable welcome banner display (default: True)",
    )
    
    group.add_argument(
        "--acp",
        action="store_true",
        default=False,
        help="Enable ACP (Agent Client Protocol) mode for structured communication (default: False)",
    )

    group.add_argument(
        "--ui",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Launch terminal UI (TUI) interface (default: True). Use --no-ui to use classic Python REPL mode",
    )

    group = parser.add_argument_group("Authentication")
    group.add_argument(
        "--logout",
        action="store_true",
        help="Sign out and clear stored credentials",
        default=False,
    )
    group.add_argument(
        "--user-id",
        metavar="USER_ID",
        help="Set the user ID (domain account) and save to conf.yaml",
        default=None,
    )
    group.add_argument(
        "--access-token",
        metavar="ACCESS_TOKEN",
        help="Set the access token (siada_api_key) and save to conf.yaml",
        default=None,
    )

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
        help="Check for new siada-cli versions on launch",
        default=True,
    )
    group.add_argument(
        "--upgrade",
        "--update",
        action="store_true",
        help="Upgrade siada-cli to the latest version from PyPI",
        default=False,
    )

    group = parser.add_argument_group("Upgrading")
    group.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show the version number and exit",
    )
    #####
    group = parser.add_argument_group("Checkpointing settings")
    group.add_argument(
        "--checkpointing",
        action=argparse.BooleanOptionalAction,
        help="Enable checkpointing (default: False in interactive mode, not supported in non-interactive mode)",
        default=None
    )
    
    group.add_argument(
        "--max-checkpoint-files",
        type=int,
        metavar="MAX_FILES",
        help="Maximum number of checkpoint files to retain (default: 50)",
        default=None
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

    ##########
    group = parser.add_argument_group("A2A API Server mode")

    group.add_argument(
        "--api_server",
        action="store_true",
        help="Start A2A API server mode (alternative to interactive CLI)",
        default=False,
    )

    group.add_argument(
        "--a2a-port",
        type=int,
        metavar="PORT",
        help="A2A API server port (default: 8001)",
        default=8001,
    )

    group.add_argument(
        "--a2a-host",
        metavar="HOST",
        help="A2A API server host to bind (default: 0.0.0.0 for external access, use 127.0.0.1 for local only)",
        default="0.0.0.0",
    )

    group.add_argument(
        "--a2a-agents-dir",
        metavar="DIR",
        help="A2A agents directory path (default: auto-detected from siada package installation)",
        default=str(Path(siada.__file__).parent / "agent_hub" / "a2a" / "a2a_agents"),
    )

    group.add_argument(
        "--stop_api_server",
        action="store_true",
        help="Stop the running A2A API server",
        default=False,
    )

    ##########
    group = parser.add_argument_group("Proactive Daemon Management")

    group.add_argument(
        "--stop-daemon",
        action="store_true",
        help="Stop the proactive daemon process",
        default=False,
    )

    group.add_argument(
        "--daemon-status",
        action="store_true",
        help="Show proactive daemon status",
        default=False,
    )

    group.add_argument(
        "--task-list",
        action="store_true",
        help="Show discovered pending tasks from proactive agent",
        default=False,
    )

    return parser


class SiadaArgs:
    """Typed, default-safe accessor for parsed CLI arguments.

    Wraps the raw ``argparse.Namespace`` so that callers never need
    ``hasattr(args, ...)`` or ``getattr(args, ..., default)`` guards.
    Any attribute not explicitly declared here falls through to the
    underlying namespace via ``__getattr__``.
    """

    def __init__(self, namespace) -> None:
        # Store without triggering __setattr__ recursion
        object.__setattr__(self, '_ns', namespace)

    def _get(self, name: str, default=None):
        return getattr(self._ns, name, default)

    def __getattr__(self, name: str):
        """Fall through to the namespace for any undeclared attribute."""
        return getattr(self._ns, name)

    def __setattr__(self, name: str, value) -> None:
        if name == '_ns':
            object.__setattr__(self, name, value)
        else:
            setattr(self._ns, name, value)

    # Agent
    @property
    def agent(self) -> str:
        return self._get('agent', 'coder')

    # Prompt / session mode
    @property
    def prompt(self):
        return self._get('prompt', None)

    @property
    def resume(self):
        return self._get('resume', None)

    @property
    def resume_list(self) -> bool:
        return self._get('resume_list', False)

    # ACP
    @property
    def acp(self) -> bool:
        return self._get('acp', False) or False

    # UI
    @property
    def ui(self) -> bool:
        return self._get('ui', True)

    # Model / provider
    @property
    def model(self):
        return self._get('model', None)

    @property
    def provider(self):
        return self._get('provider', None)

    @property
    def reasoning_effort(self):
        return self._get('reasoning_effort', None)

    @property
    def thinking(self):
        return self._get('thinking', None)

    @property
    def thinking_tokens(self):
        return self._get('thinking_tokens', None)

    @property
    def parallel_tool_calls(self):
        return self._get('parallel_tool_calls', None)

    # Output / display
    @property
    def pretty(self) -> bool:
        return self._get('pretty', True)

    @pretty.setter
    def pretty(self, value: bool) -> None:
        self._ns.pretty = value

    @property
    def theme(self) -> str:
        return self._get('theme', 'auto')

    @property
    def fancy_input(self) -> bool:
        return self._get('fancy_input', True)

    @property
    def banner(self) -> bool:
        return self._get('banner', True)

    @property
    def line_endings(self) -> str:
        return self._get('line_endings', 'platform')

    @property
    def verbose(self) -> bool:
        return self._get('verbose', False)

    @property
    def encoding(self) -> str:
        return self._get('encoding', 'utf-8')

    @property
    def editor(self):
        return self._get('editor', None)

    @property
    def vim(self) -> bool:
        return self._get('vim', False)

    @property
    def disable_console_output(self) -> bool:
        return self._get('disable_console_output', True)

    # Environment
    @property
    def env_file(self):
        return self._get('env_file', None)

    @property
    def set_env(self) -> list:
        return self._get('set_env', [])

    # Updates
    @property
    def check_update(self) -> bool:
        return self._get('check_update', True)

    @property
    def just_check_update(self) -> bool:
        return self._get('just_check_update', False)

    @property
    def upgrade(self) -> bool:
        return self._get('upgrade', False)

    # Authentication
    @property
    def logout(self) -> bool:
        return self._get('logout', False)

    @property
    def user_id(self):
        return self._get('user_id', None)

    @property
    def access_token(self):
        return self._get('access_token', None)

    # Checkpointing
    @property
    def checkpointing(self):
        return self._get('checkpointing', None)

    @property
    def max_checkpoint_files(self):
        return self._get('max_checkpoint_files', None)


    @property
    def list_models(self) -> bool:
        return self._get('list_models', False)

    # A2A server
    @property
    def api_server(self) -> bool:
        return self._get('api_server', False)

    @property
    def stop_api_server(self) -> bool:
        return self._get('stop_api_server', False)

    # Proactive daemon
    @property
    def stop_daemon(self) -> bool:
        return self._get('stop_daemon', False)

    @property
    def daemon_status(self) -> bool:
        return self._get('daemon_status', False)

    @property
    def task_list(self) -> bool:
        return self._get('task_list', False)
