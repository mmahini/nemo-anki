from django.db import models


class SupportThread(models.Model):
    """One running support conversation per user."""

    user = models.OneToOneField(
        "accounts.User", on_delete=models.CASCADE, related_name="support_thread"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"Support thread — {self.user.email}"

    @property
    def awaiting_reply(self) -> bool:
        """True when the user is waiting on an admin response (the last
        message in the thread was sent by them, not by staff)."""
        last = self.messages.last()
        return bool(last and not last.from_admin)


class PushSubscription(models.Model):
    """A staff member's browser push endpoint, so a new user message can
    trigger a real phone/desktop notification (see notifications.py)."""

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="staff_push_subscriptions"
    )
    endpoint = models.URLField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Push subscription — {self.user.email}"


class SupportMessage(models.Model):
    thread = models.ForeignKey(SupportThread, on_delete=models.CASCADE, related_name="messages")
    from_admin = models.BooleanField(default=False)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"[{'admin' if self.from_admin else 'user'}] {self.body[:40]}"
