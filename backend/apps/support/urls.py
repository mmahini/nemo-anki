from django.urls import path

from .views import PushSubscribeView, SupportThreadView

urlpatterns = [
    path("support/thread/", SupportThreadView.as_view(), name="support-thread"),
    path("support/push-subscribe/", PushSubscribeView.as_view(), name="support-push-subscribe"),
]
