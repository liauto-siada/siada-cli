import os
import sys
import logging
import tempfile
import threading
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


DEBUG = os.getenv('SIADA_DEBUG', 'False').lower() in ['true', '1', 'yes']
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
    datefmt='%Y-%m-%d %H:%M:%S',
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
    file_handler.setFormatter(FileFormatter(formatter_str, datefmt='%Y-%m-%d %H:%M:%S'))
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
    file_handler.setLevel(logging.DEBUG if DEBUG else logging.INFO)
    formatter_str = '%(asctime)s - %(name)s:%(levelname)s: %(filename)s:%(lineno)s - %(message)s'
    file_handler.setFormatter(FileFormatter(formatter_str, datefmt='%Y-%m-%d %H:%M:%S'))
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
    file_handler.setFormatter(FileFormatter(formatter_str, datefmt='%Y-%m-%d %H:%M:%S'))
    return file_handler


# Singleton file handler cache to prevent multiple TimedRotatingFileHandler
# instances from independently rotating the same log file, which causes
# log splitting and potential data loss.
_handler_lock = threading.Lock()
_shared_file_handler: Optional[logging.Handler] = None
_shared_error_handler: Optional[logging.Handler] = None
_shared_im_handler: Optional[logging.Handler] = None


class FilteredHandler(logging.Handler):
    """Wrapper that applies a filter before delegating to a shared handler.

    This allows per-logger filtering on a singleton handler without mutating
    the handler's own filter list (which would affect all loggers sharing it).
    """

    def __init__(self, target: logging.Handler, log_filter: logging.Filter):
        super().__init__()
        self.target = target
        self.addFilter(log_filter)

    def emit(self, record: logging.LogRecord) -> None:
        self.target.emit(record)

    def setLevel(self, level: int) -> None:  # noqa: N802 – keep stdlib naming
        super().setLevel(level)

    # Delegate flush / close to the real handler
    def flush(self) -> None:
        self.target.flush()

    def close(self) -> None:
        # Only remove ourselves; do NOT close the shared target.
        super().close()


def get_file_handler():
    """
    Get the shared file handler (singleton per process).

    Returns the same handler instance on every call within a process,
    preventing multiple independent TimedRotatingFileHandler instances
    from rotating the same siada_cli.log file.

    On Windows: Uses ConcurrentLogHandler to avoid file locking issues during rotation.
    On other platforms: Uses SafeTimedRotatingFileHandler for time-based rotation.

    Returns:
        logging.Handler: Configured file handler for logging
    """
    global _shared_file_handler
    if _shared_file_handler is not None:
        return _shared_file_handler

    with _handler_lock:
        # Double-check after acquiring lock
        if _shared_file_handler is not None:
            return _shared_file_handler

        # Check if running on Windows
        is_windows = sys.platform.startswith('win')

        if is_windows:
            try:
                # Try to create ConcurrentRotatingFileHandler for Windows
                _shared_file_handler = _create_concurrent_file_handler()
                return _shared_file_handler

            except ImportError:
                # Fallback to SafeTimedRotatingFileHandler if ConcurrentLogHandler is not installed
                import warnings
                warnings.warn(
                    "ConcurrentLogHandler not found. Install it with: pip install concurrent-log-handler\n"
                    "Falling back to SafeTimedRotatingFileHandler which may have file locking issues on Windows.",
                    RuntimeWarning
                )

        # Use SafeTimedRotatingFileHandler for non-Windows or as fallback
        _shared_file_handler = _create_safe_timed_rotating_handler()
        return _shared_file_handler


