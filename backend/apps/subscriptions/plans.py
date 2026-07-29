"""Subscription plans + payment config — the single source of truth.

Keep in sync with the frontend mirror in frontend/src/lib/subscription.ts and
the plan doc at docs/plans/subscription.md.
"""

MONTHLY = "monthly"
QUARTERLY = "quarterly"
YEARLY = "yearly"

# price_usd is a string so it serialises exactly (no float rounding).
PLANS = {
    MONTHLY: {"label": "1 month", "price_usd": "1.00", "days": 30},
    QUARTERLY: {"label": "3 months", "price_usd": "2.50", "days": 90},
    YEARLY: {"label": "12 months", "price_usd": "9.00", "days": 365},
}

PLAN_CHOICES = [(key, cfg["label"]) for key, cfg in PLANS.items()]

TRIAL_DAYS = 7

# Phase 1: manual crypto transfer. See docs/plans/subscription.md phase 2 for the
# planned automated flow.
PAYMENT = {
    "method": "crypto",
    "network": "BSC (BEP-20)",
    "address": "0x8D15fba1C27DBb1a056aB5245Bd8Eb3471B5CD66",
}


def plans_public() -> list[dict]:
    """Plans as a list for the API / UI."""
    return [
        {"key": key, "label": cfg["label"], "price_usd": cfg["price_usd"], "days": cfg["days"]}
        for key, cfg in PLANS.items()
    ]
