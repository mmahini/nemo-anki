from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cards.activity import streak_summary

from .models import BuddyLink

User = get_user_model()


def _active_link_for(link_user):
    """The requesting user's one active link (pending or accepted), in
    either direction — a BuddyLink row is deleted outright on decline/
    unpair, so "exists" already means "active"."""
    return (
        BuddyLink.objects.filter(Q(requester=link_user) | Q(recipient=link_user))
        .select_related("requester", "recipient")
        .first()
    )


def _other(link: BuddyLink, me):
    return link.recipient if link.requester_id == me.id else link.requester


class BuddyView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        link = _active_link_for(request.user)
        if not link:
            return Response({"status": "none"})
        if link.status == "pending":
            if link.requester_id == request.user.id:
                return Response({"status": "pending_sent", "email": link.recipient.email})
            return Response({"status": "pending_received", "email": link.requester.email})
        buddy = _other(link, request.user)
        return Response(
            {
                "status": "accepted",
                "buddy_email": buddy.email,
                "me": streak_summary(request.user),
                "buddy": streak_summary(buddy),
                "nudged_today": link.last_nudge_at is not None
                and link.last_nudge_at.date() == timezone.localdate(),
            }
        )

    def delete(self, request):
        # Cancels a sent invite, declines a received one, or unpairs an
        # accepted link — same action from either side. filter().delete()
        # is already a no-op (204) when nothing matches, so this is
        # idempotent without a separate existence check.
        BuddyLink.objects.filter(Q(requester=request.user) | Q(recipient=request.user)).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BuddyInviteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        if not email:
            return Response({"detail": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)
        if email == request.user.email.lower():
            return Response({"detail": "That's you."}, status=status.HTTP_400_BAD_REQUEST)
        if _active_link_for(request.user):
            return Response(
                {"detail": "You already have a study buddy or a pending invite."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        target = User.objects.filter(email=email).first()
        if not target:
            return Response({"detail": "No user with that email yet."}, status=status.HTTP_404_NOT_FOUND)
        if _active_link_for(target):
            return Response(
                {"detail": "That user already has a study buddy."}, status=status.HTTP_400_BAD_REQUEST
            )
        BuddyLink.objects.create(requester=request.user, recipient=target)
        return Response({"status": "pending_sent", "email": target.email}, status=status.HTTP_201_CREATED)


class BuddyAcceptView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        link = BuddyLink.objects.filter(
            recipient=request.user, status="pending"
        ).select_related("requester").first()
        if not link:
            return Response({"detail": "No pending invite to accept."}, status=status.HTTP_404_NOT_FOUND)
        link.status = "accepted"
        link.responded_at = timezone.now()
        link.save(update_fields=["status", "responded_at"])
        return Response(
            {
                "status": "accepted",
                "buddy_email": link.requester.email,
                "me": streak_summary(request.user),
                "buddy": streak_summary(link.requester),
                "nudged_today": False,
            }
        )


class BuddyNudgeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        link = _active_link_for(request.user)
        if not link or link.status != "accepted":
            return Response({"detail": "You don't have a study buddy yet."}, status=status.HTTP_404_NOT_FOUND)
        today = timezone.localdate()
        if link.last_nudge_at and link.last_nudge_at.date() == today:
            return Response(
                {"detail": "You've already nudged your buddy today."}, status=status.HTTP_400_BAD_REQUEST
            )
        buddy = _other(link, request.user)
        me_name = request.user.display_name.strip() or request.user.email
        message = f"👋 {me_name} nudged you to study today!"

        # Imported lazily to keep buddy decoupled from notifications.
        from apps.notifications.tasks import send_buddy_nudge_push, send_buddy_nudge_telegram

        if buddy.study_reminder_channel == "telegram":
            if not (hasattr(buddy, "telegram_link") and buddy.telegram_link.chat_id):
                return Response(
                    {"detail": "Your buddy hasn't connected a notification channel yet."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            send_buddy_nudge_telegram.delay(buddy.id, message)
        else:
            if not buddy.push_subscriptions.exists():
                return Response(
                    {"detail": "Your buddy hasn't connected a notification channel yet."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            send_buddy_nudge_push.delay(buddy.id, message)

        link.last_nudge_at = timezone.now()
        link.save(update_fields=["last_nudge_at"])
        return Response({"nudged_today": True})
