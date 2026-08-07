import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from requests.adapters import HTTPAdapter
from rest_framework.exceptions import Throttled
from urllib3.util.retry import Retry

from apps.cards.image_search import attach_thumbnail_from_url
from apps.imports.gemini import enrich_card, enrich_card_options, transcribe_audio
from apps.imports.services import create_sentence_card, create_vocab_card
from apps.notifications.models import PendingTelegramCard, TelegramLink, TelegramPollerState
from apps.subscriptions.quota import consume_ai_quota
from core.telegram import download_telegram_file

logger = logging.getLogger(__name__)

# Bounds the "fire and forget" Telegram calls (typing indicator, callback-query
# ack) that nothing downstream waits on — a small fixed pool instead of a raw
# thread per call, so a burst of messages can't spawn unbounded threads.
_FIRE_AND_FORGET = ThreadPoolExecutor(max_workers=4, thread_name_prefix="telegram-ack")

SUPPORTED_LANGUAGES = {"de": "German", "en": "English"}

# How long a word/sentence sent before /lang is remembered for automatic
# resume — generous on purpose (a learner may set up the bot, get pulled
# away, and only finish a while later), not a "session" concept.
PENDING_LOOKUP_TTL = timedelta(hours=24)

# Matches PendingTelegramCard.front's and TelegramLink.pending_lookup_text's
# max_length — capped before any AI call or DB write so an oversized word/
# sentence can never raise a DataError and crash the poller (see PR#9).
MAX_LOOKUP_TEXT_LENGTH = 200

# Telegram voice messages (message.voice) are OGG/Opus, a few seconds long.
# Cap both duration and size so a huge/looping clip can't stall the poller or
# run up Gemini cost — enforced here (not inside transcribe_audio) so the cap
# and its user-facing replies live with the flow that uses them.
_VOICE_MAX_DURATION_SECONDS = 30
_VOICE_MAX_BYTES = 10 * 1024 * 1024

_CONNECT_FIRST_TEXT = 'Connect your account first — open Nemo Anki and tap "Connect Telegram".'

_ONBOARDING_EXAMPLE = (
    "Send /lang de or /lang en to set your target language. Then just send a word to add it as "
    "a card, or /sentence <text> for a full sentence. For example:\n\n"
    "/lang de\n"
    "Haus\n"
    "/sentence Ich gehe heute ins Kino.\n\n"
    "You can also send a voice message to look up the word or sentence you say."
)


def _redact_token(text: str) -> str:
    """Strips the bot token out of a string before it's logged. Connection
    errors from requests/urllib3 embed the full request URL — including
    `/bot<TOKEN>/...` — in their message, so logging an exception's str()
    as-is would leak the token into stdout/log storage."""
    token = settings.TELEGRAM_BOT_TOKEN
    return text.replace(token, "<redacted>") if token else text


def _telegram_call(api: str, method: str, payload: dict) -> dict | None:
    """POSTs to the Telegram Bot API and returns Telegram's `result` payload,
    or None if the call failed or was rejected. A 200 response doesn't mean
    success — Telegram returns HTTP 200 with {"ok": false} for plenty of
    rejections (bot blocked by the user, bad chat_id, message too long,
    etc.), so callers that only checked "didn't raise" were treating those
    as silent successes."""
    try:
        resp = requests.post(f"{api}/{method}", json=payload, timeout=10)
        data = resp.json()
    except requests.RequestException as e:
        logger.warning("Telegram %s request failed: %s", method, _redact_token(str(e)))
        return None
    except ValueError:
        logger.warning("Telegram %s returned a non-JSON response (status %s)", method, resp.status_code)
        return None
    if not data.get("ok"):
        logger.warning("Telegram %s rejected: %s", method, data.get("description"))
        return None
    return data.get("result")


def _telegram_post(api: str, method: str, payload: dict) -> bool:
    """Like _telegram_call, for callers that only care whether Telegram
    accepted the call, not the result payload."""
    return _telegram_call(api, method, payload) is not None


def _reply(api: str, chat_id, text: str, reply_markup: dict | None = None) -> bool:
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _telegram_post(api, "sendMessage", payload)


def _reply_and_get_message_id(api: str, chat_id, text: str, reply_markup: dict | None = None) -> int | None:
    """Like _reply, but returns the sent message's id instead of a bool —
    needed so a later background step (see find_and_attach_proposal_image)
    can edit this exact message once it has something to add."""
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    result = _telegram_call(api, "sendMessage", payload)
    return result.get("message_id") if result else None


def _edit_message_with_photo(
    api: str, chat_id, message_id: int, photo_url: str, caption: str, reply_markup: dict | None = None
) -> bool:
    """Turns an already-sent text message into a photo message — used to
    attach a proposal's image after the fact, once the background search
    finds one, without making the user wait for it up front."""
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "media": {"type": "photo", "media": photo_url, "caption": caption},
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _telegram_call(api, "editMessageMedia", payload) is not None


