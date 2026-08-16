"""Per-user AI usage metering — a fixed 1-day window sized by subscription tier.

Call ``consume_ai_quota(user)`` at the top of any Gemini-backed endpoint: it
increments today's counter and raises HTTP 429 (Throttled) when the daily limit
is reached. ``ai_usage(user)`` reads the current count/limit for display.
"""
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import Throttled

from .models import AiUsage, Subscription


def daily_limit(user) -> int | None:
    """Today's AI limit for this user, or None for unlimited (staff)."""
    if not user or not user.is_authenticated:
        return 0
    if user.is_staff:
        return None
    return Subscription.for_user(user).daily_ai_limit


def ai_usage(user) -> tuple[int, int | None]:
    """(used_today, limit) — limit is None when unlimited."""
    limit = daily_limit(user)
    used = (
        AiUsage.objects.filter(user=user, day=timezone.now().date())
        .values_list("count", flat=True)
        .first()
        or 0
    )
    return used, limit


class AiQuotaMixin:
    """Mix into any APIView backed by Gemini: meters one AI action per request
    (after auth/permissions) and returns 429 when the daily limit is reached."""

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        consume_ai_quota(request.user)


def consume_ai_quota(user, units: int = 1) -> None:
    """Count `units` against today's window; raise 429 when the action would
    not fit inside a finite limit. Usage is always counted (so it can be
    shown), including for staff who have no limit (None) and are never
    blocked.

    Weighted actions (reels charge 5 per watch) refuse when the REMAINDER is
    too small — a single-unit action at 79/80 still fits, exactly as before.
    """
    limit = daily_limit(user)
    today = timezone.now().date()
    with transaction.atomic():
        usage, _ = AiUsage.objects.select_for_update().get_or_create(user=user, day=today)
        if limit is not None and usage.count + units > limit:
            raise Throttled(
                detail=(
                    f"You've reached today's AI limit ({limit}). It resets tomorrow — "
                    "upgrade your plan for a higher limit."
                )
            )
        usage.count += units
        usage.save(update_fields=["count"])
