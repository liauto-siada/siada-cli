import os
import sys
import logging
import tempfile
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from typing import Literal, Mapping, Optional
from termcolor import colored

from siada.foundation.constants import SIADA_HOME
from siada.foundation.log_category import LogCategory


def get_log_directory():
    """
    Get log directory with the following priority:
    - 1. Environment variable SIADA_CLI_LOG_DIR
    - 2. User home directory ~/.siada-cli/logs
    - 3. XDG cache directory ~/.cache/siada-cli/logs  
    - 4. System temp directory /tmp/siada-cli/logs
    - 5. Current working directory ./logs (fallback)
    """
    # 1. Check environment variable
    if env_log_dir := os.getenv('SIADA_CLI_LOG_DIR'):
        log_dir = Path(env_log_dir)
        if _ensure_log_dir(log_dir):
            return str(log_dir)
    
    # 2. User home directory ~/.siada-cli/logs
    home_log_dir = SIADA_HOME / 'logs'
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
log_file = os.path.join(log_dir, 'siada_cli.log')


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


class SafeTimedRotatingFileHandler(TimedRotatingFileHandler):
    """
    Windows-compatible TimedRotatingFileHandler that gracefully handles rotation errors.
    
    On Windows, when multiple processes have the same log file open, rotation can fail
    with PermissionError because Windows doesn't allow renaming files that are open
    by other processes. This handler catches such errors and continues logging to the
    current file instead of crashing.
    
    This is a common scenario when multiple siada-cli instances are running simultaneously.
    """
    
    def doRollover(self):
        """
        Override doRollover to handle Windows-specific file locking issues.
        
        When rotation fails due to PermissionError (file locked by another process),
        we silently continue using the current log file. For other errors, we log
        a warning but don't crash the application.
        """
        try:
            super().doRollover()
        except PermissionError:
            # File is locked by another process (common on Windows with multiple instances)
            # Continue using the current log file - rotation will be attempted again later
            print("Warning: siada-log locked by another process. Permission error.")
            pass
        except Exception as e:
            # Log other rotation errors to stderr but don't crash
            import sys
            print(f"Warning: Log rotation failed: {e}. Continuing with current log file.", 
                  file=sys.stderr)


def _create_concurrent_file_handler():
    """
    Create a ConcurrentRotatingFileHandler for Windows platform.
    
    This handler uses file locking mechanisms that work properly on Windows,
    avoiding the file rename issues that occur with standard rotating handlers
    when multiple processes access the same log file.
    
    Returns:
        ConcurrentRotatingFileHandler: Configured handler for Windows
        
    Raises:
        ImportError: If concurrent-log-handler package is not installed
    """
    from concurrent_log_handler import ConcurrentRotatingFileHandler
    
    file_handler = ConcurrentRotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB per file
        backupCount=30,
        encoding='utf-8',
        use_gzip=False  # Don't compress old logs
    )
    file_handler.setLevel(logging.INFO)
    formatter_str = '%(asctime)s - %(name)s:%(levelname)s: %(filename)s:%(lineno)s - %(message)s'
    file_handler.setFormatter(FileFormatter(formatter_str, datefmt='%H:%M:%S'))
    return file_handler


def _create_safe_timed_rotating_handler():
    """
    Create a SafeTimedRotatingFileHandler for non-Windows platforms or as fallback.
    
    This handler rotates logs based on time (daily at midnight) and gracefully
    handles rotation errors that may occur on Windows.
    
    Returns:
        SafeTimedRotatingFileHandler: Configured handler for time-based rotation
    """
    file_handler = SafeTimedRotatingFileHandler(
        log_file,
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8',
        delay=True  # Delay file opening until first log message
    )
    file_handler.setLevel(logging.INFO)
    formatter_str = '%(asctime)s - %(name)s:%(levelname)s: %(filename)s:%(lineno)s - %(message)s'
    file_handler.setFormatter(FileFormatter(formatter_str, datefmt='%H:%M:%S'))
    return file_handler


def get_named_file_handler(file_name: str, log_level: int = logging.INFO):
    """
    Create a rotating file handler for a specific file under the Siada log directory.

    Args:
        file_name: Target log file name, e.g. ``openai.log``.
        log_level: Logging level for the handler.

    Returns:
        logging.Handler: Configured file handler for the target file.
    """
    target_log_file = os.path.join(log_dir, file_name)
    file_handler = SafeTimedRotatingFileHandler(
        target_log_file,
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8',
        delay=True,
    )
    file_handler.setLevel(log_level)
    formatter_str = '%(asctime)s - %(name)s:%(levelname)s: %(filename)s:%(lineno)s - %(message)s'
    file_handler.setFormatter(FileFormatter(formatter_str, datefmt='%H:%M:%S'))
    return file_handler


