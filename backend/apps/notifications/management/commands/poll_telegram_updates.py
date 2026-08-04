import logging
import os
import threading
import time
from datetime import timedelta

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from requests.adapters import HTTPAdapter
from rest_framework.exceptions import Throttled
from urllib3.util.retry import Retry

from apps.cards.image_search import attach_thumbnail_from_url, find_thumbnail_url_for
from apps.imports.gemini import enrich_card, enrich_card_options
from apps.imports.services import create_sentence_card, create_vocab_card
from apps.notifications.models import PendingTelegramCard, TelegramLink, TelegramPollerState
from apps.subscriptions.quota import consume_ai_quota

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = {"de": "German", "en": "English"}

# How long a word/sentence sent before /lang is remembered for automatic
# resume — generous on purpose (a learner may set up the bot, get pulled
# away, and only finish a while later), not a "session" concept.
PENDING_LOOKUP_TTL = timedelta(hours=24)

# Matches PendingTelegramCard.front's and TelegramLink.pending_lookup_text's
# max_length — capped before any AI call or DB write so an oversized word/
# sentence can never raise a DataError and crash the poller (see PR#9).
MAX_LOOKUP_TEXT_LENGTH = 200

_CONNECT_FIRST_TEXT = 'Connect your account first — open Nemo Anki and tap "Connect Telegram".'

_ONBOARDING_EXAMPLE = (
    "Send /lang de or /lang en to set your target language. Then just send a word to add it as "
    "a card, or /sentence <text> for a full sentence. For example:\n\n"
    "/lang de\n"
    "Haus\n"
    "/sentence Ich gehe heute ins Kino."
)


def _redact_token(text: str) -> str:
    """Strips the bot token out of a string before it's logged. Connection
    errors from requests/urllib3 embed the full request URL — including
    `/bot<TOKEN>/...` — in their message, so logging an exception's str()
    as-is would leak the token into stdout/log storage."""
    token = settings.TELEGRAM_BOT_TOKEN
    return text.replace(token, "<redacted>") if token else text


def _telegram_post(api: str, method: str, payload: dict) -> bool:
    """POSTs to the Telegram Bot API and reports whether Telegram actually
    accepted the call. A 200 response doesn't mean success — Telegram
    returns HTTP 200 with {"ok": false} for plenty of rejections (bot
    blocked by the user, bad chat_id, message too long, etc.), so callers
    that only checked "didn't raise" were treating those as silent
    successes."""
    try:
        resp = requests.post(f"{api}/{method}", json=payload, timeout=10)
        data = resp.json()
    except requests.RequestException as e:
        logger.warning("Telegram %s request failed: %s", method, _redact_token(str(e)))
        return False
    except ValueError:
        logger.warning("Telegram %s returned a non-JSON response (status %s)", method, resp.status_code)
        return False
    if not data.get("ok"):
        logger.warning("Telegram %s rejected: %s", method, data.get("description"))
        return False
    return True


def _reply(api: str, chat_id, text: str, reply_markup: dict | None = None) -> bool:
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _telegram_post(api, "sendMessage", payload)


