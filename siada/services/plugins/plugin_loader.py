from __future__ import annotations
import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from siada.foundation.constants import SIADA_HOME
from siada.foundation.logging import logger
from siada.services.plugins.types import (
    HooksConfig,
    LoadedPlugin,
    PluginManifest,
    parse_plugin_manifest,
)
from siada.services.plugins.marketplace_manager import MarketplaceManager


def _git_env() -> dict:
    """Build a non-interactive git env: disables credential prompts and
    enforces SSH BatchMode. Without this, a private HTTPS GitLab clone hangs
    waiting for ``Username for 'https://...':`` on the user's terminal."""
    return {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/bin/echo",
        "GIT_SSH_COMMAND": os.environ.get(
            "GIT_SSH_COMMAND",
            "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new",
        ),
    }


def _https_to_ssh(url: str) -> str | None:
    """Convert ``https://host/owner/repo(.git)`` to ``git@host:owner/repo.git``."""
    if not url.startswith(("http://", "https://")):
        return None
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    host = parsed.hostname or ""
    path = parsed.path.strip("/")
    if not host or not path:
        return None
    if not path.endswith(".git"):
        path = f"{path}.git"
    return f"git@{host}:{path}"


if TYPE_CHECKING:
    from siada.config.mcp_config import MCPServerConfig as RuntimeMCPServerConfig

_PLUGINS_DIR = "plugins"


