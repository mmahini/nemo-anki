from datetime import timedelta

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Subscription
from .plans import TRIAL_DAYS


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_subscription_for_new_user(sender, instance, created, **kwargs):
    """Give every new user a 7-day trial the moment their account exists."""
    if not created:
        return
    joined = getattr(instance, "date_joined", None) or timezone.now()
    Subscription.objects.get_or_create(
        user=instance, defaults={"trial_end": joined + timedelta(days=TRIAL_DAYS)}
    )