def _send_photo(api: str, chat_id, data: bytes, caption: str, reply_markup: dict | None = None) -> bool:
    """Uploads raw JPEG bytes directly to Telegram. Takes bytes rather than
    a Django FieldFile so a caller that just fetched/resized an image (see
    _finalize) can forward those same bytes instead of reading them back
    from storage right after saving them there. reply_markup, if given, is
    JSON-encoded — this is a multipart request (because of `files`), and
    Telegram expects structured fields like this as a JSON string there,
    not a raw object."""
    payload = {"chat_id": chat_id, "caption": caption}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        resp = requests.post(
            f"{api}/sendPhoto",
            data=payload,
            files={"photo": ("card.jpg", data, "image/jpeg")},
            timeout=15,
        )
        result = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("Telegram sendPhoto failed: %s", _redact_token(str(e)))
        return False
    if not result.get("ok"):
        logger.warning("Telegram sendPhoto rejected: %s", result.get("description"))
        return False
    return True


def _send_typing(api: str, chat_id) -> None:
    """Best-effort "bot is typing…" cue shown before a multi-second Gemini
    call — purely cosmetic, so it's dispatched on the fire-and-forget pool
    rather than blocking the Gemini call on Telegram's own ~2s round trip."""
    _FIRE_AND_FORGET.submit(_telegram_post, api, "sendChatAction", {"chat_id": chat_id, "action": "typing"})


def _answer_callback(api: str, callback_id: str, text: str = "", show_alert: bool = False) -> None:
    """Best-effort reply to a callback_query tap. The bare textless call
    dismisses the tapped button's loading spinner; callers that need the
    user to know a tap was stale (see _pending in _handle_callback_query)
    pass text + show_alert so a brief alert explains the no-op instead of
    leaving the user to wonder why nothing happened."""
    payload = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text
    if show_alert:
        payload["show_alert"] = True
    _FIRE_AND_FORGET.submit(_telegram_post, api, "answerCallbackQuery", payload)


def _handle_start(api: str, chat_id, text: str) -> None:
    """/start — either completes the connect handshake (a token following
    the command) or is a bare /start with nothing to link (a fresh open of
    the bot with no deep link, or an already-connected user reopening the
    chat). Always replies with something useful instead of going silent —
    previously a bare /start fell through to word lookup entirely, since
    nothing else matched it (see PR#7)."""
    token = text.split(" ", 1)[1].strip() if " " in text else ""
    if token and TelegramLink.objects.filter(connect_token=token, chat_id__isnull=True).update(chat_id=chat_id):
        _reply(api, chat_id, f"Connected! {_ONBOARDING_EXAMPLE}", reply_markup=_main_menu_keyboard())
        return
    if TelegramLink.objects.filter(chat_id=chat_id).exists():
        _reply(
            api,
            chat_id,
            "👋 Welcome back!\n\nWhat would you like to do?",
            reply_markup=_main_menu_keyboard(),
        )
    else:
        _reply(api, chat_id, _CONNECT_FIRST_TEXT)


def _lang_usage_reply(link: TelegramLink) -> str:
    """The /lang usage hint, plus the current language when one is set —
    shared by the text command and the menu:lang button so both give the
    same hint instead of a bare command reference."""
    current = SUPPORTED_LANGUAGES.get(link.default_language)
    current_part = f" Currently set to {current}." if current else ""
    return f"Usage: /lang de or /lang en.{current_part}"


def _handle_lang(link: TelegramLink, api: str, chat_id, text: str) -> None:
    code = text.lower().removeprefix("/lang").strip()
    if code not in SUPPORTED_LANGUAGES:
        _reply(api, chat_id, _lang_usage_reply(link))
        return
    link.default_language = code
    link.save(update_fields=["default_language"])
    _reply(
        api, chat_id,
        f"Got it — I'll look up words in {SUPPORTED_LANGUAGES[code]} from now on.",
        reply_markup=_main_menu_keyboard(),
    )

    resume_text, resume_type = link.pending_lookup_text, link.pending_lookup_card_type
    resume_valid = bool(resume_text) and link.pending_lookup_expires_at and timezone.now() < link.pending_lookup_expires_at
    if resume_text:
        link.pending_lookup_text = ""
        link.pending_lookup_card_type = ""
        link.pending_lookup_expires_at = None
        link.save(update_fields=["pending_lookup_text", "pending_lookup_card_type", "pending_lookup_expires_at"])
    if resume_valid:
        if resume_type == "sentence":
            _handle_sentence_input(link, api, chat_id, resume_text)
        else:
            _handle_word_lookup(link, api, chat_id, resume_text)


