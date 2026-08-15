"""Admin forms for the Reels dashboard."""

import re
import uuid

from django import forms
from django.utils import timezone
from django.utils.text import slugify

from .models import INSTAGRAM, MEDIA_STORED, OWN, Reel, ReelSource

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
# MP4 container brands we accept. We can't verify H.264/AAC without ffmpeg (not
# in the backend image — see docs/plans/reels.md), so we check the container and
# tell the uploader what the codec has to be.
MP4_BRANDS = {b"isom", b"iso2", b"mp41", b"mp42", b"avc1", b"M4V ", b"dash"}

SHORTCODE_RE = re.compile(r"instagram\.com/(?:reel|reels|p|tv)/([A-Za-z0-9_-]+)")


class ReelSourceForm(forms.ModelForm):
    """Register an Instagram account to poll, or one of our own channels."""

    class Meta:
        model = ReelSource
        fields = [
            "kind",
            "username",
            "display_name",
            "language",
            "level",
            "topics",
            "results_limit",
            "poll_interval_hours",
            "retention_days",
            "permission_granted",
            "permission_note",
            "is_active",
        ]

    def clean_username(self):
        username = (self.cleaned_data["username"] or "").strip().lstrip("@").lower()
        if not username:
            raise forms.ValidationError("A username is required.")
        return username

    def clean(self):
        data = super().clean()
        # Own channels are never polled, so the cost knobs are meaningless on
        # them — normalise rather than showing knobs that do nothing.
        if data.get("kind") == OWN:
            data["results_limit"] = 0
            data["poll_interval_hours"] = 0
        return data


class ManualReelForm(forms.Form):
    """Add a reel by uploading the file — our own recordings, and any
    hand-picked Instagram reel we want in the feed without running the scraper.

    Costs nothing: no Apify call is involved.
    """

    source = forms.ModelChoiceField(queryset=ReelSource.objects.all())
    title = forms.CharField(max_length=160, required=False)
    caption = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=False)
    video = forms.FileField(help_text="MP4 (H.264 video + AAC audio), max 50 MB.")
    poster = forms.ImageField(
        required=False,
        help_text="Recommended — without ffmpeg we can't extract a frame automatically.",
    )
    language = forms.CharField(max_length=4, initial="de")
    level = forms.ChoiceField(choices=[("", "—")] + Reel._meta.get_field("level").choices, required=False)
    topics = forms.CharField(max_length=200, required=False)
    original_url = forms.URLField(
        required=False,
        help_text="If this is someone else's reel, link the original — attribution is not optional.",
    )
    posted_at = forms.DateTimeField(required=False, help_text="Defaults to now.")
    pin_until = forms.DateTimeField(
        required=False, help_text="While set and in the future, this reel leads the feed."
    )

    def clean_video(self):
        video = self.cleaned_data["video"]
        if video.size > MAX_UPLOAD_BYTES:
            raise forms.ValidationError(
                f"Video is {video.size / 1024 / 1024:.1f} MB — the limit is 50 MB."
            )
        if not video.name.lower().endswith(".mp4"):
            raise forms.ValidationError("Only .mp4 files play reliably on iOS. Please convert first.")
        head = video.read(12)
        video.seek(0)
        # bytes 4-8 are 'ftyp', 8-12 the major brand.
        if head[4:8] != b"ftyp" or head[8:12] not in MP4_BRANDS:
            raise forms.ValidationError(
                "That doesn't look like an MP4 container. Export as MP4 with H.264 video "
                "and AAC audio — it's the only combination that plays reliably in iOS Safari."
            )
        return video

    def clean(self):
        data = super().clean()
        source = data.get("source")
        url = data.get("original_url") or ""
        if source and source.kind == INSTAGRAM and not url:
            self.add_error(
                "original_url",
                "An Instagram source needs the original reel URL for attribution.",
            )
        return data

    def build_key(self) -> str:
        """The dedupe identity. For a hand-added Instagram reel we reuse the
        real shortcode so a later scrape of the same account doesn't duplicate
        it; for our own we generate a slug."""
        url = self.cleaned_data.get("original_url") or ""
        match = SHORTCODE_RE.search(url)
        if match:
            return match.group(1)
        stem = slugify(self.cleaned_data.get("title") or "")[:40]
        source = self.cleaned_data["source"]
        return f"{source.username}-{stem or 'reel'}-{uuid.uuid4().hex[:6]}"

    def save(self) -> Reel:
        data = self.cleaned_data
        source = data["source"]
        key = self.build_key()
        reel = Reel(
            source=source,
            key=key,
            url=data.get("original_url") or "",
            title=data.get("title") or "",
            caption=data.get("caption") or "",
            language=data.get("language") or source.language,
            level=data.get("level") or source.level,
            topics=data.get("topics") or source.topics,
            posted_at=data.get("posted_at") or timezone.now(),
            pin_until=data.get("pin_until"),
        )
        # Name the stored objects after the key, exactly as ingest.store_media
        # does for scraped reels, so every reel's CDN path is reels/<key>.mp4
        # rather than whatever the uploader happened to call the file.
        reel.video.save(f"{key}.mp4", data["video"], save=False)
        reel.video_bytes = data["video"].size
        if data.get("poster"):
            reel.poster.save(f"{key}.jpg", data["poster"], save=False)
        reel.media_status = MEDIA_STORED
        reel.save()
        return reel


class PurgeForm(forms.Form):
    """Delete stored media for reels posted before a date. Preview always runs
    first — a one-click irreversible bulk delete on a page you also browse daily
    is how a library gets wiped by accident."""

    cutoff = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Purge media for reels posted before this date.",
    )
    confirm = forms.BooleanField(required=False, widget=forms.HiddenInput)

    def cutoff_dt(self):
        return timezone.make_aware(
            timezone.datetime.combine(self.cleaned_data["cutoff"], timezone.datetime.min.time())
        )
