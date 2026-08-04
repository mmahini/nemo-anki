"""In-process study-reminder ticker — the single-server stand-in for
celery-beat.

The production deployment runs everything on one Render web service (no
Redis, no celery worker/beat). This module gives that deployment its
every-minute check_study_reminders tick: a daemon thread started from
NotificationsConfig.ready() when STUDY_REMINDER_TICKER=1, with
CELERY_TASK_ALWAYS_EAGER making the dispatched send tasks run inline.

Gunicorn runs several workers and each one starts this thread, so the tick
itself is guarded by a Postgres advisory lock: only the process that holds
the lock scans and sends (a session lock, so it dies with the connection if
the holder is killed); the others retry periodically and take over if the
holder goes away. Reminders only fire while the service is awake — the
keep-alive ping (.github/workflows/keepalive.yml) exists to make that the
normal state on Render's free tier.
"""

import logging
import threading
import time

from django.db import connections

logger = logging.getLogger(__name__)

# Arbitrary but fixed application-wide key ("nemo" + 1). Any Nemo Anki process
# on the same database competes for the same lock.
_ADVISORY_LOCK_KEY = 0x6E656D6F01
# How long a non-holder waits before trying to take the lock over.
_RETRY_SECONDS = 300

_started = threading.Lock()
_thread: threading.Thread | None = None


def _try_acquire_lock() -> bool:
    """Session-scoped pg_try_advisory_lock on a connection this thread then
    keeps open — the lock lives exactly as long as the holder process."""
    with connections["default"].cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [_ADVISORY_LOCK_KEY])
        return bool(cursor.fetchone()[0])


def _run() -> None:
    from .tasks import check_study_reminders

    holder = False
    while True:
        if not holder:
            try:
                holder = _try_acquire_lock()
            except Exception as e:  # noqa: BLE001 — DB briefly down; retry
                logger.warning("reminder ticker: lock attempt failed: %s", e)
            if not holder:
                time.sleep(_RETRY_SECONDS)
                continue
            logger.info("reminder ticker: this process holds the tick lock")

        try:
            check_study_reminders()
        except Exception as e:  # noqa: BLE001 — one bad tick must not kill the loop
            logger.warning("reminder ticker: tick failed: %s", e)

        # Sleep to just past the next minute boundary so each wall-clock
        # minute gets exactly one scan (the task matches HH:MM equality).
        time.sleep(60 - (time.time() % 60) + 0.5)


def start_ticker() -> None:
    """Idempotently start the ticker thread for this process."""
    global _thread
    with _started:
        if _thread is not None:
            return
        _thread = threading.Thread(target=_run, name="study-reminder-ticker", daemon=True)
        _thread.start()
