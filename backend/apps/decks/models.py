from django.db import models


class DeckConfig(models.Model):
    """Anki-style "deck options" preset. Ease and multipliers are stored as
    integers in permille (2500 = 250%, 1300 = 130%) exactly like Anki, to
    avoid floating-point drift. Steps are space-separated minutes.

    See docs/ANKI_RESEARCH.md §4 for the defaults shipped here.
    """

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="deck_configs")
    name = models.CharField(max_length=80, default="Default")

    # Learning / relearning (space-separated minutes)
    learning_steps = models.CharField(max_length=120, default="1 10")
    relearning_steps = models.CharField(max_length=120, default="10")

    graduating_interval = models.PositiveIntegerField(default=1)   # days
    easy_interval = models.PositiveIntegerField(default=4)         # days

    starting_ease = models.PositiveIntegerField(default=2500)      # permille
    easy_bonus = models.PositiveIntegerField(default=1300)         # permille
    hard_interval = models.PositiveIntegerField(default=1200)      # permille
    interval_modifier = models.PositiveIntegerField(default=1000)  # permille
    new_interval = models.PositiveIntegerField(default=0)          # permille (lapse)
    minimum_interval = models.PositiveIntegerField(default=1)      # days
    maximum_interval = models.PositiveIntegerField(default=36500)  # days

    new_per_day = models.PositiveIntegerField(default=20)
    reviews_per_day = models.PositiveIntegerField(default=200)

    leech_threshold = models.PositiveIntegerField(default=8)
    leech_suspend = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.name}"


class Deck(models.Model):
    """A hierarchically nestable group of cards. `parent` builds the tree
    (Anki's `::` separation); `full_name` joins the chain for display.
    """

    LANGUAGE_CHOICES = [
        ("de", "German"),
        ("en", "English"),
        ("", "Other"),
    ]

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="decks")
    name = models.CharField(max_length=120)
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )
    config = models.ForeignKey(DeckConfig, on_delete=models.PROTECT, related_name="decks")
    language = models.CharField(max_length=4, choices=LANGUAGE_CHOICES, blank=True, default="")
    color = models.CharField(max_length=20, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "parent", "name"], name="unique_deck_name_per_parent"
            ),
        ]

    @property
    def full_name(self) -> str:
        parts = [self.name]
        node = self.parent
        while node is not None:
            parts.append(node.name)
            node = node.parent
        return "::".join(reversed(parts))

    def descendant_ids(self) -> list[int]:
        """Self + all descendant deck ids (studying a parent studies its tree)."""
        ids = [self.id]
        frontier = [self.id]
        while frontier:
            children = list(
                Deck.objects.filter(parent_id__in=frontier).values_list("id", flat=True)
            )
            ids.extend(children)
            frontier = children
        return ids

    def __str__(self) -> str:
        return self.full_name


class DeckShare(models.Model):
    """A deck the owner has shared with another user — grants that user the
    ability to Import a copy (see apps.decks.sharing), not live access."""

    deck = models.ForeignKey(Deck, on_delete=models.CASCADE, related_name="shares")
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="shared_decks")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["deck", "user"], name="unique_deck_share"),
        ]
