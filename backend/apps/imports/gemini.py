"""Turn a pasted book section into structured draft cards.

Uses the Gemini REST API when GEMINI_API_KEY is configured; otherwise falls
back to a deterministic line parser so the Import flow works offline/in dev.
The output is a list of *draft* card dicts — never persisted here. The user
reviews/edits them on the Import page and then commits via /api/cards/bulk/.
"""
from __future__ import annotations

import json
import random
import re

import requests
from django.conf import settings

ALLOWED_TYPES = {"vocab", "sentence", "grammar", "verb"}
ALLOWED_ARTICLES = {"none", "der", "die", "das", "plural"}

_PROMPT = """You are a language-learning flashcard generator. Convert the text \
below (a section of a {language_name} coursebook) into spaced-repetition cards.

Return ONLY a JSON array. Each element has these keys:
- "card_type": one of "vocab", "sentence", "grammar", "verb". Default to \
"{default_type}" when unsure. Single words/phrases -> "vocab"; full example \
sentences -> "sentence"; rules/patterns -> "grammar"; a verb worth learning \
across tenses -> "verb".
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
    front: str, language: str = "", card_type: str = "vocab", back_language: str = "English",
    previous_proposal: dict | None = None,
) -> dict:
    """Translate + add reading/article/example for a single term (Translate button).

    `back_language` is the language the translation ("back") is written in.
    `previous_proposal` — the {back, reading, article, plural, example} the user
    already saw — is only passed by the Telegram bot's Regenerate button (see
    apps.notifications.management.commands.poll_telegram_updates); it asks
    Gemini to genuinely reconsider the whole card rather than just repeating
    itself, and is otherwise omitted so this call is unchanged for every other
    caller (EnrichView, WordToCardView).
    """
    front = (front or "").strip()
    if not front:
        return {}
    if settings.GEMINI_API_KEY:
        try:
            return _enrich_with_gemini(front, language, card_type, back_language, previous_proposal)
        except Exception:  # noqa: BLE001 — degrade to local detection
            return _enrich_fallback(front)
    return _enrich_fallback(front)


def _enrich_with_gemini(
    front: str, language: str, card_type: str, back_language: str,
    previous_proposal: dict | None = None,
) -> dict:
    prompt = _ENRICH_PROMPT.format(
        language_name=_LANG_NAMES.get(language, "the target language"),
        back_language=(back_language or "English").strip(),
        card_type=card_type if card_type in ALLOWED_TYPES else "vocab",
        front=front[:500],
    )
    if previous_proposal:
        prompt += (
            "\n\nThe user already saw this full proposal and tapped Regenerate:\n"
            f'- Translation: "{previous_proposal.get("back", "")}"\n'
            f'- Reading: "{previous_proposal.get("reading", "")}"\n'
            f'- Article: "{previous_proposal.get("article", "")}"\n'
            f'- Plural: "{previous_proposal.get("plural", "")}"\n'
            f'- Example: "{previous_proposal.get("example", "")}"\n'
            "Reconsider the whole card honestly, not just the translation — keep whatever is "
            "already correct, but genuinely rethink anything that could be better (a different "
            "nuance, a more natural reading, a clearer example). Never change something just to "
            "look different, and never make it worse."
        )
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.5 if previous_proposal else 0.2,
            "responseMimeType": "application/json",
        },
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


_ENRICH_OPTIONS_PROMPT = """For the {language_name} {card_type} below, return ONLY a JSON \
object (no markdown, no commentary) with these keys:
- "translations": a JSON array of up to {n} DIFFERENT plausible translations \
into {back_language}, ranked by likely correctness, each a short string.
- "pronunciations": a JSON array of up to {n} DIFFERENT plausible phonetic \
transcriptions (IPA or a simple respelling) of the {language_name} text, each \
a short string, or [] if not applicable.
- "article": for a {language_name} noun one of "der","die","das","plural"; \
otherwise "none".
- "plural": for a noun, its plural form WITH the plural article (e.g. \
"die Tische"); "" if not a noun or it has no plural.
- "example": one short, natural example sentence in {language_name}, or "".

