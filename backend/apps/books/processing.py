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


def read_upload(uploaded_file, pasted_text: str) -> str:
    if pasted_text and pasted_text.strip():
        return pasted_text
    if not uploaded_file:
        return ""
    name = (getattr(uploaded_file, "name", "") or "").lower()
    data = uploaded_file.read()
    if name.endswith(".pdf"):
        return _read_pdf(data)
    try:
        return data.decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return ""


def _read_pdf(data: bytes) -> str:
    try:
        import io

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:  # noqa: BLE001 — pypdf missing or unreadable PDF
        return ""


def _find_unit(text: str, kw_escaped: str, n: int, cursor: int):
    """Find lesson `n`'s heading at or after `cursor`. Prefers a clean
    line-start heading; falls back to any occurrence so mangled PDF headings
    can still be located. `0*` allows leading zeros; `\\b` after the number
    keeps "1" from matching inside "10"."""
    line_start = re.compile(
        rf"^[ \t>·•\-]*{kw_escaped}[ \t]*\.?[ \t]*0*{n}\b",
        re.IGNORECASE | re.MULTILINE,
    )
    m = line_start.search(text, cursor)
    if m:
        return m
    anywhere = re.compile(rf"\b{kw_escaped}[ \t]*\.?[ \t]*0*{n}\b", re.IGNORECASE)
    return anywhere.search(text, cursor)


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
