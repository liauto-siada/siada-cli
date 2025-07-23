"""
工具函数模块

提供项目中通用的工具函数
"""
import json
import traceback
from inspect import stack
from textwrap import indent
from typing import Any, Dict, Union, List

from siada.foundation.logging import logger


class JsonUtils:
    """JSON相关工具类"""
    
    @staticmethod
    def format_json(json_data: Union[str, Dict[str, Any]]) -> str:
        """
        美化JSON数据
        
        Args:
            json_data: JSON字符串或字典对象
            
        Returns:
            格式化后的JSON字符串
        """
        try:
            # 如果是字符串，先解析为对象
            if isinstance(json_data, str):
                data_obj = json.loads(json_data)
            else:
                data_obj = json_data
                
            # 格式化输出
            return json.dumps(data_obj, indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            # 解析失败则返回原始内容
            return str(json_data) 


class SSEUtils:
    """Server-Sent Events (SSE)相关工具类"""
    
    @staticmethod
    async def format_sse(data):
        """
        将数据格式化为SSE格式
        
        Args:
            data: 要格式化的数据
            
        Returns:
            SSE格式的数据
        """
        if isinstance(data, dict):
            event = data.get("event", "message")
            # json.dumps已经会将换行符转为\n转义序列
            json_data = json.dumps(data.get("data", {}), ensure_ascii=False)
            return f"event: {event}\ndata: {json_data}\n\n"
        
        json_str = json.dumps(data, ensure_ascii=False)
        return f"data: {json_str}\n\n" 


class AgentLogger:
    """Agent日志格式化助手类"""
    
    @staticmethod
    def format_start(agent_name: str) -> str:
        """格式化Agent启动日志"""
        return f"Agent {agent_name} start running"
    
    @staticmethod
    def format_finished(agent_name: str) -> str:
        """格式化Agent完成日志"""
        return f"Agent {agent_name} finished"
    
    @staticmethod
    def format_tool_call(tool_name: str, tool_args: Any) -> str:
        """格式化工具调用日志"""
        formatted_args = JsonUtils.format_json(tool_args)
        return f"**Tool Call**\nToolName:{tool_name}\nArguments: {formatted_args}"
    
    @staticmethod
    def format_tool_output(output: str) -> str:
        """格式化工具输出日志"""
        return f"**Tool Call Output**\n{output}"
    
    @staticmethod
    def format_action(thought: str, action: str) -> str:
        """格式化行动日志"""
        if thought:
            return f"**Thought**\n{thought} \n{action}"
        return action
    
    @staticmethod
    def format_final_output(output: str) -> str:
        """格式化最终输出日志"""
        return f"{output}"
    
    @staticmethod
    def log_user_input(input_text: str) -> None:
        """记录用户输入"""
        logger.info(input_text, extra={'msg_type': 'USER_ACTION'})
    
    @staticmethod
    def log_tool_output(output: str) -> None:
        """记录工具输出"""
        logger.info(output, extra={'msg_type': 'OBSERVATION'})
    
    @staticmethod
    def log_action(message: str) -> None:
        """记录行动"""
        logger.info(message, extra={'msg_type': 'ACTION'})
    
    @staticmethod
    def log_final_output(message: str) -> None:
        """记录最终输出"""
        logger.info(message.lstrip(), extra={"msg_type": "OUTPUT"})
    
    @staticmethod
    def format_observation(thought: str) -> str:
        """格式化观察日志"""
        return f"**Observation**\n{thought}"
    
    @staticmethod
    def format_msg_action(thought: str) -> str:
        """格式化观察日志"""
        return f"**Message**\n{thought}"
    
    @staticmethod
    def log_observation(message: str) -> None:
        """记录观察内容"""
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