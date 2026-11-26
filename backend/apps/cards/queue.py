"""Queue gathering + daily-limit accounting for study sessions.

Mirrors Anki's default gather/sort: learning due now -> review due today ->
new (capped by the deck's daily limits). See docs/ANKI_RESEARCH.md §5.5.
"""
from __future__ import annotations

from datetime import datetime

from django.db.models import Count, Q

from .models import Card, CardState, CardDirection, ReviewLog


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
    # Everything CardSerializer touches, loaded up front: without this a
    # 50-card batch fired a handful of queries *per card* (deck, reverses,
    # reverse_of, images) and the study screen stalled on every refill.
    cards = (
        Card.objects.filter(deck_id__in=deck_ids)
        .select_related("deck", "reverse_of")
        .prefetch_related("images", "reverses", "reverse_of__images")
    )

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


def bulk_deck_counts(decks, now: datetime) -> dict[int, dict]:
    """`deck_counts` + forward-card count for many decks in a fixed number of
    queries, keyed by deck id. Same numbers as calling deck_counts() per deck
    (the tests hold the two together) — that path costs ~10 queries a deck,
    which on a seeded account (dozens of decks) made every deck-list load
    crawl.

    `decks` must hold every descendant of every deck in it (e.g. all of one
    user's decks); each deck needs `config` loaded.
    """
    decks = list(decks)
    ids = [d.id for d in decks]
    children: dict[int, list[int]] = {}
    for d in decks:
        if d.parent_id is not None:
            children.setdefault(d.parent_id, []).append(d.id)

    per_deck = {
        row["deck_id"]: row
        for row in Card.objects.filter(deck_id__in=ids)
        .values("deck_id")
        .annotate(
            new_total=Count("id", filter=Q(state=CardState.NEW)),
            learning=Count(
                "id",
                filter=Q(state__in=[CardState.LEARNING, CardState.RELEARNING], due__lte=now),
            ),
            review_due=Count("id", filter=Q(state=CardState.REVIEW, due__lte=now)),
            total=Count("id", filter=~Q(state=CardState.SUSPENDED)),
            forward=Count("id", filter=Q(direction=CardDirection.FORWARD)),
        )
    }
    sod = _start_of_day(now)
    done = {
        row["card__deck_id"]: row
        for row in ReviewLog.objects.filter(card__deck_id__in=ids, reviewed_at__gte=sod)
        .values("card__deck_id")
        .annotate(
            new_done=Count("id", filter=Q(state_before=CardState.NEW)),
            review_done=Count(
                "id", filter=Q(state_before__in=[CardState.REVIEW, CardState.RELEARNING])
            ),
        )
    }

    def subtree(deck_id: int) -> list[int]:
        out, stack = [], [deck_id]
        while stack:
            cur = stack.pop()
            out.append(cur)
            stack.extend(children.get(cur, []))
        return out

    def total(rows: dict, tree: list[int], key: str) -> int:
        return sum(rows[i][key] for i in tree if i in rows)

    result = {}
    for d in decks:
        tree = subtree(d.id)
        cfg = d.config
        new_allow = max(0, cfg.new_per_day - total(done, tree, "new_done"))
        review_allow = max(0, cfg.reviews_per_day - total(done, tree, "review_done"))
        result[d.id] = {
            "new": min(total(per_deck, tree, "new_total"), new_allow),
            "learning": total(per_deck, tree, "learning"),
            "due": min(total(per_deck, tree, "review_due"), review_allow),
            "total": total(per_deck, tree, "total"),
            "card_count": total(per_deck, tree, "forward"),
        }
    return result
