"""Server-side Wiser CDP events.

The browser pixel (frontend/src/lib/cdp-pixel.ts) owns everything session-
shaped: pageviews, logins, engagement time, PWA display mode. This module
covers the moments the client cannot see or cannot be trusted to report:

  * ``signup`` — account creation is decided server-side in verify-otp; the
    client used to infer it from ``is_new_user`` and could lose it to an
    ad-blocker or a closed tab.
  * ``subscription_requested`` — the "I've paid" claim, recorded where the
    money conversation actually lands.
  * ``subscription_activated`` — an admin approving a plan happens in Django
    admin; no browser is present at all.

Events fold into the same CDP profile as the pixel's via ``external_id`` /
``email``. Fire-and-forget on a daemon thread with a short timeout: analytics
must never block or break a request. No-ops unless both env vars are set —
dev, CI and the test suite emit nothing.

Config (Render env): CDP_INGEST_URL, CDP_WRITE_KEY.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone as dt_timezone

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_TIMEOUT_S = 4


def _post(body: dict) -> None:
    try:
        requests.post(
            settings.CDP_INGEST_URL,
            json=body,
            headers={"X-CDP-Write-Key": settings.CDP_WRITE_KEY},
            timeout=_TIMEOUT_S,
        )
    except Exception as exc:  # noqa: BLE001 — analytics never raises into the app
        logger.debug("cdp: dropped %s event: %s", body.get("event"), exc)


def track(user, event: str, properties: dict | None = None) -> None:
    """Emit one behavioural event for ``user``. Silently does nothing when the
    CDP env vars are absent or the user is anonymous."""
    if not settings.CDP_INGEST_URL or not settings.CDP_WRITE_KEY:
        return
    if user is None or not getattr(user, "pk", None):
        return
    body = {
        "type": "track",
        "event": event,
        "identifiers": {"external_id": str(user.pk), "email": user.email},
        "properties": properties or {},
        "context": {
            "source": "nemo-anki",
            "channel": "server",
            "ts": datetime.now(dt_timezone.utc).isoformat(),
        },
    }
    threading.Thread(target=_post, args=(body,), daemon=True).start()
