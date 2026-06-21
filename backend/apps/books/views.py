import hashlib
import json
import re

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cards.models import Card, add_reverse_cards
from apps.decks.models import Deck, DeckConfig

from . import processing
from .models import BANNER_COLORS, Book, BookCard, BookLesson, BookShare
from .serializers import BookLessonDetailSerializer, BookLessonSerializer, BookSerializer


def _color_for(title: str) -> str:
    h = int(hashlib.md5(title.encode("utf-8")).hexdigest(), 16)
    return BANNER_COLORS[h % len(BANNER_COLORS)]


def _title_num(title: str):
    """Parse the unit number out of a lesson title ("Unit 37" -> 37)."""
    m = re.search(r"(\d+)", title or "")
    return int(m.group(1)) if m else None


def _book_for(request, pk, owner_only=False):
    """Fetch a book the user may access. owner_only=True restricts to the owner;
    otherwise the owner OR anyone it's shared with."""
    qs = Book.objects.filter(id=pk)
    if owner_only:
        return qs.filter(user=request.user).first()
    return qs.filter(Q(user=request.user) | Q(shares__user=request.user)).distinct().first()


def _book_data(book, request):
    return BookSerializer(book, context={"request": request}).data


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
    # An approved unit->start-page map (JSON list of {num, start_page}) from the
    # preview step. Takes precedence over the other modes when present.
    page_map = serializers.CharField(required=False, allow_blank=True, default="")


class RegenerateSerializer(serializers.Serializer):
    from_lesson = serializers.IntegerField()
    to_lesson = serializers.IntegerField()
    pages_per_unit = serializers.IntegerField(required=False, allow_null=True, default=None)
    start_page = serializers.IntegerField(required=False, allow_null=True, default=None)
    lesson_label = serializers.CharField(max_length=40, required=False, allow_blank=True, default="Unit")
    # Whole-book split: drop ALL existing lessons first (so the book can be
    # re-split into smaller chunks). Default keeps the per-lesson behaviour of
    # replacing only the units in [from..to].
    replace_all = serializers.BooleanField(required=False, default=False)


class BookAnalyzeSerializer(serializers.Serializer):
    file = serializers.FileField()
    lesson_label = serializers.CharField(max_length=40, required=False, allow_blank=True, default="Unit")
    from_lesson = serializers.IntegerField()
    to_lesson = serializers.IntegerField()
    pages_per_unit = serializers.IntegerField(required=False, allow_null=True, default=None)


