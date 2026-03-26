"""
Command service for managing all custom commands.

Handles:
- Loading commands from multiple sources
- Conflict resolution
- Command lookup and execution
"""

from typing import List, Dict, Optional
from .types import CustomCommand


class CommandService:
    """
    Central service for managing all custom commands.
    
    Implements conflict resolution:
    - User/project commands use "last wins" strategy
    - Extension commands get renamed if conflicts exist
    """
    
    def __init__(self, commands: List[CustomCommand]):
        self.commands = self._resolve_conflicts(commands)
        self.command_map = {cmd.name: cmd for cmd in self.commands}
    
    @classmethod
    def create(cls, loaders: List) -> 'CommandService':
        """
        Create a CommandService from multiple loaders.
        
        Args:
            loaders: List of command loader objects
            
        Returns:
            CommandService instance
        """
        all_commands: List[CustomCommand] = []
        
        for loader in loaders:
            try:
                commands = loader.load_commands()
                all_commands.extend(commands)
            except Exception as e:
                # Log error but continue
                print(f"Error loading commands from {loader}: {e}")
                # Add IO to print errors for sending ACP messages
                try:
                    from siada.io.io import InputOutput
                    io = InputOutput.get_instance()
                    if io:
                        io.print_error(f"Error loading commands from {loader}: {e}")
                except:
                    pass
        return cls(all_commands)
    
    def _resolve_conflicts(
        self,
        commands: List[CustomCommand]
    ) -> List[CustomCommand]:
        """
        Resolve naming conflicts between commands.
        
        Strategy:
        - User/project commands (no extension_name): Last wins
        - Extension commands (has extension_name): Rename with prefix
        
        Args:
            commands: List of all loaded commands
            
        Returns:
            List of commands with resolved names
        """
        command_map: Dict[str, CustomCommand] = {}
        
        for cmd in commands:
            name = cmd.name
            
            # Check for conflict
            if name in command_map:
                existing = command_map[name]
                
                # If new command is from extension, rename it
                if cmd.extension_name:
                    # Try extension.name, then extension.name1, name2, etc.
                    new_name = f"{cmd.extension_name}.{name}"
                    suffix = 1
                    while new_name in command_map:
                        new_name = f"{cmd.extension_name}.{name}{suffix}"
                        suffix += 1
                    
                    # Update command with new name
                    cmd.name = new_name
                    name = new_name
                
                # If existing command is from extension and new is not, rename existing
                elif existing.extension_name:
                    # Remove existing, rename it, add back
                    del command_map[name]
                    
                    new_name = f"{existing.extension_name}.{name}"
                    suffix = 1
                    while new_name in command_map:
                        new_name = f"{existing.extension_name}.{name}{suffix}"
                        suffix += 1
                    
                    existing.name = new_name
                    command_map[new_name] = existing
                
                # Both are user/project commands: last wins (overwrite)
                # Just proceed to add the new one
            
            command_map[name] = cmd
        
        return list(command_map.values())
    
    def get_commands(self) -> List[CustomCommand]:
        """Get all available commands"""
        return self.commands
    
    def get_command(self, name: str) -> Optional[CustomCommand]:
        """
        Get command by name.
        
        Args:
            name: Command name (without leading slash)
            
        Returns:
            CustomCommand or None if not found
        """
        return self.command_map.get(name)
    
    def get_command_names(self) -> List[str]:
        """Get list of all command names"""
        return list(self.command_map.keys())
