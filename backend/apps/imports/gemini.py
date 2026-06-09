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

_ENRICH_PROMPT = """For the {language_name} {card_type} below, return ONLY a JSON \
object (no markdown, no commentary) with these keys:
- "back": a concise translation / meaning written in {back_language}.
- "reading": phonetic transcription (IPA) of the {language_name} text, or "".
- "article": for a {language_name} noun one of "der","die","das","plural"; \
otherwise "none".
- "plural": for a noun, its plural form WITH the plural article (e.g. \
"die Tische"); "" if not a noun or it has no plural.
- "example": one short, natural example sentence in {language_name}, or "".

TEXT: {front}
"""


def enrich_card(
    front: str, language: str = "", card_type: str = "vocab", back_language: str = "English"
) -> dict:
    """Translate + add reading/article/example for a single term (Translate button).

    `back_language` is the language the translation ("back") is written in.
    """
    front = (front or "").strip()
    if not front:
        return {}
    if settings.GEMINI_API_KEY:
        try:
            return _enrich_with_gemini(front, language, card_type, back_language)
        except Exception:  # noqa: BLE001 — degrade to local detection
            return _enrich_fallback(front)
    return _enrich_fallback(front)


def _enrich_with_gemini(front: str, language: str, card_type: str, back_language: str) -> dict:
    prompt = _ENRICH_PROMPT.format(
        language_name=_LANG_NAMES.get(language, "the target language"),
        back_language=(back_language or "English").strip(),
        card_type=card_type if card_type in ALLOWED_TYPES else "vocab",
        front=front[:500],
    )
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    res = requests.post(url, json=payload, timeout=30)
    res.raise_for_status()
    raw = res.json()["candidates"][0]["content"]["parts"][0]["text"]
    obj = _extract_json_object(raw)
    article = obj.get("article") if obj.get("article") in ALLOWED_ARTICLES else _detect_article(front)
    return {
        "back": str(obj.get("back", "")).strip(),
        "reading": str(obj.get("reading", "")).strip(),
        "article": article,
        "plural": str(obj.get("plural", "")).strip(),
        "example": str(obj.get("example", "")).strip(),
    }


def _extract_json_object(raw: str) -> dict:
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        val = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        val = json.loads(match.group(0)) if match else {}
    return val if isinstance(val, dict) else {}


def _detect_article(front: str) -> str:
    m = re.match(r"\s*(der|die|das)\s+\S", front, flags=re.IGNORECASE)
    return m.group(1).lower() if m else "none"


def _enrich_fallback(front: str) -> dict:
    """No LLM: at least pull a leading der/die/das so the colour works."""
    return {"back": "", "reading": "", "article": _detect_article(front), "plural": "", "example": ""}


_ANALYZE_PROMPT = """Analyse the German sentence below. For every noun, in order \
of appearance, return ONLY a JSON array; each element is an object with:
- "noun": the noun exactly as written in the sentence.
- "gender": the noun's TRUE dictionary gender — one of "der","die","das",\
"plural" — NOT the case-inflected article (e.g. in "Ich gebe der Frau das Buch", \
Frau is "die").
- "article": the article/determiner exactly as it appears before the noun \
(e.g. "der","den","dem","einen","das"), or "" if there is none.
- "case": the grammatical case of the noun phrase — one of "Nominativ",\
"Akkusativ","Dativ","Genitiv".
- "reason": a short, beginner-friendly English explanation of WHY that case is \
used (e.g. "subject of the sentence", "direct object of geben", "indirect \
object (to whom)", "after the preposition mit, which always takes Dativ").
- "trigger": the exact word, copied verbatim from the sentence, that FORCES \
this case — the preposition before the noun (e.g. "mit","für","in","aus") or \
the governing verb for an object; use "" for a plain subject (Nominativ).

Include only nouns. No markdown, no commentary.

SENTENCE: {text}
"""