class PluginLoader:

    def load_all(self) -> list[LoadedPlugin]:
        """Scan ~/.siada-cli/plugins/ and return all plugins that have a plugin.json."""
        plugins_root = SIADA_HOME / _PLUGINS_DIR
        if not plugins_root.exists():
            return []
        loaded = []
        for plugin_dir in sorted(plugins_root.iterdir()):
            if not plugin_dir.is_dir():
                continue
            manifest_path = plugin_dir / ".claude-plugin" / "plugin.json"
            if not manifest_path.exists():
                continue
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest = parse_plugin_manifest(data, plugin_dir=plugin_dir)
                hooks_config = self._load_hooks_config(plugin_dir, manifest)
                config = MarketplaceManager().get_config()
                disabled = set(config.get("disabled_skills", []))
                plugin = LoadedPlugin(
                    name=manifest.name,
                    manifest=manifest,
                    path=str(plugin_dir),
                    source=f"{manifest.name}@installed",
                    enabled=manifest.name not in disabled,
                    hooks_config=hooks_config,
                )
                loaded.append(plugin)
            except Exception as e:
                logger.warning(f"Failed to load plugin from {plugin_dir}: {e}")
        return loaded

    def install(
        self,
        skill_name: str,
        marketplace_ref: str | None,
        progress_callback=None,
    ) -> LoadedPlugin:
        """Install a plugin/skill via git clone into ~/.siada-cli/skills/{skill_name}."""
        # If skill_name is a local filesystem path (absolute or ./relative),
        # split it into (basename, local_path) so dest_dir uses only the name.
        _local_path_override: Path | None = None
        _candidate = Path(skill_name).expanduser()
        if _candidate.is_absolute() or skill_name.startswith(("./", "../")):
            _local_path_override = _candidate
            skill_name = _candidate.name

        manager = MarketplaceManager()
        plugin_config = manager.get_config()
        branch = "main"
        skill_path_prefix = "skills"
        clone_url: str | None = None
        skill_own_repo = False

        if marketplace_ref is None:
            marketplaces = plugin_config.get("marketplaces", [])
            if not marketplaces:
                raise ValueError(
                    "No marketplaces configured. "
                    "Add one with: /plugin marketplace add <url_or_owner/repo>"
                )
            matched = marketplaces[0]
            matched_skill_entry = None
            for mp in marketplaces:
                mp_skills = manager.fetch_skills(mp)
                for s in mp_skills:
                    if s["name"] == skill_name:
                        matched = mp
                        matched_skill_entry = s
                        break
                if matched_skill_entry:
                    break
            branch = matched.get("branch", "main")
            skill_path_prefix = matched.get("path", "skills")
            clone_url = matched.get("url") or matched.get("repo", "")
            if matched_skill_entry and matched_skill_entry.get("source_url"):
                clone_url = matched_skill_entry["source_url"]
                branch = matched_skill_entry.get("source_ref") or branch
                skill_path_prefix = ""
                skill_own_repo = True
            elif matched_skill_entry and matched_skill_entry.get("source_path"):
                # Relative path within the same repo, e.g. "plugins/hookify"
                src_path = matched_skill_entry["source_path"]
                parts = src_path.rsplit("/", 1)
                skill_path_prefix = parts[0] if len(parts) == 2 else ""
                # skill_name stays as-is (last segment should match)
        else:
            for mp in plugin_config.get("marketplaces", []):
                if MarketplaceManager._mp_matches(mp, marketplace_ref):
                    branch = mp.get("branch", "main")
                    skill_path_prefix = mp.get("path", "skills")
                    clone_url = mp.get("url") or mp.get("repo", "")
                    mp_skills = manager.fetch_skills(mp)
                    for s in mp_skills:
                        if s["name"] == skill_name and s.get("source_url"):
                            clone_url = s["source_url"]
                            branch = s.get("source_ref") or branch
                            skill_path_prefix = ""
                            skill_own_repo = True
                            break
                        elif s["name"] == skill_name and s.get("source_path"):
                            src_path = s["source_path"]
                            parts = src_path.rsplit("/", 1)
                            skill_path_prefix = parts[0] if len(parts) == 2 else ""
                            break
                    break
            if clone_url is None:
                clone_url = marketplace_ref

        # Detect local filesystem path (absolute or relative ./...)
        local_src: Path | None = _local_path_override
        if local_src is None and clone_url:
            candidate = Path(clone_url).expanduser()
            if candidate.is_absolute() or clone_url.startswith(("./", "../")):
                local_src = candidate

        if local_src is None and clone_url and not clone_url.startswith(("http", "git@")):
            clone_url = f"https://github.com/{clone_url}"

        dest_dir = SIADA_HOME / _PLUGINS_DIR / skill_name
        # Also check the skills/ dir early so we detect conflicts before cloning
        _skills_dest_dir = SIADA_HOME / "skills" / skill_name
        if dest_dir.exists() or _skills_dest_dir.exists():
            raise FileExistsError(f"Skill '{skill_name}' already exists")

        # ── Local copy path ───────────────────────────────────────────────
        if local_src is not None:
            if not local_src.exists():
                raise FileNotFoundError(f"Local plugin path not found: {local_src}")
            shutil.copytree(local_src, dest_dir)
            # Validate the copied plugin
            errors, _ = PluginLoader.validate(str(dest_dir))
            if errors:
                shutil.rmtree(dest_dir, ignore_errors=True)
                raise ValueError(f"Plugin validation failed: {'; '.join(errors)}")
            plugin_config = MarketplaceManager().get_config()
            plugin_config.setdefault("enabledPlugins", {})[skill_name] = True
            MarketplaceManager().save_config(plugin_config)
            installed = [p for p in self.load_all() if p.name == skill_name]
            if installed:
                return installed[0]
            # Fallback: build a minimal LoadedPlugin
            manifest_data = {}
            manifest_json = dest_dir / ".claude-plugin" / "plugin.json"
            if manifest_json.exists():
                manifest_data = json.loads(manifest_json.read_text())
            return LoadedPlugin(
                name=skill_name,
                manifest=parse_plugin_manifest(manifest_data),
                path=str(dest_dir),
                source="local",
                enabled=True,
            )

        if not clone_url:
            raise ValueError("Could not determine clone URL for skill")

        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            # For monorepo installs, prefer sparse checkout to avoid checking out
            # unrelated files that may fail on macOS (case-insensitive FS issues etc.)
            sparse_path = (
                f"{skill_path_prefix}/{skill_name}".strip("/")
                if not skill_own_repo and skill_path_prefix
                else None
            )

            # Build clone URL candidates: HTTPS → SSH fallback (private GitLab
            # often only allows SSH for unauthenticated `git` binaries).
            ssh_clone = _https_to_ssh(clone_url)
            url_candidates = [clone_url] + ([ssh_clone] if ssh_clone else [])

            rc, err_text = -1, "no clone attempted"
            for try_url in url_candidates:
                shutil.rmtree(tmp, ignore_errors=True)
                os.makedirs(tmp, exist_ok=True)
                if sparse_path:
                    rc, err_text = self._git_clone_sparse(
                        try_url, tmp, branch, sparse_path, progress_callback, skill_name
                    )
                    if rc != 0:
                        shutil.rmtree(tmp, ignore_errors=True)
                        os.makedirs(tmp, exist_ok=True)
                        rc, err_text = self._git_clone(
                            try_url, tmp, branch, progress_callback, skill_name
                        )
                else:
                    rc, err_text = self._git_clone(
                        try_url, tmp, branch, progress_callback, skill_name
                    )
                if rc != 0:
                    # Retry without --branch (let HEAD pick default)
                    shutil.rmtree(tmp, ignore_errors=True)
                    os.makedirs(tmp, exist_ok=True)
                    rc, err_text = self._git_clone(
                        try_url, tmp, None, progress_callback, skill_name
                    )
                if rc == 0:
                    break

            if rc != 0:
                raise RuntimeError(
                    f"git clone failed (tried: {', '.join(url_candidates)}): {err_text}"
                )


            if skill_own_repo:
                skill_src = Path(tmp)
            else:
                skill_src = Path(tmp) / skill_path_prefix / skill_name
                if not skill_src.exists():
                    found = next(
                        (p for p in Path(tmp).rglob(skill_name) if p.is_dir()),
                        None,
                    )
                    if found is None:
                        raise FileNotFoundError(
                            f"Skill '{skill_name}' not found in {clone_url}"
                        )
                    skill_src = found

            # Bare Claude skill (no .claude-plugin/plugin.json) → install to
            # ~/.siada-cli/skills/ so get_user_skills_root() picks it up directly.
            if not (skill_src / ".claude-plugin" / "plugin.json").exists():
                dest_dir = SIADA_HOME / "skills" / skill_name

            shutil.copytree(str(skill_src), str(dest_dir))

        try:
            from siada.services.skills import SkillsManager
            SkillsManager.get_instance().invalidate_cache()
        except Exception:
            pass

        manifest_path = dest_dir / ".claude-plugin" / "plugin.json"
        if manifest_path.exists():
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = parse_plugin_manifest(data, plugin_dir=dest_dir)
        else:
            manifest = PluginManifest(name=skill_name)

        return LoadedPlugin(
            name=skill_name,
            manifest=manifest,
            path=str(dest_dir),
            source=marketplace_ref or "unknown",
            enabled=True,
        )

    def uninstall(self, skill_name: str, workspace: Path | None = None) -> None:
        """Remove a user-scope skill directory."""
        from siada.services.skills import SkillsManager
        from siada.services.skills.models import SkillScope

        manager = SkillsManager.get_instance()
        skill = manager.get_skill_by_name(workspace or Path("."), skill_name) if workspace else None

        if skill and skill.scope in (SkillScope.USER, SkillScope.REPO):
            dest_dir = skill.path.parent
        else:
            plugins_dir = SIADA_HOME / _PLUGINS_DIR / skill_name
            skills_dir = SIADA_HOME / "skills" / skill_name
            if plugins_dir.exists():
                dest_dir = plugins_dir
            elif skills_dir.exists():
                dest_dir = skills_dir
            else:
                dest_dir = plugins_dir  # will trigger the not found error below

        if not dest_dir.exists():
            raise FileNotFoundError(f"Skill '{skill_name}' not found at {dest_dir}")

        shutil.rmtree(dest_dir)
        manager.invalidate_cache()

    def set_enabled(self, plugin_name: str, enabled: bool) -> None:
        """Add or remove plugin_name from the disabled_skills list."""
        manager = MarketplaceManager()
        config = manager.get_config()
        disabled_list: list = config.get("disabled_skills", [])
        if enabled:
            if plugin_name in disabled_list:
                disabled_list.remove(plugin_name)
        else:
            if plugin_name not in disabled_list:
                disabled_list.append(plugin_name)
        config["disabled_skills"] = disabled_list
        manager.save_config(config)

    @staticmethod
    def validate(path: str) -> tuple[list[str], list[str]]:
        """Validate a local plugin directory. Returns (errors, warnings)."""
        import re
        plugin_dir = Path(path)
        errors: list[str] = []
        warnings: list[str] = []
        manifest_path = plugin_dir / ".claude-plugin" / "plugin.json"

        if not manifest_path.exists():
            errors.append(f".claude-plugin/plugin.json not found in {plugin_dir}")
            return errors, warnings

        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"plugin.json is not valid JSON: {e}")
            return errors, warnings

        name = data.get("name", "")
        if not name:
            errors.append("plugin.json missing required 'name' field")
        elif " " in name:
            errors.append(f"Plugin name '{name}' cannot contain spaces")

        if not data.get("version"):
            warnings.append("version not set (recommended: use semver, e.g. 1.0.0)")
        elif not re.match(r"^\d+\.\d+\.\d+", data.get("version", "")):
            warnings.append(f"version '{data.get('version')}' does not match semver format")

        if not data.get("description"):
            warnings.append("description is empty")

        skills_path = data.get("skills")  # only check if explicitly declared
        if skills_path:
            skills_dir = plugin_dir / skills_path.rstrip("/")
            if not skills_dir.exists():
                errors.append(f"Declared skills path '{skills_path}' does not exist")

        hooks_path = data.get("hooks", "hooks/hooks.json")
        if hooks_path:
            hooks_file = plugin_dir / hooks_path
            if hooks_file.exists():
                try:
                    hooks_data = json.loads(hooks_file.read_text(encoding="utf-8"))
                    valid_events = {"PreTurn", "PostTurn", "PreToolUse", "PostToolUse", "OnError"}
                    for event_name in hooks_data:
                        if event_name not in valid_events:
                            warnings.append(
                                f"Unknown hook event '{event_name}' "
                                f"(supported: {', '.join(sorted(valid_events))})"
                            )
                except json.JSONDecodeError as e:
                    errors.append(f"hooks file '{hooks_path}' is not valid JSON: {e}")

        mcp_raw = data.get("mcpServers")
        if isinstance(mcp_raw, (str, list)):
            pass  # string path or array reference — valid; runtime handles it
        elif mcp_raw is not None and not isinstance(mcp_raw, dict):
            errors.append("mcpServers must be a dict, string path, or array")
        elif isinstance(mcp_raw, dict):
            for server_name, server_config in mcp_raw.items():
                if not isinstance(server_config, dict):
                    errors.append(f"mcpServers.{server_name} must be an object")
                    continue
                if not server_config.get("command") and not server_config.get("url"):
                    errors.append(f"mcpServers.{server_name} must have 'command' or 'url'")

        return errors, warnings

    # ── private ───────────────────────────────────────────────────────────

    def _load_hooks_config(self, plugin_dir: Path, manifest: PluginManifest) -> HooksConfig | None:
        hooks_file = plugin_dir / manifest.hooks
        if not hooks_file.exists():
            return None
        try:
            data = json.loads(hooks_file.read_text(encoding="utf-8"))
            return HooksConfig.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load hooks from {hooks_file}: {e}")
            return None

    def _git_clone(
        self,
        url: str,
        dest: str,
        branch: str | None,
        progress_callback,
        skill_name: str,
    ) -> tuple[int, str]:
        import re as _re
        _progress_re = _re.compile(r"([A-Za-z][A-Za-z ]+):\s+(\d+)%")
        extra = [f"--branch={branch}"] if branch else []
        proc = subprocess.Popen(
            ["git", "clone", "--progress", "--depth=1"] + extra + [url, dest],
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            env=_git_env(),
        )
        stderr_lines: list[str] = []

        def _read_stderr():
            buf = b""
            try:
                while True:
                    chunk = proc.stderr.read(256)
                    if not chunk:
                        break
                    buf += chunk
                    parts = _re.split(b"[\r\n]", buf)
                    buf = parts[-1]
                    for part in parts[:-1]:
                        line = part.decode("utf-8", errors="replace").strip()
                        if line:
                            stderr_lines.append(line)
                        if progress_callback:
                            m = _progress_re.search(line)
                            if m:
                                progress_callback(m.group(1).strip(), int(m.group(2)))
            except Exception:
                pass

        t = threading.Thread(target=_read_stderr, daemon=True)
        t.start()
        try:
            proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            return -1, "git clone timed out"
        t.join(timeout=5)
        return proc.returncode, "\n".join(stderr_lines[-5:])


    def _git_clone_sparse(
        self,
        url: str,
        dest: str,
        branch: str | None,
        sparse_path: str,
        progress_callback,
        skill_name: str,
    ) -> tuple[int, str]:
        """Clone only a specific subdirectory using git sparse-checkout.

        Uses ``--filter=blob:none --no-checkout`` so that unrelated files in a
        monorepo (e.g. ones with names that are problematic on macOS) are never
        checked out, avoiding ``fatal: unable to checkout working tree`` errors.
        """
        import re as _re
        _progress_re = _re.compile(r"([A-Za-z][A-Za-z ]+):\s+(\d+)%")
        extra = [f"--branch={branch}"] if branch else []

        # Step 1: shallow clone without checkout, downloading only tree/commit objects
        proc = subprocess.Popen(
            [
                "git", "clone", "--progress", "--depth=1",
                "--filter=blob:none", "--no-checkout",
            ] + extra + [url, dest],
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            env=_git_env(),
        )

        stderr_lines: list[str] = []

        def _read_stderr():
            buf = b""
            try:
                while True:
                    chunk = proc.stderr.read(256)
                    if not chunk:
                        break
                    buf += chunk
                    parts = _re.split(b"[\r\n]", buf)
                    buf = parts[-1]
                    for part in parts[:-1]:
                        line = part.decode("utf-8", errors="replace").strip()
                        if line:
                            stderr_lines.append(line)
                        if progress_callback:
                            m = _progress_re.search(line)
                            if m:
                                progress_callback(m.group(1).strip(), int(m.group(2)))
            except Exception:
                pass

        t = threading.Thread(target=_read_stderr, daemon=True)
        t.start()
        try:
            proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            return -1, "git clone timed out"
        t.join(timeout=5)
        if proc.returncode != 0:
            return proc.returncode, "\n".join(stderr_lines[-5:])

        # Step 2: initialise sparse-checkout and check out only the needed path
        init_proc = subprocess.run(
            ["git", "-C", dest, "sparse-checkout", "init", "--cone"],
            capture_output=True,
            timeout=30,
        )
        if init_proc.returncode != 0:
            return init_proc.returncode, init_proc.stderr.decode("utf-8", errors="replace")

        set_proc = subprocess.run(
            ["git", "-C", dest, "sparse-checkout", "set", sparse_path],
            capture_output=True,
            timeout=30,
        )
        if set_proc.returncode != 0:
            return set_proc.returncode, set_proc.stderr.decode("utf-8", errors="replace")

        # Step 3: checkout HEAD to materialise the sparse working tree
        co_proc = subprocess.run(
            ["git", "-C", dest, "checkout"],
            capture_output=True,
            timeout=60,
        )
        err_out = co_proc.stderr.decode("utf-8", errors="replace").strip()
        return co_proc.returncode, err_out


