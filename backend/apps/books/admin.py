from django.contrib import admin

from .models import Book, BookCard, BookLesson


class BookLessonInline(admin.TabularInline):
    model = BookLesson
    extra = 0


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "source_language", "translation_language", "status", "created_at")
    list_filter = ("status", "source_language")
    search_fields = ("title", "user__email")
    inlines = [BookLessonInline]


@admin.register(BookLesson)
class BookLessonAdmin(admin.ModelAdmin):
    list_display = ("title", "book", "position")
    search_fields = ("title", "book__title")


@admin.register(BookCard)
class BookCardAdmin(admin.ModelAdmin):
    list_display = ("front", "back", "article", "lesson")
    search_fields = ("front", "back")