def get_file_handler():
    """
    Create a file handler with platform-specific rotation handling.
    
    On Windows: Uses ConcurrentLogHandler to avoid file locking issues during rotation.
    On other platforms: Uses SafeTimedRotatingFileHandler for time-based rotation.
    
    Returns:
        logging.Handler: Configured file handler for logging
    """
    # Check if running on Windows
    is_windows = sys.platform.startswith('win')
    
    if is_windows:
        try:
            # Try to create ConcurrentRotatingFileHandler for Windows
            return _create_concurrent_file_handler()
            
        except ImportError:
            # Fallback to SafeTimedRotatingFileHandler if ConcurrentLogHandler is not installed
            import warnings
            warnings.warn(
                "ConcurrentLogHandler not found. Install it with: pip install concurrent-log-handler\n"
                "Falling back to SafeTimedRotatingFileHandler which may have file locking issues on Windows.",
                RuntimeWarning
            )
    
    # Use SafeTimedRotatingFileHandler for non-Windows or as fallback
    return _create_safe_timed_rotating_handler()


def get_console_handler(log_level=logging.INFO, extra_info: Optional[str] = None):
    """Returns a console handler for logging."""
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    formatter_str = '\033[92m%(asctime)s - %(name)s:%(levelname)s\033[0m: %(filename)s:%(lineno)s - %(message)s'
    if extra_info:
        formatter_str = f'{extra_info} - ' + formatter_str
    console_handler.setFormatter(ColoredFormatter(formatter_str, datefmt='%H:%M:%S'))
    return console_handler


