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
    is_owner = serializers.SerializerMethodField()
    owner_email = serializers.CharField(source="user.email", read_only=True)
    shared_with = serializers.SerializerMethodField()
    card_count = serializers.SerializerMethodField()

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
            "is_owner",
            "owner_email",
            "shared_with",
            "card_count",
            "created_at",
        ]
        read_only_fields = ["id", "full_name", "created_at"]
        extra_kwargs = {"config": {"required": False}}

    def get_counts(self, obj) -> dict:
        return getattr(obj, "_counts", {"new": 0, "learning": 0, "due": 0, "total": 0})

    def _request_user(self):
        req = self.context.get("request")
        return req.user if req else None

    def get_is_owner(self, obj) -> bool:
        u = self._request_user()
        return bool(u and obj.user_id == u.id)

    def get_shared_with(self, obj) -> list[str]:
        # Only the owner sees who it's shared with.
        if self.get_is_owner(obj):
            return [s.user.email for s in obj.shares.select_related("user").all()]
        return []

    def get_card_count(self, obj) -> int:
        from apps.cards.models import Card

        return Card.objects.filter(deck_id__in=obj.descendant_ids(), direction="forward").count()
