from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cards", "0007_cardimage_auto"),
    ]

    operations = [
        migrations.AddField(
            model_name="card",
            name="conjugations",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name="card",
            name="card_type",
            field=models.CharField(
                choices=[
                    ("vocab", "Vocabulary"),
                    ("sentence", "Sentence"),
                    ("grammar", "Grammar"),
                    ("verb", "Verb"),
                ],
                default="vocab",
                max_length=12,
            ),
        ),
    ]
