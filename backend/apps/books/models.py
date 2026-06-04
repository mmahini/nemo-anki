from django.db import models

# A small palette so each book gets a distinct banner colour.
BANNER_COLORS = ["#4c6ef5", "#1f9d57", "#e8973a", "#e23b54", "#8a63d2", "#0ca6c2"]


class Book(models.Model):
    """An uploaded coursebook, processed into lessons + vocab the user can
    import into their own decks."""

    STATUS = [("processing", "Processing"), ("ready", "Ready"), ("failed", "Failed")]

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="books")
    title = models.CharField(max_length=160)
    source_language = models.CharField(max_length=4, blank=True, default="")   # de/en/...
    translation_language = models.CharField(max_length=40, default="English")
    status = models.CharField(max_length=12, choices=STATUS, default="processing")
    color = models.CharField(max_length=20, default="#4c6ef5")
    note = models.CharField(max_length=240, blank=True, default="")            # e.g. cap info
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title


class BookLesson(models.Model):
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(max_length=160)
    position = models.PositiveIntegerField(default=0)
    raw_text = models.TextField(blank=True, default="")
    page_start = models.PositiveIntegerField(null=True, blank=True)
    page_end = models.PositiveIntegerField(null=True, blank=True)
    # Vocab is extracted per lesson, on demand (the lesson's Process button).
    processed = models.BooleanField(default=False)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return f"{self.book_id}:{self.title}"


class BookCard(models.Model):
    """A template vocab/sentence/grammar card extracted from a lesson. Copied
    into a real cards.Card when the user imports the lesson."""

    lesson = models.ForeignKey(BookLesson, on_delete=models.CASCADE, related_name="cards")
    card_type = models.CharField(max_length=12, default="vocab")
    front = models.TextField()
    back = models.TextField(blank=True, default="")
    reading = models.TextField(blank=True, default="")
    article = models.CharField(max_length=8, default="none")
    plural = models.CharField(max_length=120, blank=True, default="")
    example = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    table = models.JSONField(null=True, blank=True)
    genders = models.JSONField(default=list, blank=True)
    tags = models.JSONField(default=list, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