def redirect_file_handler(file_name: str) -> logging.Handler:
    """
    Redirect the shared file handler to a different log file.

    Creates a new handler for *file_name* (under the standard log directory),
    replaces the old singleton in every logger that references it, closes the
    old handler, and updates the module-level cache.

    For loggers that use a :class:`FilteredHandler` wrapper around the shared
    handler, the wrapper's ``target`` is updated in-place so the wrapper (and
    its per-logger filter) remains intact.

    This must be called early in the process lifecycle (e.g. daemon startup)
    **before** heavy logging begins, to ensure all loggers pick up the new
    target file.

    Args:
        file_name: Target log file name, e.g. ``siada_daemon.log``.

    Returns:
        The newly created shared file handler.
    """
    global _shared_file_handler

    with _handler_lock:
        old_handler = _shared_file_handler

        # Create new handler for the target file
        target_log_file = os.path.join(log_dir, file_name)
        new_handler = SafeTimedRotatingFileHandler(
            target_log_file,
            when='midnight',
            interval=1,
            backupCount=30,
            encoding='utf-8',
            delay=True,
        )
        new_handler.setLevel(logging.INFO)
        formatter_str = '%(asctime)s - %(name)s:%(levelname)s: %(filename)s:%(lineno)s - %(message)s'
        new_handler.setFormatter(FileFormatter(formatter_str, datefmt='%Y-%m-%d %H:%M:%S'))

        _shared_file_handler = new_handler

        # Replace old handler in all loggers that reference it
        if old_handler is not None:
            root = logging.root
            for lg in [root] + list(root.manager.loggerDict.values()):
                if not isinstance(lg, logging.Logger):
                    continue
                for h in list(lg.handlers):
                    if h is old_handler:
                        lg.removeHandler(old_handler)
                        lg.addHandler(new_handler)
                    elif isinstance(h, FilteredHandler) and h.target is old_handler:
                        # Re-point the wrapper to the new underlying handler
                        h.target = new_handler
            old_handler.close()

    return new_handler


def get_console_handler(log_level=logging.INFO, extra_info: Optional[str] = None):
    """Returns a console handler for logging."""
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    formatter_str = '\033[92m%(asctime)s - %(name)s:%(levelname)s\033[0m: %(filename)s:%(lineno)s - %(message)s'
    if extra_info:
        formatter_str = f'{extra_info} - ' + formatter_str
    console_handler.setFormatter(ColoredFormatter(formatter_str, datefmt='%Y-%m-%d %H:%M:%S'))
    return console_handler


def get_model_error_handler():
    """
    Get the shared error file handler (singleton per process).
    
    Returns the same handler instance on every call within a process,
    preventing multiple independent TimedRotatingFileHandler instances
    from rotating the same errors.log file.
    
    Returns:
        TimedRotatingFileHandler: Handler configured to write model error logs
    """
    global _shared_error_handler
    if _shared_error_handler is not None:
        return _shared_error_handler

    with _handler_lock:
        # Double-check after acquiring lock
        if _shared_error_handler is not None:
            return _shared_error_handler

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
        _shared_error_handler = error_file_handler
        return _shared_error_handler


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
    # Suppress GitPython's verbose DEBUG output (e.g. "sys.platform='darwin', git_executable='git'")
    logging.getLogger('git').setLevel(logging.WARNING)
    # Suppress verbose MCP connection debug/info logs leaking to console/stdout
    logging.getLogger('mcp').setLevel(logging.WARNING)


