import json
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from pywebpush import WebPushException, webpush

from apps.accounts.models import User
from apps.notifications.management.commands.poll_telegram_updates import (
    SUPPORTED_LANGUAGES,
    _edit_message_with_photo,
    _main_menu_keyboard,
    _proposal_caption,
    _proposal_keyboard,
)
from apps.notifications.models import PendingTelegramCard


@shared_task
def check_study_reminders(now=None):
    """Beat-scheduled every minute. Finds users whose local wall-clock time
    matches their reminder time and haven't been sent one yet today (in their
    own timezone), and dispatches one send task per matching user — to
    whichever channel (push or telegram) they've picked.

    `now` is an explicit, injectable parameter (defaulting to `timezone.now()`)
    so tests can call this directly with a fixed instant instead of mocking
    the clock or running Celery in eager mode.
    """
    now = now or timezone.now()
    candidates = User.objects.filter(study_reminder_time__isnull=False).select_related("telegram_link")
    for user in candidates.iterator():
        try:
            local_now = now.astimezone(ZoneInfo(user.study_reminder_timezone))
        except ZoneInfoNotFoundError:
            continue
        if (local_now.hour, local_now.minute) != (
            user.study_reminder_time.hour,
            user.study_reminder_time.minute,
        ):
            continue
        if user.study_reminder_last_sent == local_now.date():
            continue
        if user.study_reminder_channel == "telegram":
            if not (hasattr(user, "telegram_link") and user.telegram_link.chat_id):
                continue
            send_reminder_telegram.delay(user.id, local_now.date().isoformat())
        else:
            if not user.push_subscriptions.exists():
                continue
            send_reminder_push.delay(user.id, local_now.date().isoformat())


@shared_task
def send_reminder_push(user_id, local_date_iso):
    user = User.objects.filter(id=user_id).first()
    if not user:
        return
    payload = json.dumps({"title": "Time to study", "body": "Your daily Nemo Anki reminder."})
    for sub in user.push_subscriptions.all():
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": f"mailto:{settings.VAPID_SUBJECT_EMAIL}"},
            )
        except WebPushException as e:
            if e.response is not None and e.response.status_code in (404, 410):
                sub.delete()
    User.objects.filter(id=user_id).update(study_reminder_last_sent=local_date_iso)


@shared_task
def find_and_attach_proposal_image(pending_id, chat_id, message_id, front, back, language, card_type, reading, example):
    """Runs the Gemini depictability check + Openverse search in the
    background (see poll_telegram_updates._send_proposal, which dispatches
    this instead of doing it inline) and edits the already-sent proposal
    message with a photo if one is found. front/back/language/card_type/
    reading/example are passed as a fixed snapshot, not re-read from the DB,
    so a Regenerate that happens while this is in flight can't make it
    search for the wrong thing. The staleness check below compares every
    field _proposal_caption renders (not just front/back) — a Regenerate
    can keep the same translation while only changing the reading or
    example, which front/back alone wouldn't catch. Best-effort throughout:
    any failure (nothing depictable, no result, the row already gone) just
    means no photo — never raises, never blocks card creation, which
    already happens independently of this."""
    from apps.cards.image_search import find_thumbnail_url_for

    image_url = find_thumbnail_url_for(front, back, language, card_type)
    if not image_url:
        return
    pending = PendingTelegramCard.objects.filter(id=pending_id).first()
    if (
        not pending
        or pending.front != front
        or pending.back != back
        or pending.card_type != card_type
        or pending.reading != reading
        or pending.example != example
    ):
        # Either Create already finished this row, or a newer lookup/
        # Regenerate has replaced its content — either way this snapshot no
        # longer matches, and editing the message with an image found for
        # stale content (rebuilding the caption from the *current* row would
        # show content that was never actually in this message) would be
        # worse than just leaving it as plain text.
        return
    pending.image_url = image_url
    pending.save(update_fields=["image_url"])
    api = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"
    _edit_message_with_photo(
        api, chat_id, message_id, image_url, _proposal_caption(pending), _proposal_keyboard(pending.id),
    )


@shared_task
def send_reminder_telegram(user_id, local_date_iso):
    user = User.objects.filter(id=user_id).select_related("telegram_link").first()
    if not user or not (hasattr(user, "telegram_link") and user.telegram_link.chat_id):
        return
    language = user.telegram_link.default_language
    if language in SUPPORTED_LANGUAGES:
        text = f"⏰ Time to study — ready to review some {SUPPORTED_LANGUAGES[language]}?"
    else:
        text = (
            "⏰ Time to study — your daily Nemo Anki reminder. "
            "Set your language with /lang de or /lang en to get more from these reminders."
        )
    requests.post(
        f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
        json={
            "chat_id": user.telegram_link.chat_id,
            "text": text,
            "reply_markup": _main_menu_keyboard(),
        },
        timeout=10,
    )
    User.objects.filter(id=user_id).update(study_reminder_last_sent=local_date_iso)
