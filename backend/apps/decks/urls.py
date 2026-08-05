from django.urls import path

from .views import (
    DeckAutotypeView,
    DeckColourizeView,
    DeckConfigDetailView,
    DeckDetailView,
    DeckListView,
    DeckSeedView,
    DeckStatsView,
)

urlpatterns = [
    path("decks/", DeckListView.as_view(), name="deck-list"),
    path("decks/seed/", DeckSeedView.as_view(), name="deck-seed"),
    path("decks/<int:pk>/", DeckDetailView.as_view(), name="deck-detail"),
    path("decks/<int:pk>/stats/", DeckStatsView.as_view(), name="deck-stats"),
    path("decks/<int:pk>/colourize/", DeckColourizeView.as_view(), name="deck-colourize"),
    path("decks/<int:pk>/autotype/", DeckAutotypeView.as_view(), name="deck-autotype"),
    path("deck-configs/<int:pk>/", DeckConfigDetailView.as_view(), name="deck-config-detail"),
]