def setup_logger():
    """
    Setup and return siada.app logger with category-based filtering.
    
    Also configures siada namespace logger to catch all siada.* submodules.
    
    This logger uses filters to route different log categories to different handlers:
    - General logs go to console and siada_cli.log
    - Model error logs go to model_errors.log
    """
    # Create logger
    log_level = logging.DEBUG if DEBUG else logging.INFO
    logger_instance = logging.getLogger('siada.app')
    logger_instance.setLevel(log_level)

    # If logger already has handlers, don't add duplicates
    if logger_instance.handlers:
        return logger_instance

    # 1. Console handler - only general logs (exclude MODEL_ERROR)
    console_handler = get_console_handler(log_level=log_level)
    console_handler.addFilter(CategoryFilter.for_general_logs())

    # 2. Shared file handler (singleton) — wrapped with FilteredHandler so
    #    MODEL_ERROR is excluded from siada_cli.log without mutating the
    #    shared handler's own filter list.
    file_handler = get_file_handler()
    filtered_file_handler = FilteredHandler(file_handler, CategoryFilter.for_general_logs())

    # 3. Shared error file handler (singleton) — only MODEL_ERROR goes here
    error_file_handler = get_model_error_handler()
    error_file_handler.addFilter(CategoryFilter.for_model_errors())

    # Add handlers to siada.app logger
    logger_instance.addHandler(console_handler)
    logger_instance.addHandler(filtered_file_handler)
    logger_instance.addHandler(error_file_handler)
    logger_instance.propagate = False

    # Setup siada namespace logger - catches all siada.* submodules.
    # Modules using logging.getLogger(__name__) within the siada.* package propagate
    # here, ensuring their messages reach both console and file without relying on
    # the siada.app logger being properly initialized.
    # siada.app.propagate=False guarantees no duplicate output from explicit imports.
    siada_logger = logging.getLogger("siada")
    siada_logger.setLevel(log_level)
    if not siada_logger.handlers:
        # File handler — wrapped with category filter
        siada_filtered_file = FilteredHandler(file_handler, CategoryFilter.for_general_logs())
        siada_logger.addHandler(siada_filtered_file)
        siada_logger.addHandler(error_file_handler)
        # Console handler — allows getLogger(__name__) modules to reach the terminal.
        # No duplication risk: siada.app.propagate=False keeps those messages isolated.
        siada_console_handler = get_console_handler(log_level=log_level)
        siada_console_handler.addFilter(CategoryFilter.for_general_logs())
        siada_logger.addHandler(siada_console_handler)
    # Disable propagation to root logger. Third-party libraries (e.g. litellm)
    # or module-level logging.basicConfig() calls may add a StreamHandler to
    # root, causing siada.* INFO messages to leak to the console with the
    # default BASIC_FORMAT (e.g. "INFO:siada.config:...").
    siada_logger.propagate = False

    # Configure third-party library log levels
    configure_third_party_loggers()

    return logger_instance



def _remove_console_handlers_from(target_logger: logging.Logger) -> None:
    """Remove all StreamHandler (non-file) handlers from a single logger."""
    handlers_to_remove = [
        h for h in target_logger.handlers
        if isinstance(h, logging.StreamHandler) and not isinstance(h, TimedRotatingFileHandler)
    ]
    for handler in handlers_to_remove:
        target_logger.removeHandler(handler)
        handler.close()


def remove_console_handler(target_logger=None):
    """
    Remove console handler from logger(s), keeping only file handlers.

    When target_logger is None, removes console handlers from both ``siada.app``
    and the ``siada`` namespace logger. This ensures that all siada.* module
    loggers (which propagate to ``siada``) also stop printing to the console —
    e.g. when switching to daemon / background mode.

    Args:
        target_logger: Logger instance to modify. If None, clears console output
            from both siada.app and siada namespace loggers.
    """
    if target_logger is None:
        _remove_console_handlers_from(logging.getLogger('siada.app'))
        _remove_console_handlers_from(logging.getLogger('siada'))
        return
    _remove_console_handlers_from(target_logger)


def _add_console_handler_to(target_logger: logging.Logger, log_level: int) -> None:
    """Add a console handler (with CategoryFilter) to a logger if absent."""
    has_console_handler = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, TimedRotatingFileHandler)
        for h in target_logger.handlers
    )
    if not has_console_handler:
        console_handler = get_console_handler(log_level)
        console_handler.addFilter(CategoryFilter.for_general_logs())
        target_logger.addHandler(console_handler)