def _main_menu_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "🔎 Lookup word", "callback_data": "menu:lookup"},
                {"text": "📝 Sentence", "callback_data": "menu:sentence"},
            ],
            [
                {"text": "🌐 Language", "callback_data": "menu:lang"},
            ],
        ]
    }


def _cancel_active_work(link: TelegramLink) -> None:
    """Discard everything the user is mid-way through — an in-progress card
    (PendingTelegramCard) and any word/sentence stashed while waiting for
    /lang — so /cancel and the Cancel buttons are a clean global escape
    rather than a dead end that forces finishing a card you don't want."""
    PendingTelegramCard.objects.filter(user=link.user).delete()
    if link.pending_lookup_text:
        link.pending_lookup_text = ""
        link.pending_lookup_card_type = ""
        link.pending_lookup_expires_at = None
        link.save(update_fields=["pending_lookup_text", "pending_lookup_card_type", "pending_lookup_expires_at"])


def _cancel_and_show_menu(api: str, chat_id) -> None:
    """The shared reply after a cancel: confirm it worked and hand the user
    the main menu, so the next thing they do is a deliberate choice instead
    of an accidental word lookup."""
    _reply(api, chat_id, "OK, cancelled. What would you like to do?", reply_markup=_main_menu_keyboard())


def _wizard_in_progress(link: TelegramLink) -> bool:
    """True when the user is mid-wizard (awaiting a translation or a
    pronunciation). Menu prompts check this so "Send me a word" can't turn
    the user's next message into a wizard answer by accident."""
    return PendingTelegramCard.objects.filter(user=link.user).exclude(awaiting_field="").exists()


def _options_keyboard(pending_id: int, options: list[str], choose_prefix: str, own_prefix: str) -> dict:
    rows = [[{"text": opt, "callback_data": f"{choose_prefix}:{pending_id}:{i}"}] for i, opt in enumerate(options)]
    rows.append([{"text": "✏️ Type my own", "callback_data": f"{own_prefix}:{pending_id}"}])
    rows.append([{"text": "❌ Cancel", "callback_data": f"cancel:{pending_id}"}])
    return {"inline_keyboard": rows}


def _cancel_keyboard(pending_id: int) -> dict:
    """A lone Cancel button for the type-it-yourself prompts — the same
    escape the options pickers get via _options_keyboard, so a user who'd
    rather abandon the card can tap instead of typing /cancel."""
    return {"inline_keyboard": [[{"text": "❌ Cancel", "callback_data": f"cancel:{pending_id}"}]]}


def _prompt_translation(api: str, chat_id, pending: PendingTelegramCard) -> None:
    if pending.translation_options:
        _reply(
            api, chat_id, f"{pending.front}\n\nWhich translation is correct?",
            reply_markup=_options_keyboard(pending.id, pending.translation_options, "choose_back", "pick_own_back"),
        )
    else:
        _reply(
            api, chat_id, f'Send the translation for "{pending.front}":',
            reply_markup=_cancel_keyboard(pending.id),
        )


def _prompt_pronunciation(api: str, chat_id, pending: PendingTelegramCard) -> None:
    if pending.pronunciation_options:
        _reply(
            api, chat_id, "Which pronunciation is correct?",
            reply_markup=_options_keyboard(
                pending.id, pending.pronunciation_options, "choose_reading", "pick_own_reading"
            ),
        )
    else:
        _reply(
            api, chat_id, "Send the pronunciation (or /skip to leave it blank):",
            reply_markup=_cancel_keyboard(pending.id),
        )


def _proposal_caption(pending: PendingTelegramCard) -> str:
    label = "Sentence" if pending.card_type == "sentence" else "Word"
    lines = [f"{label}: {pending.front}", "", f"Meaning: {pending.back}"]
    if pending.reading:
        lines += ["", f"Reading: {pending.reading}"]
    if pending.example:
        lines += ["", f"Example: {pending.example}"]
    return "\n".join(lines)


def _proposal_keyboard(pending_id: int) -> dict:
    return {
        "inline_keyboard": [
            [{"text": "✅ Create", "callback_data": f"create:{pending_id}"}],
            [{"text": "✏️ Edit", "callback_data": f"edit:{pending_id}"}],
            [{"text": "🔄 Regenerate", "callback_data": f"regenerate:{pending_id}"}],
        ]
    }


