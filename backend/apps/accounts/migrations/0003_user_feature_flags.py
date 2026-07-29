from django.db import migrations, models

from apps.accounts.feature_flags import STAFF


def seed_staff_flag(apps, schema_editor):
    """Grant the `staff` flag to everyone who is currently is_staff, so existing
    staff keep access to the now-gated features without manual setup."""
    User = apps.get_model("accounts", "User")
    for user in User.objects.filter(is_staff=True):
        flags = list(user.feature_flags or [])
        if STAFF not in flags:
            flags.append(STAFF)
            user.feature_flags = flags
            user.save(update_fields=["feature_flags"])


def unseed_staff_flag(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    for user in User.objects.all():
        if STAFF in (user.feature_flags or []):
            user.feature_flags = [f for f in user.feature_flags if f != STAFF]
            user.save(update_fields=["feature_flags"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_user_ui_language"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="feature_flags",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(seed_staff_flag, unseed_staff_flag),
    ]
