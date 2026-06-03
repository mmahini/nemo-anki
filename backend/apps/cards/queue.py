"""Queue gathering + daily-limit accounting for study sessions.

Mirrors Anki's default gather/sort: learning due now -> review due today ->
new (capped by the deck's daily limits). See docs/ANKI_RESEARCH.md §5.5.
"""
from __future__ import annotations

from datetime import datetime

from .models import Card, CardState, ReviewLog


def _start_of_day(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _done_today(deck_ids: list[int], now: datetime):
    sod = _start_of_day(now)
    logs = ReviewLog.objects.filter(card__deck_id__in=deck_ids, reviewed_at__gte=sod)
    new_done = logs.filter(state_before=CardState.NEW).count()
    review_done = logs.filter(
        state_before__in=[CardState.REVIEW, CardState.RELEARNING]
    ).count()
    return new_done, review_done


def deck_counts(deck, now: datetime) -> dict:
    """Counts shown on the deck list: new / learning / due (review)."""
    deck_ids = deck.descendant_ids()
    cfg = deck.config
    cards = Card.objects.filter(deck_id__in=deck_ids)

    new_done, review_done = _done_today(deck_ids, now)

    new_total = cards.filter(state=CardState.NEW).count()
    new_allow = max(0, cfg.new_per_day - new_done)

    learning = cards.filter(
        state__in=[CardState.LEARNING, CardState.RELEARNING], due__lte=now
    ).count()

    review_due = cards.filter(state=CardState.REVIEW, due__lte=now).count()
    review_allow = max(0, cfg.reviews_per_day - review_done)

    return {
        "new": min(new_total, new_allow),
        "learning": learning,
        "due": min(review_due, review_allow),
        "total": cards.exclude(state=CardState.SUSPENDED).count(),
    }


def study_queue(deck, now: datetime, limit: int = 50) -> list[Card]:
    """Ordered list of cards to study right now, respecting daily limits."""
    deck_ids = deck.descendant_ids()
    cfg = deck.config
    cards = Card.objects.filter(deck_id__in=deck_ids)

    new_done, review_done = _done_today(deck_ids, now)
    new_allow = max(0, cfg.new_per_day - new_done)
    review_allow = max(0, cfg.reviews_per_day - review_done)

    learning = list(
        cards.filter(
            state__in=[CardState.LEARNING, CardState.RELEARNING], due__lte=now
        ).order_by("due")
    )
    review = list(
        cards.filter(state=CardState.REVIEW, due__lte=now).order_by("due")[:review_allow]
    )
    new = list(cards.filter(state=CardState.NEW).order_by("position", "id")[:new_allow])

    ordered = learning + review + new
    return ordered[:limit] if limit else ordered
