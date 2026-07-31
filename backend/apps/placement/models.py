from django.conf import settings
from django.db import models

LEVELS = ["A1", "A2", "B1", "B2", "C1"]
LEVEL_CHOICES = [(lvl, lvl) for lvl in LEVELS]


class PlacementAttempt(models.Model):
    """One take of the Reading + Listening placement test."""

    LANGUAGE_CHOICES = [("de", "German"), ("en", "English")]
    LENGTH_CHOICES = [("quick", "Quick (10 questions)"), ("full", "Full (20 questions)")]
    STATUS_CHOICES = [("in_progress", "In progress"), ("completed", "Completed")]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="placement_attempts"
    )
    language = models.CharField(max_length=2, choices=LANGUAGE_CHOICES)
    length = models.CharField(max_length=10, choices=LENGTH_CHOICES)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="in_progress")
    estimated_level = models.CharField(max_length=2, choices=LEVEL_CHOICES, blank=True, default="")
    correct_count = models.PositiveSmallIntegerField(default=0)
    total_count = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class PlacementQuestion(models.Model):
    """One AI-generated multiple-choice question within an attempt."""

    SECTION_CHOICES = [("reading", "Reading"), ("listening", "Listening")]

    attempt = models.ForeignKey(PlacementAttempt, on_delete=models.CASCADE, related_name="questions")
    order = models.PositiveSmallIntegerField()
    section = models.CharField(max_length=10, choices=SECTION_CHOICES)
    level_tag = models.CharField(max_length=2, choices=LEVEL_CHOICES)
    # Reading: shown to the user. Listening: only spoken via TTS, never shown
    # before they answer — exactly one of these is populated per question.
    passage = models.TextField(blank=True, default="")
    audio_text = models.TextField(blank=True, default="")
    question_text = models.TextField()
    choices = models.JSONField()
    correct_choice_index = models.PositiveSmallIntegerField()
    user_choice_index = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["order"]