def _send_proposal(api: str, chat_id, pending: PendingTelegramCard) -> None:
    """Show the word/meaning/reading/example gathered so far, with Create/
    Edit/Regenerate buttons — sent as text immediately, without waiting on
    an image. The picture (if Gemini judges the meaning depictable at all)
    is searched for in the background (see find_and_attach_proposal_image)
    and, once found, edited into this same message — a Gemini call plus an
    Openverse search is 2-5+ seconds the user doesn't need to wait through
    just to see their translation and pick Create.

    image_url is explicitly cleared here (not just left as whatever it was)
    so that tapping Create before the background search finishes can never
    attach a stale image left over from an earlier proposal/regenerate. A
    full save (not update_fields) is deliberate — callers (_handle_reply,
    the choose_reading/regenerate callbacks) set fields like `reading` or
    `back` on this same in-memory instance without saving them first,
    relying on this save to persist them too."""
    pending.image_url = ""
    pending.awaiting_field = ""
    pending.save()
    caption = _proposal_caption(pending)
    keyboard = _proposal_keyboard(pending.id)
    message_id = _reply_and_get_message_id(api, chat_id, caption, reply_markup=keyboard)
    if message_id:
        from apps.notifications.tasks import find_and_attach_proposal_image

        find_and_attach_proposal_image.delay(
            pending.id, chat_id, message_id, pending.front, pending.back, pending.language, pending.card_type,
            pending.reading, pending.example,
        )


def _finalize(api: str, chat_id, pending: PendingTelegramCard) -> None:
    """Actually create the card — triggered by the Create button, never
    directly by the wizard (see _send_proposal). If the background image
    search (see find_and_attach_proposal_image) already found one by the
    time Create is tapped, pending.image_url is set and gets attached here;
    if not, the card is still created immediately without one — the image
    was always best-effort and must never hold up Create.

    The row is claimed (deleted) *before* creating the card, not after: a
    second Create tap for the same row — a genuine double-tap, or a retry
    after the user saw no confirmation because something below raised —
    must always find nothing left to claim and no-op, rather than create a
    second card. Deleting last would leave a window where the card already
    exists but the row is still claimable, so a retry duplicates it. Scoped
    by user as well as id — same ownership check _pending() already applies
    before handing this a row — so the claim itself never trusts the
    caller alone to have enforced it.

    Because the row is claimed *before* creation, a failure mid-create can't
    be retried by re-tapping — the create is wrapped so the user gets a
    clear "send it again" reply (and the menu) instead of a silent no-op,
    and the failure is logged with the exception for debugging."""
    if not PendingTelegramCard.objects.filter(id=pending.id, user=pending.user).delete()[0]:
        return
    menu = _main_menu_keyboard()
    create = create_sentence_card if pending.card_type == "sentence" else create_vocab_card
    try:
        card = create(
            pending.user, pending.front, pending.language,
            {
                "back": pending.back, "reading": pending.reading,
                "article": pending.article, "plural": pending.plural, "example": pending.example,
            },
        )
    except Exception:  # noqa: BLE001 — see docstring
        # The row was already claimed above — that ordering is what makes a
        # double-tap safe — so a failure here can't silently retry the same
        # word. The user still needs to know it failed and what to do next,
        # otherwise they stare at a tap that did nothing.
        logger.exception("Telegram card creation failed for user %s", pending.user_id)
        _reply(api, chat_id, "⚠️ Something went wrong saving your card — please send it again.", reply_markup=menu)
        return
    _, image_data = attach_thumbnail_from_url(card, pending.image_url) if pending.image_url else (None, None)
    caption = f'✅ Added "{pending.front}" — {pending.back or card.back}\n\nTo: {card.deck.full_name}'
    if image_data:
        # The card is already saved either way — if only the richer photo
        # message fails (bad/expired image URL, Telegram rejects the file),
        # still confirm via plain text rather than leaving the user with no
        # acknowledgement that Create actually worked.
        if not _send_photo(api, chat_id, image_data, caption, reply_markup=menu):
            _reply(api, chat_id, caption, reply_markup=menu)
    else:
        _reply(api, chat_id, caption, reply_markup=menu)


def _regenerate(link: TelegramLink, api: str, chat_id, pending: PendingTelegramCard) -> None:
    """Ask Gemini for a fresh take on the whole card — triggered by the
    Regenerate button — and show it as a new proposal (see _send_proposal).
    A genuinely new AI request, not a pick among candidates already fetched:
    `enrich_card` is given the full previous proposal so it can honestly
    reconsider it rather than just avoid repeating the translation."""
    try:
        consume_ai_quota(link.user)
    except Throttled as e:
        _reply(api, chat_id, str(e.detail))
        return
    previous = {
        "back": pending.back, "reading": pending.reading,
        "article": pending.article, "plural": pending.plural, "example": pending.example,
    }
    _send_typing(api, chat_id)
    result = enrich_card(
        pending.front, pending.language, pending.card_type, link.default_back_language,
        previous_proposal=previous,
    )
    if result.get("back"):
        pending.back = result["back"]
    pending.reading = result.get("reading", "")
    pending.article = result.get("article", pending.article)
    pending.plural = result.get("plural", "")
    pending.example = result.get("example", "")
    pending.save(update_fields=["back", "reading", "article", "plural", "example"])
    _send_proposal(api, chat_id, pending)


