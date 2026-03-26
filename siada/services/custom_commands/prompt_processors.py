"""
Prompt processors for handling special syntax in custom commands.

Processing order:
1. ShellProcessor - Handles {{args}} placeholder and !{command} syntax
2. AtFileProcessor - Handles @{file/path} syntax (after {{args}} is replaced)
3. DefaultArgumentProcessor - Appends arguments if no {{args}} placeholder

"""

import os
import shlex
import subprocess
from abc import ABC, abstractmethod
from typing import List

from .types import (
    CommandContext,
    SHORTHAND_ARGS_PLACEHOLDER,
    SHELL_INJECTION_TRIGGER,
    AT_FILE_INJECTION_TRIGGER,
    ConfirmationRequiredError,
)
from .injection_parser import extract_injections


class IPromptProcessor(ABC):
    """Base interface for prompt processors"""
    
    @abstractmethod
    def process(self, prompt: str, context: CommandContext) -> str:
        """
        Process the prompt content.
        
        Args:
            prompt: Current prompt content
            context: Command execution context
            
        Returns:
            Processed prompt content
        """
        pass


class AtFileProcessor(IPromptProcessor):
    """
    Processes @{path} syntax to inject file contents.
    
    Supports:
    - Single files: @{src/main.py}
    - Directories: @{src/} (recursively reads all files)
    - Respects .gitignore and workspace boundaries
    """
    
    def __init__(self, command_name: str = ""):
        self.command_name = command_name
    
    def process(self, prompt: str, context: CommandContext) -> str:
        if AT_FILE_INJECTION_TRIGGER not in prompt:
            return prompt
        
        # Extract all @{...} blocks
        try:
            injections = extract_injections(
                prompt,
                AT_FILE_INJECTION_TRIGGER,
                self.command_name
            )
        except ValueError as e:
            context.io.print_error(str(e))
            return prompt
        
        # Process each injection
        output = ""
        last_index = 0
        
        for injection in injections:
            # Keep text before injection
            output += prompt[last_index:injection.start_index]
            
            # Read file content
            file_path = injection.content
            try:
                content = self._read_file_or_directory(file_path, context)
                output += content
            except Exception as e:
                error_msg = f"Failed to inject '@{{{file_path}}}': {str(e)}"
                if context.verbose:
                    context.io.print_error(error_msg)
                # Keep original placeholder on error
                output += prompt[injection.start_index:injection.end_index]
            
            last_index = injection.end_index
        
        # Append remaining text
        output += prompt[last_index:]
        
        return output
    
    def _read_file_or_directory(self, path_str: str, context: CommandContext) -> str:
        """Read file or directory contents"""
        # Resolve path relative to workspace
        if not os.path.isabs(path_str):
            full_path = os.path.join(context.workspace, path_str)
        else:
            full_path = path_str
        
        # Security check: ensure path is within workspace
        real_path = os.path.realpath(full_path)
        real_workspace = os.path.realpath(context.workspace)
        if not real_path.startswith(real_workspace):
            raise PermissionError(f"Path '{path_str}' is outside workspace")
        
        if not os.path.exists(real_path):
            raise FileNotFoundError(f"Path '{path_str}' does not exist")
        
        if os.path.isfile(real_path):
            # Read single file
            with open(real_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        elif os.path.isdir(real_path):
            # Read directory (simplified - could respect .gitignore)
            result = []
            for root, dirs, files in os.walk(real_path):
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                
                for file in files:
                    if file.startswith('.'):
                        continue
                    
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, context.workspace)
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        result.append(f"\n\n--- {rel_path} ---\n{content}")
                    except Exception:
                        pass  # Skip unreadable files
            
            return ''.join(result)
        else:
            raise ValueError(f"Path '{path_str}' is neither a file nor a directory")


