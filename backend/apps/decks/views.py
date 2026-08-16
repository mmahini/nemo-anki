from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.subscriptions.quota import AiQuotaMixin
from core import cdp

from .models import Deck, DeckConfig, DeckShare
from .serializers import DeckConfigSerializer, DeckSerializer


def _default_config(user) -> DeckConfig:
    cfg, _ = DeckConfig.objects.get_or_create(user=user, name="Default")
    return cfg


def _with_counts(deck, now):
    from apps.cards.queue import deck_counts

    deck._counts = deck_counts(deck, now)
    return deck


def _deck_for(request, pk, owner_only=False):
    """Fetch a deck the user may access. owner_only=True restricts to the
    owner; otherwise the owner OR anyone it's shared with (see DeckShare) —
    mirrors apps.books.views._book_for."""
    qs = Deck.objects.filter(id=pk)
    if owner_only:
        return qs.filter(user=request.user).first()
    return qs.filter(Q(user=request.user) | Q(shares__user=request.user)).distinct().first()


class DeckListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        decks = list(Deck.objects.filter(user=request.user).select_related("parent", "config"))
        # New accounts start empty — the Menschen + Oxford starter trees are
        # seeded once the user finishes (or skips) the placement test, via
        # DeckSeedView below, rather than at signup.
        for d in decks:
            _with_counts(d, now)
        data = DeckSerializer(decks, many=True, context={"request": request}).data
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
        cdp.track(request.user, "feature_used", {"feature": "deck_create"})
        return Response(DeckSerializer(deck, context={"request": request}).data, status=status.HTTP_201_CREATED)


