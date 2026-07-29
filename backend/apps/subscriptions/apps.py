from django.apps import AppConfig


class SubscriptionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.subscriptions"
    label = "subscriptions"

    def ready(self):
        from . import signals  # noqa: F401 — register post_save handler
