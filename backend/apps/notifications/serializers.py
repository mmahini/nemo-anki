from rest_framework import serializers

from .models import PushSubscription


class PushSubscriptionSerializer(serializers.ModelSerializer):
    """Mirrors the browser's `PushSubscription.toJSON()` shape:
    `{endpoint, keys: {p256dh, auth}}` flattened to three fields."""

    class Meta:
        model = PushSubscription
        fields = ["endpoint", "p256dh", "auth"]
        # Re-subscribing the same endpoint is an upsert (see
        # PushSubscribeView), not a validation error — drop the automatic
        # uniqueness check DRF adds for the model's unique `endpoint` field.
        extra_kwargs = {"endpoint": {"validators": []}}
