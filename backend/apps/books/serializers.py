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

    class Meta:
        model = BookLesson
        fields = ["id", "title", "position", "card_count"]

    def get_card_count(self, obj) -> int:
        return obj.cards.count()


class BookLessonDetailSerializer(BookLessonSerializer):
    cards = BookCardSerializer(many=True, read_only=True)

    class Meta(BookLessonSerializer.Meta):
        fields = BookLessonSerializer.Meta.fields + ["cards"]


class BookSerializer(serializers.ModelSerializer):
    lessons = BookLessonSerializer(many=True, read_only=True)
    lesson_count = serializers.SerializerMethodField()
    card_count = serializers.SerializerMethodField()

    class Meta:
        model = Book
        fields = [
            "id", "title", "source_language", "translation_language",
            "status", "color", "note", "lessons", "lesson_count",
            "card_count", "created_at",
        ]

    def get_lesson_count(self, obj) -> int:
        return obj.lessons.count()

    def get_card_count(self, obj) -> int:
        return BookCard.objects.filter(lesson__book=obj).count()
