from django.utils import timezone
from rest_framework import serializers

from .models import OTP_LENGTH, User


class RequestOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()


class VerifyOTPSerializer(serializers.Serializer):
    otp_id = serializers.UUIDField()
    code = serializers.CharField(min_length=OTP_LENGTH, max_length=OTP_LENGTH)


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

    class Meta:
        model = User
        fields = [
            "id", "email", "display_name", "ui_language", "date_joined",
            "feature_flags", "subscription", "onboarded", "is_staff",
        ]
        read_only_fields = [
            "id", "email", "date_joined", "feature_flags", "subscription", "is_staff",
        ]

    def get_feature_flags(self, obj) -> list[str]:
        return obj.effective_flags

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
