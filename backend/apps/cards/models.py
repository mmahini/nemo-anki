from django.db import models
from django.utils import timezone


class CardType(models.TextChoices):
    VOCAB = "vocab", "Vocabulary"
    SENTENCE = "sentence", "Sentence"
    GRAMMAR = "grammar", "Grammar"


class CardState(models.TextChoices):
    NEW = "new", "New"
    LEARNING = "learning", "Learning"
    REVIEW = "review", "Review"
    RELEARNING = "relearning", "Relearning"
    SUSPENDED = "suspended", "Suspended"


class Article(models.TextChoices):
    """German article — drives the colour coding (see docs/GERMAN_COLORS.md)."""

    NONE = "none", "—"
    DER = "der", "der (m, blue)"
    DIE = "die", "die (f, red)"
    DAS = "das", "das (n, green)"
    PLURAL = "plural", "die (pl)"


class CardDirection(models.TextChoices):
    """Which way a card is reviewed. A vocab note becomes two cards — a forward
    (prompt = term) and a reverse (prompt = meaning) — each scheduled
    independently so their progress tracks separately."""

    FORWARD = "forward", "Forward (term → meaning)"
    REVERSE = "reverse", "Reverse (meaning → term)"


# Content fields shared by the two directions of a note. Scheduling fields are
# deliberately excluded — each direction keeps its own track.
CONTENT_FIELDS = [
    "card_type", "language", "front", "back", "reading", "article",
    "plural", "example", "notes", "table", "genders", "tags",
]


class Card(models.Model):
    deck = models.ForeignKey("decks.Deck", on_delete=models.CASCADE, related_name="cards")

    # ---- Content ----
    card_type = models.CharField(max_length=12, choices=CardType.choices, default=CardType.VOCAB)
    language = models.CharField(max_length=4, blank=True, default="")
    front = models.TextField()
    back = models.TextField(blank=True, default="")
    reading = models.TextField(blank=True, default="")          # phonetic (vocab/sentence)
    article = models.CharField(max_length=8, choices=Article.choices, default=Article.NONE)
    plural = models.CharField(max_length=120, blank=True, default="")  # e.g. "die Tische"
    example = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")            # rule explanation (grammar)
    table = models.JSONField(null=True, blank=True)             # declension/conjugation (grammar)
    # Per-noun true genders for German sentences, in order of appearance:
    # [{"noun": "Frau", "gender": "die"}]. Populated by the "Colour genders"
    # button so sentence colouring is grammatically correct (case-independent).
    genders = models.JSONField(default=list, blank=True)
    tags = models.JSONField(default=list, blank=True)

    # ---- Direction (two-sided review) ----
    # A vocab note is two rows: a forward card and a reverse card. The reverse
    # points at its forward via `reverse_of`; deleting the forward cascades to
    # it. Content is mirrored across the pair; scheduling is independent.
    direction = models.CharField(
        max_length=8, choices=CardDirection.choices, default=CardDirection.FORWARD
    )
    reverse_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="reverses"
    )

    # ---- Scheduling (Anki SM-2; see docs/ANKI_RESEARCH.md §5) ----
    state = models.CharField(max_length=12, choices=CardState.choices, default=CardState.NEW)
    due = models.DateTimeField(default=timezone.now)            # available when due <= now
    interval_days = models.PositiveIntegerField(default=0)
    ease = models.PositiveIntegerField(default=2500)            # permille
    reps = models.PositiveIntegerField(default=0)
    lapses = models.PositiveIntegerField(default=0)
    step_index = models.PositiveIntegerField(default=0)         # position in (re)learning steps
    position = models.PositiveIntegerField(default=0)           # new-card ordering
    last_reviewed_at = models.DateTimeField(null=True, blank=True)
    is_leech = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        indexes = [
            models.Index(fields=["deck", "state", "due"]),
        ]

    def __str__(self) -> str:
        return f"[{self.card_type}] {self.front[:40]}"

    def content_dict(self) -> dict:
        """The shared, direction-independent content of this card."""
        return {f: getattr(self, f) for f in CONTENT_FIELDS}

    def wants_reverse(self) -> bool:
        """Vocab notes are reviewed both ways; everything else is one-directional."""
        return self.card_type == CardType.VOCAB

    def build_reverse(self) -> "Card":
        """An unsaved reverse companion mirroring this (saved) forward card."""
        return Card(
            deck=self.deck,
            position=self.position,
            direction=CardDirection.REVERSE,
            reverse_of=self,
            **self.content_dict(),
        )

    def scheduling_snapshot(self) -> dict:
        """Capture the scheduling fields so a review can be undone."""
        return {
            "state": self.state,
            "due": self.due.isoformat(),
            "interval_days": self.interval_days,
            "ease": self.ease,
            "reps": self.reps,
            "lapses": self.lapses,
            "step_index": self.step_index,
            "last_reviewed_at": self.last_reviewed_at.isoformat() if self.last_reviewed_at else None,
            "is_leech": self.is_leech,
        }

    def restore_snapshot(self, snap: dict) -> None:
        from django.utils.dateparse import parse_datetime

        self.state = snap["state"]
        self.due = parse_datetime(snap["due"])
        self.interval_days = snap["interval_days"]
        self.ease = snap["ease"]
        self.reps = snap["reps"]
        self.lapses = snap["lapses"]
        self.step_index = snap["step_index"]
        self.last_reviewed_at = (
            parse_datetime(snap["last_reviewed_at"]) if snap["last_reviewed_at"] else None
        )
        self.is_leech = snap["is_leech"]


def add_reverse_cards(forward_cards) -> list["Card"]:
    """Create reverse companions for the eligible (vocab) forward cards.

    `forward_cards` must be saved (have PKs). Returns the created reverses.
    """
    reverses = [
        c.build_reverse()
        for c in forward_cards
        if c.direction == CardDirection.FORWARD and c.wants_reverse()
    ]
    if reverses:
        Card.objects.bulk_create(reverses)
    return reverses


def sync_card_group(edited: "Card") -> None:
    """Mirror an edited card's content (and deck) onto the other direction(s)
    of the same note. Scheduling is left untouched on every row."""
    primary = edited.reverse_of or edited
    group = [primary, *primary.reverses.all()]
    fields = [*CONTENT_FIELDS, "deck"]
    for other in group:
        if other.pk == edited.pk:
            continue
        for f in CONTENT_FIELDS:
            setattr(other, f, getattr(edited, f))
        other.deck = edited.deck
        other.save(update_fields=fields)


class ReviewLog(models.Model):
    """One row per answer — powers stats and single-step undo."""

    RATING_CHOICES = [(1, "Again"), (2, "Hard"), (3, "Good"), (4, "Easy")]

    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="review_logs")
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="review_logs")
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)
    state_before = models.CharField(max_length=12)
    state_after = models.CharField(max_length=12)
    interval_before = models.PositiveIntegerField(default=0)
    interval_after = models.PositiveIntegerField(default=0)
    ease_before = models.PositiveIntegerField(default=0)
    ease_after = models.PositiveIntegerField(default=0)
    time_ms = models.PositiveIntegerField(default=0)
    # Full pre-answer scheduling snapshot, for undo.
    prev_snapshot = models.JSONField()
    reviewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-reviewed_at"]
        indexes = [models.Index(fields=["user", "-reviewed_at"])]


class CardImage(models.Model):
    """A photo shown on a card's answer side. Always attached to the primary
    (forward) card so both directions of a note share the same images."""

    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="card_images/")
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "id"]
