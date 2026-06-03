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


class Card(models.Model):
    deck = models.ForeignKey("decks.Deck", on_delete=models.CASCADE, related_name="cards")

    # ---- Content ----
    card_type = models.CharField(max_length=12, choices=CardType.choices, default=CardType.VOCAB)
    language = models.CharField(max_length=4, blank=True, default="")
    front = models.TextField()
    back = models.TextField(blank=True, default="")
    reading = models.TextField(blank=True, default="")          # phonetic (vocab/sentence)
    article = models.CharField(max_length=8, choices=Article.choices, default=Article.NONE)
    example = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")            # rule explanation (grammar)
    table = models.JSONField(null=True, blank=True)             # declension/conjugation (grammar)
    tags = models.JSONField(default=list, blank=True)

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
