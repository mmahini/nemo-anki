from django.urls import path

from .views import (
    DeckAutotypeView,
    DeckColourizeView,
    DeckConfigDetailView,
    DeckDetailView,
    DeckImportView,
    DeckListView,
    DeckSeedView,
    DecksSharedView,
    DeckSharesView,
    DeckStatsView,
)

urlpatterns = [
    path("decks/", DeckListView.as_view(), name="deck-list"),
    path("decks/seed/", DeckSeedView.as_view(), name="deck-seed"),
    path("decks/shared/", DecksSharedView.as_view(), name="deck-shared"),
    path("decks/<int:pk>/", DeckDetailView.as_view(), name="deck-detail"),
    path("decks/<int:pk>/stats/", DeckStatsView.as_view(), name="deck-stats"),
    path("decks/<int:pk>/colourize/", DeckColourizeView.as_view(), name="deck-colourize"),
    path("decks/<int:pk>/autotype/", DeckAutotypeView.as_view(), name="deck-autotype"),
    path("decks/<int:pk>/shares/", DeckSharesView.as_view(), name="deck-shares"),
    path("decks/<int:pk>/import/", DeckImportView.as_view(), name="deck-import"),
    path("deck-configs/<int:pk>/", DeckConfigDetailView.as_view(), name="deck-config-detail"),
]
