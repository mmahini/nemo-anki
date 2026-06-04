"""Turn an uploaded book into lessons + vocab.

Pipeline:
  1. Read text (paste / .txt / .pdf).
  2. Segment into lessons by common headings (Lektion/Unit/Lesson/…).
  3. For each lesson, extract vocab with Gemini (translated into the chosen
     language). Bounded so a big book can't run unbounded.
"""
from __future__ import annotations

import re

import requests
from django.conf import settings

from apps.imports.gemini import _extract_json_array  # reuse robust JSON parsing

# Segmenting is cheap (no LLM), so allow large books (Oxford Word Skills has
# 100 units). Vocab is still extracted per lesson, on demand.
MAX_LESSONS = 200
MAX_CHARS_PER_LESSON = 8000
MAX_ITEMS_PER_LESSON = 60

_LANG_NAMES = {"de": "German", "en": "English", "": "the source language"}
ALLOWED_ARTICLES = {"none", "der", "die", "das", "plural"}

# A lesson heading at the START of a line: "Unit 12", "Unit12", "Lektion 1",
# "Kapitel 3". The keyword must begin the line (so in-sentence cross-references
# like "see Unit 33" are ignored). "lesson" is intentionally excluded — it's a
# common English word and produces false matches in book bodies.
_HEADING = re.compile(
    r"^[ \t>·•\-]*(unit|lektion|kapitel|chapter|modul|module|درس|leçon|lezione|lección|leccion)"
    r"[ \t]*\.?[ \t]*(\d{1,3})\b([^\n]*)",
    re.IGNORECASE | re.MULTILINE,
)

_HEADING_LABEL = {
    "unit": "Unit", "lektion": "Lektion", "kapitel": "Kapitel", "chapter": "Chapter",
    "modul": "Modul", "module": "Module", "leçon": "Leçon", "lezione": "Lezione",
    "lección": "Lección", "leccion": "Lección", "درس": "درس",
}
# Trailing text longer than this means the line is prose (a sentence /
# answer-key fragment), not a clean unit heading.
_MAX_HEADING_TRAILING = 60


def bytes_to_text(data: bytes, filename: str = "") -> str:
    """Extract text from uploaded bytes (.pdf via PyMuPDF, else decode)."""
    if not data:
        return ""
    if (filename or "").lower().endswith(".pdf") or _looks_like_pdf(data):
        return _read_pdf(data)
    try:
        return data.decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return ""


def _looks_like_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def read_pdf_pages(data: bytes) -> list[str]:
    """Return the text of each PDF page. Tries PyMuPDF first (best quality),
    then falls back to pypdf per page so page-based splitting works for any
    readable PDF — even ones PyMuPDF can't open. Empty list only if neither
    library can read it."""
    if not data:
        return []
    try:
        import fitz

        with fitz.open(stream=data, filetype="pdf") as doc:
            if doc.needs_pass:
                doc.authenticate("")
            pages = [page.get_text("text") for page in doc]
        if pages:
            return pages
    except Exception:  # noqa: BLE001 — fall back to pypdf
        pass
    try:
        import io

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:  # noqa: BLE001
                pass
        return [(page.extract_text() or "") for page in reader.pages]
    except Exception:  # noqa: BLE001
        return []


def _label_cap(label: str) -> str:
    label = (label or "Unit").strip() or "Unit"
    return label[:1].upper() + label[1:]


def _lesson(label: str, n: int, pages: list[str], s: int, e: int) -> dict:
    """Build one lesson dict for pages[s:e] (0-based, clamped)."""
    s = max(0, min(s, len(pages)))
    e = max(s, min(e, len(pages)))
    return {
        "title": f"{label} {n}",
        "raw_text": "\n".join(pages[s:e]).strip(),
        "page_start": s + 1,
        "page_end": max(s + 1, e),
    }


def _pdf_reader(data: bytes):
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:  # noqa: BLE001
            pass
    return reader


