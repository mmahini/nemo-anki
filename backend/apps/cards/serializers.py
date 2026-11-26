from rest_framework import serializers

from apps.decks.models import Deck

from .models import Card


class CardSerializer(serializers.ModelSerializer):
    # Predicted next intervals per button, attached by the study view.
    intervals = serializers.SerializerMethodField()
    deck_name = serializers.SerializerMethodField()
    deck_language = serializers.CharField(source="deck.language", read_only=True)
    has_reverse = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()

    class Meta:
        model = Card
        fields = [
            "id",
            "deck",
            "deck_name",
            "deck_language",
            "card_type",
            "direction",
            "reverse_of",
            "has_reverse",
            "images",
            "language",
            "front",
            "back",
            "reading",
            "article",
            "plural",
            "example",
            "notes",
            "mnemonic",
            "table",
            "genders",
            "conjugations",
            "tags",
            "state",
            "due",
            "interval_days",
            "ease",
            "reps",
            "lapses",
            "is_leech",
            "intervals",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "deck_name",
            "deck_language",
            "direction",
            "reverse_of",
            "has_reverse",
            "images",
            "state",
            "due",
            "interval_days",
            "ease",
            "reps",
            "lapses",
            "is_leech",
            "intervals",
            "created_at",
            "updated_at",
        ]

    def get_intervals(self, obj):
        return getattr(obj, "_intervals", None)

    def get_deck_name(self, obj) -> str:
        # full_name walks the parent chain (a query per level). A study batch or
        # card page is mostly one deck, so memoise per deck across the list —
        # the context dict is shared by every child of a many=True serializer.
        names = self.context.setdefault("_deck_full_names", {}) if self.context is not None else {}
        if obj.deck_id not in names:
            names[obj.deck_id] = obj.deck.full_name
        return names[obj.deck_id]

    def get_has_reverse(self, obj) -> bool:
        # True for a forward vocab card that has a reverse companion.
        if obj.reverse_of_id is not None:
            return False
        # .exists() always hits the DB; use the prefetch when the view did one.
        prefetched = getattr(obj, "_prefetched_objects_cache", {})
        if "reverses" in prefetched:
            return bool(prefetched["reverses"])
        return obj.reverses.exists()

    def get_images(self, obj):
        # Images live on the primary (forward) card; a reverse shows the same set.
        src = obj.reverse_of if obj.reverse_of_id else obj
        return [{"id": im.id, "url": im.image.url} for im in src.images.all()]

    def validate_deck(self, deck: Deck) -> Deck:
        request = self.context.get("request")
        if request and deck.user_id != request.user.id:
            raise serializers.ValidationError("Deck not found.")
        return deck


class DraftCardSerializer(CardSerializer):
    """CardSerializer variant used inside BulkCardSerializer — deck is
    provided at the top level, so it is optional per card."""

    deck = serializers.PrimaryKeyRelatedField(
        queryset=Deck.objects.all(), required=False, allow_null=True
    )


class BulkCardSerializer(serializers.Serializer):
    """Create many cards in one deck (the import "proceed" action)."""

    deck = serializers.PrimaryKeyRelatedField(queryset=Deck.objects.all())
    cards = DraftCardSerializer(many=True)

    def validate_deck(self, deck: Deck) -> Deck:
        request = self.context.get("request")
        if request and deck.user_id != request.user.id:
            raise serializers.ValidationError("Deck not found.")
        return deck


class AnswerSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=4)
    time_ms = serializers.IntegerField(min_value=0, default=0)
