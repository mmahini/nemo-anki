from rest_framework import serializers

from .models import Book, BookCard, BookLesson


class BookCardSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookCard
        fields = [
            "id", "card_type", "front", "back", "reading", "article",
            "plural", "example", "notes", "table", "genders", "tags",
        ]


class BookLessonSerializer(serializers.ModelSerializer):
    card_count = serializers.SerializerMethodField()
    pdf_url = serializers.SerializerMethodField()

    class Meta:
        model = BookLesson
        fields = ["id", "title", "position", "card_count", "processed", "page_start", "page_end", "pdf_url"]

    def get_card_count(self, obj) -> int:
        return obj.cards.count()

    def get_pdf_url(self, obj) -> str | None:
        return obj.pdf.url if obj.pdf else None


class BookLessonDetailSerializer(BookLessonSerializer):
    cards = BookCardSerializer(many=True, read_only=True)

    class Meta(BookLessonSerializer.Meta):
        fields = BookLessonSerializer.Meta.fields + ["raw_text", "cards"]


class BookSerializer(serializers.ModelSerializer):
    lessons = BookLessonSerializer(many=True, read_only=True)
    lesson_count = serializers.SerializerMethodField()
    card_count = serializers.SerializerMethodField()
    has_pdf = serializers.SerializerMethodField()

    class Meta:
        model = Book
        fields = [
            "id", "title", "source_language", "translation_language",
            "status", "color", "note", "lessons", "lesson_count",
            "card_count", "has_pdf", "created_at",
        ]

    def get_has_pdf(self, obj) -> bool:
        return bool(obj.pdf)

    def get_lesson_count(self, obj) -> int:
        return obj.lessons.count()

    def get_card_count(self, obj) -> int:
        return BookCard.objects.filter(lesson__book=obj).count()