class DeckSeedView(APIView):
    """Provision the Menschen + Oxford starter deck trees for the requesting
    user. Idempotent (get_or_create under the hood), so it's safe to call
    both when a placement test is submitted and when it's skipped."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Imported lazily to keep decks decoupled from the cards app.
        from apps.cards.seeding import seed_for_user

        result = seed_for_user(request.user)
        return Response(result)


class DecksSharedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        decks = Deck.objects.filter(shares__user=request.user).distinct()
        return Response(DeckSerializer(decks, many=True, context={"request": request}).data)


class DeckSharesView(APIView):
    """Share/unshare a deck by email. Sharing only grants the recipient a
    one-click Import (DeckImportView) — never live access to this deck; see
    apps.decks.sharing for why."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from django.contrib.auth import get_user_model

        deck = _deck_for(request, pk, owner_only=True)
        if not deck:
            return Response(status=status.HTTP_404_NOT_FOUND)
        email = (request.data.get("email") or "").strip().lower()
        if not email:
            return Response({"detail": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)
        if email == request.user.email.lower():
            return Response({"detail": "That's you."}, status=status.HTTP_400_BAD_REQUEST)
        target = get_user_model().objects.filter(email=email).first()
        if not target:
            return Response({"detail": "No user with that email yet."}, status=status.HTTP_404_NOT_FOUND)
        DeckShare.objects.get_or_create(deck=deck, user=target)
        return Response(
            DeckSerializer(deck, context={"request": request}).data, status=status.HTTP_201_CREATED
        )

    def delete(self, request, pk):
        deck = _deck_for(request, pk, owner_only=True)
        if not deck:
            return Response(status=status.HTTP_404_NOT_FOUND)
        email = (request.data.get("email") or "").strip().lower()
        DeckShare.objects.filter(deck=deck, user__email=email).delete()
        return Response(DeckSerializer(deck, context={"request": request}).data)


class DeckImportView(APIView):
    """Copy a shared deck's whole subtree into the requesting user's own
    account (see apps.decks.sharing.copy_deck_tree)."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from .sharing import copy_deck_tree

        deck = _deck_for(request, pk)
        if not deck:
            return Response(status=status.HTTP_404_NOT_FOUND)
        imported = copy_deck_tree(deck, request.user, wrapper_name=f"Shared by {deck.user.email}")
        return Response({"deck": imported.id}, status=status.HTTP_201_CREATED)


class DeckDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, request, pk):
        return Deck.objects.filter(id=pk, user=request.user).select_related("parent", "config").first()

    def get(self, request, pk):
        deck = self._get(request, pk)
        if not deck:
            return Response(status=status.HTTP_404_NOT_FOUND)
        _with_counts(deck, timezone.now())
        return Response(DeckSerializer(deck, context={"request": request}).data)

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
        return Response(DeckSerializer(deck, context={"request": request}).data)

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


class DeckColourizeView(AiQuotaMixin, APIView):
    """Bulk-run German colouring over a deck's cards: detect & set the article
    for vocab nouns, and the per-noun genders for sentence/grammar cards.
    Processes a capped batch per call (Gemini is per-card) and reports how many
    remain, so the client can re-run until done."""

    permission_classes = [IsAuthenticated]
    BATCH = 40  # cards per Gemini call (one call per request)

    def _eligible(self, deck):
        from django.db.models import Q

        from apps.cards.models import Card

        # No language filter — the action is explicitly "Colourise German", and
        # many decks (e.g. Anki imports) store no per-card language. We colour by
        # content and stamp language='de' as we go.
        return Card.objects.filter(
            deck_id__in=deck.descendant_ids(), reverse_of__isnull=True
        ).filter(
            Q(card_type="vocab", article="none")
            | Q(card_type__in=["sentence", "grammar"], genders=[])
            | Q(card_type__in=["sentence", "grammar"], genders__isnull=True)
        )

    def post(self, request, pk):
        from apps.cards.models import sync_card_group
        from apps.imports.gemini import analyze_german_batch

        deck = Deck.objects.filter(id=pk, user=request.user).first()
        if not deck:
            return Response(status=status.HTTP_404_NOT_FOUND)

        batch = list(self._eligible(deck)[: self.BATCH])
        if not batch:
            return Response({"colourized": 0, "remaining": 0})

        # One Gemini call for the whole batch.
        items = [
            {"i": c.id, "kind": "vocab" if c.card_type == "vocab" else "phrase", "text": c.front}
            for c in batch
        ]
        try:
            results = analyze_german_batch(items)
        except Exception:  # noqa: BLE001
            results = {}

        colourized = 0
        for card in batch:
            r = results.get(card.id)
            if not r:
                continue
            fields = []
            if card.card_type == "vocab":
                gender = r.get("gender")
                if gender in {"der", "die", "das", "plural"}:
                    card.article = gender
                    fields.append("article")
            else:
                nouns = r.get("nouns") or []
                if nouns:
                    card.genders = nouns
                    fields.append("genders")
            if not fields:
                continue
            if card.language != "de":
                card.language = "de"
                fields.append("language")
            card.save(update_fields=fields)
            sync_card_group(card)
            colourized += 1

        return Response({"colourized": colourized, "remaining": self._eligible(deck).count()})


class DeckAutotypeView(APIView):
    """Auto-detect each card's format (single word / sentence / grammar) from
    its content and update it. A fast, free heuristic — no LLM, so it cannot
    tell a noun from an adjective; a part of speech already on the card is
    preserved rather than flattened back to "vocab"."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def _classify(card) -> str:
        import re

        from apps.cards.models import WORD_TYPES

        f = (card.front or "").strip()
        low = f.lower()
        # A gap/cloze marker or an attached rule table ⇒ grammar.
        if card.table or "___" in f or "…" in f or "{{c" in low or ("[" in f and "]" in f):
            return "grammar"
        words = [w for w in re.split(r"\s+", f) if w]
        # Reads like a sentence: several words, or ends with sentence punctuation.
        if len(words) >= 4 or (len(words) >= 2 and f[-1:] in ".!?"):
            return "sentence"
        return card.card_type if card.card_type in WORD_TYPES else "vocab"

    def post(self, request, pk):
        from apps.cards.models import Card, sync_card_group

        deck = Deck.objects.filter(id=pk, user=request.user).first()
        if not deck:
            return Response(status=status.HTTP_404_NOT_FOUND)

        cards = Card.objects.filter(deck_id__in=deck.descendant_ids(), reverse_of__isnull=True)
        changed = 0
        counts: dict[str, int] = {"vocab": 0, "sentence": 0, "grammar": 0}
        for card in cards:
            new_type = self._classify(card)
            counts[new_type] = counts.get(new_type, 0) + 1
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
