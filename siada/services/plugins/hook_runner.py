from __future__ import annotations
import asyncio
import json
import subprocess
from collections import defaultdict
from siada.foundation.logging import logger
from siada.services.plugins.types import HookEntry, HookResponse, LoadedPlugin

_HOOK_TIMEOUT_SECONDS = 5

# Module-level active runner reference, set by controller before each turn.
# Allows HookRunnerProcessor (inside the agent SDK stack) to call the
# correct HookRunner without threading it through every function signature.
_active_runner: "HookRunner | None" = None


def set_active(runner: "HookRunner | None") -> None:
    """Set the active HookRunner for the current turn. Thread-safe via GIL."""
    global _active_runner
    _active_runner = runner


def get_active() -> "HookRunner | None":
    """Return the currently active HookRunner, or None if none is set."""
    return _active_runner


class HookRunner:
    """Executes CLI lifecycle shell hooks from installed plugins."""

    def __init__(self, workspace: str | None = None):
        # event_name -> list of (HookEntry, plugin_name, plugin_path)
        self._hooks: dict[str, list[tuple[HookEntry, str, str]]] = defaultdict(list)
        # cwd passed to hook subprocesses so relative paths (e.g. .claude/) resolve
        # against the user's workspace rather than siada's process directory.
        self._workspace = workspace

    def register_plugin_hooks(self, plugin: LoadedPlugin) -> None:
        """Register all hooks from a plugin. Disabled plugins are skipped."""
        if not plugin.enabled or plugin.hooks_config is None:
            return
        hooks_config = plugin.hooks_config
        from siada.services.plugins.types import _HOOK_EVENTS
        for event_name in _HOOK_EVENTS:
            for entry in getattr(hooks_config, event_name, []):
                self._hooks[event_name].append((entry, plugin.name, plugin.path))

    def run(self, event: str, context: dict | None = None) -> None:
        """Execute all hooks registered for event. Errors are logged, never raised."""
        entries = self._hooks.get(event, [])
        for hook_entry, plugin_name, plugin_path in entries:
            if not self._should_run(hook_entry, event, context):
                continue
            self._execute(hook_entry, plugin_name, plugin_path, event, context)

    async def run_with_result(
        self, event: str, context: dict | None = None
    ) -> list[HookResponse]:
        """Execute hooks for event and return parsed HookResponse list.

        For async-marked hooks (HookEntry.async_=True), the command is fired as
        a background task and an empty list is returned immediately.
        Errors are logged and a default HookResponse is included so callers
        can always treat the result as a non-empty list.
        """
        entries = self._hooks.get(event, [])
        responses: list[HookResponse] = []
        stdin_json = json.dumps(context or {})

        for hook_entry, plugin_name, plugin_path in entries:
            if not self._should_run(hook_entry, event, context):
                continue
            if hook_entry.async_:
                asyncio.create_task(
                    self._execute_async(hook_entry, plugin_name, plugin_path, event, stdin_json)
                )
                continue
            resp = await self._execute_with_result(
                hook_entry, plugin_name, plugin_path, event, stdin_json
            )
            responses.append(resp)

        return responses

    def run_with_result_sync(
        self, event: str, context: dict | None = None
    ) -> list[HookResponse]:
        """Synchronous wrapper around run_with_result for non-async callers."""
        import asyncio
        return asyncio.run(self.run_with_result(event, context))

    def set_workspace(self, workspace: str | None) -> None:
        """Set the cwd for hook subprocesses (call once session config is known)."""
        self._workspace = workspace

    def clear(self) -> None:
        """Remove all registered hooks."""
        self._hooks.clear()

    # ── private ───────────────────────────────────────────────────────────

    def _should_run(self, entry: HookEntry, event: str, context: dict | None) -> bool:
        if event in ("PreToolUse", "PostToolUse") and entry.matcher:
            tool_name = (context or {}).get("tool_name", "")
            return entry.matcher in tool_name
        return True

    @staticmethod
    def _make_env(plugin_path: str) -> dict:
        """Build env dict with CLAUDE_PLUGIN_ROOT set for the given plugin."""
        import os
        env = os.environ.copy()
        env["CLAUDE_PLUGIN_ROOT"] = plugin_path
        return env

    def _execute(self, entry: HookEntry, plugin_name: str, plugin_path: str, event: str, context: dict | None) -> None:
        try:
            stdin_data = json.dumps(context or {})
            result = subprocess.run(
                entry.command,
                shell=True,
                timeout=_HOOK_TIMEOUT_SECONDS,
                capture_output=True,
                text=True,
                input=stdin_data,
                env=self._make_env(plugin_path),
                cwd=self._workspace,
            )
            if result.returncode != 0:
                logger.warning(
                    f"Hook '{event}' from plugin '{plugin_name}' exited with "
                    f"code {result.returncode}: {result.stderr.strip()}"
                )
        except subprocess.TimeoutExpired:
            logger.warning(
                f"Hook '{event}' from plugin '{plugin_name}' timed out after "
                f"{_HOOK_TIMEOUT_SECONDS}s"
            )
        except Exception as e:
            logger.warning(f"Hook '{event}' from plugin '{plugin_name}' failed: {e}")

    async def _execute_with_result(
        self,
        entry: HookEntry,
        plugin_name: str,
        plugin_path: str,
        event: str,
        stdin_json: str,
    ) -> HookResponse:
        """Run hook command, capture stdout, parse JSON response."""
        try:
            proc = await asyncio.create_subprocess_shell(
                entry.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._make_env(plugin_path),
                cwd=self._workspace,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(stdin_json.encode()),
                timeout=_HOOK_TIMEOUT_SECONDS,
            )
            if proc.returncode != 0:
                logger.warning(
                    f"Hook '{event}' from plugin '{plugin_name}' exited with "
                    f"code {proc.returncode}: {stderr.decode().strip()}"
                )
            raw = stdout.decode().strip()
            if not raw:
                return HookResponse.default()
            try:
                return HookResponse.from_dict(json.loads(raw))
            except json.JSONDecodeError:
                logger.warning(
                    f"Hook '{event}' from plugin '{plugin_name}' returned "
                    f"non-JSON stdout: {raw[:200]}"
                )
                return HookResponse.default()
        except asyncio.TimeoutError:
            logger.warning(
                f"Hook '{event}' from plugin '{plugin_name}' timed out after "
                f"{_HOOK_TIMEOUT_SECONDS}s"
            )
            return HookResponse.default()
        except Exception as e:
            logger.warning(f"Hook '{event}' from plugin '{plugin_name}' failed: {e}")
            return HookResponse.default()

    async def _execute_async(
        self,
        entry: HookEntry,
        plugin_name: str,
        plugin_path: str,
        event: str,
        stdin_json: str,
    ) -> None:
        """Fire-and-forget async hook execution. Stdout is ignored."""
        try:
            proc = await asyncio.create_subprocess_shell(
                entry.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
                env=self._make_env(plugin_path),
                cwd=self._workspace,
            )
            _, stderr = await asyncio.wait_for(
                proc.communicate(stdin_json.encode()),
                timeout=_HOOK_TIMEOUT_SECONDS,
            )
            if proc.returncode != 0:
                logger.warning(
                    f"Async hook '{event}' from plugin '{plugin_name}' exited with "
                    f"code {proc.returncode}: {stderr.decode().strip()}"
                )
        except asyncio.TimeoutError:
            logger.warning(
                f"Async hook '{event}' from plugin '{plugin_name}' timed out"
            )
        except Exception as e:
            logger.warning(f"Async hook '{event}' from plugin '{plugin_name}' failed: {e}")
