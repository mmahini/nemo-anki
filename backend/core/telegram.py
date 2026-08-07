import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def _file_api(api: str) -> str:
    """Turn the bot API base (``https://api.telegram.org/bot<token>``) into the
    file-download base (``https://api.telegram.org/file/bot<token>``)."""
    return api.replace("/bot", "/file/bot", 1)


def download_telegram_file(
    api: str, file_id: str, max_bytes: int = 20 * 1024 * 1024
) -> bytes | None:
    """Download a file Telegram hosted for the bot (voice messages, photos,
    documents — anything with a file_id) and return its raw bytes, or None when
    the file can't be resolved/downloaded or exceeds max_bytes.

    Two-step Telegram dance: ``getFile`` returns the server-side file_path,
    which is then fetched from the separate ``/file/bot...`` host. Shared by the
    bot's voice lookup (see poll_telegram_updates) and any future media flow
    (e.g. OCR on photos). Best-effort — never raises."""
    if not file_id:
        return None
    import requests

    try:
        res = requests.post(f"{api}/getFile", json={"file_id": file_id}, timeout=10)
        data = res.json()
    except Exception:  # noqa: BLE001 — a Telegram hiccup degrades to None
        logger.warning("Telegram getFile failed for file_id %r", file_id)
        return None
    if not data.get("ok"):
        logger.warning("Telegram getFile rejected file_id %r: %s", file_id, data.get("description"))
        return None
    file_path = (data.get("result") or {}).get("file_path")
    if not file_path:
        logger.warning("Telegram getFile returned no file_path for %r", file_id)
        return None
    try:
        fr = requests.get(f"{_file_api(api)}/{file_path}", timeout=30, stream=True)
        fr.raise_for_status()
    except Exception:  # noqa: BLE001 — best-effort, degrade to None
        logger.warning("Telegram file download failed for file_id %r", file_id)
        return None
    buf = b""
    for chunk in fr.iter_content(65536):
        buf += chunk
        if len(buf) > max_bytes:
            logger.warning("Telegram file %r exceeded %s bytes", file_id, max_bytes)
            return None
    return buf


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
