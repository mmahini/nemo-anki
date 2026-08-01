"""Subscription tiers, plans + payment config — the single source of truth.

Two tiers (Basic / Pro). A user either has an active subscription or not; the
tier only changes how much AI they can use per day. Keep in sync with the
frontend mirror in frontend/src/lib/subscription.ts and docs/plans/subscription.md.
"""

BASIC = "basic"
PRO = "pro"

# Daily AI-action limits (a fixed 1-day window, like an API rate limit). Sized
# so a normal learner never hits them but a script can't rack up Gemini cost,
# and Pro scales with its higher price. Tunable — see docs/plans/subscription.md.
FREE_DAILY_AI_LIMIT = 10  # trial expired / no active subscription
TRIAL_DAILY_AI_LIMIT = 40

TIERS = {
    BASIC: {"label": "Basic", "daily_ai_limit": 80},
    PRO: {"label": "Pro", "daily_ai_limit": 500},
}

_MONTH, _QUARTER, _YEAR = 30, 90, 365

# price_usd is a string so it serialises exactly (no float rounding).
PLANS = {
    "basic_monthly": {"tier": BASIC, "label": "1 month", "price_usd": "1.00", "days": _MONTH},
    "basic_quarterly": {"tier": BASIC, "label": "3 months", "price_usd": "2.50", "days": _QUARTER},
    "basic_yearly": {"tier": BASIC, "label": "12 months", "price_usd": "9.00", "days": _YEAR},
    "pro_monthly": {"tier": PRO, "label": "1 month", "price_usd": "5.00", "days": _MONTH},
    "pro_quarterly": {"tier": PRO, "label": "3 months", "price_usd": "12.50", "days": _QUARTER},
    "pro_yearly": {"tier": PRO, "label": "12 months", "price_usd": "45.00", "days": _YEAR},
}

PLAN_CHOICES = [(key, f'{TIERS[cfg["tier"]]["label"]} · {cfg["label"]}') for key, cfg in PLANS.items()]

TRIAL_DAYS = 7

# Referral programme: signing up through a friend's invite link gifts the new
# account a month of Basic (see accounts.views._apply_referral).
REFERRAL_BONUS_TIER = BASIC
REFERRAL_BONUS_DAYS = _MONTH

# Phase 1: manual crypto transfer. See docs/plans/subscription.md phase 2.
PAYMENT = {
    "method": "crypto",
    "network": "BSC (BEP-20)",
    "address": "0x8D15fba1C27DBb1a056aB5245Bd8Eb3471B5CD66",
}


def plan_tier(plan: str) -> str:
    return PLANS.get(plan, {}).get("tier", "")


def tiers_public() -> list[dict]:
    """Tiers (with their plans + daily AI limit) for the API / buy page."""
    return [
        {
            "key": tier,
            "label": cfg["label"],
            "daily_ai_limit": cfg["daily_ai_limit"],
            "plans": [
                {"key": k, "label": p["label"], "price_usd": p["price_usd"], "days": p["days"]}
                for k, p in PLANS.items()
                if p["tier"] == tier
            ],
        }
        for tier, cfg in TIERS.items()
    ]
