from django.urls import path

from .views import StartPlacementView, SubmitPlacementView

urlpatterns = [
    path("placement/start/", StartPlacementView.as_view(), name="placement-start"),
    path("placement/<int:pk>/submit/", SubmitPlacementView.as_view(), name="placement-submit"),
]
