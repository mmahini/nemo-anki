import os

from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notifications"
    label = "notifications"

    def ready(self):
        # Opt-in via env so it only runs on the deployment that wants it (the
        # single-server web service). Short-lived processes (migrate, tests)
        # that inherit the env just start a daemon thread that dies with them.
        if os.getenv("STUDY_REMINDER_TICKER") == "1":
            from .ticker import start_ticker

            start_ticker()
