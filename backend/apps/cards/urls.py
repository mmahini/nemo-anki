from django.urls import path

from .views import (
    AnswerView,
    BulkCardView,
    CardColourizeView,
    CardDetailView,
    CardFindImageView,
    CardReviewView,
    CardImageDetailView,
    CardImageView,
    CardListView,
    ReviewActivityView,
    StudyView,
    UndoView,
)

urlpatterns = [
    path("cards/", CardListView.as_view(), name="card-list"),
    path("cards/bulk/", BulkCardView.as_view(), name="card-bulk"),
    path("cards/undo/", UndoView.as_view(), name="card-undo"),
    path("stats/activity/", ReviewActivityView.as_view(), name="stats-activity"),
    path("cards/<int:pk>/", CardDetailView.as_view(), name="card-detail"),
    path("cards/<int:pk>/answer/", AnswerView.as_view(), name="card-answer"),
    path("cards/<int:pk>/colourize/", CardColourizeView.as_view(), name="card-colourize"),
    path("cards/<int:pk>/review/", CardReviewView.as_view(), name="card-review"),
    path("cards/<int:pk>/find-image/", CardFindImageView.as_view(), name="card-find-image"),
    path("cards/<int:pk>/images/", CardImageView.as_view(), name="card-images"),
    path("cards/<int:pk>/images/<int:img_id>/", CardImageDetailView.as_view(), name="card-image-detail"),
    path("decks/<int:pk>/study/", StudyView.as_view(), name="deck-study"),
]
