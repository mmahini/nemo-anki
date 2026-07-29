from rest_framework import serializers

from .models import Subscription, SubscriptionRequest
from .plans import PLANS


def subscription_summary(sub: Subscription) -> dict:
    """Compact status used by the top-of-page banner (embedded in /api/me and
    returned by the subscription endpoints)."""
    return {
        "state": sub.computed_state,
        "is_active": sub.is_active,
        "access_until": sub.access_until,
        "days_left": sub.days_left,
        "plan": sub.plan or None,
        # A pending "I've paid" submission awaiting admin verification.
        "pending": sub.user.subscription_requests.filter(
            status=SubscriptionRequest.PENDING
        ).exists(),
    }


class ClaimSerializer(serializers.Serializer):
    plan = serializers.ChoiceField(choices=list(PLANS.keys()))
