from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.decks.models import Deck

from . import scheduler
from .models import Card, CardImage, ReviewLog, add_reverse_cards, sync_card_group
from .queue import study_queue
from .serializers import AnswerSerializer, BulkCardSerializer, CardSerializer


class CardListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Management list shows one row per note (the forward/primary card);
        # the reverse companion is hidden here but still studied & edited in sync.
        qs = Card.objects.filter(
            deck__user=request.user, reverse_of__isnull=True
        ).select_related("deck")
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

    @transaction.atomic
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
        add_reverse_cards([card])  # vocab → also create the reverse direction
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

    @transaction.atomic
    def patch(self, request, pk):
        card = self._get(request, pk)
        if not card:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = CardSerializer(card, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        sync_card_group(card)  # mirror content/deck onto the other direction
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
        add_reverse_cards(created)  # vocab cards get their reverse direction
        return Response(
            {"created": len(created), "deck": deck.id},
            status=status.HTTP_201_CREATED,
        )


MAX_IMAGE_BYTES = 8 * 1024 * 1024
_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp", "image/svg+xml"}


class CardImageView(APIView):
    """Attach a photo to a card (stored on the primary/forward card so both
    review directions share it)."""

    permission_classes = [IsAuthenticated]

    def _primary(self, request, pk):
        card = (
            Card.objects.filter(id=pk, deck__user=request.user)
            .select_related("reverse_of")
            .first()
        )
        if not card:
            return None
        return card.reverse_of or card

    @transaction.atomic
    def post(self, request, pk):
        card = self._primary(request, pk)
        if not card:
            return Response(status=status.HTTP_404_NOT_FOUND)
        upload = request.FILES.get("image")
        if not upload:
            return Response({"detail": "Attach an image."}, status=status.HTTP_400_BAD_REQUEST)
        if upload.size and upload.size > MAX_IMAGE_BYTES:
            return Response({"detail": "Image too large (8 MB max)."}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        if upload.content_type and upload.content_type not in _IMAGE_TYPES:
            return Response({"detail": "Unsupported image type."}, status=status.HTTP_400_BAD_REQUEST)
        if upload.content_type != "image/svg+xml":  # SVGs aren't raster — skip Pillow
            from PIL import Image

            try:
                Image.open(upload).verify()
            except Exception:  # noqa: BLE001
                return Response({"detail": "That file isn't a valid image."}, status=status.HTTP_400_BAD_REQUEST)
            upload.seek(0)
        last = card.images.order_by("-position").first()
        img = CardImage.objects.create(
            card=card, image=upload, position=(last.position + 1) if last else 0
        )
        return Response({"id": img.id, "url": img.image.url}, status=status.HTTP_201_CREATED)


class CardImageDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk, img_id):
        card = (
            Card.objects.filter(id=pk, deck__user=request.user)
            .select_related("reverse_of")
            .first()
        )
        primary = (card.reverse_of or card) if card else None
        if primary:
            CardImage.objects.filter(id=img_id, card=primary).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CardColourizeView(APIView):
    """Colour one card: detect the German article (vocab) or per-noun genders
    (sentence/grammar) and save them. Targets the note's primary card so both
    directions stay in sync."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from apps.imports.gemini import analyze_german

        card = (
            Card.objects.filter(id=pk, deck__user=request.user)
            .select_related("reverse_of")
            .first()
        )
        if not card:
            return Response(status=status.HTTP_404_NOT_FOUND)
        primary = card.reverse_of or card
        nouns = (analyze_german(primary.front) or {}).get("nouns") or []

        fields = []
        if primary.card_type == "vocab":
            if nouns:
                primary.article = nouns[0]["gender"]
                fields.append("article")
        elif nouns:
            primary.genders = nouns
            fields.append("genders")

        if fields:
            if primary.language != "de":
                primary.language = "de"
                fields.append("language")
            primary.save(update_fields=fields)
            sync_card_group(primary)

        card.refresh_from_db()
        return Response(CardSerializer(card).data)


class CardFindImageView(APIView):
    """Auto-find a small image for a card and attach it (stored on the primary
    card). Best for concrete vocab; uses the English meaning when available."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from .image_search import find_thumbnail

        card = (
            Card.objects.filter(id=pk, deck__user=request.user)
            .select_related("reverse_of")
            .first()
        )
        if not card:
            return Response(status=status.HTTP_404_NOT_FOUND)
        primary = card.reverse_of or card
        # Image search hits best on the English meaning; fall back to the term.
        term = (primary.back or primary.front or "").strip()
        data = find_thumbnail(term)
        if not data:
            return Response(
                {"detail": "Couldn't find an image for this card."},
                status=status.HTTP_404_NOT_FOUND,
            )
        last = primary.images.order_by("-position").first()
        pos = (last.position + 1) if last else 0
        img = CardImage.objects.create(
            card=primary, image=ContentFile(data, name=f"auto_{primary.id}_{pos}.jpg"), position=pos
        )
        return Response({"id": img.id, "url": img.image.url}, status=status.HTTP_201_CREATED)


class CardReviewView(APIView):
    """Return one card (with grade-interval previews) so it can be studied on
    its own from the card list."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        card = (
            Card.objects.filter(id=pk, deck__user=request.user)
            .select_related("deck", "deck__config")
            .first()
        )
        if not card:
            return Response(status=status.HTTP_404_NOT_FOUND)
        card._intervals = scheduler.preview_intervals(card, card.deck.config, timezone.now())
        return Response(CardSerializer(card).data)


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
