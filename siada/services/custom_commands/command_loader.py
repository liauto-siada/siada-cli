"""
File-based command loader.

Loads custom commands from TOML files in:
1. User global commands: ~/.siada/commands/
2. Project local commands: <project>/.siada/commands/
"""

import os
import glob as glob_module
from pathlib import Path
from typing import List, Optional, Dict, Any

try:
    import tomli as toml  # Python < 3.11
except ImportError:
    import tomllib as toml  # Python >= 3.11

from .types import CustomCommand, CommandKind, CommandContext, CommandResult
from .prompt_processors import select_processors
from siada.foundation.constants import SIADA_HOME


class FileCommandLoader:
    """
    Loads custom commands from TOML files.
    """
    
    def __init__(self, workspace: str, verbose: bool = False):
        self.workspace = workspace
        self.verbose = verbose
    
    def load_commands(self) -> List[CustomCommand]:
        """
        Load all custom commands from file system.
        
        Returns:
            List of CustomCommand objects
        """
        all_commands: List[CustomCommand] = []
        
        # Get command directories
        command_dirs = self._get_command_directories()
        
        for dir_path, is_project, plugin_prefix in command_dirs:
            if not os.path.exists(dir_path):
                continue
            
            try:
                commands = self._load_from_directory(dir_path, is_project, plugin_prefix)
                all_commands.extend(commands)
            except Exception as e:
                if self.verbose:
                    print(f"Error loading commands from {dir_path}: {e}")
                    # Add IO to print errors for sending ACP messages
                    try:
                        from siada.io.io import InputOutput
                        io = InputOutput.get_instance()
                        if io:
                            io.print_error(f"Error loading commands from {dir_path}: {e}")
                    except:
                        pass
        return all_commands
    
    def _get_command_directories(self) -> List[tuple[str, bool, Optional[str]]]:
        """
        Get list of command directories to scan.

        Returns:
            List of (directory_path, is_project_specific, plugin_prefix) tuples.
            plugin_prefix is e.g. "hookify" for plugin commands, None otherwise.
        """
        directories: List[tuple[str, bool, Optional[str]]] = []

        # User global commands: ~/.siada-cli/commands/
        user_commands_dir = str(SIADA_HOME / "commands")
        directories.append((user_commands_dir, False, None))

        # Project local commands: <project>/.siada-cli/commands/
        if self.workspace:
            project_commands_dir = os.path.join(self.workspace, ".siada-cli", "commands")
            directories.append((project_commands_dir, True, None))

        # Plugin commands: ~/.siada-cli/plugins/{name}/commands/
        plugins_root = SIADA_HOME / "plugins"
        if plugins_root.exists():
            import json as _json
            try:
                cfg_path = SIADA_HOME / "plugin_config.json"
                disabled: set = set()
                if cfg_path.exists():
                    try:
                        disabled = set(_json.loads(cfg_path.read_text()).get("disabled_skills", []))
                    except Exception:
                        pass
                for plugin_dir in sorted(plugins_root.iterdir()):
                    if not plugin_dir.is_dir():
                        continue
                    manifest = plugin_dir / ".claude-plugin" / "plugin.json"
                    if not manifest.exists():
                        continue
                    plugin_name = plugin_dir.name
                    try:
                        plugin_name = _json.loads(manifest.read_text()).get("name", plugin_dir.name)
                    except Exception:
                        pass
                    if plugin_name in disabled:
                        continue
                    cmds_dir = plugin_dir / "commands"
                    if cmds_dir.is_dir():
                        directories.append((str(cmds_dir), False, plugin_name))
            except PermissionError:
                pass

        return directories
    
    def _load_from_directory(
        self,
        directory: str,
        is_project: bool,
        plugin_prefix: Optional[str] = None,
    ) -> List[CustomCommand]:
        """
        Load all TOML/MD command files from a directory.

        Args:
            directory: Directory path to scan
            is_project: Whether this is project-specific directory
            plugin_prefix: If set, prepend "{plugin_prefix}:" to command names

        Returns:
            List of loaded commands
        """
        commands: List[CustomCommand] = []

        # Find all .toml and .md files recursively
        file_paths: List[str] = []
        for ext in ("*.toml", "*.md"):
            file_paths.extend(glob_module.glob(os.path.join(directory, "**", ext), recursive=True))

        for file_path in file_paths:
            try:
                command = self._parse_command_file(file_path, directory, plugin_prefix)
                if command:
                    commands.append(command)
            except Exception as e:
                if self.verbose:
                    print(f"Error parsing {file_path}: {e}")
                    try:
                        from siada.io.io import InputOutput
                        io = InputOutput.get_instance()
                        if io:
                            io.print_error(f"Error parsing {file_path}: {e}")
                    except:
                        pass
        return commands
    
    @staticmethod
    def _parse_md_command(file_path: str) -> Dict[str, Any]:
        """Parse a Claude Code-style .md command file with YAML frontmatter.

        Format:
            ---
            description: ...
            allowed-tools: [...]
            ---
            # Body is the prompt template
        """
        import re
        text = Path(file_path).read_text(encoding="utf-8")
        data: Dict[str, Any] = {}
        body = text

        # Extract YAML frontmatter between --- delimiters
        fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
        if fm_match:
            try:
                import yaml  # type: ignore[import]
                fm = yaml.safe_load(fm_match.group(1)) or {}
            except Exception:
                # Manual parse: key: value lines
                fm = {}
                for line in fm_match.group(1).splitlines():
                    if ':' in line:
                        k, _, v = line.partition(':')
                        fm[k.strip()] = v.strip()
            data.update(fm)
            body = text[fm_match.end():]

        data['prompt'] = body.strip()
        return data

    def _parse_command_file(
        self,
        file_path: str,
        base_dir: str,
        plugin_prefix: Optional[str] = None,
    ) -> Optional[CustomCommand]:
        """
        Parse a single TOML or MD command file.

        Args:
            file_path: Path to .toml or .md file
            base_dir: Base directory for computing relative path
            plugin_prefix: If set, prepend "{plugin_prefix}:" to command name

        Returns:
            CustomCommand object or None if invalid
        """
        if file_path.endswith('.md'):
            data = self._parse_md_command(file_path)
        else:
            # Read and parse TOML
            with open(file_path, 'rb') as f:
                data = toml.load(f)

        # Validate required fields
        if 'prompt' not in data:
            if self.verbose:
                print(f"Missing 'prompt' field in {file_path}")
                # Add IO to print errors for sending ACP messages
                try:
                    from siada.io.io import InputOutput
                    io = InputOutput.get_instance()
                    if io:
                        io.print_error(f"Missing 'prompt' field in {file_path}")
                except:
                    pass
            return None
        
        if not isinstance(data['prompt'], str):
            if self.verbose:
                print(f"'prompt' field must be a string in {file_path}")
                # Add IO to print errors for sending ACP messages
                try:
                    from siada.io.io import InputOutput
                    io = InputOutput.get_instance()
                    if io:
                        io.print_error(f"'prompt' field must be a string in {file_path}")
                except:
                    pass
            return None
        
        # Compute command name from file path
        rel_path = os.path.relpath(file_path, base_dir)
        command_name = self._compute_command_name(rel_path)
        if plugin_prefix:
            command_name = f"{plugin_prefix}:{command_name}"
        
        # Create command action function
        prompt_template = data['prompt']
        processors = select_processors(prompt_template)
        
        def action(context: CommandContext, args: str) -> CommandResult:
            """Execute the command with given context and arguments"""
            # Set up invocation details
            context.invocation['args'] = args
            
            # Process prompt through processor pipeline
            processed_prompt = prompt_template
            for processor in processors:
                processed_prompt = processor.process(processed_prompt, context)
            
            # Return result for submission
            return CommandResult(
                type='submit_prompt',
                content=processed_prompt
            )
        
        # Create and return command
        return CustomCommand(
            name=command_name,
            description=data.get('description'),
            prompt=prompt_template,
            kind=CommandKind.FILE,
            action=action
        )
    
    def _compute_command_name(self, rel_path: str) -> str:
        """
        Compute command name from relative file path.
        
        Examples:
            test.toml → test
            git/commit.toml → git:commit
            review/code.toml → review:code
        
        Args:
            rel_path: Relative path from base directory
            
        Returns:
            Command name
        """
        # Remove file extension (.toml or .md)
        name = os.path.splitext(rel_path)[0]
        
        # Replace path separators with colons
        name = name.replace(os.sep, ':')
        
        # Replace colons in segments with underscores (avoid ambiguity)
        segments = name.split(':')
        segments = [seg.replace(':', '_') for seg in segments]
        
        return ':'.join(segments)
