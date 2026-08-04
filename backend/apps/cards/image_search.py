"""Auto-find a small image for a card via Openverse (openly-licensed, no key).

Biased toward simple illustrations / clipart (clearer for study than a random
photo), falling back to photographs. Only the top few (most relevant) results
per search are considered, shuffled among themselves so re-running on the same
card yields a different picture without straying into irrelevant results
further down the page. The chosen result's thumbnail is shrunk to a tiny JPEG
so card images stay small regardless of the source.
"""
from __future__ import annotations

import io
import random

import requests
from django.core.files.base import ContentFile
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


def _fetch_and_resize(url: str) -> bytes | None:
    try:
        ir = requests.get(url, timeout=15, headers=_UA, stream=True)
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
        return None


_TOP_K = 6  # Openverse's own relevance ranking degrades fast past the first
# few hits (e.g. a "glass of milk" photo search returns unrelated results by
# position 10) — shuffling the full page, as this used to, was as likely to
# pick something irrelevant as something on-topic. Shuffling only the top
# handful keeps results relevant while still varying the pick on regenerate.


def _download_thumb(results: list[dict]) -> bytes | None:
    top = results[:_TOP_K]
    random.shuffle(top)
    for it in top:
        src = it.get("thumbnail") or it.get("url")
        if not src:
            continue
        data = _fetch_and_resize(src)
        if data:
            return data
    return None


def find_thumbnail(term: str) -> bytes | None:
    """Return a small JPEG thumbnail for `term` — prefer a clear illustration,
    then a photo. None if nothing usable is found."""
    term = (term or "").strip()
    if not term:
        return None
    # Photographs are the most literal/accurate (an "illustration" search for
    # e.g. "tree" returns family-trees and tree-diagrams). Broad search next,
    # illustration only as a last resort.
    for category in ("photograph", None, "illustration"):
        data = _download_thumb(_search(term, category))
        if data:
            return data
    return None


def find_thumbnail_url(term: str) -> str:
    """Like find_thumbnail, but returns a source URL instead of downloading —
    used for the Telegram proposal preview, where Telegram fetches the photo
    itself so we avoid downloading once for the preview and again to attach.
    "" if nothing usable is found (the URL isn't verified to be a working
    image; a broken one just fails silently as a Telegram sendPhoto error)."""
    term = (term or "").strip()
    if not term:
        return ""
    for category in ("photograph", None, "illustration"):
        top = _search(term, category)[:_TOP_K]
        random.shuffle(top)
        for it in top:
            src = it.get("thumbnail") or it.get("url")
            if src:
                return src
    return ""


def _attach_thumbnail(card, data: bytes, *, replace_auto: bool):
    from .models import CardImage

    if replace_auto:
        card.images.filter(auto=True).delete()
    last = card.images.order_by("-position").first()
    pos = (last.position + 1) if last else 0
    return CardImage.objects.create(
        card=card, image=ContentFile(data, name=f"auto_{card.id}_{pos}.jpg"), position=pos, auto=True,
    )


def _image_search_query(front: str, back: str, language: str, card_type: str) -> str:
    from apps.imports.gemini import image_search_query

    return image_search_query(front, back, language, card_type)


def find_and_attach_thumbnail(card, front: str, back: str, language: str = "", card_type: str = "vocab", *, replace_auto: bool = True):
    """Ask Gemini whether `front`/`back` is something a photo can reliably
    depict and, if so, for a short unambiguous English search phrase; then
    find a thumbnail for that phrase and attach it to `card` as an
    auto-found CardImage (appended after any existing images, replacing a
    previous auto-found one unless `replace_auto=False`).

    Without this check, a literal keyword search on Openverse regularly picks
    something unrelated for words that aren't concretely photographable (e.g.
    "Sunday" mostly returns event photos tagged with that day, not anything
    depicting the day of the week) — so no GEMINI_API_KEY configured, or
    Gemini judging the term "not depictable", means no image rather than a
    misleading one. None whenever no usable thumbnail is attached."""
    query = _image_search_query(front, back, language, card_type)
    if not query:
        return None
    data = find_thumbnail(query)
    if not data:
        return None
    return _attach_thumbnail(card, data, replace_auto=replace_auto)


def find_thumbnail_url_for(front: str, back: str, language: str = "", card_type: str = "vocab") -> str:
    """Same Gemini depictability gating as find_and_attach_thumbnail, but
    returns a source URL without downloading — for a preview shown before the
    Card exists (Telegram's Create/Edit proposal screen). "" when Gemini says
    the term isn't depictable, no GEMINI_API_KEY is configured, or nothing
    usable was found."""
    query = _image_search_query(front, back, language, card_type)
    if not query:
        return ""
    return find_thumbnail_url(query)


def attach_thumbnail_from_url(card, url: str, *, replace_auto: bool = True):
    """Download the image at `url` (as previously found by
    find_thumbnail_url_for) and attach it to `card` as an auto-found
    CardImage. Returns (CardImage, raw JPEG bytes) — the caller (Telegram's
    _finalize) forwards those same bytes to sendPhoto instead of reading
    them back from storage right after this just wrote them there.
    (None, None) if `url` is blank or the download/resize fails."""
    if not url:
        return None, None
    data = _fetch_and_resize(url)
    if not data:
        return None, None
    return _attach_thumbnail(card, data, replace_auto=replace_auto), data