def _stash_pending_lookup(link: TelegramLink, api: str, chat_id, text: str, card_type: str) -> None:
    """Remember a word/sentence sent before /lang was set, so it can resume
    automatically once it is (see _handle_lang) instead of being lost.
    Capped to MAX_LOOKUP_TEXT_LENGTH — see _handle_word_lookup and
    _handle_sentence_input for the same cap applied to their success paths
    (PR#9)."""
    text = text[:MAX_LOOKUP_TEXT_LENGTH]
    link.pending_lookup_text = text
    link.pending_lookup_card_type = card_type
    link.pending_lookup_expires_at = timezone.now() + PENDING_LOOKUP_TTL
    link.save(update_fields=["pending_lookup_text", "pending_lookup_card_type", "pending_lookup_expires_at"])
    _reply(
        api, chat_id,
        f'Tell me your language first — send /lang de or /lang en. I\'ll look up "{text}" as soon as you do.',
    )


def _handle_word_lookup(link: TelegramLink, api: str, chat_id, text: str) -> None:
    text = text[:MAX_LOOKUP_TEXT_LENGTH]
    if not link.default_language:
        _stash_pending_lookup(link, api, chat_id, text, "vocab")
        return
    try:
        consume_ai_quota(link.user)
    except Throttled as e:
        _reply(api, chat_id, str(e.detail))
        return
    _propose_word(link, api, chat_id, text)


def _propose_word(link: TelegramLink, api: str, chat_id, text: str) -> None:
    """The post-quota body of a word lookup: run enrich_card_options, pick its
    top translation/pronunciation, and show the Create/Edit proposal. Split out
    of _handle_word_lookup so the voice path (which has already consumed its
    quota on transcription — one logical lookup per request) can drive the exact
    same card pipeline without double-charging."""
    text = text[:MAX_LOOKUP_TEXT_LENGTH]
    _send_typing(api, chat_id)
    result = enrich_card_options(text, link.default_language, "vocab", link.default_back_language)
    translations = result.get("translations", [])
    pronunciations = result.get("pronunciations", [])
    # enrich_card_options ranks its candidates "by likely correctness" — take
    # its top pick and go straight to the full proposal instead of making the
    # user confirm a translation and a pronunciation on two separate screens
    # first. Edit (on the proposal) still lets them correct either one
    # manually if the top pick is wrong, via the same _handle_reply /
    # _prompt_pronunciation path this used to reach directly.
    pending, _ = PendingTelegramCard.objects.update_or_create(
        user=link.user,
        defaults={
            "card_type": "vocab",
            "language": link.default_language,
            "front": text,
            "back": translations[0] if translations else "",
            "reading": pronunciations[0] if translations and pronunciations else "",
            "article": result.get("article", "none"),
            "plural": result.get("plural", ""),
            "example": result.get("example", ""),
            "translation_options": translations,
            "pronunciation_options": pronunciations,
            "awaiting_field": "" if translations else "back",
        },
    )
    if translations:
        _send_proposal(api, chat_id, pending)
    else:
        # Same fallback as always when Gemini didn't offer anything to
        # auto-pick from — ask the user to type the translation manually.
        _prompt_translation(api, chat_id, pending)


def _handle_sentence_input(link: TelegramLink, api: str, chat_id, text: str) -> None:
    """The /sentence flow: a full sentence's translation is normally a
    single natural rendering (unlike a word, which can have several equally
    valid ones), so this skips the pick-a-translation/pick-a-pronunciation
    wizard entirely and goes straight from enrich_card to a proposal — the
    same shape _regenerate already uses."""
    text = text[:MAX_LOOKUP_TEXT_LENGTH]
    if not link.default_language:
        _stash_pending_lookup(link, api, chat_id, text, "sentence")
        return
    try:
        consume_ai_quota(link.user)
    except Throttled as e:
        _reply(api, chat_id, str(e.detail))
        return
    _propose_sentence(link, api, chat_id, text)


def _propose_sentence(link: TelegramLink, api: str, chat_id, text: str) -> None:
    """The post-quota body of the /sentence flow (see _handle_sentence_input);
    split out so the voice path can reuse it with its transcription instead of
    a typed sentence."""
    text = text[:MAX_LOOKUP_TEXT_LENGTH]
    _send_typing(api, chat_id)
    result = enrich_card(text, link.default_language, "sentence", link.default_back_language)
    pending, _ = PendingTelegramCard.objects.update_or_create(
        user=link.user,
        defaults={
            "card_type": "sentence",
            "language": link.default_language,
            "front": text,
            "back": result.get("back", ""),
            "reading": result.get("reading", ""),
            "article": "none",
            "plural": "",
            "example": result.get("example", ""),
            "translation_options": [],
            "pronunciation_options": [],
            "awaiting_field": "",
        },
    )
    _send_proposal(api, chat_id, pending)


