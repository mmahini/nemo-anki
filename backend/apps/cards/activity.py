"""Shared streak arithmetic — used by ReviewActivityView (the Stats page
heatmap) and apps.buddy's progress comparison, so the two never disagree."""
from __future__ import annotations

import datetime

from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import ReviewLog


def current_streak(active: set[datetime.date], today: datetime.date) -> int:
    """Consecutive active days ending today (or yesterday, if today has no
    activity yet — a streak isn't broken until the day is actually over)."""

    def run_back(anchor: datetime.date) -> int:
        s, cur = 0, anchor
        while cur in active:
            s += 1
            cur -= datetime.timedelta(days=1)
        return s

    return run_back(today) if today in active else run_back(today - datetime.timedelta(days=1))


def streak_summary(user, today: datetime.date | None = None, days: int = 119) -> dict:
    """Today's review count + current streak for `user`, bounded to the same
    `days`-back window as ReviewActivityView (apps/cards/views.py)."""
    today = today or timezone.localdate()
    start = today - datetime.timedelta(days=days)
    rows = (
        ReviewLog.objects.filter(user=user, reviewed_at__date__gte=start)
        .annotate(d=TruncDate("reviewed_at"))
        .values("d")
        .distinct()
    )
    active = {r["d"] for r in rows}
    today_count = ReviewLog.objects.filter(user=user, reviewed_at__date=today).count()
    return {"today": today_count, "streak": current_streak(active, today)}
