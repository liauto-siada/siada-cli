import logging
import os
from typing import Optional

import siada
from siada.foundation.logging import ColoredFormatter

_INITIAL_CWD = os.path.dirname(os.path.dirname(siada.__file__))
_INITIAL_LOG_DIRS = {}


def reset_logger_for_multiprocessing(
        logger: logging.Logger, instance_id: str, log_dir: str
):
    """Reset the logger for multiprocessing.

    Save logs to both console and a separate file for each process.
    """
    logger.setLevel(logger.level)
    abs_log_dir = _get_initial_log_path(log_dir)
    # Set up logger
    log_file = os.path.join(
        abs_log_dir,
        f'instance_{instance_id}.log',
    )
    # Remove all existing handlers from logger
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        if isinstance(handler, logging.FileHandler):
            handler.close()

    # add console handler with colored output
    console_handler = get_console_handler(log_level=logging.INFO)
    # Don't set formatter for console handler to keep the colored output
    # Just prepend instance_id to the message
    original_format = console_handler.formatter._fmt
    console_handler.formatter._fmt = f'Instance {instance_id} - ' + original_format
    logger.addHandler(console_handler)

    logger.info(
        f'Starting evaluation for instance {instance_id}.\n'
        f'Hint: run "tail -f {log_file}" to see live logs in a separate shell'
    )

    # Log INFO and above to file with standard formatting
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    )
    file_handler.setLevel(logging.INFO)
    logger.addHandler(file_handler)


def _get_initial_log_path(log_dir: str) -> str:
    """获取日志目录的初始绝对路径。
    如果是第一次访问该目录，则保存其绝对路径；否则返回已保存的路径。
    """
    if log_dir not in _INITIAL_LOG_DIRS:
        # 第一次访问该目录，计算并保存绝对路径
        if os.path.isabs(log_dir):
            abs_path = log_dir
        else:
            # 相对路径基于初始工作目录计算
            abs_path = os.path.join(_INITIAL_CWD, log_dir)
        _INITIAL_LOG_DIRS[log_dir] = os.path.normpath(abs_path)

    return _INITIAL_LOG_DIRS[log_dir]


def get_console_handler(log_level=logging.INFO, extra_info: Optional[str] = None):
    """Returns a console handler for logging."""
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    formatter_str = '\033[92m%(asctime)s - %(name)s:%(levelname)s\033[0m: %(filename)s:%(lineno)s - %(message)s'
    if extra_info:
        formatter_str = f'{extra_info} - ' + formatter_str
    console_handler.setFormatter(ColoredFormatter(formatter_str, datefmt='%H:%M:%S'))
    return console_handler
