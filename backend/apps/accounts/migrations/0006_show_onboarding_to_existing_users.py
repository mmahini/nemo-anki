from django.db import migrations
from django.db.models import F


def reset_grandfathered(apps, schema_editor):
    """Put the users 0005 grandfathered back through the welcome flow.

    0005 skipped existing accounts so nobody got force-redirected; the call has
    since been reversed — everyone should see the intro exactly once. 0005 is
    already applied in production, so it can't be edited away; this undoes its
    effect instead.

    The discriminator is that 0005 stamped `onboarded_at` with the account's own
    `date_joined`, so an exact match identifies precisely the accounts it touched.
    Anyone who has genuinely finished the flow since has a `timezone.now()` stamp,
    which will never equal `date_joined`, and accounts still waiting are already
    NULL (and NULL never matches). So this is safe to re-run and won't reset
    anyone twice.
    """
    User = apps.get_model("accounts", "User")
    User.objects.filter(onboarded_at=F("date_joined")).update(onboarded_at=None)


def noop_reverse(apps, schema_editor):
    """Deliberately not the inverse. Re-stamping `date_joined` here would undo a
    real completion for anyone who had since finished the flow, and 'has seen the
    intro' isn't recoverable once cleared. Reversing this migration simply leaves
    the flags as they are.
    """


class Migration(migrations.Migration):
    dependencies = [("accounts", "0005_mark_existing_users_onboarded")]

    operations = [migrations.RunPython(reset_grandfathered, noop_reverse)]
