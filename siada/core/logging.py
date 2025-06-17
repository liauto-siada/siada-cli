import os
import logging
from logging.handlers import TimedRotatingFileHandler
from typing import Literal, Mapping, Optional
from termcolor import colored
# 确保日志目录存在
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
os.makedirs(log_dir, exist_ok=True)

# 日志文件路径
log_file = os.path.join(log_dir, 'siada_api.log')


DEBUG = os.getenv('DEBUG', 'False').lower() in ['true', '1', 'yes']
if DEBUG:
    LOG_LEVEL = 'DEBUG'

ColorType = Literal[
    'red',
    'green',
    'yellow',
    'blue',
    'magenta',
    'cyan',
    'light_grey',
    'dark_grey',
    'light_red',
    'light_green',
    'light_yellow',
    'light_blue',
    'light_magenta',
    'light_cyan',
    'white',
]

LOG_COLORS: Mapping[str, ColorType] = {
    'ACTION': 'green',
    'USER_ACTION': 'light_yellow',
    'OBSERVATION': 'yellow',
    'USER_OBSERVATION': 'light_green',
    'DETAIL': 'cyan',
    'ERROR': 'red',
    'PLAN': 'light_magenta',
    'OUTPUT': 'light_blue',
    'MESSAGE': 'green',
}


def format_log_line(time_str, msg_type, msg, use_color=False):
    separator = "*************" * 2
    if use_color:
        separator = colored(separator, 'blue', force_color=True)
    return f"\n{separator}\n{time_str} - {msg_type}\n{msg}"


class ColoredFormatter(logging.Formatter):
    def format(self, record):
        msg_type = record.__dict__.get('msg_type')
        event_source = record.__dict__.get('event_source')
        if event_source:
            new_msg_type = f'{event_source.upper()}_{msg_type}'
            if new_msg_type in LOG_COLORS:
                msg_type = new_msg_type
        if msg_type in LOG_COLORS:
            msg_type_color = colored(msg_type, LOG_COLORS[msg_type], force_color=True)
            msg = colored(record.msg, LOG_COLORS[msg_type], force_color=True)
            time_str = colored(
                self.formatTime(record, self.datefmt), LOG_COLORS[msg_type], force_color=True
            )
            name_str = colored(record.name, LOG_COLORS[msg_type], force_color=True)
            level_str = colored(record.levelname, LOG_COLORS[msg_type], force_color=True)
            if msg_type in ['ERROR'] or DEBUG:
                return f'{time_str} - {name_str}:{level_str}: {record.filename}:{record.lineno}\n{msg_type_color}\n{msg}'
            return format_log_line(time_str, msg_type_color, msg, use_color=True)
        elif msg_type == 'STEP':
            msg = '\n\n==============\n' + record.msg + '\n'
            return f'{msg}'
        return super().format(record)


class FileFormatter(logging.Formatter):
    def format(self, record):
        msg_type = record.__dict__.get('msg_type')
        event_source = record.__dict__.get('event_source')
        
        # 处理事件源前缀
        if event_source and msg_type:
            msg_type = f'{event_source.upper()}_{msg_type}'
            
        if msg_type:
            msg = record.msg
            time_str = self.formatTime(record, self.datefmt)
            name_str = record.name
            level_str = record.levelname
            
            # 处理错误或调试信息，包含更多细节
            if msg_type == 'ERROR' or DEBUG:
                return f'{time_str} - {name_str}:{level_str}: {record.filename}:{record.lineno}\n{msg_type}\n{msg}'
            
            # 普通消息
            return format_log_line(time_str, msg_type, msg)
            
        elif msg_type == 'STEP':
            msg = '\n\n==============\n' + record.msg + '\n'
            return f'{msg}'
            
        return super().format(record)


file_formatter = logging.Formatter(
    '%(asctime)s - %(name)s:%(levelname)s: %(filename)s:%(lineno)s - %(message)s',
    datefmt='%H:%M:%S',
)
llm_formatter = logging.Formatter('%(message)s')


def get_file_handler():
    file_handler = TimedRotatingFileHandler(
        log_file,
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    formatter_str = '%(asctime)s - %(name)s:%(levelname)s: %(filename)s:%(lineno)s - %(message)s'
    file_handler.setFormatter(FileFormatter(formatter_str, datefmt='%H:%M:%S'))
    return file_handler


def get_console_handler(log_level=logging.INFO, extra_info: Optional[str] = None):
    """Returns a console handler for logging."""
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    formatter_str = '\033[92m%(asctime)s - %(name)s:%(levelname)s\033[0m: %(filename)s:%(lineno)s - %(message)s'
    if extra_info:
        formatter_str = f'{extra_info} - ' + formatter_str
    console_handler.setFormatter(ColoredFormatter(formatter_str, datefmt='%H:%M:%S'))
    return console_handler


def setup_logger():
    """
    设置并返回siada.api的logger
    """
    # 创建logger
    setup_logger = logging.getLogger('siada.api')
    setup_logger.setLevel(logging.INFO)

    # 如果logger已经有处理器，不要重复添加
    if setup_logger.handlers:
        return setup_logger

    # 创建控制台处理器
    console_handler = get_console_handler()
    # 创建文件处理器 - 每天轮转一次，保留30天的日志
    file_handler = get_file_handler()

    # 添加处理器到logger
    setup_logger.addHandler(console_handler)
    setup_logger.addHandler(file_handler)
    setup_logger.propagate = False

    return setup_logger


# 全局可访问的logger实例
logger = setup_logger()
