import zoneinfo

from django.utils import timezone
from rest_framework import serializers

from .models import OTP_LENGTH, User


class RequestOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()


class VerifyOTPSerializer(serializers.Serializer):
    otp_id = serializers.UUIDField()
    code = serializers.CharField(min_length=OTP_LENGTH, max_length=OTP_LENGTH)
    # The `?ref=` value from an invite link, sent along by the client. Only
    # honoured when this verification creates the account.
    referral_code = serializers.CharField(
        max_length=32, required=False, allow_blank=True, default=""
    )


class UserSerializer(serializers.ModelSerializer):
    # Effective flags (includes implicit superuser flags). Read-only — a user
    # must never be able to grant themselves a flag via PATCH /api/me.
    feature_flags = serializers.SerializerMethodField()
    # Subscription status for the top-of-page banner. Read-only.
    subscription = serializers.SerializerMethodField()
    # Has the welcome flow been completed? Writable as a boolean: the client
    # PATCHes `onboarded: true` when the user finishes (or skips) it, and the
    # server stamps the time. Exposed as a boolean because the timestamp is an
    # implementation detail the UI has no use for.
    onboarded = serializers.BooleanField(required=False)
    # Has this user completed the Telegram "Connect" handshake (a linked
    # chat_id)? Read-only — set only by apps.notifications.poll_telegram_updates.
    telegram_connected = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "display_name", "ui_language", "date_joined",
            "feature_flags", "subscription", "onboarded", "is_staff",
            "referral_code",
            "study_reminder_time", "study_reminder_timezone", "study_reminder_channel",
            "telegram_connected",
        ]
        read_only_fields = [
            "id", "email", "date_joined", "feature_flags", "subscription", "is_staff",
            "referral_code", "telegram_connected",
        ]

    def get_feature_flags(self, obj) -> list[str]:
        return obj.effective_flags

    def get_telegram_connected(self, obj) -> bool:
        link = getattr(obj, "telegram_link", None)
        return bool(link and link.chat_id)

    def validate_study_reminder_timezone(self, value: str) -> str:
        if value not in zoneinfo.available_timezones():
            raise serializers.ValidationError("Unknown timezone.")
        return value

    def to_representation(self, obj) -> dict:
        data = super().to_representation(obj)
        data["onboarded"] = obj.onboarded_at is not None
        return data

    def update(self, instance, validated_data):
        onboarded = validated_data.pop("onboarded", None)
        if onboarded is not None:
            # Keep the original completion time — re-watching the intro later
            # shouldn't rewrite when this user was first onboarded.
            if onboarded and instance.onboarded_at is None:
                instance.onboarded_at = timezone.now()
            elif not onboarded:
                instance.onboarded_at = None
            instance.save(update_fields=["onboarded_at"])
        return super().update(instance, validated_data)

    def get_subscription(self, obj) -> dict:
        # Imported lazily to keep accounts decoupled from the subscriptions app.
        from apps.subscriptions.models import Subscription
        from apps.subscriptions.serializers import subscription_summary

        return subscription_summary(Subscription.for_user(obj))
