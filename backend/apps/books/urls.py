from django.urls import path

from .views import (
    BookAnalyzeView,
    BookDetailView,
    BookLessonImportView,
    BookLessonProcessView,
    BookListView,
)

urlpatterns = [
    path("books/", BookListView.as_view(), name="book-list"),
    path("books/analyze/", BookAnalyzeView.as_view(), name="book-analyze"),
    path("books/<int:pk>/", BookDetailView.as_view(), name="book-detail"),
    path("books/<int:pk>/lessons/<int:lid>/process/", BookLessonProcessView.as_view(), name="book-lesson-process"),
    path("books/<int:pk>/lessons/<int:lid>/import/", BookLessonImportView.as_view(), name="book-lesson-import"),
]
