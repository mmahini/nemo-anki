from rest_framework import serializers

from apps.accounts.languages import label as language_label

from .models import Reel


class ReelSerializer(serializers.ModelSerializer):
    video_url = serializers.SerializerMethodField()
    poster_url = serializers.SerializerMethodField()
    source_username = serializers.CharField(source="source.username", read_only=True)
    source_name = serializers.CharField(source="source.display_name", read_only=True)
    source_avatar = serializers.SerializerMethodField()
    is_ours = serializers.SerializerMethodField()
    teaches = serializers.SerializerMethodField()
    saved = serializers.SerializerMethodField()

    class Meta:
        model = Reel
        fields = [
            "id", "key", "title", "caption", "hashtags",
            "video_url", "poster_url", "duration_seconds",
            "source_username", "source_name", "source_avatar", "is_ours",
            "target_language", "base_language", "teaches", "level",
            # The original post. Kept even though most of our users can't open
            # it — attribution is not conditional on the link being reachable.
            "url",
            "posted_at", "saved",
        ]

    def _media_url(self, field) -> str | None:
        """Always absolute.

        With R2 configured the storage already returns a full URL. Without it
        (local dev, or if the R2 vars ever went missing in prod) it returns
        `/media/...`, which the frontend would resolve against *its own* origin
        — a different host — and 404. Absolutising here keeps the client from
        having to know where media lives.
        """
        if not field:
            return None
        url = field.url
        if url.startswith("http"):
            return url
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url

    def get_video_url(self, obj) -> str | None:
        return self._media_url(obj.video)

    def get_poster_url(self, obj) -> str | None:
        return self._media_url(obj.poster)

    def get_source_avatar(self, obj) -> str | None:
        return self._media_url(obj.source.avatar)

    def get_is_ours(self, obj) -> bool:
        return obj.source.kind == "own"

    def get_teaches(self, obj) -> str:
        target = language_label(obj.target_language)
        if not obj.base_language:
            return target
        return f"{target} · {language_label(obj.base_language)}"

    def get_saved(self, obj) -> bool:
        """Prefetched by the view — never a query per row."""
        saved_ids = self.context.get("saved_ids")
        return obj.id in saved_ids if saved_ids is not None else False
