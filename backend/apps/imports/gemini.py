"""Turn a pasted book section into structured draft cards.

Uses the Gemini REST API when GEMINI_API_KEY is configured; otherwise falls
back to a deterministic line parser so the Import flow works offline/in dev.
The output is a list of *draft* card dicts — never persisted here. The user
reviews/edits them on the Import page and then commits via /api/cards/bulk/.
"""
from __future__ import annotations

import json
import re

import requests
from django.conf import settings

ALLOWED_TYPES = {"vocab", "sentence", "grammar"}
ALLOWED_ARTICLES = {"none", "der", "die", "das", "plural"}

_PROMPT = """You are a language-learning flashcard generator. Convert the text \
below (a section of a {language_name} coursebook) into spaced-repetition cards.

Return ONLY a JSON array. Each element has these keys:
- "card_type": one of "vocab", "sentence", "grammar". Default to "{default_type}" \
when unsure. Single words/phrases -> "vocab"; full example sentences -> \
"sentence"; rules/patterns/conjugations -> "grammar".
- "front": the prompt shown first (the {language_name} term/sentence, or for \
grammar a cloze prompt using ___ for the gap).
- "back": the answer (English translation, or the form that fills the grammar gap).
- "reading": phonetic transcription / pronunciation of the front (IPA-ish or \
simple), or "" if not applicable.
- "article": for {language_name} nouns one of "der","die","das","plural"; \
otherwise "none".
- "example": a short example sentence using the item, or "".
- "notes": for grammar cards, a one-line rule explanation; else "".
- "tags": array of short topic tags (lowercase), may be empty.

Be accurate; do not invent words that are not derivable from the text. Output \
strictly valid JSON, no markdown fences, no commentary.

TEXT:
{text}
"""

_LANG_NAMES = {"de": "German", "en": "English", "": "the target language"}


def parse_text(text: str, language: str = "", default_type: str = "vocab") -> dict:
    text = (text or "").strip()
    if not text:
        return {"cards": [], "source": "empty"}
    if default_type not in ALLOWED_TYPES:
        default_type = "vocab"

    if settings.GEMINI_API_KEY:
        try:
            cards = _parse_with_gemini(text, language, default_type)
            return {"cards": cards, "source": "gemini"}
        except Exception as exc:  # noqa: BLE001 — fall back gracefully
            return {"cards": _parse_fallback(text, default_type), "source": f"fallback:{exc.__class__.__name__}"}
    return {"cards": _parse_fallback(text, default_type), "source": "fallback"}


def _parse_with_gemini(text: str, language: str, default_type: str) -> list[dict]:
    prompt = _PROMPT.format(
        language_name=_LANG_NAMES.get(language, "the target language"),
        default_type=default_type,
        text=text[:12000],
    )
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    res = requests.post(url, json=payload, timeout=45)
    res.raise_for_status()
    data = res.json()
    raw = data["candidates"][0]["content"]["parts"][0]["text"]
    parsed = _extract_json_array(raw)
    return [_normalise(item, language, default_type) for item in parsed if isinstance(item, dict)]


def _extract_json_array(raw: str) -> list:
    raw = raw.strip()
    # Strip accidental ```json fences.
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        val = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", raw, flags=re.DOTALL)
        if not match:
            return []
        val = json.loads(match.group(0))
    if isinstance(val, dict) and "cards" in val:
        val = val["cards"]
    return val if isinstance(val, list) else []


def _normalise(item: dict, language: str, default_type: str) -> dict:
    card_type = item.get("card_type") if item.get("card_type") in ALLOWED_TYPES else default_type
    article = item.get("article") if item.get("article") in ALLOWED_ARTICLES else "none"
    tags = item.get("tags")
    if not isinstance(tags, list):
        tags = []
    return {
        "card_type": card_type,
        "language": language,
        "front": str(item.get("front", "")).strip(),
        "back": str(item.get("back", "")).strip(),
        "reading": str(item.get("reading", "")).strip(),
        "article": article,
        "example": str(item.get("example", "")).strip(),
        "notes": str(item.get("notes", "")).strip(),
        "table": item.get("table") if isinstance(item.get("table"), dict) else None,
        "tags": [str(t).strip() for t in tags if str(t).strip()],
    }


_SEPARATORS = [" — ", " – ", " - ", "\t", " = ", "=", ":", ";"]


def _parse_fallback(text: str, default_type: str) -> list[dict]:
    cards: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        front, back = line, ""
        for sep in _SEPARATORS:
            if sep in line:
                front, back = (p.strip() for p in line.split(sep, 1))
                break
        card_type = default_type
        if default_type == "vocab" and len(front.split()) > 4:
            card_type = "sentence"
        cards.append(
            {
                "card_type": card_type,
                "language": "",
                "front": front,
                "back": back,
                "reading": "",
                "article": "none",
                "example": "",
                "notes": "",
                "table": None,
                "tags": [],
            }
        )
    return cards
