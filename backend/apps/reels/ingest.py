"""Copy a reel's media off Instagram's CDN and onto our own storage.

Time-critical: `videoUrl` and `displayUrl` are signed links that expire within
days, so this runs in the same job as the fetch rather than on a nightly sweep.
A reel whose media never lands stays `media_status="failed"` and is filtered out
of the feed — it is never shown as a broken card.

The destination is Django's default storage, which core.settings points at
Cloudflare R2 when the R2_* env vars are set (and the local filesystem
otherwise), so nothing here talks to boto3 directly.
"""

import logging

import requests
from django.core.files.base import ContentFile

from .models import MEDIA_FAILED, MEDIA_STORED, Reel

logger = logging.getLogger(__name__)

# A 30s Instagram reel is a few MB; anything past this is not what we think it
# is, and we stop reading rather than filling a disk.
MAX_VIDEO_BYTES = 80 * 1024 * 1024
MAX_POSTER_BYTES = 5 * 1024 * 1024

# Instagram's CDN is picky about clients that don't look like browsers.
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def _download(url: str, max_bytes: int) -> bytes | None:
    """Stream a URL into memory, giving up past max_bytes. Best-effort: returns
    None instead of raising so one bad reel can't fail a whole batch."""
    if not url:
        return None
    try:
        res = requests.get(url, timeout=60, stream=True, headers={"User-Agent": UA})
        res.raise_for_status()
        buf = bytearray()
        for chunk in res.iter_content(65536):
            buf += chunk
            if len(buf) > max_bytes:
                logger.warning("reel media exceeded %s bytes: %s", max_bytes, url[:80])
                return None
        return bytes(buf)
    except Exception:  # noqa: BLE001 — recorded on the Reel row by the caller
        logger.warning("reel media download failed: %s", url[:80], exc_info=True)
        return None


def store_media(reel: Reel, video_url: str, poster_url: str) -> bool:
    """Fetch both files and attach them to the reel. Returns True on success.

    The video is mandatory — a reel with only a poster isn't playable, so we
    mark it failed rather than publishing a card that does nothing when tapped.
    """
    video = _download(video_url, MAX_VIDEO_BYTES)
    if not video:
        reel.media_status = MEDIA_FAILED
        reel.media_error = "video download failed or too large"
        reel.save(update_fields=["media_status", "media_error"])
        return False

    reel.video.save(f"{reel.key}.mp4", ContentFile(video), save=False)
    reel.video_bytes = len(video)

    poster = _download(poster_url, MAX_POSTER_BYTES)
    if poster:
        reel.poster.save(f"{reel.key}.jpg", ContentFile(poster), save=False)

    reel.media_status = MEDIA_STORED
    reel.media_error = ""
    reel.save()
    return True


def delete_media(reel: Reel) -> int:
    """Drop the stored objects, keeping the row. Returns bytes freed.

    The row survives on purpose: `key` is our dedupe identity, and deleting it
    would let the next poll re-scrape — and re-bill us for — the same reel.
    """
    freed = reel.video_bytes or 0
    for field in (reel.video, reel.poster):
        if field:
            try:
                field.delete(save=False)
            except Exception:  # noqa: BLE001 — a missing object is still "gone"
                logger.warning("could not delete %s for reel %s", field.name, reel.key)
    reel.video = None
    reel.poster = None
    reel.video_bytes = 0
    return freed
