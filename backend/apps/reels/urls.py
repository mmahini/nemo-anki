from django.urls import path

from .views import (
    ReelFeedView,
    ReelMakeCardsView,
    ReelSavedListView,
    ReelSaveView,
    ReelSeenView,
    ReelUnseenCountView,
)

urlpatterns = [
    path("reels/", ReelFeedView.as_view(), name="reel-feed"),
    path("reels/saved/", ReelSavedListView.as_view(), name="reel-saved"),
    path("reels/unseen-count/", ReelUnseenCountView.as_view(), name="reel-unseen-count"),
    path("reels/<int:pk>/seen/", ReelSeenView.as_view(), name="reel-seen"),
    path("reels/<int:pk>/save/", ReelSaveView.as_view(), name="reel-save"),
    path("reels/<int:pk>/make-cards/", ReelMakeCardsView.as_view(), name="reel-make-cards"),
]