def _make_lesson_pdf(reader, s0: int, e0: int) -> bytes:
    """Write pages [s0, e0) (0-based) into a new single PDF -> bytes."""
    import io

    from pypdf import PdfWriter

    writer = PdfWriter()
    for i in range(max(0, s0), min(e0, len(reader.pages))):
        writer.add_page(reader.pages[i])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _ranges(n_pages, from_n, to_n, start_page, pages_per_unit, page_map):
    """Return [(num, s0, e0)] 0-based half-open page ranges for each lesson."""
    to_n = min(to_n, from_n + MAX_LESSONS - 1)
    if page_map:
        items = sorted(
            ({"num": int(p["num"]), "s": max(0, int(p["start_page"]) - 1)} for p in page_map),
            key=lambda x: (x["s"], x["num"]),
        )
        return [
            (it["num"], it["s"], items[i + 1]["s"] if i + 1 < len(items) else n_pages)
            for i, it in enumerate(items)
        ]
    start_idx = max(0, int(start_page or 1) - 1)
    n_units = to_n - from_n + 1
    if pages_per_unit:
        ppu = max(1, int(pages_per_unit))
        return [
            (k, start_idx + (k - from_n) * ppu, start_idx + (k - from_n + 1) * ppu)
            for k in range(from_n, to_n + 1)
        ]
    # even split
    avail = max(0, n_pages - start_idx)
    base, extra = divmod(avail, n_units) if n_units else (0, 0)
    out, cur = [], start_idx
    for i, k in enumerate(range(from_n, to_n + 1)):
        size = base + (1 if i < extra else 0)
        out.append((k, cur, cur + size))
        cur += size
    return out


def segment_pdf(
    data: bytes, label: str, from_n: int, to_n: int,
    start_page: int = 1, pages_per_unit=None, page_map=None,
) -> list[dict]:
    """Split a PDF into one sub-PDF per lesson (+ that lesson's page text).
    Always yields one lesson per range — the count is guaranteed."""
    label = _label_cap(label)
    pages_text = read_pdf_pages(data)
    reader = _pdf_reader(data)
    n_pages = len(reader.pages)
    ranges = _ranges(n_pages, from_n, to_n, start_page, pages_per_unit, page_map)

    lessons = []
    for num, s0, e0 in ranges:
        s0 = max(0, min(s0, n_pages))
        e0 = max(s0, min(e0, n_pages))
        raw = "\n".join(pages_text[s0:e0]).strip() if pages_text else ""
        lessons.append({
            "num": num,
            "title": f"{label} {num}",
            "raw_text": raw,
            "pdf_bytes": _make_lesson_pdf(reader, s0, e0),
            "page_start": s0 + 1,
            "page_end": max(s0 + 1, e0),
        })
    lessons.sort(key=lambda x: x["num"])
    return lessons


def segment_by_even_pages(
    pages: list[str], label: str, from_n: int, to_n: int, start_page: int = 1
) -> list[dict]:
    """Divide the pages evenly across ALL units from..to — guarantees exactly
    that many lessons even when no headings can be found. Boundaries are
    approximate (the user can refine via the preview), but every unit gets a
    contiguous block of pages."""
    label = _label_cap(label)
    to_n = min(to_n, from_n + MAX_LESSONS - 1)
    n_units = to_n - from_n + 1
    start_idx = max(0, int(start_page) - 1)
    avail = max(0, len(pages) - start_idx)
    base, extra = divmod(avail, n_units) if n_units else (0, 0)

    lessons, cursor = [], start_idx
    for i, k in enumerate(range(from_n, to_n + 1)):
        size = base + (1 if i < extra else 0)
        lessons.append(_lesson(label, k, pages, cursor, cursor + size))
        cursor += size
    return lessons


def segment_by_pages(
    pages: list[str], label: str, from_n: int, to_n: int, start_page: int, pages_per_unit: int
) -> list[dict]:
    """Fixed-size page blocks: unit k = `pages_per_unit` pages. Guarantees all
    units from..to (units past the last page get empty content)."""
    label = _label_cap(label)
    ppu = max(1, int(pages_per_unit))
    start_idx = max(0, int(start_page) - 1)
    to_n = min(to_n, from_n + MAX_LESSONS - 1)
    return [
        _lesson(label, k, pages, start_idx + (k - from_n) * ppu, start_idx + (k - from_n + 1) * ppu)
        for k in range(from_n, to_n + 1)
    ]


def _read_pdf(data: bytes) -> str:
    # PyMuPDF (fitz) extracts far cleaner text than pypdf — it preserves digits
    # and reading order, which matters for detecting "Unit 50" (pypdf often
    # mangles these into "Unit SO" or drops the header entirely).
    try:
        import fitz  # PyMuPDF

        with fitz.open(stream=data, filetype="pdf") as doc:
            text = "\n".join(page.get_text("text") for page in doc)
        if text.strip():
            return text
    except Exception:  # noqa: BLE001 — fall back to pypdf
        pass
    try:
        import io

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:  # noqa: BLE001 — pypdf missing or unreadable PDF
        return ""


# Digits frequently extracted from PDFs as look-alike letters. Used to build a
# tolerant pattern so "Unit SO" still matches Unit 50, "Unit l2" matches 12, etc.
_DIGIT_LOOKALIKE = {
    "0": "0OoQD", "1": "1lIi", "2": "2Zz", "3": "3", "4": "4",
    "5": "5Ss", "6": "6G", "7": "7", "8": "8B", "9": "9gq",
}