class BookAnalyzeView(APIView):
    """Per-page heading scan for a PDF — returns an editable unit->page map so
    the user can review/approve page ranges before the book is created. Saves
    nothing."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = BookAnalyzeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        pages = processing.read_pdf_pages(d["file"].read())
        if not pages:
            return Response({"detail": "Couldn't read pages from the PDF."}, status=status.HTTP_400_BAD_REQUEST)
        label = d.get("lesson_label") or "Unit"
        from_n, to_n = int(d["from_lesson"]), int(d["to_lesson"])
        detected = processing.detect_unit_pages(pages, label, from_n, to_n)
        units = processing.build_page_map(
            detected, from_n, to_n, len(pages), int(d.get("pages_per_unit") or 2)
        )
        return Response(
            {"page_count": len(pages), "detected_count": len(detected), "units": units},
            status=status.HTTP_200_OK,
        )


class BookListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        books = Book.objects.filter(user=request.user).prefetch_related("lessons")
        return Response(BookSerializer(books, many=True, context={"request": request}).data)

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

        # Read the upload once. Detect PDF by filename/magic (no full parse —
        # that doubled memory and OOM'd small instances).
        data = file.read() if file else b""
        fname = getattr(file, "name", "") or ""
        is_pdf = bool(data) and (fname.lower().endswith(".pdf") or data[:5] == b"%PDF-")
        has_range = from_n is not None and to_n is not None
        page_map_raw = (d.get("page_map") or "").strip()

        # Splitting a PDF into lessons is now a separate step (on the book page),
        # so a plain PDF upload just stores the book + its source PDF with no
        # lessons yet. Splitting params are still honoured if supplied (legacy /
        # one-shot uploads). Text/.txt has no stored PDF to re-split later, so it
        # is still segmented by headings here.
        capped = False
        lessons = None  # None → don't touch lessons (PDF, split deferred)
        if is_pdf and (page_map_raw or has_range):
            page_map = None
            if page_map_raw:
                try:
                    page_map = json.loads(page_map_raw)
                except json.JSONDecodeError:
                    return Response({"detail": "Invalid page map."}, status=status.HTTP_400_BAD_REQUEST)
            elif (int(to_n) - int(from_n) + 1) > processing.MAX_LESSONS:
                capped = True
            # `lessons` is a generator — streamed/saved one at a time below.
            lessons = processing.segment_pdf(
                data, label or "Unit",
                int(from_n) if from_n is not None else 1,
                int(to_n) if to_n is not None else 1,
                int(start_page), ppu, page_map,
            )
        elif not is_pdf:
            text = processing.bytes_to_text(data, fname) or d.get("text", "")
            if not text.strip():
                return Response(
                    {"detail": "Couldn't read any text from the upload."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            built = (
                processing.segment_by_range(text, label, int(from_n), int(to_n))
                if label and has_range else processing.segment_lessons(text)
            )
            capped = len(built) > processing.MAX_LESSONS
            lessons = built[: processing.MAX_LESSONS]

        book = Book.objects.create(
            user=request.user,
            title=d["title"],
            source_language=d["source_language"],
            translation_language=d["translation_language"],
            status="ready",
            color=_color_for(d["title"]),
            note=(f"Only the first {processing.MAX_LESSONS} lessons were kept." if capped else ""),
        )
        # Keep the original PDF so it can be split (and re-split) later.
        if is_pdf and data:
            book.pdf.save(f"book{book.id}_src.pdf", ContentFile(data), save=True)
        del data  # free the source bytes before streaming sub-PDFs
        if lessons is not None:
            _create_lessons(book, lessons)
        return Response(_book_data(book, request), status=status.HTTP_201_CREATED)


class BooksSharedView(APIView):
    """Books other users have shared with me."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        books = Book.objects.filter(shares__user=request.user).distinct().prefetch_related("lessons")
        return Response(BookSerializer(books, many=True, context={"request": request}).data)


