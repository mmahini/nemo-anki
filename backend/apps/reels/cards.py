"""Make cards from a reel.

Split deliberately in two:

  * The expensive half — asking Gemini to turn the reel's caption into card
    drafts — runs **once per reel**. The drafts land in ``Reel.cards_cache``
    and every later user reuses them verbatim.
  * The metering half is **per user**: each request that goes down the AI path
    consumes one unit of the requester's daily quota, cache hit or not. The
    value delivered is identical either way; the quota measures value, not our
    marginal Gemini cost. (The caller does the consuming — see
    ReelMakeCardsView — so this module stays imperative-only.)

Drafts are dicts shaped like the Import flow's drafts (front/back/reading/…),
so materialising them is the same bulk-create + reverse-cards dance as
apps.decks.sharing.copy_deck_tree.
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings
from django.utils import timezone

from apps.accounts.languages import LANGUAGES

from .models import Reel

logger = logging.getLogger(__name__)

MAX_CARDS = 8

_ALLOWED_TYPES = {"vocab", "sentence", "verb", "adjective", "adverb", "preposition"}
_ALLOWED_ARTICLES = {"none", "der", "die", "das", "plural"}

_PROMPT = """You are a language-learning flashcard generator. The text below \
is the caption of a short {target_name}-teaching video. Extract the words and \
phrases the video actually teaches and turn them into spaced-repetition cards.

Return ONLY a JSON array, at most {max_cards} elements. Each element:
- "card_type": one of "vocab", "sentence", "verb", "adjective", "adverb", \
"preposition". Single words by part of speech; full sentences -> "sentence".
- "front": the {target_name} word or sentence, exactly as taught.
- "back": a concise translation in {back_name}.
- "reading": phonetic transcription (IPA-ish) of the front, or "".
- "article": for {target_name} nouns one of "der","die","das","plural" where \
that applies; otherwise "none".
- "example": a short natural example sentence in {target_name}, or "".

Only include items genuinely derivable from the caption — hashtags count as \
topic hints, not vocabulary. If the caption teaches nothing concrete, return [].
No markdown fences, no commentary.

CAPTION:
{text}
"""


def _language_name(code: str) -> str:
    return LANGUAGES.get(code, (code or "the target language", ""))[0]


def source_text(reel: Reel) -> str:
    parts = [reel.title, reel.caption]
    if reel.hashtags:
        parts.append(" ".join(f"#{h}" for h in reel.hashtags))
    return "\n".join(p for p in parts if p).strip()


def generate_card_drafts(reel: Reel) -> list[dict]:
    """Gemini → validated draft dicts. Empty list when there's nothing to work
    with (no caption, no API key, or the model found nothing teachable)."""
    text = source_text(reel)
    if not text or not settings.GEMINI_API_KEY:
        return []

    # Cached drafts are shared by every user, so the answer language has to be
    # a property of the reel, not the requester: the explanation language when
    # there is one, English for immersive reels.
    back_code = reel.base_language or "en"
    prompt = _PROMPT.format(
        target_name=_language_name(reel.target_language),
        back_name=_language_name(back_code),
        max_cards=MAX_CARDS,
        text=text[:2000],
    )
    try:
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
        from apps.imports.gemini import _extract_json_array

        items = _extract_json_array(raw)
    except Exception as exc:  # noqa: BLE001 — a failed generation is a 4xx, not a 500
        logger.warning("reels: card generation failed for reel %s: %s", reel.pk, exc)
        return []

    drafts: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        front = str(it.get("front", "")).strip()
        if not front:
            continue
        card_type = it.get("card_type") if it.get("card_type") in _ALLOWED_TYPES else "vocab"
        article = it.get("article") if it.get("article") in _ALLOWED_ARTICLES else "none"
        drafts.append(
            {
                "card_type": card_type,
                "front": front,
                "back": str(it.get("back", "")).strip(),
                "reading": str(it.get("reading", "")).strip(),
                "article": article,
                "example": str(it.get("example", "")).strip(),
            }
        )
        if len(drafts) >= MAX_CARDS:
            break
    return drafts


def ensure_drafts(reel: Reel) -> list[dict]:
    """The once-per-reel half: return cached drafts, generating and persisting
    them on first use."""
    if reel.cards_cache:
        return reel.cards_cache
    drafts = generate_card_drafts(reel)
    if drafts:
        reel.cards_cache = drafts
        reel.cards_generated_at = timezone.now()
        reel.save(update_fields=["cards_cache", "cards_generated_at"])
    return drafts


WRAPPER_NAME = "Reels"


def deck_name(reel: Reel) -> str:
    return reel.title or f"@{reel.source.username} · {reel.key}"


def existing_deck_for(reel: Reel, user):
    """The already-materialised deck for this user, if any — a repeat tap
    must be free (no quota) and land on the same deck."""
    from apps.decks.models import Deck

    return (
        Deck.objects.filter(
            user=user,
            parent__name=WRAPPER_NAME,
            parent__parent=None,
            name=deck_name(reel),
            cards__isnull=False,
        )
        .distinct()
        .first()
    )


def materialize(reel: Reel, user, drafts: list[dict]):
    """Create (or find) the user's deck for this reel and fill it once."""
    from apps.cards.models import Card, add_reverse_cards
    from apps.decks.models import Deck
    from apps.decks.sharing import _default_config

    cfg = _default_config(user)
    wrapper, _ = Deck.objects.get_or_create(
        user=user, parent=None, name=WRAPPER_NAME, defaults={"config": cfg, "language": ""}
    )
    deck, _ = Deck.objects.get_or_create(
        user=user,
        parent=wrapper,
        name=deck_name(reel),
        defaults={"config": cfg, "language": reel.target_language},
    )
    if not Card.objects.filter(deck=deck).exists():
        created = Card.objects.bulk_create(
            Card(
                deck=deck,
                position=i,
                language=reel.target_language,
                **draft,
            )
            for i, draft in enumerate(drafts)
        )
        add_reverse_cards(created)
    return deck
