from rest_framework import serializers

from .models import PushSubscription, SupportMessage, SupportThread


class SupportMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportMessage
        fields = ["id", "from_admin", "body", "created_at"]
        read_only_fields = ["id", "from_admin", "created_at"]


class SupportThreadSerializer(serializers.ModelSerializer):
    messages = SupportMessageSerializer(many=True, read_only=True)

    class Meta:
        model = SupportThread
        fields = ["id", "messages", "created_at", "updated_at"]
        read_only_fields = fields


class PushSubscriptionSerializer(serializers.Serializer):
    """Matches the PushSubscriptionJSON shape from the browser's
    PushManager.subscribe() — not a ModelSerializer since the nested `keys`
    object doesn't map 1:1 onto PushSubscription's flat fields."""

    endpoint = serializers.URLField(max_length=500)
    keys = serializers.DictField(child=serializers.CharField())

    def validate_keys(self, keys: dict) -> dict:
        if "p256dh" not in keys or "auth" not in keys:
            raise serializers.ValidationError("Missing p256dh/auth keys.")
        return keys
