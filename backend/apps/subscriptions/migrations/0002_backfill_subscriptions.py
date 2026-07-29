from datetime import timedelta

from django.db import migrations
from django.utils import timezone

from apps.subscriptions.plans import TRIAL_DAYS


def backfill(apps, schema_editor):
    """Give every existing user a subscription with a 7-day trial measured from
    their signup date (matching the rule new users get via the post_save signal)."""
    User = apps.get_model("accounts", "User")
    Subscription = apps.get_model("subscriptions", "Subscription")
    existing = set(Subscription.objects.values_list("user_id", flat=True))
    to_create = []
    for user in User.objects.exclude(id__in=existing):
        joined = user.date_joined or timezone.now()
        to_create.append(Subscription(user_id=user.id, trial_end=joined + timedelta(days=TRIAL_DAYS)))
    Subscription.objects.bulk_create(to_create)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0001_initial"),
        ("accounts", "0003_user_feature_flags"),
    ]

    operations = [migrations.RunPython(backfill, noop)]
