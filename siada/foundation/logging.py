import os
import logging
import tempfile
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from typing import Literal, Mapping, Optional
from termcolor import colored


def get_log_directory():
    """
    Get log directory with the following priority:
    - Development mode: Project root ./logs (detected by pyproject.toml)
    - 1. Environment variable SIADAHUB_LOG_DIR
    - 2. User home directory ~/.siada-cli/logs
    - 3. XDG cache directory ~/.cache/siada-cli/logs  
    - 4. System temp directory /tmp/siada-cli/logs
    - 5. Current working directory ./logs (fallback)
    """
    # Check if in development mode first
    if _is_development_mode():
        dev_log_dir = _get_development_log_dir()
        if dev_log_dir and _ensure_log_dir(Path(dev_log_dir)):
            return dev_log_dir
    
    # 1. Check environment variable
    if env_log_dir := os.getenv('SIADAHUB_LOG_DIR'):
        log_dir = Path(env_log_dir)
        if _ensure_log_dir(log_dir):
            return str(log_dir)
    
    # 2. User home directory ~/.siada-cli/logs
    home_log_dir = Path.home() / '.siada-cli' / 'logs'
    if _ensure_log_dir(home_log_dir):
        return str(home_log_dir)
    
    # 3. XDG cache directory ~/.cache/siada-cli/logs
    cache_dir = os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))
    xdg_log_dir = Path(cache_dir) / 'siada-cli' / 'logs'
    if _ensure_log_dir(xdg_log_dir):
        return str(xdg_log_dir)
    
    # 4. System temp directory
    temp_log_dir = Path(tempfile.gettempdir()) / 'siada-cli' / 'logs'
    if _ensure_log_dir(temp_log_dir):
        return str(temp_log_dir)
    
    # 5. Fallback: current directory
    fallback_log_dir = Path('./logs')
    _ensure_log_dir(fallback_log_dir)
    return str(fallback_log_dir)


def _is_development_mode():
    """
    Detect if running in development mode by checking environment variables:
    - SIADAHUB_ENV=development
    - SIADA_ENV=dev/development
    - DEVELOPMENT=true/1/yes
    """
    # Check specific environment variables
    env_vars = [
        ('SIADAHUB_ENV', ['development', 'dev']),
        ('SIADA_ENV', ['development', 'dev']),
        ('DEVELOPMENT', ['true', '1', 'yes']),
    ]
    
    for env_var, valid_values in env_vars:
        env_value = os.getenv(env_var, '').lower()
        if env_value in valid_values:
            return True
    
    return False


def _get_development_log_dir():
    """Get development mode log directory - try current working directory first"""
    try:
        # Try current working directory first (for project root)
        current_dir = Path.cwd()
        if (current_dir / 'pyproject.toml').exists():
            return str(current_dir / 'logs')
        
        # Fallback: use module location to find project root
        module_file = Path(__file__).resolve()
        project_root = module_file.parent.parent.parent
        if (project_root / 'pyproject.toml').exists():
            return str(project_root / 'logs')
            
    except Exception:
        pass
    
    return None


def _ensure_log_dir(log_dir: Path) -> bool:
    """Ensure log directory exists and is writable, return success status"""
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        # Test write permissions
        test_file = log_dir / '.write_test'
        test_file.touch()
        test_file.unlink()
        return True
    except (PermissionError, OSError):
        return False


# Get log directory and file path
log_dir = get_log_directory()
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
        
        # Handle event source prefix
        if event_source and msg_type:
            msg_type = f'{event_source.upper()}_{msg_type}'
            
        if msg_type:
            msg = record.msg
            time_str = self.formatTime(record, self.datefmt)
            name_str = record.name
            level_str = record.levelname
            
            # Handle error or debug info with more details
            if msg_type == 'ERROR' or DEBUG:
                return f'{time_str} - {name_str}:{level_str}: {record.filename}:{record.lineno}\n{msg_type}\n{msg}'
            
            # Normal message
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


def configure_third_party_loggers():
    """
    Configure third-party library log levels to reduce verbose log output
    """
    # Set httpx log level to ERROR to avoid excessive network request logs
    logging.getLogger('httpx').setLevel(logging.ERROR)
    
    # Add other third-party library log configurations as needed
    # logging.getLogger('urllib3').setLevel(logging.WARNING)
    # logging.getLogger('requests').setLevel(logging.WARNING)


def setup_logger():
    """
    Setup and return siada.api logger
    """
    # Create logger
    setup_logger = logging.getLogger('siada.api')
    setup_logger.setLevel(logging.INFO)

    # If logger already has handlers, don't add duplicates
    if setup_logger.handlers:
        return setup_logger

    # Create console handler
    console_handler = get_console_handler()
    # Create file handler - rotate daily, keep 30 days of logs
    file_handler = get_file_handler()

    # Add handlers to logger
    setup_logger.addHandler(console_handler)
    setup_logger.addHandler(file_handler)
    setup_logger.propagate = False

    # Configure third-party library log levels
    configure_third_party_loggers()

    return setup_logger



def remove_console_handler(target_logger=None):
    """
    Remove console handler from logger, keeping only file handler
    
    Args:
        target_logger: Logger instance to modify. If None, uses the global logger.
    """
    if target_logger is None:
        target_logger = logging.getLogger('siada.api')
    
    # Find and remove console handlers
    handlers_to_remove = []
    for handler in target_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, TimedRotatingFileHandler):
            handlers_to_remove.append(handler)
    
    for handler in handlers_to_remove:
        target_logger.removeHandler(handler)
        handler.close()


def add_console_handler(target_logger=None, log_level=logging.INFO):
    """
    Add console handler back to logger
    
    Args:
        target_logger: Logger instance to modify. If None, uses the global logger.
        log_level: Log level for console handler
    """
    if target_logger is None:
        target_logger = logging.getLogger('siada.api')
    
    # Check if console handler already exists
    has_console_handler = any(
        isinstance(handler, logging.StreamHandler) and not isinstance(handler, TimedRotatingFileHandler)
        for handler in target_logger.handlers
    )
    
    if not has_console_handler:
        console_handler = get_console_handler(log_level)
        target_logger.addHandler(console_handler)


def toggle_console_output(enable: bool = True, target_logger=None):
    """
    Toggle console output on/off
    
    Args:
        enable: True to enable console output, False to disable
        target_logger: Logger instance to modify. If None, uses the global logger.
    """
    if enable:
        add_console_handler(target_logger)
    else:
        remove_console_handler(target_logger)


# Global accessible logger instance
logger = setup_logger()
