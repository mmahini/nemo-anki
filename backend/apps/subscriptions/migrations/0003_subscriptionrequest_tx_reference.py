from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0002_backfill_subscriptions"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscriptionrequest",
            name="tx_reference",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
    ]
