"""Download an image from an arbitrary, externally-supplied URL — e.g. a
webpage image the Chrome extension's user right-clicked — and turn it into a
safe, size-capped JPEG.

Unlike apps.cards.image_search (which only ever fetches URLs from Openverse's
own API response, a trusted source), a URL handed to us by the extension can
point anywhere, so every step here is defensive: only http(s), no
private/loopback/link-local/reserved destination address (checked at the
initial host AND at every redirect hop — redirects are not auto-followed), a
hard streaming size cap, and a real Pillow decode rather than trusting
whatever Content-Type the server claims.
"""
from __future__ import annotations

import io
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests
from PIL import Image

_UA = {"User-Agent": "nemo-anki/1.0 (language study app)"}
CARD_IMAGE_MAX = (1600, 1600)  # legible enough for OCR text, unlike image_search's 320x320 icon thumbnails
_MAX_REDIRECTS = 5
_FORMAT_MIME_TYPES = {
    "JPEG": "image/jpeg", "PNG": "image/png", "GIF": "image/gif",
    "WEBP": "image/webp", "BMP": "image/bmp", "TIFF": "image/tiff",
}


class UnsafeUrlError(ValueError):
    """The URL (or a redirect target) resolves to a disallowed destination."""


class ImageFetchError(ValueError):
    """The URL couldn't be downloaded, or the bytes aren't a real image."""


class ImageTooLargeError(ImageFetchError):
    """The download exceeded the caller's byte cap."""


def _check_host(hostname: str) -> None:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Couldn't resolve {hostname!r}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified
        ):
            raise UnsafeUrlError(f"{hostname!r} resolves to a disallowed address")


def _check_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError("Only http:// and https:// URLs are allowed")
    if not parsed.hostname:
        raise UnsafeUrlError("Invalid URL")
    _check_host(parsed.hostname)


def fetch_image_safely(url: str, *, max_bytes: int, timeout: float = 10) -> bytes:
    """Download `url`, enforcing the checks in the module docstring, and
    return the raw bytes. Every redirect hop is re-validated the same way the
    original URL is — blindly following redirects is exactly how this class
    of check gets bypassed (a public URL that 302s to an internal address)."""
    for _ in range(_MAX_REDIRECTS + 1):
        _check_url(url)
        try:
            resp = requests.get(
                url, timeout=timeout, headers=_UA, stream=True, allow_redirects=False
            )
        except requests.RequestException as exc:
            raise ImageFetchError(f"Couldn't reach that URL: {exc}") from exc
        with resp:
            if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location")
                if not location:
                    raise ImageFetchError("Redirected with no destination")
                url = urljoin(url, location)
                continue
            if not resp.ok:
                raise ImageFetchError(f"Request failed ({resp.status_code})")
            buf = bytearray()
            for chunk in resp.iter_content(65536):
                buf += chunk
                if len(buf) > max_bytes:
                    raise ImageTooLargeError("That image is too large (10 MB max)")
            return bytes(buf)
    raise ImageFetchError("Too many redirects")


def normalize_image(data: bytes) -> tuple[bytes, str, str]:
    """Decode `data` with Pillow — the real format check, since Content-Type
    is never trusted — and re-encode as a size-capped JPEG for storage/
    preview. Returns (jpeg_bytes, "image/jpeg", source_mime_type); the third
    value is the *original* format's mime type, for OCR to run against the
    untouched bytes so the size-capping above never costs Gemini legibility.
    Raises ImageFetchError if the bytes aren't a real image."""
    try:
        Image.open(io.BytesIO(data)).verify()
        im = Image.open(io.BytesIO(data))  # verify() consumes the parser; reopen to actually use it
        source_mime_type = _FORMAT_MIME_TYPES.get(im.format or "", "image/jpeg")
        im.thumbnail(CARD_IMAGE_MAX)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        out = io.BytesIO()
        im.save(out, "JPEG", quality=85)
        return out.getvalue(), "image/jpeg", source_mime_type
    except Exception as exc:  # noqa: BLE001 - any decode failure means "not a real image"
        raise ImageFetchError("That doesn't look like a valid image") from exc
