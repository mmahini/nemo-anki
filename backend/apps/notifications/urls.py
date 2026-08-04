from django.urls import path

from .views import (
    PushSubscribeView,
    PushUnsubscribeView,
    TelegramConnectView,
    TelegramDisconnectView,
    TelegramStatusView,
    TelegramWebhookView,
)

urlpatterns = [
    path("notifications/push-subscribe", PushSubscribeView.as_view(), name="push-subscribe"),
    path("notifications/push-unsubscribe", PushUnsubscribeView.as_view(), name="push-unsubscribe"),
    path("notifications/telegram/connect", TelegramConnectView.as_view(), name="telegram-connect"),
    path("notifications/telegram/status", TelegramStatusView.as_view(), name="telegram-status"),
    path("notifications/telegram/disconnect", TelegramDisconnectView.as_view(), name="telegram-disconnect"),
    path("notifications/telegram/webhook", TelegramWebhookView.as_view(), name="telegram-webhook"),
]
