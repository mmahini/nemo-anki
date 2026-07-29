from django.urls import path

from .views import SupportThreadView

urlpatterns = [
    path("support/thread/", SupportThreadView.as_view(), name="support-thread"),
]
