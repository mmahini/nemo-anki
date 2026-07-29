from django.urls import path

from .views import ClaimView, PlansView, SubscriptionView

urlpatterns = [
    path("subscription", SubscriptionView.as_view(), name="subscription"),
    path("subscription/plans", PlansView.as_view(), name="subscription-plans"),
    path("subscription/claim", ClaimView.as_view(), name="subscription-claim"),
]
