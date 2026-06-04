"""Parse an Anki ``.apkg`` / ``.colpkg`` export into plain card data.

AnkiWeb has no public import API, so the supported path is: export the deck
from Anki (File → Export → Anki Deck Package) and upload the resulting file.

An ``.apkg`` is a zip holding the collection database (and media we ignore).
Two on-disk formats exist:

* legacy ``collection.anki2`` — schema 11, note types / decks live as JSON in
  the single ``col`` row; deck names use ``::`` as the hierarchy separator.
* modern ``collection.anki21b`` — schema 18, zstd-compressed; note types and
  decks live in their own tables and deck names use ``\\x1f`` as the separator.

We avoid depending on the note-type JSON for classification: cloze is detected
from field content, and a "reversed" (two-sided) note is detected from a note
having two cards (ord 0 and 1). That works the same for both schemas.
"""
from __future__ import annotations

import html as _html
import io
import re
import sqlite3
import tempfile
import urllib.parse
import zipfile
from pathlib import Path

# Hard cap so a giant collection can't exhaust memory on the small instance.
MAX_NOTES = 20000
# Image import bounds (legacy media only — see _media_map).
MAX_IMAGES_PER_NOTE = 6
MAX_IMAGE_TOTAL_BYTES = 40 * 1024 * 1024
_IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}
_IMG_SRC = re.compile(r"""<img[^>]*\bsrc\s*=\s*["']([^"']+)["']""", re.I)

FIELD_SEP = "\x1f"

_SOUND = re.compile(r"\[sound:[^\]]*\]")
_BR = re.compile(r"<\s*br\s*/?\s*>", re.I)
_BLOCK = re.compile(r"<\s*/\s*(?:div|p|li|tr|h\d)\s*>", re.I)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t ]+")
_NL = re.compile(r"\n{2,}")
_CLOZE = re.compile(r"\{\{c(\d+)::(.*?)\}\}", re.S)


class AnkiImportError(Exception):
    """Raised for an unreadable / unsupported package."""


def clean(text: str) -> str:
    """Strip Anki HTML / media markup down to plain text."""
    if not text:
        return ""
    text = _SOUND.sub("", text)
    text = _BR.sub("\n", text)
    text = _BLOCK.sub("\n", text)
    text = _TAG.sub("", text)
    text = _html.unescape(text)
    text = _WS.sub(" ", text)
    text = _NL.sub("\n", text)
    return text.strip()


def _is_cloze(fields: list[str]) -> bool:
    return any(_CLOZE.search(f) for f in fields)


def _cloze_front_back(raw: str) -> tuple[str, str]:
    """Turn a cloze field into a blanked prompt + the collected answers."""
    answers: list[str] = []

    def repl(m: re.Match) -> str:
        inner = m.group(2)
        ans, _, hint = inner.partition("::")
        answers.append(clean(ans))
        hint = clean(hint)
        return f"[{hint}]" if hint else "[…]"

    front = clean(_CLOZE.sub(repl, raw))
    back = ", ".join(a for a in answers if a)
    return front, back


def _db_from_zip(zf: zipfile.ZipFile, names: set[str]) -> bytes:
    """Return the raw SQLite bytes for the collection inside the package."""
    if "collection.anki21b" in names:
        raw = zf.read("collection.anki21b")
        try:
            import zstandard
        except ImportError as exc:  # pragma: no cover - dep is in requirements
            raise AnkiImportError(
                "This export uses Anki's newest format. Re-export with "
                "“Support older Anki versions” ticked, or update the server."
            ) from exc
        return zstandard.ZstdDecompressor().stream_reader(io.BytesIO(raw)).read()
    for name in ("collection.anki21", "collection.anki2"):
        if name in names:
            return zf.read(name)
    raise AnkiImportError("No Anki collection found inside the package.")


def _media_map(zf: zipfile.ZipFile, names: set[str]) -> dict[str, str]:
    """Map media filename → archive entry name, for the legacy media format
    (a JSON object ``{"0": "cat.jpg", ...}``). The newest format stores this as
    a zstd protobuf we don't parse, so images are skipped there (text imports
    fine regardless)."""
    if "media" not in names:
        return {}
    try:
        import json

        data = json.loads(zf.read("media").decode("utf-8"))
        return {fn: str(key) for key, fn in data.items() if isinstance(fn, str)}
    except Exception:  # noqa: BLE001 - new-format or unexpected media blob
        return {}


def _img_filenames(fields: list[str]) -> list[str]:
    """Distinct <img src> filenames referenced across a note's fields."""
    out: list[str] = []
    for f in fields:
        for m in _IMG_SRC.finditer(f or ""):
            src = urllib.parse.unquote(_html.unescape(m.group(1)))
            if src not in out:
                out.append(src)
    return out


