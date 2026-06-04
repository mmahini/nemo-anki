import hashlib

from django.db import transaction
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cards.models import Card
from apps.decks.models import Deck, DeckConfig

from . import processing
from .models import BANNER_COLORS, Book, BookCard, BookLesson
from .serializers import BookLessonSerializer, BookSerializer


def _color_for(title: str) -> str:
    h = int(hashlib.md5(title.encode("utf-8")).hexdigest(), 16)
    return BANNER_COLORS[h % len(BANNER_COLORS)]


class BookUploadSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=160)
    source_language = serializers.ChoiceField(choices=["de", "en", ""], required=False, default="")
    translation_language = serializers.CharField(max_length=40, required=False, default="English")
    text = serializers.CharField(required=False, allow_blank=True, default="")
    file = serializers.FileField(required=False)
    # Optional, for precise segmentation of messy/large books: the lesson label
    # ("Unit", "Lesson", "Lektion"…) and the number range (from..to).
    lesson_label = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    from_lesson = serializers.IntegerField(required=False, allow_null=True, default=None)
    to_lesson = serializers.IntegerField(required=False, allow_null=True, default=None)
    # Page-based split (most reliable for messy PDFs).
    pages_per_unit = serializers.IntegerField(required=False, allow_null=True, default=None)
    start_page = serializers.IntegerField(required=False, allow_null=True, default=None)


class BookListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        books = Book.objects.filter(user=request.user).prefetch_related("lessons")
        return Response(BookSerializer(books, many=True).data)

    @transaction.atomic
    def post(self, request):
        serializer = BookUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        file = d.get("file")
        label = d.get("lesson_label") or ""
        from_n, to_n = d.get("from_lesson"), d.get("to_lesson")
        ppu = d.get("pages_per_unit")
        start_page = d.get("start_page") or 1

        if ppu and from_n is not None and to_n is not None and file is not None:
            # Page-based split (most reliable for messy PDFs).
            pages = processing.read_pdf_pages(file)
            if not pages:
                return Response(
                    {"detail": "Couldn't read pages from the PDF."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            lessons = processing.segment_by_pages(
                pages, label or "Unit", int(from_n), int(to_n), int(start_page), int(ppu)
            )
        else:
            text = processing.read_upload(file, d.get("text", ""))
            if not text.strip():
                return Response(
                    {"detail": "Couldn't read any text from the upload."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if label and from_n is not None and to_n is not None:
                lessons = processing.segment_by_range(text, label, int(from_n), int(to_n))
            else:
                lessons = processing.segment_lessons(text)

        capped = len(lessons) > processing.MAX_LESSONS
        lessons = lessons[: processing.MAX_LESSONS]

        book = Book.objects.create(
            user=request.user,
            title=d["title"],
            source_language=d["source_language"],
            translation_language=d["translation_language"],
            status="ready",
            color=_color_for(d["title"]),
            note=(f"Only the first {processing.MAX_LESSONS} lessons were kept." if capped else ""),
        )
        # Upload only segments into lessons (fast). Vocab is extracted per
        # lesson via the Process button so we never block on the whole book.
        BookLesson.objects.bulk_create(
            [
                BookLesson(book=book, title=l["title"], position=i, raw_text=l["raw_text"])
                for i, l in enumerate(lessons)
            ]
        )
        return Response(BookSerializer(book).data, status=status.HTTP_201_CREATED)


class BookLessonProcessView(APIView):
    """Extract (or re-extract) one lesson's vocabulary with the LLM."""

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk, lid):
        book = Book.objects.filter(id=pk, user=request.user).first()
        lesson = BookLesson.objects.filter(id=lid, book=book).first() if book else None
        if not lesson:
            return Response(status=status.HTTP_404_NOT_FOUND)
        try:
            items = processing.extract_vocab(
                lesson.raw_text, book.source_language, book.translation_language
            )
        except Exception as exc:  # noqa: BLE001
            return Response(
                {"detail": f"Processing failed ({exc.__class__.__name__})."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        lesson.cards.all().delete()
        BookCard.objects.bulk_create(
            [BookCard(lesson=lesson, position=j, **it) for j, it in enumerate(items)]
        )
        lesson.processed = True
        lesson.save(update_fields=["processed"])
        return Response(BookLessonSerializer(lesson).data, status=status.HTTP_200_OK)


class BookDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        book = Book.objects.filter(id=pk, user=request.user).first()
        if not book:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(BookSerializer(book).data)

    def delete(self, request, pk):
        book = Book.objects.filter(id=pk, user=request.user).first()
        if not book:
            return Response(status=status.HTTP_204_NO_CONTENT)
        book.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _default_config(user) -> DeckConfig:
    cfg, _ = DeckConfig.objects.get_or_create(user=user, name="Default")
    return cfg


def _next_position(deck: Deck) -> int:
    last = Card.objects.filter(deck=deck).order_by("-position").first()
    return (last.position + 1) if last else 0


CONTENT_FIELDS = [
    "card_type", "front", "back", "reading", "article",
    "plural", "example", "notes", "table", "genders", "tags",
]


class BookLessonImportView(APIView):
    """Import one lesson into the user's decks. Creates (or reuses) a deck for
    the book under `parent_deck`, then a sub-deck for the lesson, and copies the
    lesson's vocab into it."""

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk, lid):
        book = Book.objects.filter(id=pk, user=request.user).first()
        lesson = BookLesson.objects.filter(id=lid, book=book).first() if book else None
        if not lesson:
            return Response(status=status.HTTP_404_NOT_FOUND)

        parent_id = request.data.get("parent_deck")
        parent = None
        if parent_id:
            parent = Deck.objects.filter(id=parent_id, user=request.user).first()
            if not parent:
                return Response({"detail": "Invalid parent deck."}, status=status.HTTP_400_BAD_REQUEST)

        cfg = _default_config(request.user)
        book_deck, _ = Deck.objects.get_or_create(
            user=request.user, parent=parent, name=book.title,
            defaults={"config": cfg, "language": book.source_language},
        )
        lesson_deck, _ = Deck.objects.get_or_create(
            user=request.user, parent=book_deck, name=lesson.title,
            defaults={"config": cfg, "language": book.source_language},
        )

        pos = _next_position(lesson_deck)
        cards = [
            Card(
                deck=lesson_deck,
                language=book.source_language,
                position=pos + i,
                **{f: getattr(bc, f) for f in CONTENT_FIELDS},
            )
            for i, bc in enumerate(lesson.cards.all())
        ]
        Card.objects.bulk_create(cards)
        return Response(
            {"book_deck": book_deck.id, "lesson_deck": lesson_deck.id, "cards": len(cards)},
            status=status.HTTP_201_CREATED,
        )
