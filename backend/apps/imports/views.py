import random
from datetime import datetime, timedelta, timezone as dt_timezone

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.books.models import BookCard, BookLesson
from apps.cards.models import Card, CardImage
from apps.decks.models import Deck, DeckConfig
from apps.subscriptions.quota import AiQuotaMixin

from . import anki
from .gemini import (
    analyze_german,
    conjugate_verb,
    conversation_reply,
    conversation_text,
    enrich_card,
    parse_text,
    writing_check,
    writing_prompt,
    writing_topic,
)


class ParseRequestSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=20000)
    language = serializers.ChoiceField(choices=["de", "en", ""], required=False, default="")
    default_type = serializers.ChoiceField(
        choices=["vocab", "sentence", "grammar", "verb"], required=False, default="vocab"
    )


class EnrichRequestSerializer(serializers.Serializer):
    front = serializers.CharField(max_length=500)
    language = serializers.ChoiceField(choices=["de", "en", ""], required=False, default="")
    card_type = serializers.ChoiceField(
        choices=["vocab", "sentence", "grammar", "verb"], required=False, default="vocab"
    )
    # Language the translation ("back") should be written in.
    back_language = serializers.CharField(max_length=40, required=False, default="English")


class ConjugateRequestSerializer(serializers.Serializer):
    front = serializers.CharField(max_length=200)
    language = serializers.ChoiceField(choices=["de", "en", ""], required=False, default="")
    # Language the per-form meaning ("back") should be written in.
    back_language = serializers.CharField(max_length=40, required=False, default="English")


class AnalyzeGermanSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=1000)


class ImportParseView(AiQuotaMixin, APIView):
    """Parse pasted book text into draft cards (not saved). The client edits
    them, picks a deck, then commits via /api/cards/bulk/."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ParseRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = parse_text(
            serializer.validated_data["text"],
            serializer.validated_data["language"],
            serializer.validated_data["default_type"],
        )
        return Response(result, status=status.HTTP_200_OK)


class EnrichView(AiQuotaMixin, APIView):
    """Translate one term and fill its reading / article / example (the
    Translate button on the card editor)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = EnrichRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = enrich_card(
            serializer.validated_data["front"],
            serializer.validated_data["language"],
            serializer.validated_data["card_type"],
            serializer.validated_data["back_language"],
        )
        return Response(result, status=status.HTTP_200_OK)


class ConjugateView(AiQuotaMixin, APIView):
    """Conjugate a verb across the tenses a learner needs (the "Fill
    conjugations" button on a verb card)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ConjugateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = conjugate_verb(
            serializer.validated_data["front"],
            serializer.validated_data["language"],
            serializer.validated_data["back_language"],
        )
        return Response(result, status=status.HTTP_200_OK)


class AnalyzeGermanView(AiQuotaMixin, APIView):
    """Return each noun's true gender for a German sentence so it can be
    coloured grammatically (the "Colour genders" button)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AnalyzeGermanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(analyze_german(serializer.validated_data["text"]), status=status.HTTP_200_OK)


# Anki .apkg import -----------------------------------------------------------
MAX_APKG_BYTES = 60 * 1024 * 1024  # 60 MB upload ceiling


def _map_schedule(raw: dict, crt_dt: datetime, now: datetime) -> dict:
    """Translate one Anki card's scheduling onto our SM-2 fields. Anki's
    scheduler differs from ours, so review intervals are carried over verbatim
    (days) and learning cards are simply made due now."""
    q, t = raw.get("queue", 0), raw.get("type", 0)
    out = {
        "ease": raw.get("factor") or 2500,
        "reps": max(0, raw.get("reps") or 0),
        "lapses": max(0, raw.get("lapses") or 0),
        "interval_days": 0,
        "state": "new",
        "due": now,
        "step_index": 0,
        "last_reviewed_at": now if (raw.get("reps") or 0) else None,
    }
    if q == -1:
        out["state"] = "suspended"
    elif t == 2 or q == 2:  # review
        out["state"] = "review"
        out["interval_days"] = max(0, raw.get("ivl") or 0)
        try:
            out["due"] = crt_dt + timedelta(days=int(raw.get("due") or 0))
        except (TypeError, ValueError, OverflowError):
            out["due"] = now
    elif t in (1, 3) or q in (1, 3):  # (re)learning → review soon
        out["state"] = "relearning" if t == 3 else "learning"
        out["due"] = now
    return out


