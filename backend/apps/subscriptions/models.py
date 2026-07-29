import math
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from .plans import PLAN_CHOICES, PLANS, TRIAL_DAYS


class Subscription(models.Model):
    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"
    STATUS_CHOICES = [(TRIAL, "Trial"), (ACTIVE, "Active"), (EXPIRED, "Expired")]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscription"
    )
    # Cached label for admin listing; recomputed by the "Check all" button.
    # Live access is computed from the dates below, never from this field.
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=TRIAL)
    trial_end = models.DateTimeField()
    current_period_end = models.DateTimeField(null=True, blank=True)
    plan = models.CharField(max_length=16, choices=PLAN_CHOICES, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user.email} — {self.computed_state}"

    @classmethod
    def for_user(cls, user) -> "Subscription":
        """Get or create the user's subscription, seeding the 7-day trial."""
        joined = getattr(user, "date_joined", None) or timezone.now()
        sub, _ = cls.objects.get_or_create(
            user=user, defaults={"trial_end": joined + timedelta(days=TRIAL_DAYS)}
        )
        return sub

    @property
    def access_until(self):
        ends = [e for e in (self.current_period_end, self.trial_end) if e]
        return max(ends) if ends else None

    @property
    def is_active(self) -> bool:
        au = self.access_until
        return bool(au and au > timezone.now())

    @property
    def computed_state(self) -> str:
        now = timezone.now()
        if self.current_period_end and self.current_period_end > now:
            return self.ACTIVE
        if self.trial_end and self.trial_end > now:
            return self.TRIAL
        return self.EXPIRED

    @property
    def days_left(self) -> int:
        au = self.access_until
        if not au:
            return 0
        seconds = (au - timezone.now()).total_seconds()
        return max(0, math.ceil(seconds / 86400))

    def activate(self, plan: str) -> None:
        """Start or extend the paid period by the plan's duration. Stacks onto
        remaining paid time when still active."""
        if plan not in PLANS:
            raise ValueError(f"Unknown plan: {plan}")
        now = timezone.now()
        base = max(self.current_period_end or now, now)
        self.current_period_end = base + timedelta(days=PLANS[plan]["days"])
        self.plan = plan
        self.status = self.computed_state
        self.save()

    def recompute_status(self) -> str:
        """Sync the cached status label to the live state. Returns the state."""
        self.status = self.computed_state
        self.save(update_fields=["status", "updated_at"])
        return self.status


class SubscriptionRequest(models.Model):
    """A user's "I've paid" submission — the admin verification queue."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STATUS_CHOICES = [(PENDING, "Pending"), (APPROVED, "Approved"), (REJECTED, "Rejected")]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscription_requests"
    )
    plan = models.CharField(max_length=16, choices=PLAN_CHOICES)
    # The user's source wallet address or the transaction hash, so an admin can
    # verify the transfer on-chain. Supplied by the user on "I've transferred",
    # and editable by an admin later.
    tx_reference = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user.email} · {self.plan} · {self.status}"
