"""
Marketplace configuration management.

Migrated from slash_commands.py plugin methods (_get_plugin_config,
_save_plugin_config, _fetch_marketplace_skills, _plugin_marketplace_*).

Discovery strategy (mirrors Claude Code's loadAndCacheMarketplace):
the marketplace repo is shallow-cloned into ``~/.siada-cli/marketplaces/<name>``
using the system ``git`` binary so we automatically pick up the user's git
credentials (SSH keys, credential helper, ~/.netrc), allowing private repos
on enterprise GitLab/GitHub to be discovered. We only fall back to the raw
HTTP/REST API path if git is unavailable or the clone fails.
"""
from __future__ import annotations
import json
import re
import shutil
import subprocess
import time
import urllib.request
import urllib.error
from pathlib import Path
from urllib.parse import quote, urlparse

from siada.foundation.constants import SIADA_HOME
from siada.foundation.logging import logger


# No built-in marketplaces in the open-source build; users add their own
# via the plugin config (plugin_config.json).
_DEFAULT_MARKETPLACES = []

_CONFIG_FILENAME = "plugin_config.json"


class MarketplaceManager:

    def get_config(self) -> dict:
        """Read plugin config, injecting default marketplaces if missing."""
        config_path = SIADA_HOME / _CONFIG_FILENAME
        if not config_path.exists():
            config: dict = {"marketplaces": [], "disabled_skills": []}
        else:
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception:
                config = {"marketplaces": [], "disabled_skills": []}

        existing_names = {m.get("name") for m in config.get("marketplaces", [])}
        added = False
        for default_mp in _DEFAULT_MARKETPLACES:
            if default_mp["name"] not in existing_names:
                config.setdefault("marketplaces", []).insert(0, dict(default_mp))
                added = True
        if added:
            try:
                self.save_config(config)
            except Exception:
                pass
        return config

    def save_config(self, config: dict) -> None:
        """Save plugin config to ~/.siada-cli/plugin_config.json"""
        SIADA_HOME.mkdir(parents=True, exist_ok=True)
        config_path = SIADA_HOME / _CONFIG_FILENAME
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    def add_marketplace(self, repo_input: str) -> None:
        config = self.get_config()
        marketplaces: list = config.get("marketplaces", [])
        for mp in marketplaces:
            if self._mp_matches(mp, repo_input):
                raise ValueError(f"Marketplace '{repo_input}' is already configured")

        raw_name = repo_input.rstrip("/").split("/")[-1]
        name = raw_name.removesuffix(".git")
        entry: dict = {
            "name": name,
            "repo": repo_input,
            "branch": "main",
            "path": "skills",
            "available": 0,
            "installed": 0,
        }
        if repo_input.startswith(("http://", "https://", "git@")):
            entry["url"] = repo_input
        marketplaces.append(entry)
        config["marketplaces"] = marketplaces
        self.save_config(config)

    def remove_marketplace(self, name_or_repo: str) -> None:
        config = self.get_config()
        marketplaces: list = config.get("marketplaces", [])
        before = len(marketplaces)
        marketplaces = [mp for mp in marketplaces if not self._mp_matches(mp, name_or_repo)]
        if len(marketplaces) == before:
            raise ValueError(f"Marketplace '{name_or_repo}' not found")
        config["marketplaces"] = marketplaces
        self.save_config(config)

    def update_marketplace(self, name_or_repo: str, installed_names: set | None = None) -> dict:
        """Refresh available/installed counts. Returns updated marketplace entry."""
        config = self.get_config()
        target = next(
            (mp for mp in config.get("marketplaces", []) if self._mp_matches(mp, name_or_repo)),
            None,
        )
        if target is None:
            raise ValueError(f"Marketplace '{name_or_repo}' not found")
        skills = self.fetch_skills(target, installed_names or set())
        target["available"] = len(skills)
        target["installed"] = sum(1 for s in skills if s.get("installed"))
        target["_cached_skills"] = skills
        target["updatedAt"] = time.strftime("%m/%d/%Y")
        self.save_config(config)
        return target

    def fetch_skills(self, marketplace: dict, installed_names: set | None = None) -> list[dict]:
        """Fetch available skills/plugins from marketplace.

        Discovery order (matches Claude Code's loadAndCacheMarketplace):
        1. ``git clone --depth=1`` the repo into ``~/.siada-cli/marketplaces/<name>``
           and read ``.claude-plugin/marketplace.json`` from the working tree.
           This naturally reuses the user's git credentials so private repos
           on enterprise GitLab/GitHub instances work.
        2. Fallback to anonymous HTTP/REST API (raw.githubusercontent.com /
           GitLab API v4) — only useful for fully public repos but kept for
           machines without a working ``git`` binary.
        """
        if installed_names is None:
            installed_names = set()

        repo_val = marketplace.get("repo", "")
        url_val = marketplace.get("url", "")
        ref_url = url_val or repo_val
        configured_path = marketplace.get("path", "skills")
        mp_name = marketplace.get("name", repo_val.split("/")[-1] if "/" in repo_val else repo_val)

        if not ref_url:
            return []

        # ── strategy 1: git clone (uses system git creds → handles private) ──
        local_dir = self._clone_or_pull(marketplace)
        if local_dir is not None:
            skills = self._read_local_marketplace(
                local_dir, configured_path, mp_name, repo_val, installed_names
            )
            if skills:
                return skills

        # ── detect provider for HTTP fallback ─────────────────────────────
        is_gitlab = False
        gitlab_host = ""
        gitlab_project = ""
        github_repo = ""

        if ref_url.startswith(("http://", "https://")):
            parsed = urlparse(ref_url)
            host = parsed.hostname or ""
            path_parts = parsed.path.strip("/").removesuffix(".git")
            if "github.com" in host:
                github_repo = path_parts
            else:
                is_gitlab = True
                gitlab_host = f"{parsed.scheme}://{host}"
                gitlab_project = path_parts
        elif "/" in ref_url and not ref_url.startswith("git@"):
            github_repo = ref_url.removesuffix(".git")
        else:
            return []

        # ── strategy 2 (fallback): try marketplace.json over HTTP ─────────
        marketplace_json = self._try_fetch_marketplace_json(
            github_repo, gitlab_host, gitlab_project, is_gitlab, marketplace
        )
        if marketplace_json is not None:
            skills = self._normalize_marketplace_json(marketplace_json, mp_name, repo_val, installed_names)
            if skills:
                return skills

        # ── strategy 3 (last resort): directory listing + SKILL.md ────────
        return self._fetch_by_directory_listing(
            github_repo, gitlab_host, gitlab_project, is_gitlab,
            configured_path, mp_name, repo_val, installed_names
        )


    # ── internal helpers ──────────────────────────────────────────────────

    @staticmethod
    def _normalize_clone_url(ref_url: str) -> str:
        """Normalize ``owner/repo`` shorthand to a clonable HTTPS GitHub URL.
        Leaves http(s)://, git@ and absolute paths untouched."""
        if not ref_url:
            return ref_url
        if ref_url.startswith(("http://", "https://", "git@")):
            return ref_url
        if "/" in ref_url and not ref_url.startswith(("./", "../", "/")):
            return f"https://github.com/{ref_url.removesuffix('.git')}.git"
        return ref_url

    def _local_clone_dir(self, marketplace: dict) -> Path:
        name = (
            marketplace.get("name")
            or (marketplace.get("repo") or marketplace.get("url") or "")
              .rstrip("/").split("/")[-1].removesuffix(".git")
            or "marketplace"
        )
        # Sanitize: keep only safe filename chars
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", name) or "marketplace"
        return SIADA_HOME / "marketplaces" / safe

    @staticmethod
    def _https_to_ssh(url: str) -> str | None:
        """Convert ``https://host/owner/repo(.git)`` to ``git@host:owner/repo.git``.
        Returns ``None`` if the URL isn't an https URL with at least one path
        segment."""
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

    def _clone_or_pull(self, marketplace: dict) -> Path | None:
        """Shallow-clone (or fast-update) the marketplace repo into
        ``~/.siada-cli/marketplaces/<name>``. Returns the local path on
        success, or ``None`` if git is unavailable / clone fails.

        Uses the system ``git`` binary so SSH keys, credential helpers and
        ``~/.netrc`` are picked up automatically — required for private
        enterprise repos.

        For HTTPS URLs we automatically retry with the equivalent ``git@``
        SSH URL when HTTPS auth fails (mirrors Claude Code's behaviour)."""
        ref_url = marketplace.get("url") or marketplace.get("repo") or ""
        if not ref_url:
            return None
        clone_url = self._normalize_clone_url(ref_url)
        # Local filesystem path → just return it directly
        if clone_url.startswith(("/", "./", "../")):
            p = Path(clone_url).expanduser()
            return p if p.is_dir() else None

        branch = marketplace.get("branch") or "main"
        local_dir = self._local_clone_dir(marketplace)
        local_dir.parent.mkdir(parents=True, exist_ok=True)

        # Disable interactive credential / SSH prompts so a misconfigured
        # machine fails fast instead of hanging the UI thread.
        env = {
            **__import__("os").environ,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "/bin/echo",
            "GIT_SSH_COMMAND": __import__("os").environ.get(
                "GIT_SSH_COMMAND",
                "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new",
            ),
        }

        ssh_url = self._https_to_ssh(clone_url)
        # Try HTTPS first, then SSH (covers users with SSH-only access to
        # private enterprise GitLab/GitHub instances).
        candidate_urls = [clone_url] + ([ssh_url] if ssh_url else [])

        if (local_dir / ".git").exists():
            # Try to fast-update existing clone
            try:
                fetch = subprocess.run(
                    ["git", "-C", str(local_dir), "fetch", "--depth=1",
                     "--prune", "origin", branch],
                    capture_output=True, timeout=60, env=env,
                )
                if fetch.returncode == 0:
                    subprocess.run(
                        ["git", "-C", str(local_dir), "reset", "--hard",
                         f"origin/{branch}"],
                        capture_output=True, timeout=30, env=env,
                    )
                    return local_dir
            except FileNotFoundError:
                logger.warning("git binary not found; skipping marketplace clone")
                return None
            except Exception as e:
                logger.warning(f"marketplace fetch failed for {clone_url}: {e}")
            # fetch/reset failed → re-clone fresh
            shutil.rmtree(local_dir, ignore_errors=True)

        def _clone(url: str, br: str | None) -> tuple[int, str]:
            args = ["git", "clone", "--depth=1"]
            if br:
                args.extend(["--branch", br, "--single-branch"])
            args.extend([url, str(local_dir)])
            try:
                r = subprocess.run(args, capture_output=True, timeout=120, env=env)
                return r.returncode, r.stderr.decode("utf-8", errors="replace")
            except FileNotFoundError:
                return -1, "git binary not found"
            except subprocess.TimeoutExpired:
                return -1, "git clone timed out"

        last_err = ""
        for url in candidate_urls:
            for br in ([branch, "main", "master"] if branch != "main" else ["main", "master"]):
                shutil.rmtree(local_dir, ignore_errors=True)
                rc, err = _clone(url, br)
                if rc == 0:
                    return local_dir
                last_err = err
            # Try without --branch (let git pick HEAD)
            shutil.rmtree(local_dir, ignore_errors=True)
            rc, err = _clone(url, None)
            if rc == 0:
                return local_dir
            last_err = err

        shutil.rmtree(local_dir, ignore_errors=True)
        logger.warning(
            f"git clone failed for marketplace '{marketplace.get('name')}' "
            f"(tried: {', '.join(candidate_urls)}): {last_err.strip()[:300]}"
        )
        return None


    def _read_local_marketplace(
        self, local_dir: Path, configured_path: str,
        mp_name: str, repo_val: str, installed_names: set,
    ) -> list[dict]:
        """Read ``.claude-plugin/marketplace.json`` from a cloned repo,
        falling back to a directory listing of ``configured_path`` (or repo
        root) with SKILL.md descriptions."""
        # Preferred: marketplace.json manifest
        manifest = local_dir / ".claude-plugin" / "marketplace.json"
        if manifest.exists():
            try:
                payload = json.loads(manifest.read_text(encoding="utf-8"))
                skills = self._normalize_marketplace_json(
                    payload, mp_name, repo_val, installed_names
                )
                if skills:
                    return skills
            except Exception as e:
                logger.warning(f"Failed to parse {manifest}: {e}")

        # Fallback: list directories under configured_path
        candidates: list[Path] = []
        if configured_path:
            candidates.append(local_dir / configured_path)
        candidates.append(local_dir)

        skills_dir: Path | None = None
        for cand in candidates:
            if cand.is_dir():
                skills_dir = cand
                break
        if skills_dir is None:
            return []

        skill_names: list[str] = []
        for child in sorted(skills_dir.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            # Heuristic: only count it as a skill if it has SKILL.md or
            # .claude-plugin/plugin.json — avoids picking up unrelated dirs
            # at repo root (e.g. docs/, tests/).
            if (skills_dir == local_dir and
                not (child / "SKILL.md").exists() and
                not (child / ".claude-plugin" / "plugin.json").exists()):
                continue
            skill_names.append(child.name)

        skills: list[dict] = []
        for name in skill_names:
            description = ""
            md = skills_dir / name / "SKILL.md"
            if md.exists():
                try:
                    description = self._parse_description(
                        md.read_text(encoding="utf-8", errors="replace")
                    )
                except Exception:
                    pass
            skills.append({
                "name": name,
                "description": description or f"Skill from {mp_name}",
                "marketplace": repo_val,
                "marketplaceName": mp_name,
                "installed": name in installed_names,
                "installs": "",
            })
        return skills

    def _fetch_url(self, url: str, headers: dict | None = None, timeout: int = 8) -> bytes | None:

        try:
            req = urllib.request.Request(url, headers=headers or {"User-Agent": "siada-cli"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:
            return None

    def _try_fetch_marketplace_json(
        self, github_repo: str, gitlab_host: str, gitlab_project: str,
        is_gitlab: bool, marketplace: dict
    ) -> dict | None:
        branch = marketplace.get("branch", "main")
        if is_gitlab:
            encoded_proj = quote(gitlab_project, safe="")
            for branch_name in (branch, "main", "master"):
                encoded_file = quote(".claude-plugin/marketplace.json", safe="")
                url = (
                    f"{gitlab_host}/api/v4/projects/{encoded_proj}/repository/files"
                    f"/{encoded_file}/raw?ref={quote(branch_name)}"
                )
                data = self._fetch_url(url)
                if data:
                    try:
                        return json.loads(data.decode("utf-8", errors="replace"))
                    except Exception:
                        pass
        elif github_repo:
            for branch_name in (branch, "main", "master"):
                url = (
                    f"https://raw.githubusercontent.com/{github_repo}"
                    f"/{branch_name}/.claude-plugin/marketplace.json"
                )
                data = self._fetch_url(url)
                if data:
                    try:
                        return json.loads(data.decode("utf-8", errors="replace"))
                    except Exception:
                        pass
        return None

    def _normalize_marketplace_json(
        self, payload: dict, mp_name: str, repo_val: str, installed_names: set
    ) -> list[dict]:
        items = payload.get("skills") or payload.get("plugins") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return []
        skills = []
        for item in items:
            if not isinstance(item, dict):
                continue
            skill_name = item.get("name") or item.get("id") or item.get("slug")
            if not skill_name:
                continue

            # Claude Code plugin-bundle format: a plugin item may contain a
            # "skills" array of individual skill paths (e.g. "./skills/webapp-testing").
            # Expand each path into a standalone skill entry so users can see
            # and install them individually.
            nested_skills = item.get("skills")
            if isinstance(nested_skills, list) and nested_skills:
                for skill_path in nested_skills:
                    if not isinstance(skill_path, str):
                        continue
                    # Derive skill name from the last path component
                    sub_name = skill_path.rstrip("/").split("/")[-1].lstrip(".")
                    if not sub_name:
                        continue
                    # Normalize: "./skills/webapp-testing" → "skills/webapp-testing"
                    source_path = skill_path.lstrip("./").strip("/") or None
                    entry: dict = {
                        "name": sub_name,
                        "description": f"Skill from {mp_name} ({skill_name})",
                        "marketplace": repo_val,
                        "marketplaceName": mp_name,
                        "installed": sub_name in installed_names,
                        "installs": "",
                    }
                    if source_path:
                        entry["source_path"] = source_path
                    skills.append(entry)
                continue

            source_url = None
            source_ref = None
            source_path = None
            source = item.get("source")
            if isinstance(source, dict):
                source_url = source.get("url")
                source_ref = source.get("ref")
            elif isinstance(source, str) and source:
                # Relative path within the same repo, e.g. "./plugins/hookify"
                normalized = source.lstrip("./").strip("/")
                if normalized and "/" in normalized:
                    # e.g. "plugins/hookify" — store full relative path
                    source_path = normalized
                elif normalized:
                    source_path = normalized
            entry = {
                "name": skill_name,
                "description": item.get("description", "") or f"Skill from {mp_name}",
                "marketplace": repo_val,
                "marketplaceName": mp_name,
                "installed": skill_name in installed_names,
                "installs": str(item.get("installs", "")) if item.get("installs") is not None else "",
            }
            if source_url:
                entry["source_url"] = source_url
            if source_ref:
                entry["source_ref"] = source_ref
            if source_path:
                entry["source_path"] = source_path
            skills.append(entry)
        return skills

    def _fetch_by_directory_listing(
        self, github_repo: str, gitlab_host: str, gitlab_project: str,
        is_gitlab: bool, configured_path: str, mp_name: str, repo_val: str,
        installed_names: set
    ) -> list[dict]:
        list_dirs = (
            (lambda path: self._list_dirs_gitlab(gitlab_host, gitlab_project, path))
            if is_gitlab
            else (lambda path: self._list_dirs_github(github_repo, path))
        )
        fetch_desc = (
            (lambda skill, actual_path: self._fetch_skill_md_gitlab(
                gitlab_host, gitlab_project, actual_path, skill))
            if is_gitlab
            else (lambda skill, actual_path: self._fetch_skill_md_github(
                github_repo, actual_path, skill))
        )

        skill_names = list_dirs(configured_path)
        actual_path = configured_path

        if not skill_names:
            root_dirs = list_dirs("")
            for container in root_dirs:
                sub_dirs = list_dirs(container)
                if sub_dirs:
                    skill_names = sub_dirs
                    actual_path = container
                    break
            if not skill_names:
                skill_names = root_dirs
                actual_path = ""

        if not skill_names:
            return []

        skills = []
        for skill_name in skill_names:
            description = ""
            try:
                description = fetch_desc(skill_name, actual_path)
            except Exception:
                pass
            skills.append({
                "name": skill_name,
                "description": description or f"Skill from {mp_name}",
                "marketplace": repo_val,
                "marketplaceName": mp_name,
                "installed": skill_name in installed_names,
                "installs": "",
            })
        return skills

    def _list_dirs_github(self, repo: str, path: str) -> list[str]:
        url = f"https://api.github.com/repos/{repo}/contents/{path}"
        data = self._fetch_url(url, {"User-Agent": "siada-cli", "Accept": "application/vnd.github.v3+json"})
        if not data:
            return []
        try:
            entries = json.loads(data)
            return [e["name"] for e in entries if e.get("type") == "dir" and not e["name"].startswith(".")]
        except Exception:
            return []

    def _list_dirs_gitlab(self, host: str, project: str, path: str) -> list[str]:
        encoded = quote(project, safe="")
        results = []
        page = 1
        while True:
            url = (
                f"{host}/api/v4/projects/{encoded}/repository/tree"
                f"?path={quote(path)}&per_page=100&page={page}&recursive=false"
            )
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "siada-cli"})
                with urllib.request.urlopen(req, timeout=8) as r:
                    data = r.read()
                    next_page = r.headers.get("X-Next-Page", "")
            except Exception:
                break
            try:
                entries = json.loads(data)
                results.extend(
                    e["name"] for e in entries
                    if e.get("type") == "tree" and not e["name"].startswith(".")
                )
            except Exception:
                break
            if not next_page:
                break
            page += 1
        return results

    def _fetch_skill_md_github(self, repo: str, actual_path: str, skill: str) -> str:
        prefix = f"{actual_path}/{skill}" if actual_path else skill
        url = f"https://raw.githubusercontent.com/{repo}/HEAD/{prefix}/SKILL.md"
        data = self._fetch_url(url, timeout=5)
        return self._parse_description(data.decode("utf-8", errors="replace")) if data else ""

    def _fetch_skill_md_gitlab(
        self, host: str, project: str, actual_path: str, skill: str
    ) -> str:
        prefix = f"{actual_path}/{skill}" if actual_path else skill
        encoded_proj = quote(project, safe="")
        encoded_file = quote(f"{prefix}/SKILL.md", safe="")
        url = f"{host}/api/v4/projects/{encoded_proj}/repository/files/{encoded_file}/raw"
        data = self._fetch_url(url, timeout=5)
        return self._parse_description(data.decode("utf-8", errors="replace")) if data else ""

    @staticmethod
    def _parse_description(content: str) -> str:
        in_fm = False
        for line in content.splitlines():
            if line.strip() == "---":
                in_fm = not in_fm
                continue
            if in_fm and line.startswith("description:"):
                return line[len("description:"):].strip().strip('"').strip("'")
        return ""

    @staticmethod
    def _mp_matches(mp: dict, query: str) -> bool:
        q = query.strip().lstrip("@")
        for field_name in ("name", "repo", "url"):
            val = mp.get(field_name, "")
            if val == q:
                return True
            if val.rstrip("/").removesuffix(".git") == q.removesuffix(".git"):
                return True
        return False
