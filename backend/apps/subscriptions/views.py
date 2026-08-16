from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core import cdp

from .models import Subscription, SubscriptionRequest
from .plans import PAYMENT, tiers_public
from .serializers import ClaimSerializer, subscription_summary


class SubscriptionView(APIView):
    """Current user's subscription status."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        sub = Subscription.for_user(request.user)
        return Response(subscription_summary(sub))


class PlansView(APIView):
    """Available plans + payment instructions for the buy page."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"tiers": tiers_public(), "payment": PAYMENT})


class ClaimView(APIView):
    """User taps "I've paid" — record a pending request for admin verification.

    Phase 1 is manual: this does NOT grant access. An admin approves it (see
    docs/plans/subscription.md)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ClaimSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        Subscription.for_user(request.user)  # ensure it exists
        tx_reference = serializer.validated_data.get("tx_reference", "").strip()
        # Collapse rapid double-taps: reuse an existing pending request for the
        # same plan rather than stacking duplicates in the admin queue.
        req, _ = SubscriptionRequest.objects.get_or_create(
            user=request.user,
            plan=serializer.validated_data["plan"],
            status=SubscriptionRequest.PENDING,
        )
        # Keep the latest reference the user provides (they may resubmit with it).
        if tx_reference and req.tx_reference != tx_reference:
            req.tx_reference = tx_reference
            req.save(update_fields=["tx_reference"])
        # The money conversation lands here, so it's tracked here — reliably,
        # ad-blockers notwithstanding (Wiser CDP; see core.cdp).
        cdp.track(
            request.user,
            "subscription_requested",
            {
                "plan": serializer.validated_data["plan"],
                "has_tx_reference": bool(req.tx_reference),
            },
        )
        return Response(
            {"ok": True, "request_id": req.id, "status": req.status},
            status=status.HTTP_201_CREATED,
        )
