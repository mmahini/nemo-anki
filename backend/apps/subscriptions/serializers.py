from rest_framework import serializers

from .models import Subscription, SubscriptionRequest
from .plans import PLANS
from .quota import ai_usage


def subscription_summary(sub: Subscription) -> dict:
    """Compact status used by the top-of-page banner (embedded in /api/me and
    returned by the subscription endpoints)."""
    used, limit = ai_usage(sub.user)
    return {
        "state": sub.computed_state,
        "is_active": sub.is_active,
        "access_until": sub.access_until,
        "days_left": sub.days_left,
        "plan": sub.plan or None,
        "tier": sub.active_tier,
        # AI usage in the current 1-day window (limit is null when unlimited).
        "ai_used": used,
        "ai_limit": limit,
        # A pending "I've paid" submission awaiting admin verification.
        "pending": sub.user.subscription_requests.filter(
            status=SubscriptionRequest.PENDING
        ).exists(),
    }


class ClaimSerializer(serializers.Serializer):
    plan = serializers.ChoiceField(choices=list(PLANS.keys()))
    # User's source wallet address or transaction hash (optional — an admin can
    # add it later).
    tx_reference = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
