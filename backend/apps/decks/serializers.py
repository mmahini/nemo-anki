from rest_framework import serializers

from .models import Deck, DeckConfig


class DeckConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeckConfig
        exclude = ["user"]
        read_only_fields = ["id", "created_at"]


class DeckSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    # Study counts injected by the view (avoids N+1 in the serializer).
    counts = serializers.SerializerMethodField()

    class Meta:
        model = Deck
        fields = [
            "id",
            "name",
            "full_name",
            "parent",
            "language",
            "color",
            "config",
            "counts",
            "created_at",
        ]
        read_only_fields = ["id", "full_name", "created_at"]
        extra_kwargs = {"config": {"required": False}}

    def get_counts(self, obj) -> dict:
        return getattr(obj, "_counts", {"new": 0, "learning": 0, "due": 0, "total": 0})
