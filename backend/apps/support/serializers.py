from rest_framework import serializers

from .models import SupportMessage, SupportThread


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
