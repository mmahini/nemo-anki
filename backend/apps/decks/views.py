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
    """Bulk-run German colouring over a deck's cards: detect & set the article
    for vocab nouns, and the per-noun genders for sentence/grammar cards.
    Processes a capped batch per call (Gemini is per-card) and reports how many
    remain, so the client can re-run until done."""

    permission_classes = [IsAuthenticated]
    BATCH = 30

    def _eligible(self, deck):
        from django.db.models import Q

        from apps.cards.models import Card

        return Card.objects.filter(
            deck_id__in=deck.descendant_ids(), language="de", reverse_of__isnull=True
        ).filter(
            Q(card_type="vocab", article="none")
            | Q(card_type__in=["sentence", "grammar"], genders=[])
            | Q(card_type__in=["sentence", "grammar"], genders__isnull=True)
        )

    def post(self, request, pk):
        from apps.cards.models import sync_card_group
        from apps.imports.gemini import analyze_german

        deck = Deck.objects.filter(id=pk, user=request.user).first()
        if not deck:
            return Response(status=status.HTTP_404_NOT_FOUND)

        colourized = 0
        for card in list(self._eligible(deck)[: self.BATCH]):
            try:
                nouns = (analyze_german(card.front) or {}).get("nouns") or []
            except Exception:  # noqa: BLE001 - one bad card shouldn't abort the batch
                continue
            if not nouns:
                continue
            if card.card_type == "vocab":
                # A vocab term is one word — colour it by its (first) noun gender.
                card.article = nouns[0]["gender"]
                card.save(update_fields=["article"])
            else:
                card.genders = nouns
                card.save(update_fields=["genders"])
            sync_card_group(card)
            colourized += 1

        return Response({"colourized": colourized, "remaining": self._eligible(deck).count()})


class DeckAutotypeView(APIView):
    """Auto-detect each card's type (vocab / sentence / grammar) from its
    content and update it. A fast, free heuristic — no LLM."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def _classify(card) -> str:
        import re

        f = (card.front or "").strip()
        low = f.lower()
        # A gap/cloze marker or an attached rule table ⇒ grammar.
        if card.table or "___" in f or "…" in f or "{{c" in low or ("[" in f and "]" in f):
            return "grammar"
        words = [w for w in re.split(r"\s+", f) if w]
        # Reads like a sentence: several words, or ends with sentence punctuation.
        if len(words) >= 4 or (len(words) >= 2 and f[-1:] in ".!?"):
            return "sentence"
        return "vocab"

    def post(self, request, pk):
        from apps.cards.models import Card, sync_card_group

        deck = Deck.objects.filter(id=pk, user=request.user).first()
        if not deck:
            return Response(status=status.HTTP_404_NOT_FOUND)

        cards = Card.objects.filter(deck_id__in=deck.descendant_ids(), reverse_of__isnull=True)
        changed = 0
        counts = {"vocab": 0, "sentence": 0, "grammar": 0}
        for card in cards:
            new_type = self._classify(card)
            counts[new_type] += 1
            if new_type != card.card_type:
                card.card_type = new_type
                card.save(update_fields=["card_type"])
                sync_card_group(card)
                changed += 1
        return Response({"changed": changed, "total": cards.count(), "counts": counts})


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
