"""
VersionChecker class.
Delegates to siada.internal.services.version_checker.version_checker when available.
"""
try:
    from siada.internal.services.version_checker.version_checker import (
        VersionChecker,
        VERSION_CHECK_FNAME,
    )
except ImportError:
    # Internal module not available — define a minimal local implementation.
    import os
    import time
    import packaging.version
    import siada
    from siada.foundation.constants import SIADA_HOME
    from siada.services.auto_update import (
        get_latest_release_info,
        get_runtime_auto_update_config,
        install_latest_update,
    )

    VERSION_CHECK_FNAME = SIADA_HOME / "caches" / "versioncheck"  # type: ignore[assignment]

    class VersionChecker:  # type: ignore[no-redef]
        def __init__(self, handler):
            self.handler = handler

        def get_latest_version(self):
            try:
                release = get_latest_release_info(get_runtime_auto_update_config())
                return release.version, release.version_source
            except Exception:
                if self.handler:
                    try:
                        version, status = self.handler.get_version()
                        return (version, "available") if version else (None, status)
                    except Exception as e:
                        return None, f"handler_error: {e}"
                return None, "no_handler_available"

        def install_upgrade(self, io, latest_version=None, version_source=None):
            success, release, message = install_latest_update(
                config=get_runtime_auto_update_config(),
                force=latest_version is not None,
            )
            if success:
                if release and release.version != siada.__version__:
                    io.print_info(
                        f"Installed version {release.version}. Re-run siada-cli to use the new version."
                    )
                else:
                    io.print_info(message)
                return True

            if release is not None and self.handler:
                return self.handler.install(io, release.version)

            io.print_error(message)
            return False

        def check_version(self, io, just_check=False, verbose=False):
            if not just_check and VERSION_CHECK_FNAME.exists():
                day = 60 * 60 * 24
                since = time.time() - os.path.getmtime(VERSION_CHECK_FNAME)
                if 0 < since < day:
                    if verbose:
                        io.print_info(f"Too soon to check version: {since / 3600:.1f} hours")
                    return
            current_version = siada.__version__
            latest_version, version_source = self.get_latest_version()
            try:
                if not latest_version:
                    io.print_error(f"Failed to get version information: {version_source}")
                    return False
                is_update_available = packaging.version.parse(latest_version) > packaging.version.parse(current_version)
            except Exception as err:
                io.print_error(f"Error checking version: {err}")
                return False
            finally:
                VERSION_CHECK_FNAME.parent.mkdir(parents=True, exist_ok=True)
                VERSION_CHECK_FNAME.touch()
            if just_check or verbose:
                if is_update_available:
                    install_hint = None
                    if self.handler:
                        try:
                            install_hint = self.handler.get_manual_upgrade_hint()
                        except Exception:
                            install_hint = None
                    if install_hint is None:
                        install_hint = "siada-cli --upgrade"
                    io.print_info(
                        f"Latest version {latest_version} available:\n{install_hint}"
                    )
            if just_check:
                return is_update_available
            if not is_update_available:
                return False
            self.install_upgrade(io, latest_version, version_source)
            return True

__all__ = ["VersionChecker", "VERSION_CHECK_FNAME"]
