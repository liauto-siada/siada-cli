"""
Version checker interface for external access
"""
import os
import time
from pathlib import Path
import packaging.version
import siada

VERSION_CHECK_FNAME = Path.home() / ".siada-cli" / "caches" / "versioncheck"


class VersionChecker:
    """
    Interface class for version checking operations
    This is the main entry point for external code
    """
    
    def __init__(self, handler):
        self.handler = handler
    
    def get_latest_version(self):
        """Get latest version using the handler"""
        if self.handler:
            try:
                version, status = self.handler.get_version()
                if version:
                    return version, "available"
                else:
                    return None, status
            except Exception as e:
                return None, f"handler_error: {e}"
        return None, "no_handler_available"
    
    def install_upgrade(self, io, latest_version=None, version_source=None):
        """Install upgrade using the handler"""
        if self.handler:
            if latest_version is None:
                latest_version, _ = self.get_latest_version()
            return self.handler.install(io, latest_version)
        return False
    
    def check_version(self, io, just_check=False, verbose=False):
        """
        Unified version check function supporting three modes with unified cache file
        """
        
        # Check cache only for non-forced checks (when just_check=False)
        if not just_check and VERSION_CHECK_FNAME.exists():
            day = 60 * 60 * 24
            since = time.time() - os.path.getmtime(VERSION_CHECK_FNAME)
            if 0 < since < day:
                if verbose:
                    hours = since / 60 / 60
                    io.print_info(f"Too soon to check version: {hours:.1f} hours")
                return

        current_version = siada.__version__
        # Get version information (with network requests)
        latest_version, version_source = self.get_latest_version()

        try:
            # Handle failed version retrieval
            if not latest_version:
                io.print_error(f"Failed to get version information: {version_source}")
                return False

            # Display version information
            if just_check or verbose:
                io.print_info(f"Current version: {current_version}")
                io.print_info(f"Latest version: {latest_version}")

            # Version comparison
            is_update_available = packaging.version.parse(latest_version) > packaging.version.parse(current_version)
            
        except Exception as err:
            io.print_error(f"Error checking version: {err}")
            return False
        finally:
            # Update unified cache file
            VERSION_CHECK_FNAME.parent.mkdir(parents=True, exist_ok=True)
            VERSION_CHECK_FNAME.touch()

        # Handle results based on command type
        if just_check or verbose:
            if is_update_available:
                io.print_info("Update available")
            else:
                io.print_info("No update available")

        # Just check mode, return result without executing update
        if just_check:
            return is_update_available

        # No update available
        if not is_update_available:
            return False

        # Update available, prompt update based on version source
        self.install_upgrade(io, latest_version, version_source)
        return True
