"""
Utility Functions Module

Provides common utility functions for the project
"""
import hashlib
import json
import os
import traceback
from inspect import stack
from pathlib import Path
from textwrap import indent
from typing import Any, Dict, Union, List

from siada.foundation.logging import logger


class JsonUtils:
    """JSON-related utility class"""

    @staticmethod
    def format_json(json_data: Union[str, Dict[str, Any]]) -> str:
        """
        Format JSON data for better readability
        
        Args:
            json_data: JSON string or dictionary object
            
        Returns:
            Formatted JSON string
        """
        try:
            # If it's a string, parse it to object first
            if isinstance(json_data, str):
                data_obj = json.loads(json_data)
            else:
                data_obj = json_data
            
            # Format output
            return json.dumps(data_obj, indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            # Return original content if parsing fails
            return str(json_data) 


class SSEUtils:
    """Server-Sent Events (SSE) utility class"""
    
    @staticmethod
    async def format_sse(data):
        """
        Format data into SSE format
        
        Args:
            data: Data to format
            
        Returns:
            Data in SSE format
        """
        if isinstance(data, dict):
            event = data.get("event", "message")
            # json.dumps will convert newlines to \n escape sequences
            json_data = json.dumps(data.get("data", {}), ensure_ascii=False)
            return f"event: {event}\ndata: {json_data}\n\n"
        
        json_str = json.dumps(data, ensure_ascii=False)
        return f"data: {json_str}\n\n" 


class AgentLogger:
    """Agent logging formatter helper class"""
    
    @staticmethod
    def format_start(agent_name: str) -> str:
        """Format agent start log"""
        return f"Agent {agent_name} start running"
    
    @staticmethod
    def format_finished(agent_name: str) -> str:
        """Format agent completion log"""
        return f"Agent {agent_name} finished"
    
    @staticmethod
    def format_tool_call(tool_name: str, tool_args: Any) -> str:
        """Format tool call log"""
        formatted_args = JsonUtils.format_json(tool_args)
        return f"**Tool Call**\nToolName:{tool_name}\nArguments: {formatted_args}"
    
    @staticmethod
    def format_tool_output(output: str) -> str:
        """Format tool output log"""
        return f"**Tool Call Output**\n{output}"
    
    @staticmethod
    def format_action(thought: str, action: str) -> str:
        """Format action log"""
        if thought:
            return f"**Thought**\n{thought} \n{action}"
        return action
    
    @staticmethod
    def format_final_output(output: str) -> str:
        """Format final output log"""
        return f"{output}"
    
    @staticmethod
    def log_user_input(input_text: str) -> None:
        """Log user input"""
        logger.info(input_text, extra={'msg_type': 'USER_ACTION'})
    
    @staticmethod
    def log_tool_output(output: str) -> None:
        """Log tool output"""
        logger.info(output, extra={'msg_type': 'OBSERVATION'})
    
    @staticmethod
    def log_action(message: str) -> None:
        """Log action"""
        logger.info(message, extra={'msg_type': 'ACTION'})
    
    @staticmethod
    def log_final_output(message: str) -> None:
        """Log final output"""
        logger.info(message.lstrip(), extra={"msg_type": "OUTPUT"})
    
    @staticmethod
    def format_observation(thought: str) -> str:
        """Format observation log"""
        return f"**Observation**\n{thought}"
    
    @staticmethod
    def format_msg_action(thought: str) -> str:
        """Format message action log"""
        return f"**Message**\n{thought}"
    
    @staticmethod
    def log_observation(message: str) -> None:
        """Log observation content"""
        logger.info(message, extra={'msg_type': 'MESSAGE'})


class DebugUtils:
    "Debug Utils"

    @staticmethod
    def _cvt(s: Any):
        if isinstance(s, str):
            return s
        try:
            return json.dumps(s, indent=4)
        except TypeError:
            return str(s)

    def dump(*args):
        stack = traceback.extract_stack()
        vars = stack[-2][-3]

        vars = "(".join(vars.split("(")[1:])
        vars = ")".join(vars.split(")")[:-1])

        args = [DebugUtils._cvt(v) for v in args]
        has_newline = sum(1 for v in vars if "\n" in v)
        if has_newline:
            print("%s:" % vars)
            print(",".join(args))
        else:
            print("%s:" % vars, ", ".join(args))


class ImageUtils:
    """Image Utils"""
    IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp", ".pdf"]

    @staticmethod
    def is_image_file(filename: str) -> bool:
        """Check if a file is an image file"""
        file_name = str(filename)  # Convert file_name to string
        return any(file_name.endswith(ext) for ext in ImageUtils.IMAGE_EXTENSIONS)


class SettingsUtils:

    @staticmethod
    def format_settings(parser, args):
        """Format settings"""
        show = parser.format_values()
        # clean up the headings for consistency w/ new lines
        heading_env = "Environment Variables:"
        heading_defaults = "Defaults:"
        if heading_env in show:
            show = show.replace(heading_env, "\n" + heading_env)
            show = show.replace(heading_defaults, "\n" + heading_defaults)
        show += "\n"
        show += "Option settings:\n"
        for arg, val in sorted(vars(args).items()):
            show += f"  - {arg}: {val}\n"  # noqa: E221
        return show


class DirectoryUtils:
    """Utility class for common directory operations."""

    @staticmethod
    def get_global_temp_dir() -> str:
        """Get global temp directory ~/.siada-cli/data/tmp
        
        Returns:
            Path to the global temp directory
        """
        siada_temp_dir = Path.home() / ".siada-cli" / "data" / "tmp"
        # Ensure directory exists
        siada_temp_dir.mkdir(parents=True, exist_ok=True)
        return str(siada_temp_dir)

    @staticmethod
    def get_global_sessions_dir(cwd: str) -> str:
        """Get sessions directory based on project context
        
        Args:
            cwd: Current working directory/project root (required)
            
        Returns:
            Path to the project-specific sessions directory
        """
        # Project-specific sessions directory
        project_temp_dir = DirectoryUtils.get_project_temp_dir(cwd)
        sessions_dir = Path(project_temp_dir) / "sessions"

        # Ensure directory exists
        sessions_dir.mkdir(parents=True, exist_ok=True)
        return str(sessions_dir)

    @staticmethod
    def get_file_path_hash(file_path: str) -> str:
        """Calculate SHA256 hash of file path
        
        Args:
            file_path: Path to hash
            
        Returns:
            SHA256 hash of the file path
        """
        return hashlib.sha256(file_path.encode('utf-8')).hexdigest()

    @staticmethod
    def get_project_temp_dir(project_root: str) -> str:
        """Get project-specific temp directory using project root path hash
        
        Args:
            project_root: Root directory of the project
            
        Returns:
            Path to the project-specific temp directory
        """
        hash_value = DirectoryUtils.get_file_path_hash(project_root)
        temp_dir = DirectoryUtils.get_global_temp_dir()
        project_temp_dir = os.path.join(temp_dir, hash_value)
        # Ensure directory exists
        Path(project_temp_dir).mkdir(parents=True, exist_ok=True)
        return project_temp_dir

    @staticmethod
    def get_project_checkpoint_dir(project_root: str) -> str:
        """Get project-specific checkpoint directory"""
        return os.path.join(DirectoryUtils.get_project_temp_dir(project_root), "checkpoints")

    @staticmethod
    def get_siada_config_dir() -> str:
        """Get siada configuration directory ~/.siada-cli
        
        Returns:
            Path to the siada configuration directory
        """
        config_dir = Path.home() / ".siada-cli"
        # Ensure directory exists
        config_dir.mkdir(parents=True, exist_ok=True)
        return str(config_dir)

    @staticmethod
    def get_siada_data_dir() -> str:
        """Get siada data directory ~/.siada-cli/data
        
        Returns:
            Path to the siada data directory
        """
        data_dir = Path.home() / ".siada-cli" / "data"
        # Ensure directory exists
        data_dir.mkdir(parents=True, exist_ok=True)
        return str(data_dir)
