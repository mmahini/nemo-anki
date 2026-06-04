from django.db import migrations

# Content fields mirrored across the two directions of a note (kept inline so
# the migration is independent of later model edits).
CONTENT_FIELDS = [
    "card_type", "language", "front", "back", "reading", "article",
    "plural", "example", "notes", "table", "genders", "tags",
]


def create_reverses(apps, schema_editor):
    """Give every existing vocab card a reverse companion (meaning → term)."""
    Card = apps.get_model("cards", "Card")
    forwards = Card.objects.filter(
        card_type="vocab", direction="forward", reverse_of__isnull=True
    )
    new = []
    for c in forwards.iterator():
        new.append(
            Card(
                deck_id=c.deck_id,
                position=c.position,
                direction="reverse",
                reverse_of_id=c.id,
                **{f: getattr(c, f) for f in CONTENT_FIELDS},
            )
        )
        if len(new) >= 500:
            Card.objects.bulk_create(new)
            new = []
    if new:
        Card.objects.bulk_create(new)


def drop_reverses(apps, schema_editor):
    Card = apps.get_model("cards", "Card")
    Card.objects.filter(direction="reverse").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("cards", "0004_card_direction_card_reverse_of"),
    ]

    operations = [
        migrations.RunPython(create_reverses, drop_reverses),
    ]
