from django.urls import path

from .views import (
    BookAnalyzeView,
    BookDetailView,
    BookLessonDetailView,
    BookLessonImportView,
    BookLessonProcessView,
    BookLessonPublishView,
    BookListView,
    BookRegenerateView,
    BookSharesView,
    BooksSharedView,
    LibraryAddView,
    LibraryBookView,
    LibraryListView,
)

urlpatterns = [
    path("books/", BookListView.as_view(), name="book-list"),
    path("books/shared/", BooksSharedView.as_view(), name="books-shared"),
    path("books/analyze/", BookAnalyzeView.as_view(), name="book-analyze"),
    path("books/<int:pk>/", BookDetailView.as_view(), name="book-detail"),
    path("books/<int:pk>/shares/", BookSharesView.as_view(), name="book-shares"),
    path("books/<int:pk>/regenerate/", BookRegenerateView.as_view(), name="book-regenerate"),
    path("books/<int:pk>/lessons/<int:lid>/", BookLessonDetailView.as_view(), name="book-lesson-detail"),
    path("books/<int:pk>/lessons/<int:lid>/process/", BookLessonProcessView.as_view(), name="book-lesson-process"),
    path("books/<int:pk>/lessons/<int:lid>/import/", BookLessonImportView.as_view(), name="book-lesson-import"),
    path("books/<int:pk>/lessons/<int:lid>/publish/", BookLessonPublishView.as_view(), name="book-lesson-publish"),
    path("library/", LibraryListView.as_view(), name="library-list"),
    path("library/<int:pk>/", LibraryBookView.as_view(), name="library-book"),
    path("library/<int:pk>/add/", LibraryAddView.as_view(), name="library-add"),
]
