"""Install the proxy + extension into ~/.siada-cli/browser/.

Two sources:
  - A chrome-acp checkout (``install_proxy/install_extension``): copy
    dist/public/package.json, then ``npm install --omit=dev`` in the staging
    dir. The repo's bun workspace node_modules cannot be copied — it
    symlinks into the repo-root .bun store and drops transitive deps.
  - BOS tarball/zip (``install_*_from_bos``): artifacts produced by the
    chrome-acp CI (``just pack``), sha256-verified. This is what end users
    get via ``siada-browser setup`` (no repo) and the installer's
    ``--with-browser`` flag, with ``--base-url`` pointing at an artifact host.

The proxy tarball ships per-platform variants (``...-{version}-{tag}.tar.gz``,
tag e.g. ``macos-arm64``/``linux-x64``/``windows-x64``) bundling that
platform's native @parcel/watcher binary, plus an un-suffixed noarch fallback
(pure JS; the watcher degrades to fs.watch). Platform build is preferred,
noarch is the fallback.
"""

from __future__ import annotations

import hashlib
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from siada.browser_addon import paths

# Prebuilt chrome-acp artifact host. Empty in the open-source build: build the
# proxy/extension from the chrome-acp/ directory, or pass --base-url to an
# artifact host that serves the packed tarballs.
DEFAULT_BOS_BASE = ""

_PROXY_ITEMS = ("dist", "public", "package.json")
_EXT_ITEMS = ("manifest.json", "icons", "rules", "dist")


def _replace_dir(target: Path, stage: Path) -> None:
    """Swap ``stage`` into ``target`` atomically-ish (rm old, rename new)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        old = target.with_name(target.name + ".old")
        shutil.rmtree(old, ignore_errors=True)
        shutil.move(str(target), str(old))
        shutil.rmtree(old, ignore_errors=True)
    stage.rename(target)


def install_proxy(repo: Path) -> None:
    src = Path(repo).expanduser() / "packages" / "proxy-server"
    if not (src / "dist" / "cli" / "bin.js").is_file():
        raise FileNotFoundError(f"{src / 'dist'} not built — run `bun run build:proxy` in {repo}")

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
        npm + ["install", "--omit=dev", "--no-audit", "--no-fund", "--loglevel=error"],
        cwd=str(stage), check=True, timeout=300,
    )
    _replace_dir(paths.proxy_dir(), stage)


def install_extension(repo: Path) -> None:
    src = Path(repo).expanduser() / "packages" / "chrome-extension"
    if not (src / "manifest.json").is_file():
        raise FileNotFoundError(f"missing {src / 'manifest.json'}")

    # Fixed destination: Chrome pins the absolute path of load-unpacked
    # extensions, so updates must replace the contents in place.
    dst = paths.extension_dir()
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
    _replace_dir(dst, stage)


# ---------------------------------------------------------------------------
# BOS artifacts (produced by the chrome-acp CI ``just pack`` job)
# ---------------------------------------------------------------------------

_ARCH_ALIASES = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}


def proxy_platform_tag() -> str | None:
    """Platform tag of the per-platform proxy tarballs, matching the siada
    venv tarball naming (``macos-arm64`` / ``linux-x64`` / ``windows-x64``).
    None for unsupported platforms (caller falls back to the noarch tarball)."""
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
    with urllib.request.urlopen(url, timeout=15) as resp:
        return resp.read().decode().strip()


def _download_file(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=300) as resp, open(dest, "wb") as f:
        shutil.copyfileobj(resp, f)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download_verified(base: str, filename: str, dest: Path) -> None:
    """Download ``base/filename`` and verify against ``base/filename.sha256``."""
    expected = _fetch_text(f"{base}/{filename}.sha256").split()[0]
    _download_file(f"{base}/{filename}", dest)
    actual = _sha256(dest)
    if actual != expected:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"SHA256 mismatch for {filename}: expected {expected}, got {actual}")


def _bos_version(base: str) -> str:
    return _fetch_text(f"{base}/latest_version")


def install_proxy_from_bos(base: str | None = None) -> str:
    """Download + verify + unpack the prebuilt proxy tarball. Returns version.

    Prefers the per-platform tarball (bundles that platform's native
    @parcel/watcher binary); falls back to the un-suffixed noarch tarball
    (pure JS, watcher degrades to fs.watch) when the platform build is absent.
    A sha256 mismatch on an existing artifact is never silently downgraded.
    """
    base = base or DEFAULT_BOS_BASE
    version = _bos_version(base)
    tag = proxy_platform_tag()
    names = [f"chrome-acp-proxy-{version}-{tag}.tar.gz"] if tag else []
    names.append(f"chrome-acp-proxy-{version}.tar.gz")

    last_err: OSError | None = None
    for filename in names:
        try:
            _install_proxy_archive(base, filename)
            return version
        except RuntimeError:
            raise  # sha256 mismatch / bad layout on an existing artifact
        except OSError as e:  # artifact missing for this platform → next candidate
            last_err = e
    raise RuntimeError(
        f"no downloadable chrome-acp proxy tarball for version {version}"
    ) from last_err


def _install_proxy_archive(base: str, filename: str) -> None:
    # Tarball root dir matches the tarball basename (see build_chrome_acp.sh)
    root = filename[: -len(".tar.gz")]
    # Windows AV scanners may briefly lock freshly downloaded files in %TEMP%;
    # a leftover temp dir must not fail the install.
    with tempfile.TemporaryDirectory(
        prefix="chrome-acp-proxy-", ignore_cleanup_errors=True
    ) as tmp:
        archive = Path(tmp) / filename
        _download_verified(base, filename, archive)
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(tmp, filter="data")
        stage = paths.browser_home() / "proxy.staging"
        shutil.rmtree(stage, ignore_errors=True)
        shutil.move(str(Path(tmp) / root), str(stage))
    if not (stage / "dist" / "cli" / "bin.js").is_file():
        raise RuntimeError(f"tarball layout unexpected: no dist/cli/bin.js in {filename}")
    _replace_dir(paths.proxy_dir(), stage)


def install_extension_from_bos(base: str | None = None) -> str:
    """Download + verify + unpack the extension zip. Returns version."""
    base = base or DEFAULT_BOS_BASE
    version = _bos_version(base)
    filename = f"chrome-acp-extension-{version}.zip"

    # Windows AV scanners may briefly lock freshly downloaded files in %TEMP%;
    # a leftover temp dir must not fail the install.
    with tempfile.TemporaryDirectory(
        prefix="chrome-acp-ext-", ignore_cleanup_errors=True
    ) as tmp:
        archive = Path(tmp) / filename
        _download_verified(base, filename, archive)
        stage = paths.browser_home() / "extension.staging"
        shutil.rmtree(stage, ignore_errors=True)
        stage.mkdir(parents=True)
        # Zip entries are at the root: manifest.json, icons/, rules/, dist/
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(stage)
    if not (stage / "manifest.json").is_file():
        raise RuntimeError(f"zip layout unexpected: no manifest.json at root of {filename}")
    _replace_dir(paths.extension_dir(), stage)
    return version