def _handle_voice_message(link: TelegramLink, api: str, chat_id, voice: dict) -> None:
    """A Telegram voice message is an *input method*, not a separate premium
    AI feature: the audio is transcribed with Gemini (one AI call, one quota
    unit — the same logical lookup a typed word costs) and the result is fed
    into the exact same word/sentence card pipeline as typed text, via
    _propose_word/_propose_sentence (so they share the quota semantics and the
    proposal UI). The OGG/Opus bytes go straight to Gemini via inline_data —
    no ffmpeg transcoding step."""
    duration = voice.get("duration") or 0
    if duration > _VOICE_MAX_DURATION_SECONDS:
        _reply(
            api, chat_id,
            f"🎤 Voice messages must be under {_VOICE_MAX_DURATION_SECONDS}s — send the word as text instead.",
        )
        return
    if (voice.get("file_size") or 0) > _VOICE_MAX_BYTES:
        _reply(api, chat_id, "🎤 That voice message is too large — send the word as text instead.")
        return
    if not link.default_language:
        _reply(api, chat_id, "Tell me your language first — send /lang de or /lang en.")
        return
    try:
        consume_ai_quota(link.user)
    except Throttled as e:
        _reply(api, chat_id, str(e.detail))
        return

    _send_typing(api, chat_id)
    file_id = voice.get("file_id")
    data = download_telegram_file(api, file_id, max_bytes=_VOICE_MAX_BYTES)
    if not data:
        _reply(api, chat_id, "🎤 I couldn't download that voice message — send the word as text instead.")
        return
    result = transcribe_audio(
        data, mime_type=voice.get("mime_type") or "audio/ogg", language=link.default_language
    )
    text = result.get("text", "")
    if not text:
        _reply(api, chat_id, "🎤 I couldn't make out what you said — send the word as text instead.")
        return
    text = text[:MAX_LOOKUP_TEXT_LENGTH]
    # Echo what was heard before the (multi-second) Gemini enrichment runs —
    # a misheard word should be obvious to the user *before* they read a
    # full proposal built around it, so they can /cancel instead of being
    # presented with a card for the wrong word.
    _reply(api, chat_id, f'🎤 I heard: "{text}" — one moment…')
    if result.get("kind") == "sentence":
        _propose_sentence(link, api, chat_id, text)
    else:
        _propose_word(link, api, chat_id, text)


def _handle_reply(pending: PendingTelegramCard, api: str, chat_id, text: str) -> None:
    if pending.awaiting_field == "back":
        pending.back = text
        pending.awaiting_field = "reading"
        pending.save(update_fields=["back", "awaiting_field"])
        _prompt_pronunciation(api, chat_id, pending)
        return
    if text.strip().lower() != "/skip":
        pending.reading = text
    _send_proposal(api, chat_id, pending)


