from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.decks.models import Deck

from . import scheduler
from .models import Card, ReviewLog
from .queue import study_queue
from .serializers import AnswerSerializer, BulkCardSerializer, CardSerializer


class CardListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Card.objects.filter(deck__user=request.user).select_related("deck")
        deck_id = request.query_params.get("deck")
        if deck_id:
            deck = Deck.objects.filter(id=deck_id, user=request.user).first()
            if not deck:
                return Response([], status=status.HTTP_200_OK)
            qs = qs.filter(deck_id__in=deck.descendant_ids())
        card_type = request.query_params.get("type")
        if card_type:
            qs = qs.filter(card_type=card_type)
        return Response(CardSerializer(qs, many=True).data)

    def post(self, request):
        serializer = CardSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        deck = serializer.validated_data["deck"]
        # Inherit deck language when the card didn't specify one.
        extra = {}
        if not serializer.validated_data.get("language"):
            extra["language"] = deck.language
        extra["position"] = _next_position(deck)
        card = serializer.save(**extra)
        return Response(CardSerializer(card).data, status=status.HTTP_201_CREATED)


def _next_position(deck: Deck) -> int:
    last = Card.objects.filter(deck=deck).order_by("-position").first()
    return (last.position + 1) if last else 0


class CardDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, request, pk):
        return Card.objects.filter(id=pk, deck__user=request.user).select_related("deck").first()

    def get(self, request, pk):
        card = self._get(request, pk)
        if not card:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(CardSerializer(card).data)

    def patch(self, request, pk):
        card = self._get(request, pk)
        if not card:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = CardSerializer(card, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(CardSerializer(card).data)

    def delete(self, request, pk):
        card = self._get(request, pk)
        if not card:
            return Response(status=status.HTTP_204_NO_CONTENT)
        card.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class BulkCardView(APIView):
    """The import "proceed" action: create many edited cards in one deck."""

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        serializer = BulkCardSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        deck = serializer.validated_data["deck"]
        pos = _next_position(deck)
        created = []
        for i, item in enumerate(serializer.validated_data["cards"]):
            item.pop("deck", None)
            if not item.get("language"):
                item["language"] = deck.language
            created.append(Card(deck=deck, position=pos + i, **item))
        Card.objects.bulk_create(created)
        return Response(
            {"created": len(created), "deck": deck.id},
            status=status.HTTP_201_CREATED,
        )


class StudyView(APIView):
    """Return the next batch of due cards for a deck (with interval previews)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        deck = Deck.objects.filter(id=pk, user=request.user).select_related("config").first()
        if not deck:
            return Response(status=status.HTTP_404_NOT_FOUND)
        now = timezone.now()
        cards = study_queue(deck, now)
        config = deck.config
        for c in cards:
            c._intervals = scheduler.preview_intervals(c, config, now)
        return Response(CardSerializer(cards, many=True).data)


class AnswerView(APIView):
    """Apply a 1-4 rating to a card and persist the new scheduling state."""

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        card = (
            Card.objects.select_for_update()
            .filter(id=pk, deck__user=request.user)
            .select_related("deck", "deck__config")
            .first()
        )
        if not card:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = AnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rating = serializer.validated_data["rating"]
        time_ms = serializer.validated_data["time_ms"]

        now = timezone.now()
        config = card.deck.config
        snapshot = card.scheduling_snapshot()
        state_before, interval_before, ease_before = card.state, card.interval_days, card.ease

        scheduler.answer(card, rating, config, now)
        card.save()

        ReviewLog.objects.create(
            card=card,
            user=request.user,
            rating=rating,
            state_before=state_before,
            state_after=card.state,
            interval_before=interval_before,
            interval_after=card.interval_days,
            ease_before=ease_before,
            ease_after=card.ease,
            time_ms=time_ms,
            prev_snapshot=snapshot,
        )
        return Response(CardSerializer(card).data)


class UndoView(APIView):
    """Undo the most recent answer for the user, restoring the card state."""

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        log = (
            ReviewLog.objects.select_related("card")
            .filter(user=request.user)
            .order_by("-reviewed_at")
            .first()
        )
        if not log:
            return Response({"detail": "Nothing to undo."}, status=status.HTTP_404_NOT_FOUND)
        card = log.card
        card.restore_snapshot(log.prev_snapshot)
        card.save()
        log.delete()
        return Response(CardSerializer(card).data)