def _send_photo(api: str, chat_id, image_field, caption: str) -> bool:
    image_field.open("rb")
    try:
        data = image_field.read()
    finally:
        image_field.close()
    try:
        resp = requests.post(
            f"{api}/sendPhoto",
            data={"chat_id": chat_id, "caption": caption},
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


def _handle_lang(link: TelegramLink, api: str, chat_id, text: str) -> None:
    code = text.lower().removeprefix("/lang").strip()
    if code not in SUPPORTED_LANGUAGES:
        _reply(api, chat_id, "Usage: /lang de or /lang en")
        return
    link.default_language = code
    link.save(update_fields=["default_language"])
    _reply(api, chat_id, f"Got it — I'll look up words in {SUPPORTED_LANGUAGES[code]} from now on.")

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


def _options_keyboard(pending_id: int, options: list[str], choose_prefix: str, own_prefix: str) -> dict:
    rows = [[{"text": opt, "callback_data": f"{choose_prefix}:{pending_id}:{i}"}] for i, opt in enumerate(options)]
    rows.append([{"text": "✏️ Type my own", "callback_data": f"{own_prefix}:{pending_id}"}])
    return {"inline_keyboard": rows}


def _prompt_translation(api: str, chat_id, pending: PendingTelegramCard) -> None:
    if pending.translation_options:
        _reply(
            api, chat_id, f"{pending.front}\n\nWhich translation is correct?",
            reply_markup=_options_keyboard(pending.id, pending.translation_options, "choose_back", "pick_own_back"),
        )
    else:
        _reply(api, chat_id, f'Send the translation for "{pending.front}":')


def _prompt_pronunciation(api: str, chat_id, pending: PendingTelegramCard) -> None:
    if pending.pronunciation_options:
        _reply(
            api, chat_id, "Which pronunciation is correct?",
            reply_markup=_options_keyboard(
                pending.id, pending.pronunciation_options, "choose_reading", "pick_own_reading"
            ),
        )
    else:
        _reply(api, chat_id, "Send the pronunciation (or /skip to leave it blank):")


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
    """Show the word/meaning/reading/example gathered so far — plus an
    auto-suggested picture, if Gemini judges the meaning depictable (see
    apps.cards.image_search.find_thumbnail_url_for) — with Create/Edit
    buttons. Only a source URL is looked up here (no download): Telegram
    fetches it directly for the preview, and it's saved on `pending` so the
    real, one-time download happens only if/when Create is tapped."""
    pending.image_url = find_thumbnail_url_for(pending.front, pending.back, pending.language, pending.card_type)
    pending.awaiting_field = ""
    pending.save()
    caption = _proposal_caption(pending)
    keyboard = _proposal_keyboard(pending.id)
    if pending.image_url:
        _telegram_post(
            api, "sendPhoto",
            {"chat_id": chat_id, "photo": pending.image_url, "caption": caption, "reply_markup": keyboard},
        )
    else:
        _reply(api, chat_id, caption, reply_markup=keyboard)


def _finalize(api: str, chat_id, pending: PendingTelegramCard) -> None:
    """Actually create the card — triggered by the Create button, never
    directly by the wizard (see _send_proposal)."""
    create = create_sentence_card if pending.card_type == "sentence" else create_vocab_card
    card = create(
        pending.user, pending.front, pending.language,
        {
            "back": pending.back, "reading": pending.reading,
            "article": pending.article, "plural": pending.plural, "example": pending.example,
        },
    )
    image = attach_thumbnail_from_url(card, pending.image_url) if pending.image_url else None
    pending.delete()
    caption = f"✅ Added to {card.deck.full_name}"
    if image:
        # The card is already saved either way — if only the richer photo
        # message fails (bad/expired image URL, Telegram rejects the file),
        # still confirm via plain text rather than leaving the user with no
        # acknowledgement that Create actually worked.
        if not _send_photo(api, chat_id, image.image, caption):
            _reply(api, chat_id, caption)
    else:
        _reply(api, chat_id, caption)


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

    result = enrich_card_options(text, link.default_language, "vocab", link.default_back_language)
    pending, _ = PendingTelegramCard.objects.update_or_create(
        user=link.user,
        defaults={
            "card_type": "vocab",
            "language": link.default_language,
            "front": text,
            "back": "",
            "reading": "",
            "article": result.get("article", "none"),
            "plural": result.get("plural", ""),
            "example": result.get("example", ""),
            "translation_options": result.get("translations", []),
            "pronunciation_options": result.get("pronunciations", []),
            "awaiting_field": "back",
        },
    )
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
    _telegram_post(api, "answerCallbackQuery", {"callback_query_id": callback_id})
    if not chat_id:
        return
    link = TelegramLink.objects.filter(chat_id=chat_id).select_related("user").first()
    if not link:
        return

    def _pending(prefix: str):
        try:
            pending_id = int(data.removeprefix(prefix).split(":")[0])
        except ValueError:
            return None
        return PendingTelegramCard.objects.filter(id=pending_id, user=link.user).first()

    if data == "menu:lookup":
        _reply(api, chat_id, "Send me a word to look up.")
        return

    if data == "menu:sentence":
        _reply(api, chat_id, "Send me a sentence.")
        return

    if data == "menu:lang":
        _reply(api, chat_id, "Usage: /lang de or /lang en")
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
        pending = _pending("create:")
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


def process_telegram_update(update: dict, api: str) -> None:
    """Handles one Telegram update — routes to /start (linking, or a
    welcome/help reply if there's no token to link), /lang, /help, /menu
    (the same main-menu keyboard shown after connecting), /sentence
    (straight to a proposal, no picker), a word-lookup wizard (translation
    options, then pronunciation options, then a Create/Edit proposal
    screen), or a wizard button tap. Split out from the poll loop so it's
    unit-testable without an infinite loop or a live getUpdates call.
    """
    if "callback_query" in update:
        _handle_callback_query(update, api)
        return

    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    chat_id = (message.get("chat") or {}).get("id")
    if not (text and chat_id):
        return

    # Bare "start"/"menu"/"help" (no leading slash) are treated the same as
    # their slash commands — a common typo (or autocomplete dropping the
    # slash) would otherwise silently fall through to word lookup instead.
    if text.lower().startswith("/start") or text.lower() == "start":
        _handle_start(api, chat_id, text)
        return

    link = TelegramLink.objects.filter(chat_id=chat_id).select_related("user").first()
    if not link:
        _reply(api, chat_id, _CONNECT_FIRST_TEXT)
        return

    pending = PendingTelegramCard.objects.filter(user=link.user).first()
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
        "proposes a sentence card directly, and any other text starts a translation/pronunciation "
        "wizard ending in a Create/Edit proposal screen (no public webhook needed)."
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