def _read_images(zf, names, fname_to_key, wanted, budget) -> list[dict]:
    images: list[dict] = []
    for fn in wanted[:MAX_IMAGES_PER_NOTE]:
        if Path(fn).suffix.lower() not in _IMG_EXT:
            continue
        key = fname_to_key.get(fn) or fname_to_key.get(Path(fn).name)
        if not key or key not in names:
            continue
        data = zf.read(key)
        if budget["used"] + len(data) > MAX_IMAGE_TOTAL_BYTES:
            budget["truncated"] = True
            break
        budget["used"] += len(data)
        images.append({"name": Path(fn).name, "data": data})
    return images


def _deck_names(con: sqlite3.Connection) -> dict[int, str]:
    """Map deck id → full '::'-separated name, across both schemas."""
    import json

    row = con.execute("SELECT decks FROM col").fetchone()
    if row and row[0]:
        data = json.loads(row[0])
        return {int(did): d.get("name", "") for did, d in data.items()}
    out: dict[int, str] = {}
    try:
        for did, name in con.execute("SELECT id, name FROM decks"):
            out[int(did)] = (name or "").replace(FIELD_SEP, "::")
    except sqlite3.OperationalError:
        pass
    return out


def parse_apkg(data: bytes) -> dict:
    """Parse package bytes into ``{crt, total_cards, truncated, notes:[...]}``.

    Each note dict: ``{deck, kind, two_sided, front, back, tags, cards}`` where
    ``cards`` is an ordinal-sorted list of raw scheduling dicts (one per Anki
    card of the note); ``kind`` is ``"grammar"`` (cloze) or ``"vocab"``.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise AnkiImportError("Not a valid .apkg file (expected a zip archive).") from exc
    names = set(zf.namelist())
    db_bytes = _db_from_zip(zf, names)
    fname_to_key = _media_map(zf, names)

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "collection.db"
        db_path.write_bytes(db_bytes)
        con = sqlite3.connect(str(db_path))
        try:
            con.row_factory = sqlite3.Row
            crt_row = con.execute("SELECT crt FROM col").fetchone()
            crt = int(crt_row[0]) if crt_row and crt_row[0] else 0
            decks = _deck_names(con)

            rows = con.execute(
                """
                SELECT n.id AS nid, n.flds AS flds, n.tags AS tags,
                       c.ord AS ord, c.did AS did, c.type AS type, c.queue AS queue,
                       c.due AS due, c.ivl AS ivl, c.factor AS factor,
                       c.reps AS reps, c.lapses AS lapses
                FROM notes n JOIN cards c ON c.nid = n.id
                ORDER BY n.id, c.ord
                """
            )

            grouped: dict[int, dict] = {}
            order: list[int] = []
            total_cards = 0
            truncated = False
            for r in rows:
                nid = r["nid"]
                if nid not in grouped:
                    if len(order) >= MAX_NOTES:
                        truncated = True
                        continue  # note over the cap — drop it and its cards
                    grouped[nid] = {
                        "fields": (r["flds"] or "").split(FIELD_SEP),
                        "tags": [t for t in (r["tags"] or "").split(" ") if t],
                        "did": r["did"],
                        "cards": [],
                    }
                    order.append(nid)
                if nid not in grouped:
                    continue  # a card whose note was dropped by the cap
                grouped[nid]["cards"].append(
                    {
                        "ord": r["ord"],
                        "type": r["type"],
                        "queue": r["queue"],
                        "due": r["due"],
                        "ivl": r["ivl"],
                        "factor": r["factor"],
                        "reps": r["reps"],
                        "lapses": r["lapses"],
                    }
                )
                total_cards += 1
        finally:
            con.close()

    notes = []
    img_budget = {"used": 0, "truncated": False}
    for nid in order:
        g = grouped[nid]
        fields = g["fields"]
        deck_name = decks.get(int(g["did"]), "") or "Imported"
        if _is_cloze(fields):
            front, back = _cloze_front_back(fields[0] if fields else "")
            kind, two_sided = "grammar", False
        else:
            front = clean(fields[0]) if fields else ""
            back = clean(fields[1]) if len(fields) > 1 else ""
            kind = "vocab"
            two_sided = len(g["cards"]) >= 2
        images = (
            _read_images(zf, names, fname_to_key, _img_filenames(fields), img_budget)
            if fname_to_key
            else []
        )
        if not front and not images:
            continue  # skip empty / media-only-without-image notes
        notes.append(
            {
                "deck": deck_name,
                "kind": kind,
                "two_sided": two_sided,
                "front": front or "(image)",
                "back": back,
                "tags": g["tags"],
                "cards": g["cards"],
                "images": images,
            }
        )

    zf.close()
    return {
        "crt": crt,
        "total_cards": total_cards,
        "truncated": truncated,
        "img_truncated": img_budget["truncated"],
        "notes": notes,
    }
