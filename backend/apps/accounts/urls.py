from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import MeView, RequestOTPView, VerifyOTPView

urlpatterns = [
    path("auth/request-otp", RequestOTPView.as_view(), name="auth-request-otp"),
    path("auth/verify-otp", VerifyOTPView.as_view(), name="auth-verify-otp"),
    path("auth/refresh", TokenRefreshView.as_view(), name="auth-refresh"),
    path("me", MeView.as_view(), name="me"),
]