# Stops a number matching inside a longer one ("5" inside "50"), allowing for
# OCR look-alikes in the following character too.
_NUM_TAIL = r"(?![0-9OoSsIlZBGgqQD])"


def _num_pattern(n: int) -> str:
    return "".join(f"[{_DIGIT_LOOKALIKE[d]}]" for d in str(n))


def _heading_regex(kw_escaped: str, n: int, line_start: bool):
    anchor = r"(?m)^[ \t>·•\-]*" if line_start else r"\b"
    return re.compile(
        rf"{anchor}{kw_escaped}[ \t]*\.?[ \t]*0*{_num_pattern(n)}{_NUM_TAIL}",
        re.IGNORECASE,
    )


def _find_unit(text: str, kw_escaped: str, n: int, cursor: int):
    """Find lesson `n`'s heading at or after `cursor`. Prefers a clean
    line-start heading; falls back to any occurrence so mangled PDF headings
    can still be located. The number is matched OCR-tolerantly."""
    m = _heading_regex(kw_escaped, n, True).search(text, cursor)
    if m:
        return m
    return _heading_regex(kw_escaped, n, False).search(text, cursor)


def detect_unit_pages(pages: list[str], label: str, from_n: int, to_n: int) -> dict[int, int]:
    """Per-page heading scan: return {unit_number: 0-based page index} for the
    units whose "<label> N" heading is found, scanning pages in order so the
    detected pages stay monotonic (review/section pages don't shift things)."""
    label = (label or "Unit").strip() or "Unit"
    kw = re.escape(label)
    to_n = min(to_n, from_n + MAX_LESSONS - 1)
    detected: dict[int, int] = {}
    last_page = 0
    for n in range(from_n, to_n + 1):
        rx = _heading_regex(kw, n, True)
        for pi in range(last_page, len(pages)):
            if rx.search(pages[pi]):
                detected[n] = pi
                last_page = pi
                break
    return detected


