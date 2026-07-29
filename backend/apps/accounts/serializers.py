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

    class Meta:
        model = User
        fields = [
            "id", "email", "display_name", "ui_language", "date_joined",
            "feature_flags", "subscription",
        ]
        read_only_fields = ["id", "email", "date_joined", "feature_flags", "subscription"]

    def get_feature_flags(self, obj) -> list[str]:
        return obj.effective_flags

    def get_subscription(self, obj) -> dict:
        # Imported lazily to keep accounts decoupled from the subscriptions app.
        from apps.subscriptions.models import Subscription
        from apps.subscriptions.serializers import subscription_summary

        return subscription_summary(Subscription.for_user(obj))
