import datetime
import math

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import ExtractHour, TruncDate
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.decks.models import Deck
from apps.subscriptions.quota import AiQuotaMixin, consume_ai_quota

from . import scheduler
from .activity import current_streak
from .models import (
    Card,
    CardImage,
    CardState,
    ReviewLog,
    add_reverse_cards,
    sync_card_group,
)
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


class CardMnemonicView(APIView):
    """Generate (once) and cache an AI memory aid for a card, stored on the
    note's primary card so both directions share it. Deliberately does NOT
    mix in AiQuotaMixin (which would meter every request in `initial()`,
    before we know whether this is a cache hit) — quota is only consumed in
    the branch that actually calls Gemini, so repeat clicks on an
    already-generated card are free."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from apps.imports.gemini import mnemonic_for

        card = (
            Card.objects.filter(id=pk, deck__user=request.user)
            .select_related("reverse_of")
            .first()
        )
        if not card:
            return Response(status=status.HTTP_404_NOT_FOUND)
        primary = card.reverse_of or card
        if not primary.mnemonic:
            consume_ai_quota(request.user)
            text = mnemonic_for(primary.front, primary.back, primary.language, primary.card_type)
            if text:
                primary.mnemonic = text
                primary.save(update_fields=["mnemonic"])
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
        streak = current_streak(active, today)

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


# Card states that still get scheduled (i.e. can come due).
SCHEDULED_STATES = [CardState.LEARNING, CardState.REVIEW, CardState.RELEARNING]

# "Mature" threshold, matching Anki: a review card with a >= 21 day interval.
MATURE_DAYS = 21

# Interval histogram buckets as (label, lower, upper) in days; upper None = open.
INTERVAL_BUCKETS = [
    ("1d", 0, 1),
    ("2-3d", 2, 3),
    ("4-7d", 4, 7),
    ("1-2w", 8, 14),
    ("2-4w", 15, 30),
    ("1-3m", 31, 90),
    ("3-6m", 91, 180),
    ("6-12m", 181, 365),
    ("1y+", 366, None),
]


class StatsOverviewView(APIView):
    """Everything the performance page shows, in one call.

    Two kinds of numbers live here and they answer different questions, so they
    are namespaced apart rather than merged:

    * `range` — derived from ReviewLog over the last `days` days: what you *did*.
    * `collection` / `forecast` — derived from the cards' current scheduling
      state: where you *are* and what's coming.

    "Retention" is Anki's true retention: of the answers given on cards that
    were already in the `review` state, the share not rated Again. Hard counts as
    a pass — the card *was* recalled, just with effort. Answers on new/learning
    cards are excluded entirely: failing a card you are still learning is the
    system working, not a memory lapse.
    """

    permission_classes = [IsAuthenticated]
    FORECAST_DAYS = 30
    ALLOWED_DAYS = (7, 30, 90, 365)
    TOP_LEECHES = 8

    def get(self, request):
        try:
            days = int(request.query_params.get("days", 30))
        except (TypeError, ValueError):
            days = 30
        if days not in self.ALLOWED_DAYS:
            days = 30

        user = request.user
        now = timezone.now()
        today = timezone.localdate()
        start = today - datetime.timedelta(days=days - 1)

        logs = ReviewLog.objects.filter(user=user, reviewed_at__date__gte=start)

        return Response(
            {
                "range_days": days,
                "range": {
                    **self._range_totals(logs),
                    "days": self._daily_series(logs, start, days),
                    "hours": self._hourly_series(logs),
                },
                "collection": self._collection(user, now),
                "forecast": self._forecast(user, today),
                "intervals": self._intervals(user),
                "decks": self._decks(user, now, start),
                "leeches": self._leeches(user),
            }
        )

    # ---- Review log (what you did) ----

    def _range_totals(self, logs) -> dict:
        agg = logs.aggregate(
            reviews=Count("id"),
            ms=Sum("time_ms"),
            mature=Count("id", filter=Q(state_before=CardState.REVIEW)),
            mature_pass=Count("id", filter=Q(state_before=CardState.REVIEW, rating__gt=1)),
            again=Count("id", filter=Q(rating=1)),
            hard=Count("id", filter=Q(rating=2)),
            good=Count("id", filter=Q(rating=3)),
            easy=Count("id", filter=Q(rating=4)),
        )
        reviews = agg["reviews"]
        mature = agg["mature"]
        active_days = (
            logs.annotate(d=TruncDate("reviewed_at")).values("d").distinct().count()
        )
        return {
            "reviews": reviews,
            "seconds": round((agg["ms"] or 0) / 1000),
            "active_days": active_days,
            # Per *active* day — averaging over calendar days punishes people for
            # picking a long range and makes the number meaningless.
            "avg_per_active_day": round(reviews / active_days, 1) if active_days else 0,
            "avg_seconds_per_card": round((agg["ms"] or 0) / 1000 / reviews, 1) if reviews else 0,
            "retention": round(agg["mature_pass"] / mature, 4) if mature else None,
            "mature_answers": mature,
            "ratings": {
                "again": agg["again"],
                "hard": agg["hard"],
                "good": agg["good"],
                "easy": agg["easy"],
            },
        }

    def _daily_series(self, logs, start, days) -> list[dict]:
        """Reviews per day, split by how far along the card was — the three
        buckets are a maturity progression, so the UI ramps one hue over them."""
        rows = (
            logs.annotate(d=TruncDate("reviewed_at"))
            .values("d")
            .annotate(
                count=Count("id"),
                ms=Sum("time_ms"),
                new=Count("id", filter=Q(state_before=CardState.NEW)),
                learning=Count(
                    "id",
                    filter=Q(state_before__in=[CardState.LEARNING, CardState.RELEARNING]),
                ),
                review=Count("id", filter=Q(state_before=CardState.REVIEW)),
            )
        )
        by_date = {r["d"]: r for r in rows}
        out = []
        for i in range(days):
            day = start + datetime.timedelta(days=i)
            r = by_date.get(day)
            out.append(
                {
                    "date": day.isoformat(),
                    "count": r["count"] if r else 0,
                    "seconds": round((r["ms"] or 0) / 1000) if r else 0,
                    "new": r["new"] if r else 0,
                    "learning": r["learning"] if r else 0,
                    "review": r["review"] if r else 0,
                }
            )
        return out

    def _hourly_series(self, logs) -> list[dict]:
        """Reviews (and retention) by hour of day — answers "when do I study
        well?", which is actionable in a way a raw count is not."""
        rows = (
            logs.annotate(h=ExtractHour("reviewed_at"))
            .values("h")
            .annotate(
                count=Count("id"),
                mature=Count("id", filter=Q(state_before=CardState.REVIEW)),
                mature_pass=Count("id", filter=Q(state_before=CardState.REVIEW, rating__gt=1)),
            )
        )
        by_hour = {r["h"]: r for r in rows}
        out = []
        for h in range(24):
            r = by_hour.get(h)
            mature = r["mature"] if r else 0
            out.append(
                {
                    "hour": h,
                    "count": r["count"] if r else 0,
                    "retention": round(r["mature_pass"] / mature, 4) if mature else None,
                }
            )
        return out

    # ---- Scheduling state (where you are) ----

    def _collection(self, user, now) -> dict:
        cards = Card.objects.filter(deck__user=user)
        agg = cards.aggregate(
            total=Count("id"),
            new=Count("id", filter=Q(state=CardState.NEW)),
            learning=Count(
                "id", filter=Q(state__in=[CardState.LEARNING, CardState.RELEARNING])
            ),
            young=Count(
                "id", filter=Q(state=CardState.REVIEW, interval_days__lt=MATURE_DAYS)
            ),
            mature=Count(
                "id", filter=Q(state=CardState.REVIEW, interval_days__gte=MATURE_DAYS)
            ),
            suspended=Count("id", filter=Q(state=CardState.SUSPENDED)),
            due_now=Count("id", filter=Q(state__in=SCHEDULED_STATES, due__lte=now)),
            leeches=Count("id", filter=Q(is_leech=True)),
            avg_ease=Avg("ease", filter=Q(state=CardState.REVIEW)),
            avg_interval=Avg("interval_days", filter=Q(state=CardState.REVIEW)),
        )
        return {
            **{k: v for k, v in agg.items() if k not in ("avg_ease", "avg_interval")},
            "avg_ease": round(agg["avg_ease"]) if agg["avg_ease"] else None,
            "avg_interval": round(agg["avg_interval"], 1) if agg["avg_interval"] else None,
        }

    def _forecast(self, user, today) -> list[dict]:
        """Cards coming due over the next 30 days. Anything already overdue is
        folded into day 0 — it is work waiting today, not history."""
        end = today + datetime.timedelta(days=self.FORECAST_DAYS - 1)
        rows = (
            Card.objects.filter(
                deck__user=user, state__in=SCHEDULED_STATES, due__date__lte=end
            )
            .annotate(d=TruncDate("due"))
            .values("d")
            .annotate(count=Count("id"))
        )
        by_date = {r["d"]: r["count"] for r in rows}
        backlog = sum(c for d, c in by_date.items() if d < today)

        out, running = [], 0
        for i in range(self.FORECAST_DAYS):
            day = today + datetime.timedelta(days=i)
            count = by_date.get(day, 0) + (backlog if i == 0 else 0)
            running += count
            out.append({"date": day.isoformat(), "count": count, "cumulative": running})
        return out

    def _intervals(self, user) -> list[dict]:
        rows = Card.objects.filter(
            deck__user=user, state=CardState.REVIEW
        ).values_list("interval_days", flat=True)
        counts = [0] * len(INTERVAL_BUCKETS)
        for iv in rows:
            for i, (_, lo, hi) in enumerate(INTERVAL_BUCKETS):
                if iv >= lo and (hi is None or iv <= hi):
                    counts[i] += 1
                    break
        return [
            {"label": label, "count": c}
            for (label, _, _), c in zip(INTERVAL_BUCKETS, counts)
        ]

    def _decks(self, user, now, start) -> list[dict]:
        """Per-deck rows. Counts are the deck's *own* cards (not its subtree) so
        the column sums to the collection total instead of double-counting."""
        card_rows = (
            Card.objects.filter(deck__user=user)
            .values("deck_id")
            .annotate(
                cards=Count("id"),
                due=Count("id", filter=Q(state__in=SCHEDULED_STATES, due__lte=now)),
                new=Count("id", filter=Q(state=CardState.NEW)),
                mature=Count(
                    "id", filter=Q(state=CardState.REVIEW, interval_days__gte=MATURE_DAYS)
                ),
            )
        )
        log_rows = (
            ReviewLog.objects.filter(user=user, reviewed_at__date__gte=start)
            .values("card__deck_id")
            .annotate(
                reviews=Count("id"),
                ms=Sum("time_ms"),
                mature=Count("id", filter=Q(state_before=CardState.REVIEW)),
                mature_pass=Count("id", filter=Q(state_before=CardState.REVIEW, rating__gt=1)),
            )
        )
        by_deck_logs = {r["card__deck_id"]: r for r in log_rows}
        names = {d.id: d for d in Deck.objects.filter(user=user).select_related("parent")}

        out = []
        for row in card_rows:
            deck = names.get(row["deck_id"])
            if deck is None:
                continue
            log = by_deck_logs.get(row["deck_id"])
            mature = log["mature"] if log else 0
            out.append(
                {
                    "id": deck.id,
                    "name": deck.name,
                    "full_name": deck.full_name,
                    "language": deck.language,
                    "cards": row["cards"],
                    "new": row["new"],
                    "mature": row["mature"],
                    "due": row["due"],
                    "reviews": log["reviews"] if log else 0,
                    "seconds": round((log["ms"] or 0) / 1000) if log else 0,
                    "retention": round(log["mature_pass"] / mature, 4) if mature else None,
                }
            )
        out.sort(key=lambda r: (-r["reviews"], -r["cards"], r["full_name"]))
        return out

    def _leeches(self, user) -> list[dict]:
        """The cards fighting back hardest — highest lapse count first. Only the
        primary direction is listed so a note doesn't appear twice."""
        cards = (
            Card.objects.filter(deck__user=user, lapses__gt=0, reverse_of__isnull=True)
            .select_related("deck")
            .order_by("-lapses", "id")[: self.TOP_LEECHES]
        )
        return [
            {
                "id": c.id,
                "front": c.front[:80],
                "back": c.back[:80],
                "deck": c.deck.name,
                "lapses": c.lapses,
                "state": c.state,
                "interval_days": c.interval_days,
                "is_leech": c.is_leech,
            }
            for c in cards
        ]


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
