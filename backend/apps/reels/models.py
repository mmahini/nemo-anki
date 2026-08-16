"""Reels — a feed of short language-teaching videos.

Two content paths, one model (see docs/plans/reels.md):

  * `ReelSource(kind="instagram")` — a public Instagram account we poll through
    Apify. We pay per reel *returned*, so dedupe happens on our side after
    we've already been billed; that's what makes `results_limit` the main cost
    knob and `Reel.key` the thing we must never lose.
  * `ReelSource(kind="own")` — our own channel. Reels are uploaded through the
    admin, cost nothing, and are never auto-purged.

Media (video + poster) rides Django's default storage, which core.settings
already points at Cloudflare R2 when the R2_* env vars are set, and at the local
filesystem otherwise.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

INSTAGRAM = "instagram"
OWN = "own"
SOURCE_KINDS = [(INSTAGRAM, "Instagram"), (OWN, "Our own")]

MEDIA_PENDING = "pending"
MEDIA_STORED = "stored"
MEDIA_FAILED = "failed"
MEDIA_PURGED = "purged"
MEDIA_STATUS = [
    (MEDIA_PENDING, "Pending"),
    (MEDIA_STORED, "Stored"),
    (MEDIA_FAILED, "Failed"),
    (MEDIA_PURGED, "Purged"),
]

LEVELS = [(lvl, lvl.upper()) for lvl in ["a1", "a2", "b1", "b2", "c1", "c2"]]


class ReelSource(models.Model):
    """A content channel — an Instagram account we scrape, or one of ours."""

    kind = models.CharField(max_length=12, choices=SOURCE_KINDS, default=INSTAGRAM)
    username = models.CharField(max_length=80, unique=True)  # no leading @
    display_name = models.CharField(max_length=120, blank=True, default="")
    avatar = models.ImageField(upload_to="reel_avatars/", null=True, blank=True)
    # Every account teaches one language *in* another: @easytodeutsch teaches
    # German to English speakers (target=de, base=en); a Persian-language German
    # channel is target=de, base=fa. A reel only reaches a user whose
    # learning_languages contain the target AND whose known_languages contain
    # the base — otherwise we'd show a learner explanations they can't read.
    # base_language="" means immersive (taught in the target language itself),
    # which reaches every learner of the target. See accounts.languages.
    target_language = models.CharField(max_length=4, default="de")
    base_language = models.CharField(max_length=4, blank=True, default="")
    level = models.CharField(max_length=2, choices=LEVELS, blank=True, default="")
    topics = models.CharField(max_length=200, blank=True, default="")  # free tags, comma-separated

    is_active = models.BooleanField(default=True)
    # Did the creator agree to be featured? Not enforced anywhere — it's a record
    # so we can launch with the accounts that said yes (docs/plans/reels.md).
    permission_granted = models.BooleanField(default=False)
    permission_note = models.CharField(max_length=240, blank=True, default="")

    # The three cost knobs. results_limit is how many of the newest reels we ask
    # for per poll, and we are billed for every one of them — including reels we
    # already have. Keep it just above the account's posting rate.
    poll_interval_hours = models.PositiveIntegerField(default=24)
    results_limit = models.PositiveIntegerField(default=3)
    retention_days = models.PositiveIntegerField(
        null=True, blank=True, help_text="Blank = use the global default."
    )

    last_polled_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=20, blank=True, default="")
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kind", "username"]

    def __str__(self) -> str:
        return f"@{self.username}"

    @property
    def is_own(self) -> bool:
        return self.kind == OWN

    @property
    def instagram_url(self) -> str:
        return "" if self.is_own else f"https://www.instagram.com/{self.username}/"

    def is_due(self, now=None) -> bool:
        """Only Instagram sources are ever polled — `own` sources have nothing
        to fetch from."""
        if self.kind != INSTAGRAM or not self.is_active:
            return False
        if self.last_polled_at is None:
            return True
        now = now or timezone.now()
        return now >= self.last_polled_at + timezone.timedelta(hours=self.poll_interval_hours)


class Reel(models.Model):
    """One reel — scraped or uploaded. `key` is the dedupe identity and the
    reason rows outlive their media (see ReelPurgeLog / purge_expired_reel_media):
    delete the row and the next poll happily re-scrapes and re-bills the same
    reel."""

    source = models.ForeignKey(ReelSource, on_delete=models.CASCADE, related_name="reels")
    # Instagram shortcode for scraped reels; a generated slug for our own.
    key = models.CharField(max_length=80, unique=True)
    url = models.URLField(blank=True, default="")  # original reel, for attribution
    title = models.CharField(max_length=160, blank=True, default="")  # own reels
    caption = models.TextField(blank=True, default="")
    hashtags = models.JSONField(default=list, blank=True)

    video = models.FileField(upload_to="reels/", null=True, blank=True)
    poster = models.ImageField(upload_to="reel_posters/", null=True, blank=True)
    video_bytes = models.BigIntegerField(default=0)
    media_status = models.CharField(max_length=10, choices=MEDIA_STATUS, default=MEDIA_PENDING)
    media_purged_at = models.DateTimeField(null=True, blank=True)
    media_error = models.TextField(blank=True, default="")

    duration_seconds = models.FloatField(null=True, blank=True)
    view_count = models.BigIntegerField(default=0)
    like_count = models.BigIntegerField(default=0)
    comment_count = models.BigIntegerField(default=0)

    # Copied from the source at ingest, overridable per reel — a mostly-Persian
    # channel still posts the occasional immersive clip.
    target_language = models.CharField(max_length=4, default="de")
    base_language = models.CharField(max_length=4, blank=True, default="")
    level = models.CharField(max_length=2, choices=LEVELS, blank=True, default="")
    topics = models.CharField(max_length=200, blank=True, default="")

    # "Make cards from this reel", two ways (docs/plans/reels.md, Phase 4):
    #   * linked_deck — staff curated the cards; import is a plain deck copy,
    #     costs no AI and no quota. The strongest form, meant for own reels.
    #   * cards_cache — Gemini drafts built from the caption, generated ONCE
    #     per reel and reused by every later user. The per-user quota is still
    #     charged on each use (value delivered, not marginal cost) — see
    #     ReelMakeCardsView.
    linked_deck = models.ForeignKey(
        "decks.Deck",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reels",
        help_text="Optional: a curated deck that 'make cards from this reel' imports as-is.",
    )
    cards_cache = models.JSONField(default=list, blank=True)
    cards_generated_at = models.DateTimeField(null=True, blank=True)

    posted_at = models.DateTimeField(null=True, blank=True)  # Instagram's timestamp
    is_published = models.BooleanField(default=True)
    # Exempt from the retention purge. Defaults true for our own reels (set in
    # save()) — there is no re-scrape path if we delete those.
    is_evergreen = models.BooleanField(default=False)
    pin_until = models.DateTimeField(null=True, blank=True)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-posted_at", "-id"]
        indexes = [
            models.Index(fields=["is_published", "target_language", "-posted_at"]),
            models.Index(fields=["media_status"]),
        ]

    def __str__(self) -> str:
        return self.title or self.key

    def save(self, *args, **kwargs):
        if self.source_id and self.source.kind == OWN and not self.pk:
            self.is_evergreen = True
        super().save(*args, **kwargs)

    @property
    def is_playable(self) -> bool:
        return self.media_status == MEDIA_STORED and bool(self.video)


SUGGESTION_PENDING = "pending"
SUGGESTION_APPROVED = "approved"
SUGGESTION_REJECTED = "rejected"
SUGGESTION_STATUS = [
    (SUGGESTION_PENDING, "Pending"),
    (SUGGESTION_APPROVED, "Approved"),
    (SUGGESTION_REJECTED, "Rejected"),
]


class ReelSourceSuggestion(models.Model):
    """A user's "please add this Instagram account" — reviewed by staff in the
    admin, where an action turns an approved suggestion into a real
    ReelSource. Suggesters pick the languages themselves (they know what the
    channel teaches better than we do at review time); staff can still edit
    the created source afterwards."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="reel_source_suggestions",
    )
    username = models.CharField(max_length=80)  # no leading @
    target_language = models.CharField(max_length=4, default="de")
    base_language = models.CharField(max_length=4, blank=True, default="")
    status = models.CharField(max_length=10, choices=SUGGESTION_STATUS, default=SUGGESTION_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    handled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["status", "-created_at"]
        indexes = [models.Index(fields=["status"])]

    def __str__(self) -> str:
        return f"@{self.username} ({self.status})"


class ReelView(models.Model):
    """One user's relationship to one reel — seen, and optionally saved.
    Saved reels are exempt from the retention purge."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reel_views"
    )
    reel = models.ForeignKey(Reel, on_delete=models.CASCADE, related_name="views")
    seen_at = models.DateTimeField(auto_now_add=True)
    saved = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "reel"], name="unique_reel_view"),
        ]


class ReelFetchRun(models.Model):
    """One Apify run — the spend ledger. `cost_usd` is read back from the run's
    reported usage, not our own estimate, so the Costs page can reconcile."""

    STATUS = [
        ("running", "Running"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
        ("skipped", "Skipped (budget)"),
    ]

    sources = models.ManyToManyField(ReelSource, related_name="fetch_runs", blank=True)
    apify_run_id = models.CharField(max_length=40, blank=True, default="")
    status = models.CharField(max_length=12, choices=STATUS, default="running")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    items_returned = models.PositiveIntegerField(default=0)
    items_new = models.PositiveIntegerField(default=0)
    estimated_usd = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    cost_usd = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    triggered_by = models.CharField(max_length=80, default="cron")
    error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"run {self.pk} · {self.status} · ${self.cost_usd}"


class ReelPurgeLog(models.Model):
    """Every media purge, cron or manual. A destructive job should never be
    invisible."""

    ran_at = models.DateTimeField(auto_now_add=True)
    cutoff_date = models.DateTimeField(null=True, blank=True)
    reels_purged = models.PositiveIntegerField(default=0)
    bytes_freed = models.BigIntegerField(default=0)
    hard_delete = models.BooleanField(default=False)
    triggered_by = models.CharField(max_length=80, default="cron")

    class Meta:
        ordering = ["-ran_at"]


class ReelsStorageSnapshot(models.Model):
    """Daily storage reading. R2 bills GB-*month*, so the monthly figure is the
    mean of these — not a reading taken on the last day, which a purge on the
    29th would make look free."""

    day = models.DateField(unique=True)
    stored_bytes = models.BigIntegerField(default=0)
    reel_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-day"]


class ReelsCostMonth(models.Model):
    """Monthly cost roll-up. Deliberately separate from ReelFetchRun so the
    spend record outlives the reels it paid for."""

    month = models.CharField(max_length=7, unique=True)  # YYYY-MM
    reels_billed = models.PositiveIntegerField(default=0)
    reels_new = models.PositiveIntegerField(default=0)
    apify_usd = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    storage_gb_month = models.FloatField(default=0)
    storage_usd = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    total_usd = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-month"]

    def __str__(self) -> str:
        return f"{self.month} · ${self.total_usd}"


class ReelsBudget(models.Model):
    """Singleton settings row. Loaded via ReelsBudget.load()."""

    monthly_budget_usd = models.DecimalField(max_digits=8, decimal_places=2, default=5)
    month = models.CharField(max_length=7, blank=True, default="")  # YYYY-MM
    spent_this_month_usd = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    default_results_limit = models.PositiveIntegerField(default=3)
    default_retention_days = models.PositiveIntegerField(default=90)
    # Which alert thresholds have already fired this month, so each fires once.
    alerts_sent = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = "Reels budget"
        verbose_name_plural = "Reels budget"

    def __str__(self) -> str:
        return f"${self.spent_this_month_usd} / ${self.monthly_budget_usd}"

    @classmethod
    def load(cls) -> "ReelsBudget":
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create(
                # Decimal(str(...)): the setting comes straight from the
                # environment as a string, and every use of it is arithmetic.
                monthly_budget_usd=Decimal(str(settings.REELS_MONTHLY_BUDGET_USD)),
                default_retention_days=settings.REELS_RETENTION_DAYS or 90,
            )
        return obj.roll_month()

    def roll_month(self) -> "ReelsBudget":
        """Zero the spend counter when the calendar month turns over."""
        current = timezone.now().strftime("%Y-%m")
        if self.month != current:
            self.month = current
            self.spent_this_month_usd = 0
            self.alerts_sent = []
            self.save(update_fields=["month", "spent_this_month_usd", "alerts_sent"])
        return self
