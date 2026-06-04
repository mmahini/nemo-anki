from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Deck, DeckConfig
from .serializers import DeckConfigSerializer, DeckSerializer


def _default_config(user) -> DeckConfig:
    cfg, _ = DeckConfig.objects.get_or_create(user=user, name="Default")
    return cfg


def _with_counts(deck, now):
    from apps.cards.queue import deck_counts

    deck._counts = deck_counts(deck, now)
    return deck


class DeckListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        decks = list(Deck.objects.filter(user=request.user).select_related("parent", "config"))
        # New accounts start empty — users build their own decks. The Menschen
        # + Oxford trees remain available on demand via `manage.py seed_decks`.
        for d in decks:
            _with_counts(d, now)
        data = DeckSerializer(decks, many=True).data
        # Sort by full_name so the tree reads top-down.
        data.sort(key=lambda d: d["full_name"].lower())
        return Response(data)

    def post(self, request):
        serializer = DeckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        parent = serializer.validated_data.get("parent")
        if parent and parent.user_id != request.user.id:
            return Response({"detail": "Invalid parent."}, status=status.HTTP_400_BAD_REQUEST)
        config = serializer.validated_data.get("config") or _default_config(request.user)
        deck = serializer.save(user=request.user, config=config)
        _with_counts(deck, timezone.now())
        return Response(DeckSerializer(deck).data, status=status.HTTP_201_CREATED)


class DeckDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, request, pk):
        return Deck.objects.filter(id=pk, user=request.user).select_related("parent", "config").first()

    def get(self, request, pk):
        deck = self._get(request, pk)
        if not deck:
            return Response(status=status.HTTP_404_NOT_FOUND)
        _with_counts(deck, timezone.now())
        return Response(DeckSerializer(deck).data)

    def patch(self, request, pk):
        deck = self._get(request, pk)
        if not deck:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = DeckSerializer(deck, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        # Validate a parent change: must be the user's deck, not itself, and
        # not one of its own descendants (which would create a cycle).
        if "parent" in serializer.validated_data:
            parent = serializer.validated_data["parent"]
            if parent is not None:
                if parent.user_id != request.user.id:
                    return Response({"detail": "Invalid parent."}, status=status.HTTP_400_BAD_REQUEST)
                if parent.id == deck.id or parent.id in deck.descendant_ids():
                    return Response(
                        {"detail": "A deck can't be moved under itself or its own sub-deck."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        serializer.save()
        _with_counts(deck, timezone.now())
        return Response(DeckSerializer(deck).data)

    def delete(self, request, pk):
        deck = self._get(request, pk)
        if not deck:
            return Response(status=status.HTTP_204_NO_CONTENT)
        deck.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DeckStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from apps.cards.queue import deck_counts

        deck = Deck.objects.filter(id=pk, user=request.user).select_related("config").first()
        if not deck:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(deck_counts(deck, timezone.now()))


class DeckColourizeView(APIView):
    """Bulk-run the German gender analysis over a deck's multi-word cards
    (sentence + grammar) so they colour correctly. Processes a capped batch per
    call (Gemini is per-card) and reports how many remain, so the client can
    re-run until done."""

    permission_classes = [IsAuthenticated]
    BATCH = 30

    def post(self, request, pk):
        from django.db.models import Q

        from apps.cards.models import Card, sync_card_group
        from apps.imports.gemini import analyze_german

        deck = Deck.objects.filter(id=pk, user=request.user).first()
        if not deck:
            return Response(status=status.HTTP_404_NOT_FOUND)

        eligible = Card.objects.filter(
            deck_id__in=deck.descendant_ids(),
            language="de",
            reverse_of__isnull=True,
            card_type__in=["sentence", "grammar"],
        ).filter(Q(genders=[]) | Q(genders__isnull=True))

        colourized = 0
        for card in list(eligible[: self.BATCH]):
            try:
                nouns = (analyze_german(card.front) or {}).get("nouns") or []
            except Exception:  # noqa: BLE001 - one bad card shouldn't abort the batch
                continue
            if nouns:
                card.genders = nouns
                card.save(update_fields=["genders"])
                sync_card_group(card)
                colourized += 1

        remaining = (
            Card.objects.filter(
                deck_id__in=deck.descendant_ids(),
                language="de",
                reverse_of__isnull=True,
                card_type__in=["sentence", "grammar"],
            )
            .filter(Q(genders=[]) | Q(genders__isnull=True))
            .count()
        )
        return Response({"colourized": colourized, "remaining": remaining})


class DeckConfigDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        cfg = DeckConfig.objects.filter(id=pk, user=request.user).first()
        if not cfg:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(DeckConfigSerializer(cfg).data)

    def patch(self, request, pk):
        cfg = DeckConfig.objects.filter(id=pk, user=request.user).first()
        if not cfg:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = DeckConfigSerializer(cfg, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