def _handle_callback_query(update: dict, api: str) -> None:
    callback = update["callback_query"]
    data = callback.get("data") or ""
    chat_id = (callback.get("message") or {}).get("chat", {}).get("id")
    callback_id = callback["id"]

    # Each callback query is answered exactly once. Telegram only reliably
    # shows the first answer and rejects a second answerCallbackQuery for
    # the same query, so a stale button's alert (see _pending) must replace
    # — not follow — the plain spinner dismiss. The guarded helper means
    # whichever path fires first wins and the rest no-op.
    answered = False

    def _answer_once(text: str = "", show_alert: bool = False) -> None:
        nonlocal answered
        if answered:
            return
        answered = True
        _answer_callback(api, callback_id, text, show_alert)

    if not chat_id:
        _answer_once()
        return
    link = TelegramLink.objects.filter(chat_id=chat_id).select_related("user").first()
    if not link:
        _answer_once()
        return

    def _pending(prefix: str, stale_text: str = "This action is no longer available."):
        try:
            pending_id = int(data.removeprefix(prefix).split(":")[0])
        except ValueError:
            _answer_once(stale_text, show_alert=True)
            return None
        pending = PendingTelegramCard.objects.filter(id=pending_id, user=link.user).first()
        if pending is None:
            # A stale button (the row was already created, or replaced by a
            # newer lookup) must not feel like a dead tap — tell the user why
            # nothing happened instead of leaving a silent no-op.
            _answer_once(stale_text, show_alert=True)
            return None
        _answer_once()
        return pending

    if data == "menu:lookup":
        _answer_once()
        if _wizard_in_progress(link):
            _reply(api, chat_id, "You're in the middle of a card — finish it or send /cancel first.")
            return
        _reply(api, chat_id, "Send me a word to look up.")
        return

    if data == "menu:sentence":
        _answer_once()
        if _wizard_in_progress(link):
            _reply(api, chat_id, "You're in the middle of a card — finish it or send /cancel first.")
            return
        _reply(api, chat_id, "Send me a sentence.")
        return

    if data == "menu:lang":
        _answer_once()
        _reply(api, chat_id, _lang_usage_reply(link))
        return

    if data.startswith("choose_back:"):
        pending = _pending("choose_back:")
        if not pending:
            return
        try:
            idx = int(data.rsplit(":", 1)[1])
            pending.back = pending.translation_options[idx]
        except (IndexError, ValueError):
            return
        pending.awaiting_field = "reading"
        pending.save(update_fields=["back", "awaiting_field"])
        _prompt_pronunciation(api, chat_id, pending)
        return

    if data.startswith("pick_own_back:"):
        pending = _pending("pick_own_back:")
        if not pending:
            return
        pending.awaiting_field = "back"
        pending.save(update_fields=["awaiting_field"])
        _reply(api, chat_id, f'Send the translation for "{pending.front}":')
        return

    if data.startswith("choose_reading:"):
        pending = _pending("choose_reading:")
        if not pending:
            return
        try:
            idx = int(data.rsplit(":", 1)[1])
            pending.reading = pending.pronunciation_options[idx]
        except (IndexError, ValueError):
            return
        _send_proposal(api, chat_id, pending)
        return

    if data.startswith("pick_own_reading:"):
        pending = _pending("pick_own_reading:")
        if not pending:
            return
        _reply(api, chat_id, "Send the pronunciation (or /skip to leave it blank):")
        return

    if data.startswith("create:"):
        pending = _pending("create:", stale_text="This card was already added.")
        if not pending:
            return
        _finalize(api, chat_id, pending)
        return

    if data.startswith("edit:"):
        pending = _pending("edit:")
        if not pending:
            return
        pending.awaiting_field = "back"
        pending.save(update_fields=["awaiting_field"])
        _reply(api, chat_id, f'Send the translation for "{pending.front}":')
        return

    if data.startswith("regenerate:"):
        pending = _pending("regenerate:")
        # Only valid from a finished proposal — a stale button from a
        # superseded lookup must not clobber an in-progress wizard.
        if not pending or pending.awaiting_field:
            return
        _regenerate(link, api, chat_id, pending)
        return

    if data.startswith("cancel:"):
        _cancel_active_work(link)
        _cancel_and_show_menu(api, chat_id)
        return


def process_telegram_update(update: dict, api: str) -> None:
    """Handles one Telegram update — routes to /start (linking, or a
    welcome/help reply if there's no token to link), /lang, /help, /menu
    (the same main-menu keyboard shown after connecting), /sentence
    (straight to a proposal, no picker), a word-lookup wizard (translation
    options, then pronunciation options, then a Create/Edit proposal
    screen), a voice message (transcribed, then routed into the same word/
    sentence pipeline — it's an input method, never a wizard answer), or a
    wizard button tap. Split out from the poll loop so it's unit-testable
    without an infinite loop or a live getUpdates call.
    """
    if "callback_query" in update:
        _handle_callback_query(update, api)
        return

    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    voice = message.get("voice") or {}
    chat_id = (message.get("chat") or {}).get("id")
    if not (text or voice.get("file_id")) or not chat_id:
        return

    # Bare "start"/"menu"/"help" (no leading slash) are treated the same as
    # their slash commands — a common typo (or autocomplete dropping the
    # slash) would otherwise silently fall through to word lookup instead.
    if text and (text.lower().startswith("/start") or text.lower() == "start"):
        _handle_start(api, chat_id, text)
        return

    link = TelegramLink.objects.filter(chat_id=chat_id).select_related("user").first()
    if not link:
        _reply(api, chat_id, _CONNECT_FIRST_TEXT)
        return

    # Global escape — checked before the mid-wizard gate so a user who wants
    # out is never forced to finish a card they don't want, and a stray word
    # can't accidentally become a wizard answer.
    if text.lower() in ("/cancel", "cancel"):
        _cancel_active_work(link)
        _cancel_and_show_menu(api, chat_id)
        return

    pending = PendingTelegramCard.objects.filter(user=link.user).first()
    if voice.get("file_id"):
        # Voice is an input method, but never a mid-wizard answer — a spoken
        # translation/pronunciation can't be parsed, so reject it rather than
        # letting it fall through _handle_reply as empty text.
        if pending and pending.awaiting_field:
            _reply(api, chat_id, "Please send that as text while we finish your card.")
            return
        _handle_voice_message(link, api, chat_id, voice)
        return

    if pending and pending.awaiting_field:
        _handle_reply(pending, api, chat_id, text)
        return

    if text.lower().startswith("/lang"):
        _handle_lang(link, api, chat_id, text)
        return

    if text.lower().startswith("/help") or text.lower() == "help":
        _reply(api, chat_id, _ONBOARDING_EXAMPLE)
        return

    if text.lower().startswith("/menu") or text.lower() == "menu":
        _reply(api, chat_id, "What would you like to do?", reply_markup=_main_menu_keyboard())
        return

    if text.lower().startswith("/sentence"):
        sentence = text[len("/sentence"):].strip()
        if not sentence:
            _reply(api, chat_id, "Usage: /sentence <a sentence in your target language>")
            return
        _handle_sentence_input(link, api, chat_id, sentence)
        return

    _handle_word_lookup(link, api, chat_id, text)