def _deck_resolver(user, cfg, parent):
    """Return a function mapping an Anki '::' deck name to a (cached) Deck row,
    creating the nested tree under `parent` on first use."""
    cache: dict[str, Deck] = {}

    def resolve(full_name: str) -> Deck:
        parts = [p.strip() for p in (full_name or "").split("::") if p.strip()] or ["Imported"]
        node, path = parent, ""
        for part in parts:
            path = f"{path}::{part}" if path else part
            cached = cache.get(path)
            if cached is None:
                cached, _ = Deck.objects.get_or_create(
                    user=user, parent=node, name=part[:120], defaults={"config": cfg}
                )
                cache[path] = cached
            node = cached
        return node

    return resolve


class AnkiImportView(APIView):
    """Import an uploaded Anki .apkg/.colpkg: rebuild the deck tree and create
    cards, preserving each card's study progress. Cloze notes become grammar
    cards; 'reversed' notes become two-sided vocab (forward + reverse, each
    keeping its own Anki schedule)."""

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response({"detail": "Attach an .apkg file."}, status=status.HTTP_400_BAD_REQUEST)
        if upload.size and upload.size > MAX_APKG_BYTES:
            return Response(
                {"detail": "File too large (60 MB max). Export a smaller deck."},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        parent = None
        parent_id = request.data.get("parent_deck")
        if parent_id:
            parent = Deck.objects.filter(id=parent_id, user=request.user).first()
            if not parent:
                return Response({"detail": "Invalid parent deck."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            parsed = anki.parse_apkg(upload.read())
        except anki.AnkiImportError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:  # noqa: BLE001 - corrupt/odd packages
            return Response(
                {"detail": "Couldn't read that package. Re-export it from Anki and try again."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        now = timezone.now()
        crt_dt = datetime.fromtimestamp(parsed["crt"], dt_timezone.utc) if parsed["crt"] else now
        cfg, _ = DeckConfig.objects.get_or_create(user=request.user, name="Default")
        resolve = _deck_resolver(request.user, cfg, parent)

        per_deck: dict[int, int] = {}

        def next_pos(deck: Deck) -> int:
            if deck.id not in per_deck:
                last = Card.objects.filter(deck=deck).order_by("-position").first()
                per_deck[deck.id] = (last.position + 1) if last else 0
            pos = per_deck[deck.id]
            per_deck[deck.id] = pos + 1
            return pos

        forwards: list[Card] = []
        meta: list[dict] = []  # parallel to forwards: reverse schedule if any
        decks_touched: set[int] = set()

        for note in parsed["notes"]:
            deck = resolve(note["deck"])
            decks_touched.add(deck.id)
            content = dict(
                card_type="grammar" if note["kind"] == "grammar" else "vocab",
                language=deck.language or "",
                front=note["front"],
                back=note["back"],
                tags=note["tags"],
            )
            cards = note["cards"] or [{}]
            forwards.append(
                Card(deck=deck, position=next_pos(deck), direction="forward",
                     **content, **_map_schedule(cards[0], crt_dt, now))
            )
            reverse_raw = cards[1] if (note["two_sided"] and len(cards) > 1) else None
            meta.append({"deck": deck, "content": content, "reverse_raw": reverse_raw,
                         "images": note.get("images") or []})

        Card.objects.bulk_create(forwards)

        reverses: list[Card] = []
        photos = 0
        for fwd, m in zip(forwards, meta):
            if m["reverse_raw"] is not None:
                reverses.append(
                    Card(deck=m["deck"], position=fwd.position, direction="reverse",
                         reverse_of=fwd, **m["content"], **_map_schedule(m["reverse_raw"], crt_dt, now))
                )
            for j, img in enumerate(m["images"]):
                ext = (img["name"].rsplit(".", 1)[-1] or "img")[:8]
                CardImage.objects.create(
                    card=fwd, position=j,
                    image=ContentFile(img["data"], name=f"anki{fwd.id}_{j}.{ext}"),
                )
                photos += 1
        if reverses:
            Card.objects.bulk_create(reverses)

        return Response(
            {
                "decks": len(decks_touched),
                "notes": len(forwards),
                "cards": len(forwards) + len(reverses),
                "reversed": len(reverses),
                "photos": photos,
                "truncated": parsed["truncated"],
                "img_truncated": parsed.get("img_truncated", False),
                "max_notes": anki.MAX_NOTES,
            },
            status=status.HTTP_201_CREATED,
        )


# Writing practice -----------------------------------------------------------

def _books_with_processed_lessons(user):
    """Return queryset of books (own + shared) that have at least one processed lesson."""
    from apps.books.models import Book
    from django.db.models import Q

    book_ids = (
        BookLesson.objects
        .filter(processed=True)
        .filter(Q(book__user=user) | Q(book__shares__user=user))
        .values_list("book_id", flat=True)
        .distinct()
    )
    return Book.objects.filter(id__in=book_ids).order_by("title")


def _pick_lesson_for_book(user, book_id):
    """Return {lesson, vocab} for a random processed lesson from a specific book, or None."""
    from apps.books.models import Book
    from django.db.models import Q

    # Verify the user can access this book
    accessible = (
        BookLesson.objects
        .filter(book_id=book_id, processed=True)
        .filter(Q(book__user=user) | Q(book__shares__user=user))
        .select_related("book")
        .order_by("?")
    )
    for lesson in list(accessible[:10]):
        cards = list(BookCard.objects.filter(lesson=lesson).exclude(back="")[:15])
        if len(cards) >= 3:
            random.shuffle(cards)
            vocab = [{"front": c.front, "back": c.back} for c in cards[:8]]
            return {"lesson": lesson, "vocab": vocab}
    return None


class WritingBooksView(APIView):
    """Return the list of books (own + shared) that have at least one processed lesson."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        books = _books_with_processed_lessons(request.user)
        return Response([{"id": b.id, "title": b.title} for b in books])


class WritingPromptView(AiQuotaMixin, APIView):
    """Return a short native-language passage for the user to translate into the target language."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        language = (request.data.get("language") or "").strip()
        translation_language = (request.data.get("translation_language") or "English").strip()
        source = (request.data.get("source") or "auto").strip()
        book_id = request.data.get("book_id")

        lesson_info = None
        if source == "books" and book_id:
            lesson_info = _pick_lesson_for_book(request.user, book_id)
            if lesson_info is None:
                return Response(
                    {"detail": "No processed lessons found in this book."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(writing_prompt(language, translation_language, lesson_info), status=status.HTTP_200_OK)


class WritingTopicView(AiQuotaMixin, APIView):
    """Suggest one short writing-practice topic for a chosen language."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        language = (request.data.get("language") or "").strip()
        return Response(writing_topic(language), status=status.HTTP_200_OK)


class WritingCheckView(AiQuotaMixin, APIView):
    """Correct a piece of writing; return per-issue corrections + explanations."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        text = request.data.get("text") or ""
        language = (request.data.get("language") or "").strip()
        if not text.strip():
            return Response({"detail": "Write something first."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(writing_check(text, language), status=status.HTTP_200_OK)


class WritingToCardView(APIView):
    """Turn one writing issue into a sentence card in the per-language deck
    'Writing problems (<lang>)' (created on demand)."""

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        language = (request.data.get("language") or "").strip()
        front = (request.data.get("front") or "").strip()
        if not front:
            return Response({"detail": "Nothing to add."}, status=status.HTTP_400_BAD_REQUEST)
        back = (request.data.get("back") or "").strip()
        notes = (request.data.get("notes") or "").strip()

        cfg, _ = DeckConfig.objects.get_or_create(user=request.user, name="Default")
        deck, _ = Deck.objects.get_or_create(
            user=request.user,
            parent=None,
            name=f"Writing problems ({language or '?'})",
            defaults={"config": cfg, "language": language},
        )
        last = Card.objects.filter(deck=deck).order_by("-position").first()
        card = Card.objects.create(
            deck=deck,
            card_type="sentence",
            language=language,
            front=front,
            back=back,
            notes=notes,
            position=(last.position + 1) if last else 0,
        )
        return Response(
            {"card_id": card.id, "deck_id": deck.id, "deck_name": deck.full_name},
            status=status.HTTP_201_CREATED,
        )


class ConversationMessageView(AiQuotaMixin, APIView):
    """Send a learner's spoken/typed message; get an AI reply + corrections."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        language = (request.data.get("language") or "de").strip()
        user_text = (request.data.get("text") or "").strip()
        history = request.data.get("history") or []
        if not user_text:
            return Response({"detail": "text required"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(conversation_reply(language, user_text, history), status=status.HTTP_200_OK)


class ConversationTextView(AiQuotaMixin, APIView):
    """Generate a short passage in the target language for reading-aloud practice."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        language = (request.data.get("language") or "de").strip()
        book_id = request.data.get("book_id")
        lesson_info = None
        if book_id:
            lesson_info = _pick_lesson_for_book(request.user, book_id)
        return Response(conversation_text(language, lesson_info), status=status.HTTP_200_OK)