_ANALYZE_ARTICLES = {"der", "die", "das", "plural"}
_ANALYZE_CASES = {"Nominativ", "Akkusativ", "Dativ", "Genitiv"}


def analyze_german(text: str) -> dict:
    """Return each noun's true gender so a sentence can be coloured correctly,
    independent of grammatical case. {"nouns": [{"noun","gender"}], "source"}."""
    text = (text or "").strip()
    if not text:
        return {"nouns": [], "source": "empty"}
    if not settings.GEMINI_API_KEY:
        return {"nouns": [], "source": "no-key"}
    try:
        prompt = _ANALYZE_PROMPT.format(text=text[:1000])
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"},
        }
        res = requests.post(url, json=payload, timeout=30)
        res.raise_for_status()
        raw = res.json()["candidates"][0]["content"]["parts"][0]["text"]
        parsed = _extract_json_array(raw)
        nouns = []
        for it in parsed:
            if not isinstance(it, dict):
                continue
            noun = str(it.get("noun", "")).strip()
            if not noun or it.get("gender") not in _ANALYZE_ARTICLES:
                continue
            case = it.get("case") if it.get("case") in _ANALYZE_CASES else ""
            nouns.append(
                {
                    "noun": noun,
                    "gender": it.get("gender"),
                    "article": str(it.get("article", "")).strip(),
                    "case": case,
                    "reason": str(it.get("reason", "")).strip(),
                    "trigger": str(it.get("trigger", "")).strip(),
                }
            )
        return {"nouns": nouns, "source": "gemini"}
    except Exception as exc:  # noqa: BLE001
        return {"nouns": [], "source": f"error:{exc.__class__.__name__}"}


# ---- Writing practice (topic suggestion + correction) ----
_WRITING_LANGS = {
    "de": "German", "en": "English", "fr": "French", "es": "Spanish",
    "it": "Italian", "fa": "Persian", "tr": "Turkish",
}


def _writing_lang_name(code: str) -> str:
    return _WRITING_LANGS.get(code, code or "the target language")


def _gemini_text(prompt: str, timeout: int = 30) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"},
    }
    res = requests.post(url, json=payload, timeout=timeout)
    res.raise_for_status()
    return res.json()["candidates"][0]["content"]["parts"][0]["text"]


def writing_topic(language: str) -> dict:
    """Suggest one short writing-practice topic for a learner of `language`."""
    name = _writing_lang_name(language)
    if not settings.GEMINI_API_KEY:
        return {"topic": f"Schreibe über deinen Tag." if language == "de" else f"Write a short paragraph about your day.",
                "en": "Write a short paragraph about your day."}
    prompt = (
        f"Suggest ONE short, engaging writing-practice topic for a {name} learner "
        f"(about A2-B1 level). Return ONLY JSON: "
        f'{{"topic": "<the prompt written in {name}>", "en": "<English translation>"}}. '
        f"One concrete sentence. No markdown."
    )
    try:
        obj = _extract_json_object(_gemini_text(prompt))
        topic = str(obj.get("topic", "")).strip()
        if not topic:
            raise ValueError("empty")
        return {"topic": topic, "en": str(obj.get("en", "")).strip()}
    except Exception:  # noqa: BLE001
        return {"topic": f"Write a short paragraph in {name} about your weekend.", "en": ""}


_WRITING_TYPES = {
    "grammar", "spelling", "word order", "article", "case",
    "preposition", "vocabulary", "punctuation", "style", "agreement",
}


