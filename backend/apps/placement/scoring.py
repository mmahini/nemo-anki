"""Turn per-question results into a single estimated CEFR level.

"Ladder" method: walk the levels from A1 upward; the estimate is the highest
level where that level (and every level below it) scored at least PASS_RATE.
Simple, explainable, and easy to retune later.
"""
from .models import LEVELS

PASS_RATE = 0.6


def estimate_level(results: list[dict]) -> str:
    """`results`: iterable of {"level_tag": "A1".."C1", "is_correct": bool}."""
    by_level: dict[str, list[bool]] = {lvl: [] for lvl in LEVELS}
    for r in results:
        if r["level_tag"] in by_level:
            by_level[r["level_tag"]].append(bool(r["is_correct"]))

    estimated = LEVELS[0]
    for level in LEVELS:
        scored = by_level[level]
        if not scored:
            continue
        pass_rate = sum(scored) / len(scored)
        if pass_rate >= PASS_RATE:
            estimated = level
        else:
            break
    return estimated
