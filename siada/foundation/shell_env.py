"""Environment builder for user-facing shell commands.

The siada launcher/UI inject toolchain paths into the process environment
(bundled Node.js dir on PATH, PYTHONPATH for module mode, etc.) so that
siada's own subprocesses work regardless of the host setup.  Those
injections must not leak into shell commands the user (or user plugins)
run, where e.g. `node` should resolve to the user's own Node.js.

The launcher snapshots the pre-injection values into SIADA_USER_ENV (see
UILauncher._setup_node_env); make_user_shell_env() restores them here.
"""

import json
import os


def make_user_shell_env():
    """Build the environment for user-facing shell commands.

    Restores the user's original environment (undoing siada's own toolchain
    injections) and disables terminal pagers that would block execution
    inside a Siada session.  Used by run_cmd, custom-command shell
    injections, plugin hooks, and the notification command.
    """
    env = os.environ.copy()

    # Restore the user's original environment captured by the launcher before
    # siada injected its own toolchain paths (UILauncher._setup_node_env and
    # the Node UI's PYTHONPATH injection).  Without this, user commands
    # resolve node/npm against siada's bundled Node.js and pick up siada's
    # own site-packages via PYTHONPATH.
    # Snapshot semantics: a JSON null value means the variable was unset in
    # the user's environment and must be removed rather than restored.
    snapshot = os.environ.get("SIADA_USER_ENV")
    if snapshot:
        try:
            user_env = json.loads(snapshot)
        except ValueError:
            user_env = {}
        if isinstance(user_env, dict):
            for name, value in user_env.items():
                if value is None:
                    env.pop(name, None)
                else:
                    env[name] = value
    # PYTHONSAFEPATH exists to protect the siada backend from CWD shadowing of
    # installed packages; user commands must see default sys.path behavior.
    env.pop("PYTHONSAFEPATH", None)

    env["GIT_PAGER"] = "cat"
    env["SYSTEMD_PAGER"] = "cat"
    env["PAGER"] = "cat"
    env["LESS"] = "-FRX"
    return env
