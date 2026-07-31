"""Feishu media resource download and processing utilities.

Handles:
- Extracting media keys (image_key / file_key) from raw Feishu message content
- Downloading resources via lark-oapi im.v1.message_resource.get API
- Key-based file caching under session directory (avoids repeated downloads)
- Classifying downloads: image / document / video (video is skipped)
- Building multimodal TResponseInputItem lists for agent input

Caching strategy:
  When ``cache_dir`` is supplied to ``download_message_resource``, the file
  is saved as ``<cache_dir>/<file_key><ext>`` with a ``<file_key>.meta``
  sidecar (JSON: ``{"path": ..., "content_type": ...}``).  A cache-hit check
  is performed before every network call, so repeated references to the same
  attachment (e.g. the user re-sends an image in the same session) cost zero
  extra bandwidth.

  When ``cache_dir`` is None (legacy / test path) the file falls back to a
  temporary file via ``tempfile.mkstemp``.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("siada.im.lark.media")


class _UnsupportedResourceError(Exception):
    """Raised when Feishu returns error 234043.

    Error 234043 means the resource belongs to a merged-forward sub-message
    or a card message — the API refuses to serve it by design.  Raised here
    so ``_download_with_type`` can abort all retries immediately.
    """


@dataclass
class DownloadedMedia:
    """A successfully downloaded Feishu media resource."""

    key: str            # original image_key / file_key
    path: str           # local file path (session cache or temp)
    content_type: str   # MIME type (e.g. "image/jpeg")
    is_image: bool
    is_video: bool      # videos are excluded from agent input
    is_document: bool
    cached: bool = False  # True when loaded from session cache (skip cleanup)


def extract_media_keys_from_message(
    raw_content: str, msg_type: str
) -> List[tuple]:
    """Extract (file_key, resource_type) pairs from raw Feishu message content.

    Rules:
    - video / media / audio / sticker → skip entirely (return empty list)
      (Feishu API does not support downloading sticker/emoji resources)
    - image            → image_key with resource_type "image"
    - file             → file_key  with resource_type "file"
    - post             → scan content nodes for "img" tags → image_key with "image"

    Returns:
        List of (key, resource_type) tuples ready for API download.
    """
    # Skip video, media, audio, and sticker entirely — Feishu API refuses sticker downloads
    if msg_type in ("video", "media", "audio", "sticker"):
        return []

    try:
        data = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
    except (json.JSONDecodeError, TypeError):
        return []

    if not isinstance(data, dict):
        return []

    pairs: List[tuple] = []

    if msg_type == "image":
        key = data.get("image_key", "")
        if key:
            pairs.append((key, "image"))

    elif msg_type == "file":
        key = data.get("file_key", "")
        if key:
            pairs.append((key, "file"))

    elif msg_type == "post":
        # Rich text: scan content nodes for "img" tags.
        # Support both formats:
        #   locale-wrapped: {"zh_cn": {"title": "", "content": [[...]]}}
        #   direct (no locale): {"title": "", "content": [[...]]}
        if isinstance(data.get("content"), list):
            # Direct format — content is at the top level
            locale_items = [data]
        else:
            # Locale-wrapped format — gather all locale dicts
            locale_items = [v for v in data.values() if isinstance(v, dict)]

        for locale_data in locale_items:
            for line in locale_data.get("content", []):
                for element in line:
                    tag = element.get("tag", "")
                    if tag == "img":
                        img_key = element.get("image_key", "")
                        if img_key:
                            pairs.append((img_key, "image"))
            break  # Use first locale only

    return pairs


# ── Cache helpers ──────────────────────────────────────────────────────────────


def _load_from_cache(cache_dir: Path, file_key: str) -> Optional[DownloadedMedia]:
    """Return a DownloadedMedia from the session cache, or None on miss.

    Cache layout:
      <cache_dir>/<file_key><ext>        — actual bytes
      <cache_dir>/<file_key>.meta        — JSON with path + content_type
    """
    meta_path = cache_dir / f"{file_key}.meta"
    if not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        file_path = Path(meta["path"])
        if not file_path.exists():
            # Stale cache entry — remove meta so next call re-downloads
            try:
                meta_path.unlink(missing_ok=True)
            except OSError:
                pass
            return None
        content_type = meta["content_type"]
        is_image = content_type.startswith("image/")
        is_video = content_type.startswith("video/") or content_type.startswith("audio/")
        is_document = not is_image and not is_video
        logger.info("Cache hit for media key=%s: %s", file_key, file_path)
        return DownloadedMedia(
            key=file_key,
            path=str(file_path),
            content_type=content_type,
            is_image=is_image,
            is_video=is_video,
            is_document=is_document,
            cached=True,
        )
    except Exception as exc:
        logger.warning("Failed to read cache meta for key=%s: %s", file_key, exc)
        return None


def _save_to_cache(
    raw_bytes: bytes,
    content_type: str,
    file_key: str,
    cache_dir: Path,
) -> Optional[str]:
    """Write bytes to the session cache dir.  Returns the saved path or None."""
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        suffix = _get_suffix_for_mime(content_type)
        file_path = cache_dir / f"{file_key}{suffix}"
        file_path.write_bytes(raw_bytes)
        # Write meta sidecar
        meta = {"path": str(file_path), "content_type": content_type}
        (cache_dir / f"{file_key}.meta").write_text(
            json.dumps(meta), encoding="utf-8"
        )
        logger.info(
            "Cached media: key=%s, path=%s, size=%d bytes",
            file_key, file_path, len(raw_bytes),
        )
        return str(file_path)
    except Exception as exc:
        logger.warning(
            "Failed to save media to session cache: key=%s, error=%s",
            file_key, exc,
        )
        return None


def _save_to_temp(raw_bytes: bytes, content_type: str) -> Optional[str]:
    """Write bytes to a temporary file.  Returns the path or None."""
    suffix = _get_suffix_for_mime(content_type)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix="feishu_media_")
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(raw_bytes)
        return tmp_path
    except Exception:
        try:
            os.close(tmp_fd)
        except OSError:
            pass
        return None


# ── Download API ───────────────────────────────────────────────────────────────


async def download_message_resource(
    lark_client,
    message_id: str,
    file_key: str,
    resource_type: str,
    *,
    cache_dir: Optional[Path] = None,
) -> Optional[DownloadedMedia]:
    """Download a Feishu message resource, with session-dir caching.

    Args:
        lark_client:   lark-oapi Client instance
        message_id:    Feishu message ID (e.g. "om_...")
        file_key:      image_key or file_key from the message content
        resource_type: "image" | "file" (Feishu API query param "type")
        cache_dir:     Directory for persistent key-based file cache.
                       When provided, a cache-hit skips the network call;
                       downloaded files are stored here for future reuse.
                       When None, falls back to a one-time temp file.

    Returns:
        DownloadedMedia on success, None on failure or if classified as video/audio.
    """
    # Cache-hit check (before any network call)
    if cache_dir is not None:
        cached = _load_from_cache(cache_dir, file_key)
        if cached is not None:
            return cached

    try:
        return await _try_single_download(
            lark_client, message_id, file_key, resource_type, cache_dir=cache_dir,
        )
    except _UnsupportedResourceError as exc:
        # Feishu refused (code 234043) — abort
        logger.info("Skipping unsupported resource: %s", exc)
        return None


async def _try_single_download(
    lark_client,
    message_id: str,
    file_key: str,
    resource_type: str,
    *,
    cache_dir: Optional[Path] = None,
) -> Optional[DownloadedMedia]:
    """Make one API call to download a resource.  Returns None on any failure."""
    try:
        from lark_oapi.api.im.v1 import GetMessageResourceRequest

        request = (
            GetMessageResourceRequest.builder()
            .message_id(message_id)
            .file_key(file_key)
            .type(resource_type)
            .build()
        )

        response = await asyncio.to_thread(
            lark_client.im.v1.message_resource.get, request
        )

        # Standard success check — works for binary responses per SDK contract
        if not response.success():
            # Error 234043: merged-forward sub-message or card-message resource.
            # The API refuses to serve these by design — abort all type retries.
            if response.code == 234043:
                raise _UnsupportedResourceError(
                    f"merged-forward/card resource is not downloadable "
                    f"(code=234043): key={file_key}, msg={response.msg}"
                )
            logger.info(
                "Download attempt failed: key=%s, type=%s, code=%s, msg=%s",
                file_key, resource_type, response.code, response.msg,
            )
            return None

        # Get binary content from the file-like object (SDK contract)
        file_obj = getattr(response, "file", None)
        file_name: str = getattr(response, "file_name", None) or ""

        if file_obj is None:
            logger.warning("No file object in response for resource key=%s", file_key)
            return None

        raw_bytes: bytes = file_obj.read()
        if not raw_bytes:
            logger.warning("Empty content for resource key=%s", file_key)
            return None

        # Per official docs: Content-Type is authoritative in the response header.
        # Fall back to filename-extension inference only when the header is absent.
        content_type = "application/octet-stream"
        raw_resp = getattr(response, "raw", None)
        if raw_resp is not None:
            headers: dict = getattr(raw_resp, "headers", None) or {}
            ct = headers.get("content-type") or headers.get("Content-Type") or ""
            if ct:
                content_type = ct.split(";")[0].strip()
        if content_type == "application/octet-stream" and file_name:
            content_type = _get_mime_for_filename(file_name)

        # Classify the content type
        is_image = content_type.startswith("image/")
        is_video = content_type.startswith("video/") or content_type.startswith("audio/")
        is_document = not is_image and not is_video

        # Skip video/audio content
        if is_video:
            logger.info(
                "Skipping video/audio resource: key=%s, file_name=%s, content_type=%s",
                file_key, file_name, content_type,
            )
            return None

        # Persist to session cache or fall back to a temp file
        if cache_dir is not None:
            path = _save_to_cache(raw_bytes, content_type, file_key, cache_dir)
            cached_flag = path is not None
        else:
            path = _save_to_temp(raw_bytes, content_type)
            cached_flag = False

        if path is None:
            logger.warning("Failed to save media to disk: key=%s", file_key)
            return None

        logger.info(
            "Downloaded media: key=%s, type=%s, file_name=%s, path=%s, "
            "content_type=%s, size=%d bytes",
            file_key, resource_type, file_name, path, content_type, len(raw_bytes),
        )
        return DownloadedMedia(
            key=file_key,
            path=path,
            content_type=content_type,
            is_image=is_image,
            is_video=is_video,
            is_document=is_document,
            cached=cached_flag,
        )

    except _UnsupportedResourceError:
        raise  # propagate to caller
    except Exception as e:
        logger.warning(
            "Error downloading media key=%s type=%s: %s",
            file_key, resource_type, e, exc_info=True,
        )
        return None


# ── Misc helpers ───────────────────────────────────────────────────────────────


def _get_mime_for_filename(file_name: str) -> str:
    """Derive a MIME type from the filename extension returned by the server.

    Falls back to ``application/octet-stream`` when the extension is unknown.
    """
    if not file_name:
        return "application/octet-stream"
    # mimetypes.guess_type works on filenames (not just extensions)
    mime, _ = mimetypes.guess_type(file_name)
    if mime:
        return mime
    # Manual fallback for extensions that mimetypes may miss
    ext = Path(file_name).suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".pdf": "application/pdf",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xls": "application/vnd.ms-excel",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".txt": "text/plain",
        ".mp4": "video/mp4",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
    }.get(ext, "application/octet-stream")


def _get_suffix_for_mime(content_type: str) -> str:
    """Return a reasonable file extension for a given MIME type."""
    # Special-case jpeg because mimetypes returns ".jpe" on some systems
    if content_type in ("image/jpeg", "image/jpg"):
        return ".jpg"
    ext = mimetypes.guess_extension(content_type)
    if ext:
        return ext
    return {
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
        "application/pdf": ".pdf",
        "text/plain": ".txt",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/vnd.ms-excel": ".xls",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    }.get(content_type, ".bin")


# ── Agent input builder ────────────────────────────────────────────────────────


def build_multimodal_input_with_media(
    text: str,
    downloaded_media: List[DownloadedMedia],
) -> list:
    """Build a multimodal TResponseInputItem list from text + downloaded media.

    Encoding strategy:
    - Images    → base64 data URL encoded as input_image content parts
                  (file is read from the cached/temp path and encoded at call time)
    - Documents → file path appended to text as a hint (agent can read the file)
    - Videos    → should already be filtered out before calling this function

    Returns:
        A list in the format expected by SiadaRunner.run_agent(user_input=...)
        i.e. [{"role": "user", "content": [...]}]
    """
    content = []
    doc_hints: list = []

    # Collect document path hints
    for media in downloaded_media:
        if media.is_document:
            doc_hints.append(f"[Attached file: {media.path}]")

    # Build text part (including document hints)
    full_text = text
    if doc_hints:
        full_text = full_text.rstrip() + "\n\n" + "\n".join(doc_hints)

    if full_text:
        content.append({"type": "input_text", "text": full_text})

    # Append base64-encoded image content parts (read from disk at this point)
    for media in downloaded_media:
        if media.is_image:
            try:
                with open(media.path, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode("utf-8")
                data_url = f"data:{media.content_type};base64,{encoded}"
                content.append({
                    "type": "input_image",
                    "image_url": data_url,
                })
                logger.info(
                    "Attached image to agent input: %s (%s)",
                    media.path, media.content_type,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to encode image %s as base64: %s", media.path, exc
                )

    return [{"role": "user", "content": content}]


def cleanup_media_files(downloaded_media: List[DownloadedMedia]) -> None:
    """Remove temporary (non-cached) media files.

    Files saved to a session cache directory (``DownloadedMedia.cached=True``)
    are kept for future reuse and are NOT deleted.
    Only one-off temp files (created when ``cache_dir`` was None) are removed.
    """
    for media in downloaded_media:
        if media.cached:
            continue  # Persistent session cache — keep the file
        try:
            if media.path and os.path.exists(media.path):
                os.unlink(media.path)
                logger.info("Cleaned up temp media file: %s", media.path)
        except Exception as e:
            logger.warning("Failed to clean up temp file %s: %s", media.path, e)
