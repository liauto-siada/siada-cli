"""
Custom exceptions for HandleAtCommand functionality.
"""


class AtCommandError(Exception):
    """Base class for @ command processing errors"""
    
    def __init__(self, message: str, file_path: str = None):
        super().__init__(message)
        self.file_path = file_path


class PathNotFoundError(AtCommandError):
    """Raised when a path cannot be found"""
    pass


class PathIgnoredError(AtCommandError):
    """Raised when a path is ignored by filtering rules"""
    pass


class FileTooLargeError(AtCommandError):
    """Raised when a file exceeds size limits"""
    pass


class PermissionDeniedError(AtCommandError):
    """Raised when access to a file is denied"""
    pass


class SecurityViolationError(AtCommandError):
    """Raised when a security violation is detected (e.g., path traversal)"""
    pass


class InvalidPathError(AtCommandError):
    """Raised when a path is invalid or malformed"""
    pass


class WorkspaceSecurityError(AtCommandError):
    """Raised when a path is outside the workspace boundaries"""
    pass
