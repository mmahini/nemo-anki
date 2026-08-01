# Referral programme: every user gets a shareable invite code, and a new
# account remembers who invited it.
#
# referral_code is unique, so it's added in three steps: nullable first, then a
# per-row backfill (a single-shot default would give every existing user the
# same code), then the real unique + default definition.

from django.db import migrations, models
import django.db.models.deletion

import apps.accounts.models


def backfill_referral_codes(apps_registry, schema_editor):
    from apps.accounts.models import generate_referral_code

    User = apps_registry.get_model("accounts", "User")
    taken = set(User.objects.exclude(referral_code=None).values_list("referral_code", flat=True))
    for user in User.objects.filter(referral_code=None):
        code = generate_referral_code()
        while code in taken:
            code = generate_referral_code()
        taken.add(code)
        user.referral_code = code
        user.save(update_fields=["referral_code"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_show_onboarding_to_existing_users"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="referral_code",
            field=models.CharField(max_length=12, null=True),
        ),
        migrations.RunPython(backfill_referral_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="referral_code",
            field=models.CharField(
                default=apps.accounts.models.generate_referral_code,
                max_length=12,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="referred_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="referrals",
                to="accounts.user",
            ),
        ),
    ]