def writing_check(text: str, language: str) -> dict:
    """Return {feedback, issues:[{original, correction, type, explanation}]}."""
    text = (text or "").strip()
    if not text:
        return {"feedback": "", "issues": []}
    name = _writing_lang_name(language)
    if not settings.GEMINI_API_KEY:
        return {"feedback": "AI is not configured.", "issues": []}
    prompt = (
        f"You are a {name} writing tutor. Find the mistakes in the student's text below. "
        f"Return ONLY a JSON object:\n"
        f'{{"feedback": "<one short encouraging overall note in English>", '
        f'"issues": [{{"original": "<the exact problematic word/phrase/sentence copied from the text>", '
        f'"correction": "<the corrected {name} version>", '
        f'"type": "<one of: grammar, spelling, word order, article, case, preposition, vocabulary, punctuation, style, agreement>", '
        f'"explanation": "<one short English explanation of the mistake>"}}]}}\n'
        f"Only include real mistakes. If the text is correct, return an empty issues array. "
        f"No markdown, no commentary.\n\nTEXT:\n{text[:4000]}"
    )
    try:
        obj = _extract_json_object(_gemini_text(prompt, timeout=45))
    except Exception as exc:  # noqa: BLE001
        return {"feedback": "", "issues": [], "source": f"error:{exc.__class__.__name__}"}
    issues = []
    for it in obj.get("issues") or []:
        if not isinstance(it, dict):
            continue
        original = str(it.get("original", "")).strip()
        correction = str(it.get("correction", "")).strip()
        if not (original or correction):
            continue
        t = str(it.get("type", "")).strip().lower()
        issues.append(
            {
                "original": original,
                "correction": correction,
                "type": t if t in _WRITING_TYPES else "grammar",
                "explanation": str(it.get("explanation", "")).strip(),
            }
        )
    return {"feedback": str(obj.get("feedback", "")).strip(), "issues": issues}


_BATCH_PROMPT = """You are a German teacher. For each item in the INPUT JSON array \
decide the noun gender(s). Return ONLY a JSON array with exactly one object per \
input item, keeping the same "i" index:
- item "kind":"vocab" (a single word/term) -> {"i": <i>, "gender": its TRUE \
dictionary gender if it is a noun, one of "der","die","das","plural"; otherwise \
"none"}.
- item "kind":"phrase" (a sentence/clause) -> {"i": <i>, "nouns": [{"noun": the \
noun as written, "gender": its TRUE dictionary gender one of "der","die","das",\
"plural"}]} for every noun in order; [] if none.
Use the dictionary gender, NOT the case-inflected article. No markdown, no \
commentary — just the JSON array.

INPUT:
{items}
"""


def analyze_german_batch(items: list[dict]) -> dict[int, dict]:
    """Resolve genders for many cards in ONE Gemini call.

    `items`: ``[{"i": int, "kind": "vocab"|"phrase", "text": str}]``.
    Returns ``{i: {"gender": "der"|...}}`` for vocab and
    ``{i: {"nouns": [{"noun","gender"}]}}`` for phrases. Missing items are simply
    absent from the result (the caller retries them next round)."""
    if not items or not settings.GEMINI_API_KEY:
        return {}
    compact = [
        {"i": int(it["i"]), "kind": it["kind"], "text": (it["text"] or "")[:300]}
        for it in items
    ]
    # str.replace (not .format) — the prompt contains literal JSON braces.
    prompt = _BATCH_PROMPT.replace("{items}", json.dumps(compact, ensure_ascii=False))
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"},
    }
    res = requests.post(url, json=payload, timeout=90)
    res.raise_for_status()
    raw = res.json()["candidates"][0]["content"]["parts"][0]["text"]
    out: dict[int, dict] = {}
    for el in _extract_json_array(raw):
        if not isinstance(el, dict) or "i" not in el:
            continue
        try:
            i = int(el["i"])
        except (TypeError, ValueError):
            continue
        if isinstance(el.get("nouns"), list):
            nouns = [
                {"noun": str(n.get("noun", "")).strip(), "gender": n.get("gender")}
                for n in el["nouns"]
                if isinstance(n, dict)
                and str(n.get("noun", "")).strip()
                and n.get("gender") in _ANALYZE_ARTICLES
            ]
            out[i] = {"nouns": nouns}
        else:
            g = el.get("gender")
            out[i] = {"gender": g if g in _ANALYZE_ARTICLES else "none"}
    return out


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
