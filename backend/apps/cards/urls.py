from django.urls import path

from .views import (
    AnswerView,
    BulkCardView,
    CardDetailView,
    CardListView,
    StudyView,
    UndoView,
)

urlpatterns = [
    path("cards/", CardListView.as_view(), name="card-list"),
    path("cards/bulk/", BulkCardView.as_view(), name="card-bulk"),
    path("cards/undo/", UndoView.as_view(), name="card-undo"),
    path("cards/<int:pk>/", CardDetailView.as_view(), name="card-detail"),
    path("cards/<int:pk>/answer/", AnswerView.as_view(), name="card-answer"),
    path("decks/<int:pk>/study/", StudyView.as_view(), name="deck-study"),
]