def _process_update_safely(update: dict, api: str) -> None:
    """Runs one update through process_telegram_update, catching and logging
    any failure so a single bad update (an unexpected payload shape, a DB
    hiccup, a bug in a handler) can't crash the whole long-running poller —
    only that one update is dropped and the rest of the batch keeps going.
    Split out from the poll loop so it's independently unit-testable."""
    try:
        process_telegram_update(update, api)
    except Exception as e:  # noqa: BLE001 — see docstring
        logger.warning("update %s failed: %s", update.get("update_id"), _redact_token(str(e)))


# Liveness/backoff tuning for the long-poll loop (see Command.handle) — kept
# here as named constants rather than inline magic numbers.
_LIVENESS_TIMEOUT = 90   # seconds — generous upper bound for one getUpdates cycle (25s long-poll + margin)
_WATCHDOG_INTERVAL = 15  # seconds — how often the watchdog checks the heartbeat
_CONFLICT_BACKOFF = 15   # seconds — Telegram 409 means another instance's connection hasn't expired yet


def _build_session() -> requests.Session:
    """One connection, retried at the transport level for transient 5xx/
    connection errors, and never kept alive across requests (Connection:
    close) — a pooled keep-alive socket is exactly what can go stale after a
    host sleep/network change without ever raising an exception. Rebuilt
    from scratch on every failure (see handle()) so a bad socket is never
    reused for the next attempt either."""
    session = requests.Session()
    session.headers.update({"Connection": "close"})
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry, pool_connections=1, pool_maxsize=1))
    return session


class Command(BaseCommand):
    help = (
        "Long-polls the Telegram Bot API for messages: /start links a chat_id (or shows a "
        "welcome/help reply if there's no token to link), /lang sets a study language, /help "
        "repeats onboarding instructions, /menu shows the main menu keyboard, /sentence <text> "
        "proposes a sentence card directly, voice messages are transcribed (Gemini) and routed "
        "into the same word/sentence proposal pipeline, and any other text starts a "
        "translation/pronunciation wizard ending in a Create/Edit proposal screen (no public "
        "webhook needed)."
    )

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BOT_TOKEN:
            self.stdout.write("TELEGRAM_BOT_TOKEN unset — Telegram reminders disabled, idling.")
            while True:
                time.sleep(3600)

        api = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"
        state = TelegramPollerState.load()
        offset = state.offset
        session = _build_session()
        last_heartbeat = time.monotonic()

        def _watchdog():
            # Runs independently of the main loop. If the main thread is
            # blocked on a socket read that never times out (the one failure
            # mode a try/except can't catch — a connection wedged after a
            # host suspend/network change), this notices and hard-kills the
            # process; restart: unless-stopped brings it back with a clean
            # network stack. os._exit, not sys.exit: this fires from a
            # background thread and must kill the whole process even though
            # the main thread is unresponsive, not just raise in this thread.
            while True:
                time.sleep(_WATCHDOG_INTERVAL)
                if time.monotonic() - last_heartbeat > _LIVENESS_TIMEOUT:
                    self.stderr.write("Poller heartbeat stale — forcing a restart.")
                    self.stderr.flush()
                    os._exit(1)

        threading.Thread(target=_watchdog, daemon=True).start()

        self.stdout.write("Polling Telegram for messages...")
        while True:
            last_heartbeat = time.monotonic()
            try:
                resp = session.get(
                    f"{api}/getUpdates", params={"offset": offset, "timeout": 25}, timeout=(10, 35)
                )
                if resp.status_code == 409:
                    self.stderr.write(
                        "getUpdates 409 Conflict — waiting for the other instance's connection to expire."
                    )
                    time.sleep(_CONFLICT_BACKOFF)
                    continue
                resp.raise_for_status()
                for update in resp.json().get("result", []):
                    offset = update["update_id"] + 1
                    _process_update_safely(update, api)
                    # Persisted per-update (not once per batch) so a bad
                    # update is never retried after a restart — it's been
                    # logged and dropped already, and re-delivering it would
                    # just crash-loop the exact same failure forever.
                    state.offset = offset
                    state.save(update_fields=["offset"])
            except requests.RequestException as e:
                self.stderr.write(f"getUpdates failed: {_redact_token(str(e))}")
                session = _build_session()
                time.sleep(5)
