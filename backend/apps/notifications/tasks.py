import json
from datetime import date, timedelta
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


# How far past the reminder time a send still goes out (late) instead of
# being dropped. The free-tier instance can be asleep at the exact minute —
# it's only guaranteed awake around the hourly keep-alive ping (plus GitHub
# cron jitter) — so the tick that eventually runs catches the reminder up;
# `study_reminder_last_sent` keeps it to one per day.
REMINDER_CATCHUP = timedelta(minutes=75)


@shared_task
def check_study_reminders(now=None):
    """Scheduled every minute (celery-beat, or the in-process ticker in the
    single-server deployment). Finds users whose local wall-clock time is at —
    or within REMINDER_CATCHUP after — their reminder time and haven't been
    sent one yet today (in their own timezone), and dispatches one send task
    per matching user — to whichever channel (push or telegram) they've picked.

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
        target = local_now.replace(
            hour=user.study_reminder_time.hour,
            minute=user.study_reminder_time.minute,
            second=0,
            microsecond=0,
        )
        if not (target <= local_now < target + REMINDER_CATCHUP):
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


# Monday. Fixed, not user-configurable — this is a passive weekly summary,
# not a feature with its own settings UI.
DIGEST_WEEKDAY = 0


@shared_task
def check_weekly_digests(now=None):
    """Same shape as check_study_reminders (same tick, same candidates, same
    per-user timezone + catch-up window against study_reminder_time/channel)
    but gated to once a week on DIGEST_WEEKDAY, via study_digest_last_sent."""
    now = now or timezone.now()
    candidates = User.objects.filter(study_reminder_time__isnull=False).select_related("telegram_link")
    for user in candidates.iterator():
        try:
            local_now = now.astimezone(ZoneInfo(user.study_reminder_timezone))
        except ZoneInfoNotFoundError:
            continue
        if local_now.weekday() != DIGEST_WEEKDAY:
            continue
        target = local_now.replace(
            hour=user.study_reminder_time.hour,
            minute=user.study_reminder_time.minute,
            second=0,
            microsecond=0,
        )
        if not (target <= local_now < target + REMINDER_CATCHUP):
            continue
        if user.study_digest_last_sent and (local_now.date() - user.study_digest_last_sent).days < 7:
            continue
        if user.study_reminder_channel == "telegram":
            if not (hasattr(user, "telegram_link") and user.telegram_link.chat_id):
                continue
            send_digest_telegram.delay(user.id, local_now.date().isoformat())
        else:
            if not user.push_subscriptions.exists():
                continue
            send_digest_push.delay(user.id, local_now.date().isoformat())


def _weekly_stats(user, since) -> dict:
    """reviews/retention/leeches for the digest message. `retention` mirrors
    apps.cards.views.StatsOverviewView._range_totals: of the answers on
    cards that were already in the `review` state, the share not rated
    Again (Hard counts as a pass) — None if there were no such answers."""
    from apps.cards.models import Card, CardState, ReviewLog

    logs = ReviewLog.objects.filter(user=user, reviewed_at__date__gte=since)
    mature = logs.filter(state_before=CardState.REVIEW).count()
    mature_pass = logs.filter(state_before=CardState.REVIEW, rating__gt=1).count()
    return {
        "reviews": logs.count(),
        "retention": round(mature_pass / mature, 4) if mature else None,
        "leeches": Card.objects.filter(deck__user=user, is_leech=True, reverse_of__isnull=True).count(),
    }


def _digest_text(stats: dict) -> str:
    if not stats["reviews"]:
        return "📊 No reviews this week — your decks are waiting whenever you're ready."
    retention = f"{round(stats['retention'] * 100)}% retention" if stats["retention"] is not None else "no retention data yet"
    leech_part = f", {stats['leeches']} card(s) stuck (leeches)" if stats["leeches"] else ""
    return f"📊 This week: {stats['reviews']} reviews, {retention}{leech_part}."


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


@shared_task
def send_digest_push(user_id, local_date_iso):
    user = User.objects.filter(id=user_id).first()
    if not user:
        return
    since = date.fromisoformat(local_date_iso) - timedelta(days=7)
    text = _digest_text(_weekly_stats(user, since))
    payload = json.dumps({"title": "Your week in review", "body": text})
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
    User.objects.filter(id=user_id).update(study_digest_last_sent=local_date_iso)


@shared_task
def send_digest_telegram(user_id, local_date_iso):
    user = User.objects.filter(id=user_id).select_related("telegram_link").first()
    if not user or not (hasattr(user, "telegram_link") and user.telegram_link.chat_id):
        return
    since = date.fromisoformat(local_date_iso) - timedelta(days=7)
    text = _digest_text(_weekly_stats(user, since))
    requests.post(
        f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
        json={
            "chat_id": user.telegram_link.chat_id,
            "text": text,
            "reply_markup": _main_menu_keyboard(),
        },
        timeout=10,
    )
    User.objects.filter(id=user_id).update(study_digest_last_sent=local_date_iso)
