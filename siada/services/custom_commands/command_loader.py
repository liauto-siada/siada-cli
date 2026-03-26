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
        
        for dir_path, is_project in command_dirs:
            if not os.path.exists(dir_path):
                continue
            
            try:
                commands = self._load_from_directory(dir_path, is_project)
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
    
    def _get_command_directories(self) -> List[tuple[str, bool]]:
        """
        Get list of command directories to scan.
        
        Returns:
            List of (directory_path, is_project_specific) tuples
        """
        directories = []
        
        # User global commands: ~/.siada-cli/commands/
        user_commands_dir = str(SIADA_HOME / "commands")
        directories.append((user_commands_dir, False))
        
        # Project local commands: <project>/.siada-cli/commands/
        if self.workspace:
            project_commands_dir = os.path.join(self.workspace, ".siada-cli", "commands")
            directories.append((project_commands_dir, True))
        
        return directories
    
    def _load_from_directory(
        self,
        directory: str,
        is_project: bool
    ) -> List[CustomCommand]:
        """
        Load all TOML command files from a directory.
        
        Args:
            directory: Directory path to scan
            is_project: Whether this is project-specific directory
            
        Returns:
            List of loaded commands
        """
        commands: List[CustomCommand] = []
        
        # Find all .toml files recursively
        pattern = os.path.join(directory, "**", "*.toml")
        toml_files = glob_module.glob(pattern, recursive=True)
        
        for file_path in toml_files:
            try:
                command = self._parse_command_file(file_path, directory)
                if command:
                    commands.append(command)
            except Exception as e:
                if self.verbose:
                    print(f"Error parsing {file_path}: {e}")
                    # Add IO to print errors for sending ACP messages
                    try:
                        from siada.io.io import InputOutput
                        io = InputOutput.get_instance()
                        if io:
                            io.print_error(f"Error parsing {file_path}: {e}")
                    except:
                        pass
        return commands
    
    def _parse_command_file(
        self,
        file_path: str,
        base_dir: str
    ) -> Optional[CustomCommand]:
        """
        Parse a single TOML command file.
        
        Args:
            file_path: Path to TOML file
            base_dir: Base directory for computing relative path
            
        Returns:
            CustomCommand object or None if invalid
        """
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
        # Remove .toml extension
        name = rel_path.replace('.toml', '')
        
        # Replace path separators with colons
        name = name.replace(os.sep, ':')
        
        # Replace colons in segments with underscores (avoid ambiguity)
        segments = name.split(':')
        segments = [seg.replace(':', '_') for seg in segments]
        
        return ':'.join(segments)
