"""Auto-find a small image for a card via Openverse (openly-licensed, no key).

Biased toward simple illustrations / clipart (clearer for study than a random
photo), falling back to photographs. Results are shuffled so re-running on the
same card yields a different picture. The chosen result's thumbnail is shrunk
to a tiny JPEG so card images stay small regardless of the source.
"""
from __future__ import annotations

import io
import random

import requests
from PIL import Image

_UA = {"User-Agent": "nemo-anki/1.0 (language study app)"}
_OPENVERSE = "https://api.openverse.org/v1/images/"
THUMB_MAX = (320, 320)
_DL_CAP = 6 * 1024 * 1024  # don't pull more than ~6 MB before resizing


def _search(term: str, category: str | None) -> list[dict]:
    params = {"q": term, "page_size": 20}
    if category:
        params["category"] = category
    try:
        r = requests.get(_OPENVERSE, params=params, timeout=15, headers=_UA)
        r.raise_for_status()
        return r.json().get("results") or []
    except Exception:  # noqa: BLE001 - search is best-effort
        return []


def _download_thumb(results: list[dict]) -> bytes | None:
    random.shuffle(results)  # vary the pick so "regenerate" differs
    for it in results[:20]:
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


def find_thumbnail(term: str) -> bytes | None:
    """Return a small JPEG thumbnail for `term` — prefer a clear illustration,
    then a photo. None if nothing usable is found."""
    term = (term or "").strip()
    if not term:
        return None
    # Illustrations / clipart read clearest on a flashcard; photos as a fallback.
    for category in ("illustration", "photograph", None):
        data = _download_thumb(_search(term, category))
        if data:
            return data
    return None
