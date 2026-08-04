from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PushSubscription, TelegramLink, _generate_connect_token
from .serializers import PushSubscriptionSerializer


class PushSubscribeView(APIView):
    """Registers (or re-registers) this browser's push subscription for the
    current user — called right after `pushManager.subscribe()` succeeds."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PushSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        endpoint = serializer.validated_data["endpoint"]
        with transaction.atomic():
            # `endpoint` is unique per browser subscription, so it can only
            # ever belong to one user at a time. update_or_create(endpoint=…)
            # used to key on endpoint alone, so a second account subscribing
            # from the same browser (a shared/reused device) would silently
            # steal the row via its `defaults={"user": request.user, ...}` —
            # the original owner's reminders would just stop, with nothing
            # in the API response or logs to explain why. Doing the handoff
            # explicitly — drop any other owner's row first — keeps the same
            # real-world behavior (one browser subscription, one current
            # owner) but makes the transfer an intentional, visible step
            # instead of an accidental side effect of a loose lookup key.
            PushSubscription.objects.filter(endpoint=endpoint).exclude(user=request.user).delete()
            PushSubscription.objects.update_or_create(
                user=request.user, endpoint=endpoint, defaults=serializer.validated_data,
            )
        return Response(status=status.HTTP_201_CREATED)


class PushUnsubscribeView(APIView):
    """Removes this browser's push subscription for the current user."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        endpoint = (request.data.get("endpoint") or "").strip()
        request.user.push_subscriptions.filter(endpoint=endpoint).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TelegramConnectView(APIView):
    """Starts (or restarts) the "Connect Telegram" handshake: returns a
    t.me deep link that, once the user presses Start on our bot, delivers
    their chat_id back to us via poll_telegram_updates."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not (settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_BOT_USERNAME):
            return Response(
                {"detail": "Telegram reminders aren't configured yet."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        link, _ = TelegramLink.objects.get_or_create(user=request.user)
        if link.chat_id is None:
            # Rotate the token on every (re)connect attempt so an abandoned
            # attempt's token can't be used later.
            link.connect_token = _generate_connect_token()
            link.save(update_fields=["connect_token"])
        return Response({"deep_link": f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={link.connect_token}"})


class TelegramStatusView(APIView):
    """Polled by the frontend after opening the deep link, to detect when
    the handshake completes."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        link = getattr(request.user, "telegram_link", None)
        return Response({"connected": bool(link and link.chat_id)})


class TelegramDisconnectView(APIView):
    """Unlinks the user's Telegram chat. Only clears chat_id — the
    TelegramLink row (connect_token, default_language) is kept, so
    reconnecting later doesn't lose the language preference set via /lang."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        link = getattr(request.user, "telegram_link", None)
        if link and link.chat_id is not None:
            link.chat_id = None
            link.save(update_fields=["chat_id"])
        return Response(status=status.HTTP_204_NO_CONTENT)
