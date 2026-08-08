from django.db import models


class BuddyLink(models.Model):
    """A study-buddy pairing between two users — mutual (needs the recipient's
    acceptance) and singular (a user has at most one active link, pending or
    accepted, at a time; enforced in the view, not the DB — see
    apps.buddy.views._active_link_for)."""

    STATUS_CHOICES = [("pending", "Pending"), ("accepted", "Accepted")]

    requester = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="buddy_links_sent"
    )
    recipient = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="buddy_links_received"
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    # Anti-spam: one nudge per calendar day for the pair, either direction.
    last_nudge_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.requester_id} <-> {self.recipient_id} ({self.status})"
