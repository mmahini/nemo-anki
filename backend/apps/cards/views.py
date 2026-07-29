import datetime
import math

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.decks.models import Deck
from apps.subscriptions.quota import AiQuotaMixin

from . import scheduler
from .models import Card, CardImage, ReviewLog, add_reverse_cards, sync_card_group
from .queue import study_queue
from .serializers import AnswerSerializer, BulkCardSerializer, CardSerializer


DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


def _empty_page(page_size: int) -> dict:
    return {"results": [], "count": 0, "page": 1, "page_size": page_size, "num_pages": 1}


class CardListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Management list shows one row per note (the forward/primary card);
        # the reverse companion is hidden here but still studied & edited in sync.
        # Paginated + searchable so heavy decks stay fast. prefetch avoids an
        # N+1 on images / reverse lookups when serializing the page.
        qs = (
            Card.objects.filter(deck__user=request.user, reverse_of__isnull=True)
            .select_related("deck")
            .prefetch_related("images", "reverses")
        )

        page_size = self._int_param(request, "page_size", DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE)

        deck_id = request.query_params.get("deck")
        if deck_id:
            deck = Deck.objects.filter(id=deck_id, user=request.user).first()
            if not deck:
                return Response(_empty_page(page_size), status=status.HTTP_200_OK)
            qs = qs.filter(deck_id__in=deck.descendant_ids())

        card_type = request.query_params.get("type")
        if card_type:
            qs = qs.filter(card_type=card_type)

        search = (request.query_params.get("q") or "").strip()
        if search:
            qs = qs.filter(
                Q(front__icontains=search)
                | Q(back__icontains=search)
                | Q(reading__icontains=search)
            )

        count = qs.count()
        num_pages = max(1, math.ceil(count / page_size))
        page = self._int_param(request, "page", 1, 1, num_pages)
        offset = (page - 1) * page_size
        rows = qs[offset : offset + page_size]

        return Response(
            {
                "results": CardSerializer(rows, many=True).data,
                "count": count,
                "page": page,
                "page_size": page_size,
                "num_pages": num_pages,
            }
        )

    @staticmethod
    def _int_param(request, name: str, default: int, lo: int, hi: int) -> int:
        try:
            val = int(request.query_params.get(name, default))
        except (TypeError, ValueError):
            val = default
        return max(lo, min(hi, val))

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


class CardColourizeView(AiQuotaMixin, APIView):
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

    @staticmethod
    def _looks_latin(s: str) -> bool:
        letters = [c for c in s if c.isalpha()]
        return bool(letters) and sum(1 for c in letters if ord(c) < 0x250) >= 0.6 * len(letters)

    def _english_term(self, primary) -> str:
        """A good English search term: the meaning if it's Latin-script, else a
        translation of the word (the stored meaning may be Persian/etc.)."""
        back = (primary.back or "").strip()
        if back and self._looks_latin(back):
            return back
        front = (primary.front or "").strip()
        lang = primary.language or (primary.deck.language if primary.deck_id else "")
        if front and lang and lang != "en":
            try:
                from apps.imports.gemini import enrich_card

                tr = (enrich_card(front, lang, "vocab", "English") or {}).get("back", "").strip()
                if tr:
                    return tr
            except Exception:  # noqa: BLE001 - fall back to the raw term
                pass
        return front or back

    def post(self, request, pk):
        from .image_search import find_thumbnail

        card = (
            Card.objects.filter(id=pk, deck__user=request.user)
            .select_related("reverse_of", "deck")
            .first()
        )
        if not card:
            return Response(status=status.HTTP_404_NOT_FOUND)
        primary = card.reverse_of or card
        data = find_thumbnail(self._english_term(primary))
        if not data:
            return Response(
                {"detail": "Couldn't find an image for this card."},
                status=status.HTTP_404_NOT_FOUND,
            )
        # Regenerate: drop the previous auto-found image (keep manual uploads).
        primary.images.filter(auto=True).delete()
        last = primary.images.order_by("-position").first()
        pos = (last.position + 1) if last else 0
        img = CardImage.objects.create(
            card=primary,
            image=ContentFile(data, name=f"auto_{primary.id}_{pos}.jpg"),
            position=pos,
            auto=True,
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


class ReviewActivityView(APIView):
    """Per-day review activity for the motivational panel: counts + time spent
    over a trailing window, plus current/longest streaks."""

    permission_classes = [IsAuthenticated]
    DAYS = 119  # ~17 weeks of heatmap

    def get(self, request):
        today = timezone.localdate()
        start = today - datetime.timedelta(days=self.DAYS)
        rows = (
            ReviewLog.objects.filter(user=request.user, reviewed_at__date__gte=start)
            .annotate(d=TruncDate("reviewed_at"))
            .values("d")
            .annotate(count=Count("id"), ms=Sum("time_ms"))
        )
        by_date = {r["d"]: (r["count"], r["ms"] or 0) for r in rows}

        days = []
        for i in range(self.DAYS + 1):
            day = start + datetime.timedelta(days=i)
            c, ms = by_date.get(day, (0, 0))
            days.append({"date": day.isoformat(), "count": c, "seconds": round(ms / 1000)})

        active = {d for d, (c, _) in by_date.items() if c > 0}

        def run_back(anchor):
            s, cur = 0, anchor
            while cur in active:
                s += 1
                cur -= datetime.timedelta(days=1)
            return s

        # Today counts toward the streak once done; before that, yesterday's run still stands.
        streak = run_back(today) if today in active else run_back(today - datetime.timedelta(days=1))

        longest = 0
        if active:
            ordered = sorted(active)
            run = 1
            longest = 1
            for a, b in zip(ordered, ordered[1:]):
                run = run + 1 if (b - a).days == 1 else 1
                longest = max(longest, run)

        tc, tms = by_date.get(today, (0, 0))
        return Response(
            {
                "days": days,
                "streak": streak,
                "longest_streak": longest,
                "active_days": len(active),
                "today": {"count": tc, "seconds": round(tms / 1000)},
                "total_reviews": ReviewLog.objects.filter(user=request.user).count(),
            }
        )


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
