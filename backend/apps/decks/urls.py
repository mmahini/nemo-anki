from django.urls import path

from .views import (
    DeckColourizeView,
    DeckConfigDetailView,
    DeckDetailView,
    DeckListView,
    DeckStatsView,
)

urlpatterns = [
    path("decks/", DeckListView.as_view(), name="deck-list"),
    path("decks/<int:pk>/", DeckDetailView.as_view(), name="deck-detail"),
    path("decks/<int:pk>/stats/", DeckStatsView.as_view(), name="deck-stats"),
    path("decks/<int:pk>/colourize/", DeckColourizeView.as_view(), name="deck-colourize"),
    path("deck-configs/<int:pk>/", DeckConfigDetailView.as_view(), name="deck-config-detail"),
]
