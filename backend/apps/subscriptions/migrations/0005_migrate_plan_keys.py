from django.db import migrations

# Old (single-tier) plan keys -> new tiered keys. Everything that existed before
# tiers was the Basic price points.
RENAME = {
    "monthly": "basic_monthly",
    "quarterly": "basic_quarterly",
    "yearly": "basic_yearly",
}


def forwards(apps, schema_editor):
    Subscription = apps.get_model("subscriptions", "Subscription")
    SubscriptionRequest = apps.get_model("subscriptions", "SubscriptionRequest")

    for old, new in RENAME.items():
        SubscriptionRequest.objects.filter(plan=old).update(plan=new)
        Subscription.objects.filter(plan=old).update(plan=new)

    # Anyone who had purchased a plan was on Basic.
    Subscription.objects.exclude(plan="").filter(tier="").update(tier="basic")


def backwards(apps, schema_editor):
    Subscription = apps.get_model("subscriptions", "Subscription")
    SubscriptionRequest = apps.get_model("subscriptions", "SubscriptionRequest")
    for old, new in RENAME.items():
        SubscriptionRequest.objects.filter(plan=new).update(plan=old)
        Subscription.objects.filter(plan=new).update(plan=old)


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0004_subscription_tier_alter_subscription_plan_and_more"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