class BookSharesView(APIView):
    """Owner: list / add the users a book is shared with."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        book = _book_for(request, pk, owner_only=True)
        if not book:
            return Response(status=status.HTTP_404_NOT_FOUND)
        email = (request.data.get("email") or "").strip().lower()
        if not email:
            return Response({"detail": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)
        if email == request.user.email.lower():
            return Response({"detail": "That's you."}, status=status.HTTP_400_BAD_REQUEST)
        from apps.accounts.models import User

        target = User.objects.filter(email=email).first()
        if not target:
            return Response({"detail": "No user with that email yet."}, status=status.HTTP_404_NOT_FOUND)
        BookShare.objects.get_or_create(book=book, user=target)
        return Response(_book_data(book, request), status=status.HTTP_201_CREATED)

    def delete(self, request, pk):
        book = _book_for(request, pk, owner_only=True)
        if not book:
            return Response(status=status.HTTP_404_NOT_FOUND)
        email = (request.data.get("email") or "").strip().lower()
        BookShare.objects.filter(book=book, user__email=email).delete()
        return Response(_book_data(book, request), status=status.HTTP_200_OK)


def _create_lessons(book, lessons):
    """(Re)create a book's lessons from segmenter output (list OR generator),
    saving each lesson's sub-PDF one at a time so peak memory stays low.
    Replaces any existing lessons."""
    book.lessons.all().delete()
    for i, l in enumerate(lessons):
        if i >= processing.MAX_LESSONS:
            break
        bl = BookLesson(
            book=book, title=l["title"], position=i, raw_text=l["raw_text"],
            page_start=l.get("page_start"), page_end=l.get("page_end"),
        )
        if l.get("pdf_bytes"):
            bl.pdf.save(f"book{book.id}_{i:03d}.pdf", ContentFile(l["pdf_bytes"]), save=True)
        else:
            bl.save()
        l["pdf_bytes"] = None  # free the bytes before the next lesson


class BookRegenerateView(APIView):
    """Re-split the book's original PDF with new page settings, replacing all
    its lessons. Requires the original PDF (stored on upload)."""

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        book = Book.objects.filter(id=pk, user=request.user).first()
        if not book:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if not book.pdf:
            return Response(
                {"detail": "No original PDF stored for this book — re-upload it to enable re-generate."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = RegenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data
        from_n, to_n = int(v["from_lesson"]), int(v["to_lesson"])
        data = book.pdf.read()
        new_lessons = processing.segment_pdf(
            data, v.get("lesson_label") or "Unit",
            from_n, to_n, int(v.get("start_page") or 1), v.get("pages_per_unit"), None,
        )

        if v.get("replace_all"):
            # Whole-book (re-)split: clear every existing lesson first.
            book.lessons.all().delete()
        else:
            # Replace ONLY the units in [from..to]; keep every other lesson intact.
            replace = set(range(from_n, to_n + 1))
            for l in list(book.lessons.all()):
                if _title_num(l.title) in replace:
                    l.delete()
        for l in new_lessons:
            bl = BookLesson(
                book=book, title=l["title"], position=0, raw_text=l["raw_text"],
                page_start=l.get("page_start"), page_end=l.get("page_end"),
            )
            if l.get("pdf_bytes"):
                bl.pdf.save(f"book{book.id}_u{l['num']}.pdf", ContentFile(l["pdf_bytes"]), save=False)
            bl.save()
        # Re-order by unit number so the list stays sequential.
        ordered = sorted(book.lessons.all(), key=lambda x: (_title_num(x.title) or 10**9, x.id))
        for pos, l in enumerate(ordered):
            if l.position != pos:
                BookLesson.objects.filter(id=l.id).update(position=pos)
        return Response(_book_data(book, request), status=status.HTTP_200_OK)


class BookLessonDetailView(APIView):
    """A single lesson's content (raw page text + any extracted cards) so the
    user can view exactly the pages assigned to it."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk, lid):
        book = _book_for(request, pk)  # owner or shared
        lesson = BookLesson.objects.filter(id=lid, book=book).first() if book else None
        if not lesson:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(BookLessonDetailSerializer(lesson).data)


class BookLessonProcessView(APIView):
    """Extract (or re-extract) one lesson's vocabulary with the LLM."""

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk, lid):
        book = _book_for(request, pk)  # owner or shared can extract vocab
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
        book = _book_for(request, pk)  # owner or shared
        if not book:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(_book_data(book, request))

    def patch(self, request, pk):
        book = _book_for(request, pk, owner_only=True)
        if not book:
            return Response(status=status.HTTP_404_NOT_FOUND)
        fields = []
        if "source_language" in request.data:
            book.source_language = request.data["source_language"]
            fields.append("source_language")
        if "translation_language" in request.data:
            book.translation_language = (request.data["translation_language"] or "English").strip()
            fields.append("translation_language")
        if "title" in request.data and str(request.data["title"]).strip():
            book.title = str(request.data["title"]).strip()
            fields.append("title")
        if fields:
            book.save(update_fields=fields)
        return Response(_book_data(book, request))

    def delete(self, request, pk):
        book = _book_for(request, pk, owner_only=True)
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
        book = _book_for(request, pk)  # owner or shared can review into their own decks
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
        add_reverse_cards(cards)  # vocab cards get their reverse direction too
        return Response(
            {"book_deck": book_deck.id, "lesson_deck": lesson_deck.id, "cards": len(cards)},
            status=status.HTTP_201_CREATED,
        )
