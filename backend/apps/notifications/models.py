import secrets

from django.conf import settings
from django.db import models

from apps.cards.models import CardType


def _generate_connect_token() -> str:
    return secrets.token_urlsafe(32)


class TelegramLink(models.Model):
    """Links a user to their Telegram chat, for the study reminder's
    Telegram channel. `chat_id` is only known once the user has pressed
    Start on our bot via the `t.me/<bot>?start=<connect_token>` deep link
    (see apps.notifications.views.TelegramConnectView and the
    poll_telegram_updates management command that captures it)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="telegram_link"
    )
    chat_id = models.BigIntegerField(null=True, blank=True, unique=True)
    connect_token = models.CharField(max_length=43, unique=True, default=_generate_connect_token)
    created_at = models.DateTimeField(auto_now_add=True)
    # Set via the bot's `/lang de` or `/lang en` command — there's no other
    # source for "what language is this user studying" (see
    # apps.notifications.management.commands.poll_telegram_updates).
    default_language = models.CharField(max_length=4, blank=True, default="")
    default_back_language = models.CharField(max_length=32, default="English")

    # A word/sentence sent before default_language was set, so it isn't lost
    # — resumed automatically once /lang succeeds (see poll_telegram_updates
    # ._handle_lang). Deliberately separate from PendingTelegramCard: this is
    # "waiting for a language, AI never consulted yet", not "mid-wizard" —
    # conflating the two would overload PendingTelegramCard.awaiting_field's
    # meaning and the mid-wizard routing gate. "" means nothing is pending;
    # single slot — a newer attempt replaces an unresolved older one rather
    # than queuing.
    pending_lookup_text = models.CharField(max_length=200, blank=True, default="")
    pending_lookup_card_type = models.CharField(max_length=12, choices=CardType.choices, blank=True, default="")
    pending_lookup_expires_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.user.email} ({'connected' if self.chat_id else 'pending'})"


class PendingTelegramCard(models.Model):
    """A word/phrase the bot is walking the user through turning into a card:
    pick (or type) a translation, then pick (or type) a pronunciation, then
    it's saved as a real Card — see apps.notifications.management.commands
    .poll_telegram_updates. One per user — a new lookup replaces any
    unfinished previous one rather than piling up. Never itself the source
    of truth for a saved card; deleted once create_vocab_card runs."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # Which kind of card this row is becoming — set explicitly by whichever
    # flow created/reused it (word lookup vs. /sentence), since it can't be
    # reliably inferred from content (e.g. "none" article is also common for
    # plain vocab). Drives _finalize's deck choice, _regenerate's enrich_card
    # call, and _send_proposal's image-depictability framing.
    card_type = models.CharField(max_length=12, choices=CardType.choices, default=CardType.VOCAB)
    language = models.CharField(max_length=4, blank=True)
    front = models.CharField(max_length=200)
    back = models.TextField(blank=True)
    reading = models.CharField(max_length=200, blank=True)
    article = models.CharField(max_length=8, default="none")
    plural = models.CharField(max_length=200, blank=True)
    example = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # AI-suggested candidates shown as quick-pick buttons; empty means "ask
    # the user to type it" (no AI, or nothing plausible to offer).
    translation_options = models.JSONField(default=list, blank=True)
    pronunciation_options = models.JSONField(default=list, blank=True)
    # "back" = waiting for a translation (tap or type), "reading" = waiting
    # for a pronunciation (tap, type, or /skip), "" once the reading is in and
    # the Create/Edit proposal has been sent — see poll_telegram_updates.
    awaiting_field = models.CharField(max_length=8, blank=True, default="")
    # The auto-suggested image shown on the proposal screen, as a source URL
    # (not downloaded yet — Telegram fetches it directly for the preview).
    # Only pulled down for real, once, if the user taps Create.
    image_url = models.URLField(max_length=500, blank=True, default="")


class PushSubscription(models.Model):
    """A browser's Web Push registration (Push API + Service Worker) for a
    user — backs the study-reminder notification. `endpoint` is unique
    because it's issued per browser+origin by the push service, which also
    gives us a natural upsert key when the browser re-subscribes."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions"
    )
    endpoint = models.URLField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.user.email} ({self.endpoint[:40]}...)"
