"""Install a versioned platform ZIP from a public GitHub release."""

from __future__ import annotations

from importlib.metadata import version as package_version
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
import urllib.parse
import zipfile

from siada.browser_addon import installer, manager, paths
from siada.foundation.node_runtime import NODE_VERSION, runtime_node

RELEASE_BASE = "https://github.com/liauto-siada/siada-cli/releases/download"


def _extract(archive: Path, target: Path) -> None:
    """Extract regular files and directories, rejecting links and unsafe paths."""
    with zipfile.ZipFile(archive) as zf:
        for entry in zf.infolist():
            name = PurePosixPath(entry.filename)
            mode = entry.external_attr >> 16
            if (
                name.is_absolute() or ".." in name.parts
                or "\\" in entry.filename or ":" in entry.filename
                or not name.parts or name.parts[0] not in {"runtime", "proxy", "extension"}
                or stat.S_ISLNK(mode)
                or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)
            ):
                raise RuntimeError("Unsafe browser archive member")
            dest = target.joinpath(*name.parts)
            if entry.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(entry) as source, dest.open("wb") as output:
                    shutil.copyfileobj(source, output)
                if os.name != "nt":
                    dest.chmod(0o755 if mode & 0o111 else 0o644)


def _validate(stage: Path, node_version: str) -> None:
    for kind, required in (
        ("proxy", (*installer._PROXY_ITEMS, "node_modules", "dist/cli/bin.js", "public/index.html")),
        ("extension", (*installer._EXT_ITEMS, "dist/background.js")),
    ):
        package = stage / kind
        installer._require_license_files(package)
        for item in required:
            if not (package / item).exists():
                raise RuntimeError(f"Incomplete browser package: {kind}/{item}")
    node = runtime_node(stage / "runtime")
    license_file = stage / "runtime" / "LICENSE"
    if not node.is_file() or not license_file.is_file() or not license_file.read_bytes().strip():
        raise RuntimeError("Incomplete Node runtime or license")
    result = subprocess.run(
        [str(node), "--version"], check=True, capture_output=True, text=True, timeout=30,
    )
    if result.stdout.strip() != f"v{node_version}":
        raise RuntimeError("Node runtime version mismatch")
    subprocess.run(
        [str(node), str(stage / "proxy/dist/cli/bin.js"), "--help"],
        cwd=stage / "proxy", check=True, capture_output=True, timeout=60,
    )


def _commit(stage: Path, metadata: dict) -> None:
    """Replace all components with rollback, leaving connection state intact."""
    home = paths.browser_home()
    was_running = manager.is_running()
    stopped = manager.stop()
    if str(stopped).startswith("error"):
        raise RuntimeError(f"Could not stop browser proxy: {stopped}")
    moved: list[str] = []
    installed: list[str] = []
    with tempfile.TemporaryDirectory(prefix=".browser-backup-", dir=home) as backup_dir:
        backup = Path(backup_dir)
        try:
            for name in ("runtime", "proxy", "extension", "installed.json"):
                target = home / name
                if target.exists():
                    target.rename(backup / name)
                    moved.append(name)
                installed.append(name)
                if name == "installed.json":
                    target.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
                else:
                    (stage / name).rename(target)
        except Exception:
            for name in reversed(installed):
                target = home / name
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink(missing_ok=True)
            for name in reversed(moved):
                (backup / name).rename(home / name)
            if was_running:
                manager.start()
            raise


def install_release(base_url: str | None = None) -> str:
    """Download the platform package matching the installed CLI version."""
    version = package_version("siada-cli")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?", version):
        raise RuntimeError("No release version available; install from a built checkout")
    base = (base_url or f"{RELEASE_BASE}/v{version}").rstrip("/")
    url = urllib.parse.urlsplit(base)
    if url.scheme != "https" or not url.netloc or url.query or url.fragment:
        raise ValueError("Browser artifact base URL must be an HTTPS directory URL")
    manifest = json.loads(installer._fetch_text(f"{base}/browser-manifest.json"))
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != 1
        or manifest.get("version") != version
    ):
        raise RuntimeError("Browser manifest schema or CLI version mismatch")
    node_version = manifest.get("node_version")
    if node_version != NODE_VERSION:
        raise RuntimeError("Browser manifest Node version mismatch")
    tag = installer.proxy_platform_tag()
    platforms = manifest.get("platforms")
    entry = platforms.get(tag) if isinstance(platforms, dict) else None
    if not tag or not isinstance(entry, dict):
        raise RuntimeError(f"No browser package for platform {tag or 'unsupported'}")
    filename = f"siada-browser-{version}-{tag}.zip"
    digest = entry.get("sha256")
    if (
        entry.get("filename") != filename
        or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-fA-F]{64}", digest)
    ):
        raise RuntimeError("Invalid browser artifact filename or SHA-256")
    home = paths.browser_home()
    home.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".browser-install-", dir=home, ignore_cleanup_errors=True,
    ) as temp:
        archive = Path(temp) / filename
        installer._download_file(f"{base}/{filename}", archive)
        if installer._sha256(archive) != digest.lower():
            raise RuntimeError("Browser package SHA256 mismatch")
        stage = Path(temp) / "stage"
        stage.mkdir()
        try:
            _extract(archive, stage)
        except zipfile.BadZipFile as exc:
            raise RuntimeError("Invalid browser ZIP archive") from exc
        _validate(stage, node_version)
        _commit(stage, {
            "version": version, "platform": tag, "node_version": node_version,
            "filename": filename, "sha256": digest.lower(),
        })
    return version