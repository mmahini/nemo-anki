import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def send_telegram_message(text: str) -> None:
    """Post a message to the team's Telegram group (support alerts, new-user
    signups, etc). Best-effort — never raises, so a Telegram outage or an
    unset TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID can't break the caller."""
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        return

    import requests

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        res = requests.post(
            url, json={"chat_id": settings.TELEGRAM_CHAT_ID, "text": text}, timeout=5
        )
        if not res.ok:
            logger.warning("Telegram send failed (%s): %s", res.status_code, res.text)
    except Exception:  # noqa: BLE001 — never let a Telegram failure break the caller
        logger.exception("Unexpected error sending Telegram notification")