def get_model_error_handler():
    """
    Create and configure a file handler specifically for model errors.
    
    Returns:
        TimedRotatingFileHandler: Handler configured to write model error logs
    """
    error_log_file = os.path.join(log_dir, 'errors.log')
    error_file_handler = TimedRotatingFileHandler(
        error_log_file,
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    error_file_handler.setLevel(logging.ERROR)
    error_formatter = logging.Formatter(
        '%(asctime)s - %(name)s:%(levelname)s\n%(message)s\n' + '='*80 + '\n',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    error_file_handler.setFormatter(error_formatter)
    return error_file_handler


class CategoryFilter(logging.Filter):
    """
    Filter logs based on log category.
    
    Supports two modes:
    - Include mode: only allow specified categories to pass
    - Exclude mode: exclude specified categories
    """
    
    def __init__(
        self,
        include_categories: list[LogCategory] | None = None,
        exclude_categories: list[LogCategory] | None = None
    ):
        super().__init__()
        self.include_categories = include_categories
        self.exclude_categories = exclude_categories
        
        if include_categories and exclude_categories:
            raise ValueError("Cannot specify both include and exclude categories")
    
    def filter(self, record):
        """Filter log records based on their log_category attribute."""
        category = getattr(record, 'log_category', LogCategory.GENERAL)
        
        if self.include_categories:
            return category in self.include_categories
        
        if self.exclude_categories:
            return category not in self.exclude_categories
        
        return True
    
    @classmethod
    def for_general_logs(cls):
        """Create a filter for general logs (excludes model errors)."""
        return cls(exclude_categories=[LogCategory.MODEL_ERROR])
    
    @classmethod
    def for_model_errors(cls):
        """Create a filter for model error logs only."""
        return cls(include_categories=[LogCategory.MODEL_ERROR])


def configure_third_party_loggers():
    """
    Configure third-party library log levels to reduce verbose log output
    """
    # Set httpx/httpcore log level to ERROR to avoid excessive network request logs
    logging.getLogger('httpx').setLevel(logging.ERROR)
    logging.getLogger('httpcore').setLevel(logging.ERROR)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
    logging.getLogger('LiteLLM').setLevel(logging.ERROR)
    # Suppress htmldate/trafilatura verbose debug logs (e.g. "minimum date setting: ...")
    logging.getLogger('htmldate').setLevel(logging.WARNING)
    logging.getLogger('trafilatura').setLevel(logging.WARNING)


def setup_logger():
    """
    Setup and return siada.api logger with category-based filtering.
    
    Also configures siada namespace logger to catch all siada.* submodules.
    
    This logger uses filters to route different log categories to different handlers:
    - General logs go to console and siada_cli.log
    - Model error logs go to model_errors.log
    """
    # Create logger
    logger_instance = logging.getLogger('siada.api')
    logger_instance.setLevel(logging.INFO)

    # If logger already has handlers, don't add duplicates
    if logger_instance.handlers:
        return logger_instance

    # 1. Console handler - only general logs
    console_handler = get_console_handler()
    console_handler.addFilter(CategoryFilter.for_general_logs())
    
    # 2. Main file handler - only general logs
    file_handler = get_file_handler()
    file_handler.addFilter(CategoryFilter.for_general_logs())
    
    # 3. Error file handler - all error level logs
    error_file_handler = get_model_error_handler()

    # Add handlers to siada.api logger
    logger_instance.addHandler(console_handler)
    logger_instance.addHandler(file_handler)
    logger_instance.addHandler(error_file_handler)
    logger_instance.propagate = False

    # Setup siada namespace logger - catches all siada.* submodules
    # This ensures modules like memory_agent can output to log files
    siada_logger = logging.getLogger("siada")
    siada_logger.setLevel(logging.INFO)
    if not siada_logger.handlers:
        # Create separate file handlers for siada namespace (without category filter)
        siada_file_handler = get_file_handler()
        siada_error_handler = get_model_error_handler()
        siada_logger.addHandler(siada_file_handler)
        siada_logger.addHandler(siada_error_handler)
        # Note: No console handler to avoid duplicate console output
    # propagate=True (default) is fine; root logger has no handlers

    # Configure third-party library log levels
    configure_third_party_loggers()

    return logger_instance



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

def redirect_agents_logger():
    """
    Process the agents logger to set appropriate log levels and handlers.
    """
    logger_names = ['openai.agents', 'openai.agents.tracing']
    target_level = logging.DEBUG
    file_handler = get_named_file_handler('openai.log', log_level=target_level)

    for logger_name in logger_names:
        target_logger = logging.getLogger(logger_name)
        target_logger.setLevel(target_level)
        target_logger.propagate = False

        has_openai_log_handler = any(
            getattr(handler, 'baseFilename', None) == getattr(file_handler, 'baseFilename', None)
            for handler in target_logger.handlers
        )
        if not has_openai_log_handler:
            target_logger.addHandler(file_handler)

    logging.getLogger('openai.agents').info(
        'OpenAI Agents logging redirected to %s',
        getattr(file_handler, 'baseFilename', 'openai.log'),
    )

def redirect_aiohttp_asyncio_logger():
    """
    Redirect aiohttp and asyncio loggers to file to suppress console warnings.
    This prevents unclosed resource warnings from cluttering the console output.
    """
    # Process aiohttp logger
    aiohttp_logger = logging.getLogger('aiohttp')
    aiohttp_logger.propagate = False
    
    if not aiohttp_logger.handlers:
        file_handler = get_file_handler()
        aiohttp_logger.addHandler(file_handler)
    
    # Process asyncio logger
    asyncio_logger = logging.getLogger('asyncio')
    asyncio_logger.propagate = False
    
    if not asyncio_logger.handlers:
        file_handler = get_file_handler()
        asyncio_logger.addHandler(file_handler)

def log_model_error(
    error_type: str,
    error_message: str,
    llm_request_body: Optional[dict] = None
) -> None:
    """
    Log detailed model error information
    
    Args:
        error_type: Type of error (e.g., 'API_ERROR', 'TIMEOUT', 'VALIDATION_ERROR')
        error_message: Main error message
        llm_request_body: Complete LLM request body (already includes UUID and all request parameters)
    """
    import json
    from datetime import datetime
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    
    # Build comprehensive error log
    log_parts = [
        f"[MODEL ERROR DETECTED]",
        f"Timestamp: {timestamp}",
        f"Error Type: {error_type}",
        f"Error Message: {error_message}",
    ]
    
    # Add complete LLM request body
    if llm_request_body:
        log_parts.append("\n--- Complete LLM Request Body ---")
        log_parts.append(json.dumps(llm_request_body, ensure_ascii=False, indent=2))
    
    # Join all parts and log with MODEL_ERROR category
    full_log = '\n'.join(log_parts)
    logger.error(full_log, extra={'log_category': LogCategory.MODEL_ERROR})


def cleanup_old_logs(log_pattern: str, keep_days: int = 30, log_directory: str = None) -> int:
    """
    清理超过指定天数的日志文件
    
    Args:
        log_pattern: 日志文件名模式，支持通配符，如 'a2a_log_*.log' 或 'a2a_server_*.log'
        keep_days: 保留的天数，默认 30 天
        log_directory: 日志目录路径，默认使用 get_log_directory()
        
    Returns:
        int: 删除的文件数量
        
    Example:
        # 清理 30 天前的 a2a_log 文件
        cleanup_old_logs('a2a_log_*.log', keep_days=30)
        
        # 清理 7 天前的 a2a_server 文件
        cleanup_old_logs('a2a_server_*.log', keep_days=7)
    """
    from datetime import datetime, timedelta
    
    if log_directory is None:
        log_directory = get_log_directory()
    
    log_dir = Path(log_directory)
    if not log_dir.exists():
        return 0
    
    # Calculate cutoff time
    cutoff_time = datetime.now() - timedelta(days=keep_days)
    cutoff_timestamp = cutoff_time.timestamp()
    
    deleted_count = 0
    
    try:
        # Find matching log files
        for log_file in log_dir.glob(log_pattern):
            if not log_file.is_file():
                continue
            
            try:
                # Get file modification time
                file_mtime = log_file.stat().st_mtime
                
                # If the file is older than the cutoff time, delete it
                if file_mtime < cutoff_timestamp:
                    log_file.unlink()
                    deleted_count += 1
                    logger.debug(f"Deleted old log file: {log_file.name}")
                    
            except (OSError, PermissionError) as e:
                # Silently handle single file deletion failure
                logger.debug(f"Failed to delete {log_file.name}: {e}")
                continue
                
    except Exception as e:
        # Silently handle overall cleanup failure
        logger.debug(f"Log cleanup failed for pattern '{log_pattern}': {e}")
    
    return deleted_count


class TimingLogger:
    """Logger wrapper that adds phase timing capability.

    Usage::

        logger.start_timing("main")
        # ... do work ...
        logger.log_timing("parse_args")   # logs phase time + total time
        # ... do more work ...
        logger.log_timing("init_io")
    """

    def __init__(self, base_logger: logging.Logger) -> None:
        self._logger = base_logger
        self._t_start: float | None = None
        self._t: float | None = None

    def start_timing(self, label: str = '') -> None:
        """Start a new timing session without emitting timing logs."""
        import time
        self._t_start = time.time()
        self._t = self._t_start

    def log_timing(self, phase: str) -> None:
        """Advance the phase timer without emitting timing logs."""
        import time
        if self._t_start is None or self._t is None:
            return
        self._t = time.time()

    def __getattr__(self, name: str):
        return getattr(self._logger, name)


def _get_im_file_handler():
    """
    Create a file handler for IM-related logs writing to im.log.

    Returns:
        SafeTimedRotatingFileHandler: Configured handler for IM logs
    """
    im_log_file = os.path.join(log_dir, 'im.log')
    im_file_handler = SafeTimedRotatingFileHandler(
        im_log_file,
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8',
        delay=True,
    )
    im_file_handler.setLevel(logging.DEBUG)
    formatter_str = '%(asctime)s - %(name)s:%(levelname)s: %(filename)s:%(lineno)s - %(message)s'
    im_file_handler.setFormatter(FileFormatter(formatter_str, datefmt='%H:%M:%S'))
    return im_file_handler


def setup_im_logger():
    """
    Setup IM-related loggers to write to im.log file.

    Redirects all siada.im.* loggers (via parent siada.im),
    and siada.io.lark to im.log.

    Also configures these loggers with error handler for errors.log.
    """
    # Logger names that should write to im.log
    logger_names = [
        'siada.im',               # parent for all siada.im.* loggers (including siada.im.lark.*)
        'siada.io.lark',
    ]

    for name in logger_names:
        lg = logging.getLogger(name)
        lg.setLevel(logging.DEBUG)

        # If logger already has handlers, don't add duplicates
        if lg.handlers:
            continue

        # 1. IM file handler - writes to im.log
        im_file_handler = _get_im_file_handler()

        # 2. Error file handler - writes to errors.log
        error_file_handler = get_model_error_handler()

        lg.addHandler(im_file_handler)
        lg.addHandler(error_file_handler)
        lg.propagate = False


# Global accessible logger instance
logger = TimingLogger(setup_logger())
