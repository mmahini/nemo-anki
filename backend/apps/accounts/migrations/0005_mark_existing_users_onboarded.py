from django.db import migrations


def mark_existing_onboarded(apps, schema_editor):
    """Accounts that existed before the welcome flow shipped shouldn't be pushed
    through it — they already have a language set and know their way around. They
    can still replay it from the account menu. Without this, every existing user
    gets force-redirected to /welcome on their next visit.

    Stamped with date_joined rather than "now" so the timestamp stays honest:
    these users were never actually walked through onboarding.
    """
    User = apps.get_model("accounts", "User")
    for user in User.objects.filter(onboarded_at__isnull=True).only("id", "date_joined"):
        User.objects.filter(pk=user.pk).update(onboarded_at=user.date_joined)


def unmark(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.update(onboarded_at=None)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0004_user_onboarded_at")]

    operations = [migrations.RunPython(mark_existing_onboarded, unmark)]
