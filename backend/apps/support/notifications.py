import json
import logging

from django.conf import settings

from .models import PushSubscription

logger = logging.getLogger(__name__)


def notify_staff_of_message(thread, message) -> None:
    """Push a browser/phone notification to every subscribed staff member
    about a new user support message. Best-effort — a push failure (or VAPID
    being unconfigured) must never break the message-send request."""
    if not settings.VAPID_PRIVATE_KEY:
        return

    from pywebpush import WebPushException, webpush

    payload = json.dumps(
        {
            "title": "New support message",
            "body": f"{thread.user.email}: {message.body[:120]}",
            "url": f"/admin/support/supportthread/{thread.id}/change/",
        }
    )

    for sub in PushSubscription.objects.filter(user__is_staff=True):
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": f"mailto:{settings.VAPID_CLAIM_EMAIL}"},
            )
        except WebPushException as e:
            status_code = getattr(e.response, "status_code", None)
            if status_code in (404, 410):
                sub.delete()  # endpoint expired/unsubscribed on the browser side
            else:
                logger.warning("Push send failed for %s: %s", sub.endpoint, e)
        except Exception:  # noqa: BLE001 — never let a push failure break the request
            logger.exception("Unexpected error sending push to %s", sub.endpoint)


def notify_telegram_of_message(thread, message) -> None:
    """Post a new user support message into the team's Telegram group.
    Best-effort — unconfigured or failing Telegram must never break the
    message-send request."""
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        return

    import requests

    text = (
        f"\U0001f4ac New support message\n"
        f"From: {thread.user.email}\n\n"
        f"{message.body}"
    )
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        res = requests.post(
            url, json={"chat_id": settings.TELEGRAM_CHAT_ID, "text": text}, timeout=5
        )
        if not res.ok:
            logger.warning("Telegram send failed (%s): %s", res.status_code, res.text)
    except Exception:  # noqa: BLE001 — never let a Telegram failure break the request
        logger.exception("Unexpected error sending Telegram notification")