TEXT: {front}
"""


def enrich_card_options(
    front: str, language: str = "", card_type: str = "vocab", back_language: str = "English", n: int = 3
) -> dict:
    """Like enrich_card, but offers several ranked translation and
    pronunciation candidates instead of committing to one — backs the
    Telegram bot's pick-one-or-type-your-own word lookup (see
    apps.notifications.management.commands.poll_telegram_updates).
    """
    front = (front or "").strip()
    if not front:
        return {"translations": [], "pronunciations": [], "article": "none", "plural": "", "example": ""}
    if settings.GEMINI_API_KEY:
        try:
            return _enrich_options_with_gemini(front, language, card_type, back_language, n)
        except Exception:  # noqa: BLE001 — degrade to manual entry
            pass
    fallback = _enrich_fallback(front)
    return {
        "translations": [], "pronunciations": [],
        "article": fallback["article"], "plural": fallback["plural"], "example": fallback["example"],
    }


def _enrich_options_with_gemini(front: str, language: str, card_type: str, back_language: str, n: int) -> dict:
    prompt = _ENRICH_OPTIONS_PROMPT.format(
        language_name=_LANG_NAMES.get(language, "the target language"),
        back_language=(back_language or "English").strip(),
        card_type=card_type if card_type in ALLOWED_TYPES else "vocab",
        n=n,
        front=front[:500],
    )
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"},
    }
    res = requests.post(url, json=payload, timeout=30)
    res.raise_for_status()
    raw = res.json()["candidates"][0]["content"]["parts"][0]["text"]
    obj = _extract_json_object(raw)
    article = obj.get("article") if obj.get("article") in ALLOWED_ARTICLES else _detect_article(front)
    return {
        "translations": _dedupe_strings(obj.get("translations"), n),
        "pronunciations": _dedupe_strings(obj.get("pronunciations"), n),
        "article": article,
        "plural": str(obj.get("plural", "")).strip(),
        "example": str(obj.get("example", "")).strip(),
    }


def _dedupe_strings(values, n: int) -> list[str]:
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        s = str(v).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
        if len(out) >= n:
            break
    return out


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


_IMAGE_QUERY_PROMPT = """A language-flashcard app wants to auto-attach a small \
illustrative photo to this {language_name} {card_type} card.
Front: "{front}"
Meaning: "{back}"

Decide whether a photo could unambiguously depict this specific meaning. Concrete \
objects, animals, places, foods, and physical actions usually can. Days of the \
week, numbers, abstract concepts, emotions, grammar/function words, and terms \
whose most common photos online are unrelated to this meaning (e.g. a proper \
noun that collides with an event or brand name) usually can NOT — be honest and \
default to false when unsure, rather than risking a misleading picture.

If depictable, phrase the query so the item itself is the obvious, sole subject \
— prefer "glass of milk" over "breakfast table with milk", "red apple" over \
"fruit basket" — since a busy multi-object scene is as misleading here as an \
unrelated picture.

Return ONLY JSON (no markdown, no commentary):
{{"depictable": true|false, "query": "<if depictable, a short unambiguous \
English image-search phrase naming this single item as the sole subject; \
otherwise \"\">"}}
"""


def image_search_query(front: str, back: str, language: str = "", card_type: str = "vocab") -> str:
    """Ask Gemini whether `front`/`back` is something a photo can reliably
    depict and, if so, for a short unambiguous English image-search phrase.
    Returns "" (skip the image) when it isn't depictable, no GEMINI_API_KEY is
    configured, or the call fails — auto-picture-suggestion is best-effort and
    must never block card creation. Backs apps.cards.image_search
    .find_and_attach_thumbnail, shared by the web "find image" button and the
    Telegram bot's word wizard.
    """
    front = (front or "").strip()
    if not front or not settings.GEMINI_API_KEY:
        return ""
    try:
        prompt = _IMAGE_QUERY_PROMPT.format(
            language_name=_LANG_NAMES.get(language, "the target language"),
            card_type=card_type if card_type in ALLOWED_TYPES else "vocab",
            front=front[:200],
            back=(back or "")[:200],
        )
        obj = _extract_json_object(_gemini_text(prompt, timeout=20, temperature=0.0))
        if not obj.get("depictable"):
            return ""
        return str(obj.get("query", "")).strip()
    except Exception:  # noqa: BLE001 — degrade to no image
        return ""


_MNEMONIC_PROMPT = """A language learner is stuck on this {language_name} {card_type} \
card and wants a memory aid to make it stick.
Front: "{front}"
Meaning: "{back}"

Give ONE short, vivid memory trick — a mnemonic association, a sound-alike, a \
vivid mini-scene, or a clever way to link the form to the meaning. Write it in \
English, 1-2 sentences, no preamble like "Here's a mnemonic:".