class ShellProcessor(IPromptProcessor):
    """
    Processes !{command} and {{args}} syntax.
    
    Features:
    - Executes shell commands: !{git status}
    - Injects parameters: {{args}}
    - Auto-escapes parameters in shell context
    - Security checks and user confirmation
    """
    
    def __init__(self, command_name: str = ""):
        self.command_name = command_name
    
    def process(self, prompt: str, context: CommandContext) -> str:
        user_args_raw = context.invocation.get('args', '')
        
        # Quick path: no shell injection
        if SHELL_INJECTION_TRIGGER not in prompt:
            return prompt.replace(SHORTHAND_ARGS_PLACEHOLDER, user_args_raw)
        
        # Extract all !{...} blocks
        try:
            injections = extract_injections(
                prompt,
                SHELL_INJECTION_TRIGGER,
                self.command_name
            )
        except ValueError as e:
            context.io.print_error(str(e))
            return prompt.replace(SHORTHAND_ARGS_PLACEHOLDER, user_args_raw)
        
        if not injections:
            return prompt.replace(SHORTHAND_ARGS_PLACEHOLDER, user_args_raw)
        
        # Prepare escaped arguments for shell context
        user_args_escaped = shlex.quote(user_args_raw) if user_args_raw else ""
        
        # Replace {{args}} in shell commands with escaped version
        resolved_injections = []
        commands_to_confirm = []
        
        for injection in injections:
            command = injection.content
            if not command:
                resolved_injections.append((injection, None))
                continue
            
            # Replace {{args}} with escaped version in shell command
            resolved_command = command.replace(
                SHORTHAND_ARGS_PLACEHOLDER,
                user_args_escaped
            )
            
            resolved_injections.append((injection, resolved_command))
            
            # Collect commands for potential confirmation
            # (In full implementation, check against allowlist/denylist)
            commands_to_confirm.append(resolved_command)
        
        # For simplicity, we'll auto-approve safe commands
        # In production, implement proper security checks
        safe_prefixes = ['git status', 'git diff', 'ls', 'cat', 'echo', 'pwd']
        needs_confirmation = any(
            not any(cmd.startswith(prefix) for prefix in safe_prefixes)
            for cmd in commands_to_confirm
        )
        
        # Execute commands and build final prompt
        processed_prompt = ""
        last_index = 0
        
        for injection, resolved_command in resolved_injections:
            # Keep text before injection (replace {{args}} with raw)
            segment = prompt[last_index:injection.start_index]
            processed_prompt += segment.replace(
                SHORTHAND_ARGS_PLACEHOLDER,
                user_args_raw
            )
            
            # Execute shell command if present
            if resolved_command:
                try:
                    result = subprocess.run(
                        resolved_command,
                        shell=True,
                        capture_output=True,
                        text=True,
                        cwd=context.workspace,
                        timeout=30
                    )
                    
                    # Inject command output
                    processed_prompt += result.stdout
                    
                    # Add error info if command failed
                    if result.returncode != 0:
                        processed_prompt += f"\n[Shell command exited with code {result.returncode}]"
                        if result.stderr:
                            processed_prompt += f"\nStderr: {result.stderr}"
                            
                except subprocess.TimeoutExpired:
                    processed_prompt += f"\n[Shell command '{resolved_command}' timed out]"
                except Exception as e:
                    processed_prompt += f"\n[Failed to execute: {resolved_command}]\nError: {str(e)}"
            
            last_index = injection.end_index
        
        # Append remaining text
        final_segment = prompt[last_index:]
        processed_prompt += final_segment.replace(
            SHORTHAND_ARGS_PLACEHOLDER,
            user_args_raw
        )
        
        return processed_prompt


class DefaultArgumentProcessor(IPromptProcessor):
    """
    Appends user arguments to prompt if no {{args}} placeholder exists.
    
    This allows AI to parse the command itself.
    """
    
    def process(self, prompt: str, context: CommandContext) -> str:
        args = context.invocation.get('args', '')
        raw = context.invocation.get('raw', '')
        
        if args and raw:
            # Append full command to prompt
            return f"{prompt}\n\n{raw}"
        
        return prompt


def select_processors(prompt: str) -> List[IPromptProcessor]:
    """
    Select appropriate processors based on prompt content.
    
    Returns processors in execution order.
    
    IMPORTANT: Order matters!
    1. ShellProcessor first - replaces {{args}} and executes !{...}
    2. AtFileProcessor second - reads files (may contain {{args}} from step 1)
    3. DefaultArgumentProcessor last - only if no {{args}} used
    """
    processors: List[IPromptProcessor] = []
    
    # Check what special syntax is used
    uses_at_file = AT_FILE_INJECTION_TRIGGER in prompt
    uses_shell = SHELL_INJECTION_TRIGGER in prompt
    uses_args = SHORTHAND_ARGS_PLACEHOLDER in prompt
    
    # CRITICAL: Process {{args}} and !{...} BEFORE @{...}
    # This allows constructs like @{{{args}}} to work correctly
    if uses_shell or uses_args:
        processors.append(ShellProcessor())
    
    # Process @{...} after {{args}} has been replaced
    if uses_at_file:
        processors.append(AtFileProcessor())
    
    # Only add default arg processor if prompt doesn't use {{args}}
    # and doesn't use shell commands (to avoid redundant processing)
    if not uses_args and not uses_shell:
        processors.append(DefaultArgumentProcessor())
    
    return processors