def extract_plugin_mcp_configs(
    plugins: list[LoadedPlugin],
) -> list[tuple[str, RuntimeMCPServerConfig]]:
    """Convert enabled plugins' MCP server configs to (scoped_name, RuntimeMCPServerConfig) pairs.

    scoped_name format: ``plugin:{plugin_name}:{server_name}``

    ``${CLAUDE_PLUGIN_ROOT}`` in command/args/env/url is replaced with the
    plugin's installed path so the subprocess or HTTP endpoint resolves
    correctly regardless of where siada is installed.

    Returns only enabled plugins. Servers with neither command nor url are
    skipped with a warning.
    """
    from siada.config.mcp_config import MCPServerConfig as RuntimeMCPServerConfig  # lazy

    def _expand(value: str, plugin_root: str) -> str:
        return value.replace("${CLAUDE_PLUGIN_ROOT}", plugin_root)

    result: list[tuple[str, RuntimeMCPServerConfig]] = []

    for plugin in plugins:
        if not plugin.enabled:
            continue
        plugin_root = plugin.path
        for server_name, srv in plugin.manifest.mcp_servers.items():
            scoped_name = f"plugin:{plugin.name}:{server_name}"

            command = _expand(srv.command, plugin_root) if srv.command else None
            args = [_expand(a, plugin_root) for a in (srv.args or [])]
            env = {k: _expand(v, plugin_root) for k, v in (srv.env or {}).items()}
            # Always expose CLAUDE_PLUGIN_ROOT so plugin scripts can reference it
            env.setdefault("CLAUDE_PLUGIN_ROOT", plugin_root)
            url = _expand(srv.url, plugin_root) if srv.url else None

            if not command and not url:
                logger.warning(
                    f"Plugin MCP server '{scoped_name}' has neither command nor url — skipped"
                )
                continue

            transport_type = "stdio" if command else "sse"
            cfg = RuntimeMCPServerConfig(
                type=transport_type,
                command=command,
                args=args,
                env=env,
                cwd=plugin_root,
                url=url,
            )
            result.append((scoped_name, cfg))

    return result