Return ONLY JSON (no markdown, no commentary): {{"mnemonic": "<the memory aid>"}}
"""


def mnemonic_for(front: str, back: str, language: str = "", card_type: str = "vocab") -> str:
    """Ask Gemini for a short memory aid specific to this card. Returns "" when
    no GEMINI_API_KEY is configured or the call fails — best-effort, callers
    cache a non-empty result and never re-ask for the same card (see
    apps.cards.views.CardMnemonicView)."""
    front = (front or "").strip()
    if not front or not settings.GEMINI_API_KEY:
        return ""
    try:
        prompt = _MNEMONIC_PROMPT.format(
            language_name=_LANG_NAMES.get(language, "the target language"),
            card_type=card_type if card_type in ALLOWED_TYPES else "vocab",
            front=front[:200],
            back=(back or "")[:200],
        )
        obj = _extract_json_object(_gemini_text(prompt, timeout=20, temperature=0.7))
        return str(obj.get("mnemonic", "")).strip()
    except Exception:  # noqa: BLE001 — best-effort, never block the request
        return ""


_CONJUGATE_PROMPT = """You are a language teacher. Conjugate the {language_name} \
verb below across the situations/tenses a learner needs. Return ONLY a JSON \
object (no markdown, no commentary):
- "back": a concise meaning of the verb written in {back_language} (e.g. \
"to make / to do"), or "".
- "conjugations": an ordered JSON array. Each element is an object:
  - "tense": the name of the situation/tense (e.g. "Infinitiv", "Präsens", \
"Präteritum", "Perfekt", "Futur", "Imperativ"). For English use "base form", \
"present (3rd person)", "past simple", "past participle", "-ing form".
  - "form": the {language_name} conjugated form, using a natural example \
subject where helpful (e.g. "er macht", "er hat gemacht").
  - "meaning": the {back_language} equivalent of that exact form (e.g. \
"he makes", "he has made").
Cover the most useful forms for a learner (aim for 4-6). Be accurate.

