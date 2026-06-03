from rest_framework import serializers

from apps.decks.models import Deck

from .models import Card


class CardSerializer(serializers.ModelSerializer):
    # Predicted next intervals per button, attached by the study view.
    intervals = serializers.SerializerMethodField()
    deck_name = serializers.CharField(source="deck.full_name", read_only=True)

    class Meta:
        model = Card
        fields = [
            "id",
            "deck",
            "deck_name",
            "card_type",
            "language",
            "front",
            "back",
            "reading",
            "article",
            "example",
            "notes",
            "table",
            "genders",
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

    def validate_deck(self, deck: Deck) -> Deck:
        request = self.context.get("request")
        if request and deck.user_id != request.user.id:
            raise serializers.ValidationError("Deck not found.")
        return deck


class BulkCardSerializer(serializers.Serializer):
    """Create many cards in one deck (the import "proceed" action)."""

    deck = serializers.PrimaryKeyRelatedField(queryset=Deck.objects.all())
    cards = CardSerializer(many=True)

    def validate_deck(self, deck: Deck) -> Deck:
        request = self.context.get("request")
        if request and deck.user_id != request.user.id:
            raise serializers.ValidationError("Deck not found.")
        return deck


class AnswerSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=4)
    time_ms = serializers.IntegerField(min_value=0, default=0)