def add_console_handler(target_logger=None, log_level=logging.INFO):
    """
    Add console handler back to logger(s).

    When target_logger is None, adds console handlers to both ``siada.app`` and
    the ``siada`` namespace logger, restoring console output for all siada.*
    module loggers that use getLogger(__name__).

    Args:
        target_logger: Logger instance to modify. If None, adds to both siada.app
            and siada namespace loggers.
        log_level: Log level for the console handler.
    """
    if target_logger is None:
        _add_console_handler_to(logging.getLogger('siada.app'), log_level)
        _add_console_handler_to(logging.getLogger('siada'), log_level)
        return
    _add_console_handler_to(target_logger, log_level)


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

    These loggers are set to WARNING so that DEBUG-level teardown messages
    (e.g. "Shutting down trace provider") emitted by the openai-agents SDK
    during Python's atexit phase do not leak to stderr after the file handler
    has already been closed by logging.shutdown().  DEBUG output is still
    captured in the file for the duration of the process (the file handler
    accepts DEBUG), but the logger gate itself is WARNING to suppress noisy
    shutdown chatter.
    """
    logger_names = ['openai.agents', 'openai.agents.tracing']
    file_handler = get_named_file_handler('openai.log', log_level=logging.DEBUG)

    for logger_name in logger_names:
        target_logger = logging.getLogger(logger_name)
        target_logger.setLevel(logging.WARNING)
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

def redirect_openhands_aci_logger():
    """
    Redirect openhands_aci loggers (e.g. openhands_aci.editor.file_cache) to
    a dedicated log file so their DEBUG output does not leak to the console.

    The openhands_aci package emits verbose DEBUG messages (FileCache init,
    size updates, etc.). We route them to ``openhands_aci.log`` under the
    standard Siada log directory and disable propagation to keep them out of
    the siada.app console/file handlers.
    """
    file_handler = get_named_file_handler('openhands_aci.log', log_level=logging.DEBUG)

    target_logger = logging.getLogger('openhands_aci')
    target_logger.setLevel(logging.DEBUG)
    target_logger.propagate = False

    has_handler = any(
        getattr(handler, 'baseFilename', None) == getattr(file_handler, 'baseFilename', None)
        for handler in target_logger.handlers
    )
    if not has_handler:
        target_logger.addHandler(file_handler)


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
        """Start a new timing session and emit a start log."""
        import time
        self._t_start = time.time()
        self._t = self._t_start
        self._logger.debug("[startup-timing] >>> start: %s", label)

    def log_timing(self, phase: str) -> None:
        """Log elapsed time for the current phase and since startup."""
        import time
        now = time.time()
        if self._t_start is None or self._t is None:
            self._logger.debug("[startup-timing] phase=%-36s (timing not started)", phase)
            return
        phase_ms = (now - self._t) * 1000
        total_ms = (now - self._t_start) * 1000
        self._t = now
        self._logger.debug(
            "[startup-timing] phase=%-36s  +%7.1f ms  total=%7.1f ms",
            phase, phase_ms, total_ms,
        )

    def __getattr__(self, name: str):
        return getattr(self._logger, name)


def _get_im_file_handler():
    """
    Get the shared IM file handler (singleton per process).

    Returns the same handler instance on every call, preventing multiple
    independent TimedRotatingFileHandler instances from rotating the same
    im.log file — which would cause the backup to be overwritten with an
    empty file and result in log data loss.

    Returns:
        SafeTimedRotatingFileHandler: Configured handler for IM logs
    """
    global _shared_im_handler
    if _shared_im_handler is not None:
        return _shared_im_handler

    with _handler_lock:
        # Double-check after acquiring lock
        if _shared_im_handler is not None:
            return _shared_im_handler

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
        im_file_handler.setFormatter(FileFormatter(formatter_str, datefmt='%Y-%m-%d %H:%M:%S'))
        _shared_im_handler = im_file_handler
        return _shared_im_handler


def setup_im_logger():
    """
    Setup IM-related loggers to write to im.log file.

    Redirects all siada.im.* loggers (via parent siada.im),
    siada.im.lark (intermediate namespace), and siada.io.lark to im.log.

    Also configures these loggers with error handler for errors.log.

    Two-level setup:
    - siada.im / siada.im.lark / siada.io.lark get im.log handlers
      and propagate=False to prevent leaking into siada_cli.log.
    - All child loggers (e.g. siada.im.lark.controller) propagate
      up to one of these loggers naturally.
    """
    # Logger names that should write to im.log
    logger_names = [
        'siada.im',               # parent for all siada.im.* loggers
        'siada.im.lark',          # intermediate namespace; ensures controller logs are captured
        'siada.io.lark',          # LarkIO adapter
    ]

    for name in logger_names:
        lg = logging.getLogger(name)
        lg.setLevel(logging.DEBUG)
        # Always prevent propagation to siada namespace (siada_cli.log)
        lg.propagate = False

        # If logger already has handlers, don't add duplicates
        if lg.handlers:
            continue

        # 1. IM file handler - writes to im.log
        im_file_handler = _get_im_file_handler()

        # 2. Error file handler - writes to errors.log
        error_file_handler = get_model_error_handler()

        lg.addHandler(im_file_handler)
        lg.addHandler(error_file_handler)


# Global accessible logger instance
logger = TimingLogger(setup_logger())
