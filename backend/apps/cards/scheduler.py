"""Anki classic (SM-2) scheduler.

Pure functions that mutate a card's scheduling fields. Implemented to mirror
docs/ANKI_RESEARCH.md §5 line-for-line so it can be verified against the spec
and unit-tested in isolation. Operates on any object exposing the scheduling
attributes of `cards.models.Card` (so previews can run on a throwaway copy).
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta
from types import SimpleNamespace

AGAIN, HARD, GOOD, EASY = 1, 2, 3, 4
EASE_FLOOR = 1300  # permille (130%)
DAY = 86400


def _steps(raw: str) -> list[int]:
    """Parse '1 10' (space-separated minutes) -> [1, 10]."""
    out = []
    for tok in (raw or "").split():
        try:
            out.append(max(1, int(float(tok))))
        except ValueError:
            continue
    return out or [1]


def _start_of_day(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _fuzz_days(interval: int) -> int:
    """Anki-style fuzz on day intervals >= 3 days to spread siblings out."""
    if interval < 3:
        return interval
    if interval < 7:
        frac = 0.25
    elif interval < 30:
        frac = 0.15
    else:
        frac = 0.05
    delta = max(1, round(interval * frac))
    return interval + random.randint(-delta, delta)


def _clamp_interval(interval: int, config) -> int:
    return max(1, min(interval, config.maximum_interval))


def label_for_interval_days(days: int) -> str:
    if days < 1:
        return "<1d"
    if days < 30:
        return f"{days}d"
    if days < 365:
        return f"{days / 30:.1f}mo"
    return f"{days / 365:.1f}yr"


def _label_minutes(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes}m"
    return f"{minutes / 60:.0f}h"


# --------------------------------------------------------------------------
# Core transition. Mutates `c` (scheduling attrs) and returns a label string
# describing the resulting interval (for the answer-button preview).
# --------------------------------------------------------------------------
def _transition(c, rating: int, config, now: datetime, *, fuzz: bool) -> str:
    learn = _steps(config.learning_steps)
    relearn = _steps(config.relearning_steps)
    im = config.interval_modifier / 1000.0

    def graduate(interval_days: int) -> str:
        c.state = "review"
        c.step_index = 0
        c.interval_days = _clamp_interval(interval_days, config)
        c.due = _start_of_day(now) + timedelta(days=c.interval_days)
        c.reps += 1
        return label_for_interval_days(c.interval_days)

    def enter_step(steps: list[int], idx: int, state: str) -> str:
        idx = max(0, min(idx, len(steps) - 1))
        c.state = state
        c.step_index = idx
        c.due = now + timedelta(minutes=steps[idx])
        return _label_minutes(steps[idx])

    # ---- NEW or LEARNING ----
    if c.state in ("new", "learning"):
        if rating == AGAIN:
            return enter_step(learn, 0, "learning")
        if rating == EASY:
            c.ease = config.starting_ease
            return graduate(config.easy_interval)
        if rating == HARD:
            # Stay on / repeat the current step (Anki: average of current+next
            # with a single-step config this just repeats the current step).
            return enter_step(learn, c.step_index if c.state == "learning" else 0, "learning")
        # GOOD: advance one step; graduate off the end.
        next_idx = (c.step_index + 1) if c.state == "learning" else 1
        if next_idx >= len(learn):
            c.ease = config.starting_ease if c.reps == 0 else c.ease
            return graduate(config.graduating_interval)
        return enter_step(learn, next_idx, "learning")

    # ---- RELEARNING ----
    if c.state == "relearning":
        if rating == AGAIN:
            return enter_step(relearn, 0, "relearning")
        if rating == HARD:
            return enter_step(relearn, c.step_index, "relearning")
        # GOOD / EASY: advance; return to review off the end.
        next_idx = c.step_index + 1
        if rating == EASY or next_idx >= len(relearn):
            base = max(config.minimum_interval, c.interval_days)
            bonus = 1 if rating == EASY else 0
            return graduate(base + bonus)
        return enter_step(relearn, next_idx, "relearning")

    # ---- REVIEW ----
    i = c.interval_days or 1
    if rating == AGAIN:
        c.lapses += 1
        c.ease = max(EASE_FLOOR, c.ease - 200)
        lapse_interval = max(config.minimum_interval, round(i * config.new_interval / 1000.0))
        c.interval_days = _clamp_interval(lapse_interval, config)
        if config.leech_threshold and c.lapses >= config.leech_threshold:
            c.is_leech = True
            if config.leech_suspend:
                c.state = "suspended"
                c.due = now
                return "suspended"
        return enter_step(relearn, 0, "relearning")

    if rating == HARD:
        c.ease = max(EASE_FLOOR, c.ease - 150)
        new_i = i * (config.hard_interval / 1000.0) * im
    elif rating == GOOD:
        new_i = i * (c.ease / 1000.0) * im
    else:  # EASY
        c.ease = c.ease + 150
        new_i = i * (c.ease / 1000.0) * (config.easy_bonus / 1000.0) * im

    interval = max(i + 1, math.ceil(new_i))
    if fuzz:
        interval = _fuzz_days(interval)
    interval = _clamp_interval(interval, config)
    c.interval_days = interval
    c.reps += 1
    c.state = "review"
    c.due = _start_of_day(now) + timedelta(days=interval)
    return label_for_interval_days(interval)


def answer(card, rating: int, config, now: datetime) -> None:
    """Apply a rating (1-4) to a real Card, mutating it in place (with fuzz)."""
    _transition(card, rating, config, now, fuzz=True)
    card.last_reviewed_at = now


def preview_intervals(card, config, now: datetime) -> dict[str, str]:
    """Return the interval label each button would produce, without mutating
    the card and without fuzz (matches Anki's button hints)."""
    out: dict[str, str] = {}
    for rating in (AGAIN, HARD, GOOD, EASY):
        clone = SimpleNamespace(
            state=card.state,
            due=card.due,
            interval_days=card.interval_days,
            ease=card.ease,
            reps=card.reps,
            lapses=card.lapses,
            step_index=card.step_index,
            is_leech=card.is_leech,
        )
        out[str(rating)] = _transition(clone, rating, config, now, fuzz=False)
    return out
