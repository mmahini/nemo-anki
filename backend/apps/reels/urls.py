from django.urls import path

from .views import ReelFeedView, ReelSavedListView, ReelSaveView, ReelSeenView

urlpatterns = [
    path("reels/", ReelFeedView.as_view(), name="reel-feed"),
    path("reels/saved/", ReelSavedListView.as_view(), name="reel-saved"),
    path("reels/<int:pk>/seen/", ReelSeenView.as_view(), name="reel-seen"),
    path("reels/<int:pk>/save/", ReelSaveView.as_view(), name="reel-save"),
]
