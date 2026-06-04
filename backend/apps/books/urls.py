from django.urls import path

from .views import (
    BookAnalyzeView,
    BookDetailView,
    BookLessonDetailView,
    BookLessonImportView,
    BookLessonProcessView,
    BookListView,
    BookRegenerateView,
)

urlpatterns = [
    path("books/", BookListView.as_view(), name="book-list"),
    path("books/analyze/", BookAnalyzeView.as_view(), name="book-analyze"),
    path("books/<int:pk>/", BookDetailView.as_view(), name="book-detail"),
    path("books/<int:pk>/regenerate/", BookRegenerateView.as_view(), name="book-regenerate"),
    path("books/<int:pk>/lessons/<int:lid>/", BookLessonDetailView.as_view(), name="book-lesson-detail"),
    path("books/<int:pk>/lessons/<int:lid>/process/", BookLessonProcessView.as_view(), name="book-lesson-process"),
    path("books/<int:pk>/lessons/<int:lid>/import/", BookLessonImportView.as_view(), name="book-lesson-import"),
]