VERB: {front}
"""


def conjugate_verb(front: str, language: str = "", back_language: str = "English") -> dict:
    """Return conjugations for a verb card (the "Fill conjugations" button).

    ``{"back": str, "conjugations": [{"tense","form","meaning"}]}``. Degrades to
    an empty result if no key is configured or the call fails.
    """
    front = (front or "").strip()
    if not front or not settings.GEMINI_API_KEY:
        return {"back": "", "conjugations": []}
    try:
        prompt = _CONJUGATE_PROMPT.format(
            language_name=_LANG_NAMES.get(language, "the target language"),
            back_language=(back_language or "English").strip(),
            front=front[:200],
        )
        obj = _extract_json_object(_gemini_text(prompt, timeout=45))
    except Exception:  # noqa: BLE001 — degrade gracefully
        return {"back": "", "conjugations": []}
    return {"back": str(obj.get("back", "")).strip(), "conjugations": _clean_conjugations(obj.get("conjugations"))}


def _clean_conjugations(raw) -> list[dict]:
    """Coerce an LLM conjugation array into clean {tense, form, meaning} rows."""
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    for it in raw:
        if not isinstance(it, dict):
            continue
        tense = str(it.get("tense", "")).strip()
        form = str(it.get("form", "")).strip()
        meaning = str(it.get("meaning", "")).strip()
        if not (tense or form or meaning):
            continue
        out.append({"tense": tense, "form": form, "meaning": meaning})
    return out


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


def _gemini_text(prompt: str, timeout: int = 30, temperature: float = 0.4) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    verify = getattr(settings, "GEMINI_VERIFY_SSL", True)
    res = requests.post(url, json=payload, timeout=timeout, verify=verify)
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


_PROMPT_FALLBACKS = {
    "Persian": [
        "امروز صبح زود بیدار شدم. بعد از صبحانه به سر کار رفتم. عصر با یک دوست قهوه خوردیم و درباره تعطیلات تابستان صحبت کردیم.",
        "آخر هفته گذشته با خانواده‌ام به بازار رفتیم. میوه و سبزیجات تازه خریدیم. بعد از ناهار در پارک قدم زدیم.",
        "دیروز هوا خیلی خوب بود. دوستم زنگ زد و پیشنهاد داد که دوچرخه‌سواری برویم. یک ساعت در کنار رودخانه رکاب زدیم.",
        "این هفته کلاس زبان جدیدی شروع کردم. معلم خیلی صبور است و تمرین‌های جالبی می‌دهد. هر روز یک ساعت مطالعه می‌کنم.",
        "دیشب یک فیلم خوب دیدم. داستان درباره سفر یک خانواده به کوهستان بود. صحنه‌های طبیعت بسیار زیبا بودند.",
        "امروز در رستوران غذای جدیدی امتحان کردم. طعم آن خیلی متفاوت بود اما دوست داشتم. حتماً دوباره می‌روم.",
        "هفته پیش برای اولین بار آشپزی کردم. یک سوپ ساده با سبزیجات درست کردم. همه از آن تعریف کردند.",
        "دیروز با قطار به شهر دیگری رفتم. از پنجره منظره زیبای مزارع را تماشا کردم. شب دیروقت برگشتم.",
        "امروز صبح بارندگی شدیدی بود. یک فنجان چای دم کردم و کنار پنجره نشستم. کتابی که چند وقت بود شروع نکرده بودم را برداشتم.",
        "این ماه تصمیم گرفتم هر روز نیم ساعت پیاده‌روی کنم. دیروز از خیابان‌های قدیمی شهر گذشتم. منظره مغازه‌های کوچک خیلی دلنشین بود.",
        "دوستم تولدش بود و برایش سورپرایز کوچکی ترتیب دادیم. یک کیک خانگی پختم و چند نفر از دوستان مشترکمان را دعوت کردم. خیلی خوش گذشت.",
        "دیروز به کتابخانه رفتم تا کتاب جدیدی پیدا کنم. کتابدار یک رمان تاریخی پیشنهاد داد. همان شب شروع به خواندن آن کردم.",
        "آخر هفته در خانه ماندم و خانه را مرتب کردم. چند جعبه قدیمی را باز کردم و چیزهای جالبی پیدا کردم. از دیدن عکس‌های قدیمی خیلی خوشحال شدم.",
        "امروز با همکارانم در کافه‌ای نزدیک محل کار ناهار خوردیم. از پروژه‌های جدید حرف زدیم. فضای کافه خیلی دنج و آرام بود.",
        "دیروز اولین برف زمستان بارید. بچه‌های همسایه در حیاط آدم‌برفی درست می‌کردند. من هم یک کاکائوی گرم درست کردم و از پنجره تماشا کردم.",
    ],
    "French": [
        "Je me suis réveillé tôt ce matin. Après le petit-déjeuner, je suis allé au travail. Le soir, j'ai retrouvé un ami pour boire un café.",
        "Le week-end dernier, j'ai visité un musée avec ma famille. Les expositions étaient très intéressantes. Nous avons mangé dans un petit restaurant après.",
        "Hier, le temps était magnifique. J'ai décidé de me promener dans le parc. J'ai rencontré des voisins et nous avons parlé longtemps.",
        "Ce matin, il pleuvait fort. J'ai préparé un thé chaud et j'ai lu un livre près de la fenêtre. C'était une matinée très agréable.",
        "La semaine dernière, j'ai commencé à apprendre une nouvelle recette. J'ai fait une soupe de légumes simple mais délicieuse. Toute la famille a aimé.",
    ],
    "Spanish": [
        "Me desperté temprano esta mañana. Después del desayuno, fui al trabajo. Por la tarde, tomé un café con un amigo.",
        "El fin de semana pasado fui al mercado con mi familia. Compramos frutas y verduras frescas. Después almorzamos juntos en casa.",
        "Ayer hizo muy buen tiempo. Salí a caminar por el parque y me encontré con unos vecinos. Charlamos durante un buen rato.",
        "Esta mañana llovía mucho. Preparé un té caliente y leí un libro junto a la ventana. Fue una mañana muy agradable.",
        "La semana pasada empecé a aprender una nueva receta. Hice una sopa de verduras sencilla pero deliciosa. A toda la familia le encantó.",
    ],
    "Arabic": [
        "استيقظت مبكرًا هذا الصباح. بعد الفطور، ذهبت إلى العمل. في المساء، تناولت القهوة مع صديق.",
        "في عطلة نهاية الأسبوع، ذهبت مع عائلتي إلى السوق. اشترينا الخضروات والفواكه الطازجة. ثم تناولنا الغداء معًا.",
        "أمس كان الطقس جميلًا. قررت التنزه في الحديقة. التقيت بجيران لطيفين وتحدثنا طويلًا.",
        "في الصباح كانت الأمطار غزيرة. أعددت كوبًا من الشاي الساخن وقرأت كتابًا بجانب النافذة. كان صباحًا هادئًا جدًا.",
        "الأسبوع الماضي بدأت تعلم وصفة جديدة. صنعت حساء خضار بسيطًا ولذيذًا. أحب الجميع الطعم.",
    ],
    "Russian": [
        "Сегодня я проснулся рано утром. После завтрака я пошёл на работу. Вечером встретился с другом за кофе.",
        "В прошлые выходные мы ходили с семьёй на рынок. Купили свежие овощи и фрукты. Потом вместе пообедали дома.",
        "Вчера была отличная погода. Я решил погулять в парке. Встретил соседей и мы долго разговаривали.",
        "Утром шёл сильный дождь. Я заварил чай и читал книгу у окна. Это было очень приятное утро.",
        "На прошлой неделе я начал учить новый рецепт. Приготовил простой овощной суп. Всей семье очень понравилось.",
    ],
    "Turkish": [
        "Bu sabah erken uyandım. Kahvaltının ardından işe gittim. Akşam bir arkadaşımla kahve içtik.",
        "Geçen hafta sonu ailемle pazara gittik. Taze sebze ve meyve aldık. Sonra birlikte öğle yemeği yedik.",
        "Dün hava çok güzeldi. Parkta yürüyüş yapmaya karar verdim. Komşularımla karşılaştık ve uzun süre sohbet ettik.",
        "Sabah çok yağmur yağıyordu. Sıcak bir çay hazırladım ve pencere kenarında kitap okudum. Çok huzurlu bir sabah geçirdim.",
        "Geçen hafta yeni bir tarif öğrenmeye başladım. Basit ama lezzetli bir sebze çorbası yaptım. Ailем çok beğendi.",
    ],
}

_PROMPT_TOPICS = [
    "a morning routine or daily schedule",
    "a visit to a market, shop, or restaurant",
    "a walk in a park or a trip to nature",
    "meeting a friend or family gathering",
    "a hobby or leisure activity",
    "a recent journey or short trip",
    "the weather and outdoor plans",
    "learning something new or a school/work day",
    "cooking a meal or trying new food",
    "a favourite book, film, or song",
]


def writing_prompt(language: str, translation_language: str, lesson_info: dict | None) -> dict:
    """Generate a short passage in *translation_language* for the learner to
    translate into *language*.  If *lesson_info* is given (dict with
    ``lesson`` and ``vocab``), tries to build the text around those words."""
    target_lang = _writing_lang_name(language)
    native_lang = (translation_language or "English").strip()

    if not settings.GEMINI_API_KEY:
        pool = _PROMPT_FALLBACKS.get(native_lang)
        if pool:
            fallback = random.choice(pool)
        else:
            fallback = random.choice([
                "I woke up early this morning. After breakfast, I went to work. In the evening, I had coffee with a friend.",
                "Last weekend I visited a market with my family. We bought fresh vegetables and fruit. We had lunch together afterwards.",
                "Yesterday the weather was beautiful. I decided to take a walk in the park. I met some neighbours and we chatted for a while.",
                "This week I started a new language class. The teacher is very patient and gives interesting exercises. I study for an hour every day.",
                "Last night I watched a good film. The story was about a family travelling in the mountains. The nature scenes were stunning.",
            ])
        return {"text": fallback, "source": "auto"}

    try:
        if lesson_info:
            vocab_lines = "\n".join(
                f"- {v['front']}: {v['back']}"
                for v in (lesson_info.get("vocab") or [])
                if v.get("front") and v.get("back")
            )
            if vocab_lines:
                prompt = (
                    f"You are helping a {target_lang} learner practise translation. "
                    f"Using 4-6 of the vocabulary words below, write a short, natural paragraph "
                    f"(3-5 sentences) in {native_lang} about everyday life. "
                    f"Make it feel like a real text, not a word list. "
                    f'Return ONLY JSON: {{"text": "<paragraph in {native_lang}>"}}. No markdown.\n\n'
                    f"Vocabulary ({target_lang} → {native_lang}):\n{vocab_lines}"
                )
                obj = _extract_json_object(_gemini_text(prompt, timeout=30, temperature=0.9))
                text = str(obj.get("text", "")).strip()
                if text:
                    lesson = lesson_info["lesson"]
                    return {
                        "text": text,
                        "source": "books",
                        "book_title": lesson.book.title,
                        "lesson_title": lesson.title,
                    }

        topic = random.choice(_PROMPT_TOPICS)
        prompt = (
            f"You are helping a {target_lang} learner practise translation. "
            f"Write a short, natural paragraph (3-5 sentences) in {native_lang} about: {topic}. "
            f"Use A2-B1 vocabulary — accessible but not trivial. "
            f"Write something specific and vivid, not generic. "
            f'Return ONLY JSON: {{"text": "<paragraph in {native_lang}>"}}. No markdown.'
        )
        obj = _extract_json_object(_gemini_text(prompt, timeout=30, temperature=0.9))
        text = str(obj.get("text", "")).strip()
        if not text:
            raise ValueError("empty")
        return {"text": text, "source": "auto"}

    except Exception:  # noqa: BLE001
        pool = _PROMPT_FALLBACKS.get(native_lang)
        fallback = random.choice(pool) if pool else "I woke up early this morning. After breakfast, I went to work."
        return {"text": fallback, "source": "auto"}


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


_READING_FALLBACKS: dict[str, list[str]] = {
    "de": [
        "Heute Morgen bin ich früh aufgestanden. Nach dem Frühstück bin ich zur Arbeit gegangen. Am Abend habe ich mit einem Freund Kaffee getrunken.",
        "Das Wetter ist heute sehr schön. Ich gehe gerne in den Park und lese ein Buch. Die Vögel singen und die Sonne scheint hell.",
        "Letzte Woche habe ich einen neuen Film gesehen. Die Geschichte war sehr interessant. Ich empfehle ihn allen meinen Freunden.",
        "Jeden Morgen trinke ich eine Tasse Kaffee und lese die Nachrichten. Dann fahre ich mit dem Fahrrad zur Arbeit. Der Weg dauert ungefähr zwanzig Minuten.",
        "Am Wochenende bin ich mit meiner Familie in die Berge gefahren. Wir haben gewandert und frische Luft genossen. Abends haben wir in einer kleinen Hütte gegessen.",
    ],
    "en": [
        "This morning I woke up early. After breakfast, I went to work. In the evening, I had coffee with a friend.",
        "The weather is beautiful today. I like going to the park and reading a book. The birds are singing and the sun is shining.",
        "Last week I watched a new film. The story was very interesting. I recommend it to all my friends.",
        "Every morning I drink a cup of coffee and read the news. Then I cycle to work. The journey takes about twenty minutes.",
    ],
    "fr": [
        "Ce matin, je me suis réveillé tôt. Après le petit-déjeuner, je suis allé au travail. Le soir, j'ai pris un café avec un ami.",
        "Le temps est très beau aujourd'hui. J'aime me promener dans le parc et lire un livre. Les oiseaux chantent et le soleil brille.",
    ],
    "es": [
        "Esta mañana me desperté temprano. Después del desayuno, fui al trabajo. Por la tarde, tomé un café con un amigo.",
        "El tiempo está muy bonito hoy. Me gusta ir al parque y leer un libro. Los pájaros cantan y el sol brilla.",
    ],
    "it": [
        "Stamattina mi sono svegliato presto. Dopo colazione, sono andato al lavoro. La sera, ho preso un caffè con un amico.",
        "Il tempo è molto bello oggi. Mi piace andare al parco e leggere un libro. Gli uccelli cantano e il sole splende.",
    ],
}


def conversation_reply(language: str, user_text: str, history: list[dict]) -> dict:
    """Reply to a learner's spoken/typed message, returning corrections.

    Returns ``{"response": str, "corrections": [{"original","correction","explanation"}]}``.
    """
    name = _writing_lang_name(language)
    if not settings.GEMINI_API_KEY:
        return {
            "response": "Sehr gut! Kannst du mehr erzählen?" if language == "de" else "Good! Can you tell me more?",
            "corrections": [],
        }

    history_text = "\n".join(
        f"{'User' if m.get('role') == 'user' else 'Tutor'}: {m.get('text', '')}"
        for m in (history or [])[-6:]
    )
    prompt = (
        f"You are a friendly {name} language tutor having a short conversation with a learner.\n"
        + (f"Recent conversation:\n{history_text}\n\n" if history_text else "")
        + f'The learner just said (in {name}): "{user_text[:500]}"\n\n'
        f"1. Spot any grammar or vocabulary errors in what the learner said.\n"
        f"2. Write a short natural reply in {name} (1-2 sentences). Continue the conversation naturally.\n"
        f"Return ONLY JSON (no markdown):\n"
        f'{{"response": "<your {name} reply>", '
        f'"corrections": [{{"original": "<wrong phrase>", "correction": "<correct version>", "explanation": "<short English note>"}}]}}\n'
        f"If no errors, corrections must be []. Keep the reply short and encouraging."
    )
    try:
        obj = _extract_json_object(_gemini_text(prompt, timeout=30, temperature=0.7))
        corrections = []
        for c in obj.get("corrections") or []:
            if not isinstance(c, dict):
                continue
            orig = str(c.get("original", "")).strip()
            corr = str(c.get("correction", "")).strip()
            if orig or corr:
                corrections.append({
                    "original": orig,
                    "correction": corr,
                    "explanation": str(c.get("explanation", "")).strip(),
                })
        return {"response": str(obj.get("response", "")).strip(), "corrections": corrections}
    except Exception:  # noqa: BLE001
        fallback = "Interessant! Weiter so." if language == "de" else "Interesting! Keep going."
        return {"response": fallback, "corrections": []}


def conversation_text(language: str, lesson_info: dict | None = None) -> dict:
    """Generate a short passage in *language* for reading-aloud practice (A2-B1).

    If *lesson_info* is given (same shape as writing_prompt), builds the text
    around that lesson's vocabulary so the reader practises known words.
    Returns ``{"text": str, "source": "books"|"auto"|"fallback", ...}``.
    """
    name = _writing_lang_name(language)

    if lesson_info and settings.GEMINI_API_KEY:
        vocab_lines = "\n".join(
            f"- {v['front']}"
            for v in (lesson_info.get("vocab") or [])
            if v.get("front")
        )
        if vocab_lines:
            try:
                prompt = (
                    f"Write a short, natural paragraph (3-5 sentences) in {name} for a language learner to read aloud. "
                    f"Use 4-6 of the {name} words/phrases below naturally in the text. "
                    f"A2-B1 level — clear and flowing, not a word list. "
                    f'Return ONLY JSON: {{"text": "<paragraph in {name}>"}}. No markdown.\n\n'
                    f"Words to use:\n{vocab_lines}"
                )
                obj = _extract_json_object(_gemini_text(prompt, timeout=30, temperature=0.9))
                text = str(obj.get("text", "")).strip()
                if text:
                    lesson = lesson_info["lesson"]
                    return {
                        "text": text,
                        "source": "books",
                        "book_title": lesson.book.title,
                        "lesson_title": lesson.title,
                    }
            except Exception:  # noqa: BLE001
                pass  # fall through to auto

    if not settings.GEMINI_API_KEY:
        pool = _READING_FALLBACKS.get(language, _READING_FALLBACKS["en"])
        return {"text": random.choice(pool), "source": "fallback"}

    topic = random.choice(_PROMPT_TOPICS)
    prompt = (
        f"Write a short, natural paragraph (3-5 sentences) in {name} for a language learner to read aloud. "
        f"Use A2-B1 vocabulary — clear and natural, not overly simple. Topic: {topic}. "
        f"Write something specific and vivid. "
        f'Return ONLY JSON: {{"text": "<paragraph in {name}>"}}. No markdown.'
    )
    try:
        obj = _extract_json_object(_gemini_text(prompt, timeout=30, temperature=0.9))
        text = str(obj.get("text", "")).strip()
        if text:
            return {"text": text, "source": "auto"}
        raise ValueError("empty")
    except Exception:  # noqa: BLE001
        pool = _READING_FALLBACKS.get(language, _READING_FALLBACKS["en"])
        return {"text": random.choice(pool), "source": "fallback"}


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
        "plural": str(item.get("plural", "")).strip(),
        "example": str(item.get("example", "")).strip(),
        "notes": str(item.get("notes", "")).strip(),
        "table": item.get("table") if isinstance(item.get("table"), dict) else None,
        "genders": [],
        "conjugations": _clean_conjugations(item.get("conjugations")),
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
                "plural": "",
                "example": "",
                "notes": "",
                "table": None,
                "genders": [],
                "tags": [],
            }
        )
    return cards
