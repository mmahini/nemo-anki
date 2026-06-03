from django.urls import path

from .views import BookDetailView, BookLessonImportView, BookListView

urlpatterns = [
    path("books/", BookListView.as_view(), name="book-list"),
    path("books/<int:pk>/", BookDetailView.as_view(), name="book-detail"),
    path("books/<int:pk>/lessons/<int:lid>/import/", BookLessonImportView.as_view(), name="book-lesson-import"),
]
