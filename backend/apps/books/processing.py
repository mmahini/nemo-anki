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

MAX_LESSONS = 24
MAX_CHARS_PER_LESSON = 8000
MAX_ITEMS_PER_LESSON = 60

_LANG_NAMES = {"de": "German", "en": "English", "": "the source language"}
ALLOWED_ARTICLES = {"none", "der", "die", "das", "plural"}

# A lesson heading like "Lektion 1", "Unit 12 – Food", "Kapitel 3", "درس ۵".
_HEADING = re.compile(
    r"^\s*(lektion|lesson|unit|kapitel|chapter|modul|module|درس|leçon|lezione|lección|leccion)"
    r"\s*\.?\s*([0-9۰-۹]+)\b.*$",
    re.IGNORECASE | re.MULTILINE,
)


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


def segment_lessons(text: str) -> list[dict]:
    """Split text into [{title, raw_text}] by lesson headings."""
    matches = list(_HEADING.finditer(text))
    if not matches:
        return [{"title": "Lesson 1", "raw_text": text[: MAX_CHARS_PER_LESSON * 4]}]
    lessons = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        title = m.group(0).strip()[:120] or f"Lesson {i + 1}"
        lessons.append({"title": title, "raw_text": text[start:end]})
    return lessons


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
