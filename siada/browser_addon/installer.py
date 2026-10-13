"""Install a built checkout and provide transport helpers for release ZIPs."""

from __future__ import annotations

import hashlib
import platform
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from siada.browser_addon import paths

_PROXY_ITEMS = (
    "dist", "public", "package.json", "package-lock.json",
    "LICENSE", "THIRD_PARTY_NOTICES.md",
)
_EXT_ITEMS = ("manifest.json", "icons", "rules", "dist", "LICENSE", "THIRD_PARTY_NOTICES.md")


def _require_license_files(package: Path) -> None:
    """Reject packages that would drop redistribution notices."""
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        notice = package / name
        if not notice.is_file() or not notice.read_bytes().strip():
            raise RuntimeError(f"missing or empty {name} in browser package {package.name}")


def _replace_dir(target: Path, stage: Path) -> None:
    """Replace a source installation while preserving its previous copy on failure."""
    target.parent.mkdir(parents=True, exist_ok=True)
    old = target.with_name(target.name + ".old")
    shutil.rmtree(old, ignore_errors=True)
    if target.exists():
        target.rename(old)
    try:
        stage.rename(target)
    except OSError:
        if old.exists():
            old.rename(target)
        raise
    shutil.rmtree(old, ignore_errors=True)


def install_proxy(repo: Path) -> None:
    """Copy a built proxy and install production dependencies from its lock."""
    src = Path(repo).expanduser() / "packages" / "proxy-server"
    if not (src / "dist" / "cli" / "bin.js").is_file():
        raise FileNotFoundError(f"{src / 'dist'} not built — run `bun run build:proxy` in {repo}")
    _require_license_files(src)
    stage = paths.browser_home() / "proxy.staging"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    for item in _PROXY_ITEMS:
        if not (src / item).exists():
            raise FileNotFoundError(f"missing {src / item}")
        if (src / item).is_dir():
            shutil.copytree(src / item, stage / item)
        else:
            shutil.copy2(src / item, stage / item)
    npm = paths.npm_argv()
    if npm is None:
        raise RuntimeError("npm not found (needed for the proxy's production dependencies)")
    subprocess.run(
        npm + ["ci", "--omit=dev", "--ignore-scripts", "--no-audit", "--no-fund", "--loglevel=error"],
        cwd=str(stage), check=True, timeout=300,
    )
    _replace_dir(paths.proxy_dir(), stage)


def install_extension(repo: Path) -> None:
    """Install the built extension at Chrome's fixed unpacked directory."""
    src = Path(repo).expanduser() / "packages" / "chrome-extension"
    if not (src / "manifest.json").is_file():
        raise FileNotFoundError(f"missing {src / 'manifest.json'}")
    _require_license_files(src)
    stage = paths.browser_home() / "extension.staging"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    for item in _EXT_ITEMS:
        if not (src / item).exists():
            raise FileNotFoundError(f"missing {src / item}")
        if (src / item).is_dir():
            shutil.copytree(src / item, stage / item)
        else:
            shutil.copy2(src / item, stage / item)
    _replace_dir(paths.extension_dir(), stage)


_ARCH_ALIASES = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}


def proxy_platform_tag() -> str | None:
    """Return the manifest platform key for a supported OS and architecture."""
    if sys.platform == "darwin":
        os_part = "macos"
    elif sys.platform.startswith("win"):
        os_part = "windows"
    elif sys.platform.startswith("linux"):
        os_part = "linux"
    else:
        return None
    arch = _ARCH_ALIASES.get(platform.machine().lower())
    return f"{os_part}-{arch}" if arch else None


def _fetch_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=15) as response:
        return response.read().decode().strip()


def _download_file(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=300) as response, dest.open("wb") as output:
        shutil.copyfileobj(response, output)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()