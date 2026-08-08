from django.urls import path

from .views import BuddyAcceptView, BuddyInviteView, BuddyNudgeView, BuddyView

urlpatterns = [
    path("buddy/", BuddyView.as_view(), name="buddy"),
    path("buddy/invite/", BuddyInviteView.as_view(), name="buddy-invite"),
    path("buddy/accept/", BuddyAcceptView.as_view(), name="buddy-accept"),
    path("buddy/nudge/", BuddyNudgeView.as_view(), name="buddy-nudge"),
]
