"""Auto-find a small image for a card via Openverse (openly-licensed, no key).

We download the search result's thumbnail and shrink it to a tiny JPEG so card
images stay small regardless of the source.
"""
from __future__ import annotations

import io

import requests
from PIL import Image

_UA = {"User-Agent": "nemo-anki/1.0 (language study app)"}
_OPENVERSE = "https://api.openverse.org/v1/images/"
THUMB_MAX = (320, 320)
_DL_CAP = 6 * 1024 * 1024  # don't pull more than ~6 MB before resizing


def find_thumbnail(term: str) -> bytes | None:
    """Return a small JPEG thumbnail for `term`, or None if nothing usable."""
    term = (term or "").strip()
    if not term:
        return None
    try:
        r = requests.get(_OPENVERSE, params={"q": term, "page_size": 8}, timeout=15, headers=_UA)
        r.raise_for_status()
        results = r.json().get("results") or []
    except Exception:  # noqa: BLE001 - search is best-effort
        return None

    for it in results:
        src = it.get("thumbnail") or it.get("url")
        if not src:
            continue
        try:
            ir = requests.get(src, timeout=15, headers=_UA, stream=True)
            ir.raise_for_status()
            buf = b""
            for chunk in ir.iter_content(65536):
                buf += chunk
                if len(buf) > _DL_CAP:
                    break
            im = Image.open(io.BytesIO(buf))
            im.thumbnail(THUMB_MAX)
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            out = io.BytesIO()
            im.save(out, "JPEG", quality=80)
            return out.getvalue()
        except Exception:  # noqa: BLE001 - try the next result
            continue
    return None
