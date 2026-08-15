"""The language catalogue — the single source of truth for language codes.

Two different questions are asked about a user, and they must not be confused:

  * `ui_language` — what the *interface* is written in. Only en/fa, because
    that's what we've translated.
  * `learning_languages` / `known_languages` — what the user wants to learn and
    what they already understand. These drive content matching, notably which
    reels reach them (see apps.reels).

Content carries the mirror image of the same pair: a reel has a
**target language** (what it teaches) and a **base language** (what it's
explained in). An Instagram account teaching German to Persian speakers is
target=de, base=fa. A reel matches a user when the target is something they're
learning and the base is something they already understand.

Keep in sync with the frontend mirror in frontend/src/lib/languages.ts.
"""

# code -> (English name, endonym). The endonym matters: someone picking their
# own language should see it written the way they write it.
LANGUAGES = {
    "de": ("German", "Deutsch"),
    "en": ("English", "English"),
    "fa": ("Persian", "فارسی"),
    "ar": ("Arabic", "العربية"),
    "tr": ("Turkish", "Türkçe"),
    "fr": ("French", "Français"),
    "es": ("Spanish", "Español"),
    "it": ("Italian", "Italiano"),
    "ru": ("Russian", "Русский"),
    "nl": ("Dutch", "Nederlands"),
}

LANGUAGE_CODES = list(LANGUAGES)
LANGUAGE_CHOICES = [(code, names[0]) for code, names in LANGUAGES.items()]

# Content that teaches a language *in* that language — a German-only reel with
# no translation. Stored as "" rather than a code: it isn't a language the user
# has to already know, so it reaches every learner of the target language.
IMMERSIVE = ""


def label(code: str) -> str:
    """"German (Deutsch)", or the raw code if we don't know it."""
    names = LANGUAGES.get(code)
    if not names:
        return code
    english, endonym = names
    return english if english == endonym else f"{english} ({endonym})"


def clean_codes(values) -> list[str]:
    """Normalise a client-supplied list: known codes only, lower-cased,
    de-duplicated, order preserved (the first entry is the user's primary)."""
    if not isinstance(values, (list, tuple)):
        return []
    seen, out = set(), []
    for raw in values:
        code = str(raw).strip().lower()
        if code in LANGUAGES and code not in seen:
            seen.add(code)
            out.append(code)
    return out


def languages_public() -> list[dict]:
    """The catalogue, for the onboarding picker."""
    return [
        {"code": code, "name": english, "endonym": endonym}
        for code, (english, endonym) in LANGUAGES.items()
    ]