def build_page_map(
    detected: dict[int, int], from_n: int, to_n: int, page_count: int, fallback_ppu: int = 2
) -> list[dict]:
    """Fill a full unit->start-page list for [from_n..to_n], interpolating the
    pages of units that weren't detected. Returns 1-based start pages,
    non-decreasing. Editable by the user before commit."""
    to_n = min(to_n, from_n + MAX_LESSONS - 1)
    known = sorted(detected.items())  # [(num, page_idx)]
    # Estimate pages-per-unit from detected spacing.
    ppu = fallback_ppu
    if len(known) >= 2:
        spans = [
            (known[i + 1][1] - known[i][1]) / (known[i + 1][0] - known[i][0])
            for i in range(len(known) - 1)
            if known[i + 1][0] != known[i][0]
        ]
        if spans:
            ppu = max(1, round(sorted(spans)[len(spans) // 2]))  # median

    def interp(n: int) -> int:
        if n in detected:
            return detected[n]
        prev = [k for k in known if k[0] < n]
        nxt = [k for k in known if k[0] > n]
        if prev and nxt:
            (pn, pp), (nn, np_) = prev[-1], nxt[0]
            return round(pp + (np_ - pp) * (n - pn) / (nn - pn))
        if prev:
            pn, pp = prev[-1]
            return pp + (n - pn) * ppu
        if nxt:
            nn, np_ = nxt[0]
            return np_ - (nn - n) * ppu
        return (n - from_n) * ppu

    out = []
    last = 0
    for n in range(from_n, to_n + 1):
        idx = interp(n)
        idx = max(last, min(idx, max(0, page_count - 1)))  # clamp + non-decreasing
        last = idx
        out.append({"num": n, "start_page": idx + 1})  # 1-based
    return out


def segment_by_page_map(pages: list[str], label: str, page_map: list[dict]) -> list[dict]:
    """Build lessons from an (approved) unit->start-page map. Produces exactly
    one lesson per entry (never drops), so the requested count is guaranteed."""
    label = _label_cap(label)
    items = sorted(
        ({"num": int(p["num"]), "start": max(1, int(p["start_page"]))} for p in page_map),
        key=lambda x: (x["start"], x["num"]),
    )
    out = []
    for i, it in enumerate(items):
        s = it["start"] - 1
        end = (items[i + 1]["start"] - 1) if i + 1 < len(items) else len(pages)
        out.append((it["num"], _lesson(label, it["num"], pages, s, end)))
    out.sort(key=lambda x: x[0])
    return [l for _, l in out]


def segment_by_range(text: str, keyword: str, from_n: int, to_n: int) -> list[dict]:
    """Segment using a known label + number range (e.g. Unit 1..100).

    Because lessons are sequential and don't overlap, we scan forward looking
    for each expected number in turn — so cross-references and noise are
    ignored, and missing headings just leave their content with the previous
    lesson instead of breaking detection.
    """
    keyword = (keyword or "").strip()
    if not keyword or to_n < from_n:
        return segment_lessons(text)
    # Bound the range so a typo can't create a runaway loop.
    to_n = min(to_n, from_n + MAX_LESSONS - 1)
    kw_escaped = re.escape(keyword)

    found = []  # (num, start)
    cursor = 0
    for n in range(from_n, to_n + 1):
        m = _find_unit(text, kw_escaped, n, cursor)
        if m:
            found.append((n, m.start()))
            cursor = m.end()  # next search continues after this heading (no overlap)

    if not found:
        return segment_lessons(text)

    label = keyword[:1].upper() + keyword[1:]
    lessons = []
    for i, (n, start) in enumerate(found):
        end = found[i + 1][1] if i + 1 < len(found) else len(text)
        lessons.append({"title": f"{label} {n}", "raw_text": text[start:end]})
    return lessons


def segment_lessons(text: str) -> list[dict]:
    """Split text into [{title, raw_text}] by lesson headings.

    Robust against messy PDF extraction: only accepts clean heading lines,
    de-duplicates repeated headings (PDF page headers / cross-references),
    and orders lessons by their number. Titles are normalised to
    "<Label> N" so junk after the number never leaks into the title.
    """
    candidates = []
    for m in _HEADING.finditer(text):
        trailing = (m.group(3) or "").strip()
        # Reject sentence-like lines (prose / answer-key fragments).
        if len(trailing) > _MAX_HEADING_TRAILING:
            continue
        candidates.append({"start": m.start(), "kw": m.group(1).lower(), "num": int(m.group(2))})

    if not candidates:
        return [{"title": "Lesson 1", "raw_text": text[: MAX_CHARS_PER_LESSON * 4]}]

    # De-duplicate by (keyword, number) — keep the first occurrence in the text.
    seen: set[tuple[str, int]] = set()
    uniq = []
    for c in candidates:
        key = (c["kw"], c["num"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)

    # Slice the text on heading boundaries in document order, then present the
    # lessons ordered by their unit number.
    uniq.sort(key=lambda c: c["start"])
    lessons = []
    for i, c in enumerate(uniq):
        end = uniq[i + 1]["start"] if i + 1 < len(uniq) else len(text)
        label = _HEADING_LABEL.get(c["kw"], c["kw"].title())
        lessons.append({"num": c["num"], "title": f"{label} {c['num']}", "raw_text": text[c["start"]:end]})

    lessons.sort(key=lambda l: l["num"])
    return [{"title": l["title"], "raw_text": l["raw_text"]} for l in lessons]


_VOCAB_PROMPT = """You are building flashcards from a {src_name} coursebook \
lesson. Extract the key VOCABULARY as a JSON array (no markdown, no commentary). \
Each item:
- "front": the {src_name} word/phrase to memorise. For {src_name} nouns put NO \
article here (it goes in "article").
- "back": the translation written in {translation_language}.
- "article": for a German noun one of "der","die","das","plural"; else "none".
- "reading": IPA pronunciation of the front, or "".
- "plural": noun plural with its article (e.g. "die Tische"), or "".
- "example": one short example sentence in {src_name}, or "".
Only include real vocabulary that appears in the text; do not invent words. \
Return at most {max_items} of the most useful items.

LESSON TEXT:
{text}
"""


def extract_vocab(lesson_text: str, source_language: str, translation_language: str) -> list[dict]:
    if not settings.GEMINI_API_KEY or not lesson_text.strip():
        return []
    prompt = _VOCAB_PROMPT.format(
        src_name=_LANG_NAMES.get(source_language, "the source language"),
        translation_language=(translation_language or "English").strip(),
        max_items=MAX_ITEMS_PER_LESSON,
        text=lesson_text[:MAX_CHARS_PER_LESSON],
    )
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
    }
    res = requests.post(url, json=payload, timeout=60)
    res.raise_for_status()
    raw = res.json()["candidates"][0]["content"]["parts"][0]["text"]
    items = _extract_json_array(raw)
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        front = str(it.get("front", "")).strip()
        if not front:
            continue
        article = it.get("article") if it.get("article") in ALLOWED_ARTICLES else "none"
        out.append(
            {
                "card_type": "vocab",
                "front": front,
                "back": str(it.get("back", "")).strip(),
                "reading": str(it.get("reading", "")).strip(),
                "article": article,
                "plural": str(it.get("plural", "")).strip(),
                "example": str(it.get("example", "")).strip(),
            }
        )
    return out
