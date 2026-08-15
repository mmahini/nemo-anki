"""Reels staff tooling.

Two custom views hang off ReelSourceAdmin:
  * /admin/reels/reelsource/dashboard/ — add sources, upload reels, fetch now,
    browse and moderate, purge.
  * /admin/reels/reelsource/costs/ — every expense this feature generates, with
    a month-end projection and a reconciliation against the vendors' own
    numbers, so cost is answerable without logging into Apify or Cloudflare.

The per-model admins below stay as the detail/edit views.
"""

from datetime import timedelta

from django.contrib import admin, messages
from django.db.models import Count, Sum
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from apps.accounts.languages import label as language_label

from . import costs, ingest, tasks
from .forms import ManualReelForm, PurgeForm, ReelSourceForm
from .models import (
    INSTAGRAM,
    MEDIA_PURGED,
    MEDIA_STORED,
    OWN,
    Reel,
    ReelFetchRun,
    ReelPurgeLog,
    ReelsBudget,
    ReelsCostMonth,
    ReelSource,
    ReelsStorageSnapshot,
    ReelView,
)


def _mb(value) -> str:
    return f"{(value or 0) / 1024 / 1024:.1f} MB"


@admin.register(ReelSource)
class ReelSourceAdmin(admin.ModelAdmin):
    list_display = (
        "username",
        "kind",
        "teaches",
        "is_active",
        "permission_granted",
        "results_limit",
        "poll_interval_hours",
        "retention_days",
        "last_polled_at",
        "reel_count",
    )
    list_filter = ("kind", "is_active", "target_language", "base_language", "permission_granted")
    search_fields = ("username", "display_name")
    actions = ["fetch_now", "apply_languages", "activate", "deactivate"]

    @admin.display(description="Teaches")
    def teaches(self, obj) -> str:
        """"German in Persian", or "German (immersive)" when there's no
        translation language."""
        target = language_label(obj.target_language)
        if not obj.base_language:
            return f"{target} (immersive)"
        return f"{target} in {language_label(obj.base_language)}"

    @admin.display(description="Reels")
    def reel_count(self, obj) -> int:
        return obj.reels.count()

    def get_urls(self):
        return [
            path(
                "dashboard/",
                self.admin_site.admin_view(self.dashboard_view),
                name="reels_dashboard",
            ),
            path("costs/", self.admin_site.admin_view(self.costs_view), name="reels_costs"),
        ] + super().get_urls()

    # --- actions ---------------------------------------------------------

    @admin.action(description="Fetch now (costs money)")
    def fetch_now(self, request, queryset):
        ids = list(queryset.filter(kind=INSTAGRAM).values_list("id", flat=True))
        if not ids:
            self.message_user(request, "No Instagram sources selected.", messages.WARNING)
            return
        result = tasks.poll_reel_sources(force_source_ids=ids, triggered_by=request.user.email)
        self.message_user(request, f"Fetch finished: {result}", messages.INFO)

    @admin.action(description="Apply this channel's languages to its existing reels")
    def apply_languages(self, request, queryset):
        """Reels copy the source's language pair at ingest, so correcting a
        source afterwards leaves everything already fetched pointing at the
        wrong pair — and silently out of (or into) people's feeds."""
        total = 0
        for source in queryset:
            total += source.reels.exclude(
                target_language=source.target_language, base_language=source.base_language
            ).update(
                target_language=source.target_language, base_language=source.base_language
            )
        self.message_user(request, f"Updated {total} reels to match their channel.")

    @admin.action(description="Activate")
    def activate(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=True)} activated.")

    @admin.action(description="Deactivate")
    def deactivate(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=False)} deactivated.")

    # --- dashboard -------------------------------------------------------

    def dashboard_view(self, request):
        source_form = ReelSourceForm()
        reel_form = ManualReelForm()
        purge_form = PurgeForm()
        preview = None

        if request.method == "POST":
            action = request.POST.get("action")
            if action == "add_source":
                source_form = ReelSourceForm(request.POST)
                if source_form.is_valid():
                    source = source_form.save()
                    messages.success(request, f"Added @{source.username}.")
                    return redirect("admin:reels_dashboard")
            elif action == "add_reel":
                reel_form = ManualReelForm(request.POST, request.FILES)
                if reel_form.is_valid():
                    reel = reel_form.save()
                    messages.success(request, f"Uploaded “{reel}” — no scraping cost.")
                    return redirect("admin:reels_dashboard")
            elif action in {"purge_preview", "purge_confirm"}:
                purge_form = PurgeForm(request.POST)
                if purge_form.is_valid():
                    cutoff = purge_form.cutoff_dt()
                    if action == "purge_preview":
                        preview = tasks.purge_preview(cutoff)
                        preview["cutoff"] = cutoff
                    else:
                        result = tasks.purge_expired_reel_media(
                            cutoff=cutoff, triggered_by=request.user.email
                        )
                        messages.success(
                            request,
                            f"Purged {result['purged']} reels, freed {_mb(result['bytes_freed'])}.",
                        )
                        return redirect("admin:reels_dashboard")
            elif action == "fetch_source":
                source = ReelSource.objects.filter(pk=request.POST.get("source_id")).first()
                if source:
                    result = tasks.poll_reel_sources(
                        force_source_ids=[source.pk], triggered_by=request.user.email
                    )
                    messages.info(request, f"@{source.username}: {result}")
                return redirect("admin:reels_dashboard")

        summary = costs.dashboard_summary()
        sources = ReelSource.objects.annotate(
            n_reels=Count("reels"), stored=Sum("reels__video_bytes")
        )
        reels = Reel.objects.select_related("source").order_by("-posted_at", "-id")[:60]

        next_purge = None
        if request.GET.get("kind") or True:
            days = ReelsBudget.load().default_retention_days
            if days:
                cutoff = timezone.now() - timedelta(days=days)
                next_purge = tasks.purge_preview(cutoff)
                next_purge["cutoff"] = cutoff

        context = {
            **self.admin_site.each_context(request),
            "title": "Reels dashboard",
            "summary": summary,
            "sources": sources,
            "reels": reels,
            "source_form": source_form,
            "reel_form": reel_form,
            "purge_form": purge_form,
            "preview": preview,
            "next_purge": next_purge,
            "costs_url": reverse("admin:reels_costs"),
        }
        return render(request, "admin/reels/dashboard.html", context)

    # --- costs -----------------------------------------------------------

    def costs_view(self, request):
        if request.method == "POST" and request.POST.get("action") == "save_budget":
            budget = ReelsBudget.load()
            budget.monthly_budget_usd = request.POST.get("monthly_budget_usd") or 0
            budget.default_results_limit = request.POST.get("default_results_limit") or 3
            budget.default_retention_days = request.POST.get("default_retention_days") or 90
            budget.save()
            messages.success(request, "Budget updated.")
            return redirect("admin:reels_costs")

        since = timezone.now() - timedelta(days=int(request.GET.get("days", 30)))
        context = {
            **self.admin_site.each_context(request),
            "title": "Reels costs",
            "summary": costs.dashboard_summary(),
            "history": ReelsCostMonth.objects.all()[:12],
            "per_source": costs.per_source_costs(since=since),
            "since_days": int(request.GET.get("days", 30)),
            "reconcile": costs.reconcile(),
            "runs": ReelFetchRun.objects.prefetch_related("sources")[:20],
            "dashboard_url": reverse("admin:reels_dashboard"),
        }
        return render(request, "admin/reels/costs.html", context)


@admin.register(Reel)
class ReelAdmin(admin.ModelAdmin):
    list_display = (
        "thumb",
        "__str__",
        "source",
        "teaches",
        "level",
        "posted_at",
        "media_status",
        "size",
        "is_published",
        "is_evergreen",
    )
    list_filter = (
        "source__kind", "media_status", "is_published", "is_evergreen",
        "target_language", "base_language", "source",
    )
    search_fields = ("key", "title", "caption")
    readonly_fields = ("video_bytes", "media_purged_at", "fetched_at")
    actions = ["publish", "unpublish", "mark_evergreen", "purge_media", "hard_delete"]

    @admin.display(description="Teaches")
    def teaches(self, obj) -> str:
        target = language_label(obj.target_language)
        if not obj.base_language:
            return f"{target} (immersive)"
        return f"{target} in {language_label(obj.base_language)}"

    @admin.display(description="")
    def thumb(self, obj):
        if obj.poster:
            return format_html('<img src="{}" style="height:56px;border-radius:4px">', obj.poster.url)
        return "—"

    @admin.display(description="Size")
    def size(self, obj):
        return _mb(obj.video_bytes)

    @admin.action(description="Publish")
    def publish(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_published=True)} published.")

    @admin.action(description="Unpublish")
    def unpublish(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_published=False)} unpublished.")

    @admin.action(description="Mark evergreen (exempt from purge)")
    def mark_evergreen(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_evergreen=True)} marked evergreen.")

    @admin.action(description="Purge media (keep the row)")
    def purge_media(self, request, queryset):
        freed = count = 0
        for reel in queryset.filter(media_status=MEDIA_STORED):
            if reel.source.kind == OWN:
                continue  # never purge our own content — there is no way back
            freed += ingest.delete_media(reel)
            reel.media_status = MEDIA_PURGED
            reel.media_purged_at = timezone.now()
            reel.save()
            count += 1
        ReelPurgeLog.objects.create(
            reels_purged=count, bytes_freed=freed, triggered_by=request.user.email
        )
        self.message_user(request, f"Purged {count} reels, freed {_mb(freed)}.")

    @admin.action(description="Hard delete (re-scraping these will cost money again)")
    def hard_delete(self, request, queryset):
        count = queryset.count()
        for reel in queryset:
            ingest.delete_media(reel)
        queryset.delete()
        ReelPurgeLog.objects.create(
            reels_purged=count, hard_delete=True, triggered_by=request.user.email
        )
        self.message_user(
            request,
            f"Deleted {count} reels including their rows. If any are still among their "
            "account's newest posts, the next poll will re-scrape and re-bill them.",
            messages.WARNING,
        )


@admin.register(ReelFetchRun)
class ReelFetchRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "started_at",
        "status",
        "items_returned",
        "items_new",
        "estimated_usd",
        "cost_usd",
        "triggered_by",
    )
    list_filter = ("status",)
    readonly_fields = [f.name for f in ReelFetchRun._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(ReelPurgeLog)
class ReelPurgeLogAdmin(admin.ModelAdmin):
    list_display = ("ran_at", "cutoff_date", "reels_purged", "freed", "hard_delete", "triggered_by")
    readonly_fields = [f.name for f in ReelPurgeLog._meta.fields]

    @admin.display(description="Freed")
    def freed(self, obj):
        return _mb(obj.bytes_freed)

    def has_add_permission(self, request):
        return False


@admin.register(ReelsCostMonth)
class ReelsCostMonthAdmin(admin.ModelAdmin):
    list_display = (
        "month",
        "reels_billed",
        "reels_new",
        "apify_usd",
        "storage_gb_month",
        "storage_usd",
        "total_usd",
    )
    readonly_fields = [f.name for f in ReelsCostMonth._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(ReelsStorageSnapshot)
class ReelsStorageSnapshotAdmin(admin.ModelAdmin):
    list_display = ("day", "reel_count", "size")
    readonly_fields = [f.name for f in ReelsStorageSnapshot._meta.fields]

    @admin.display(description="Stored")
    def size(self, obj):
        return _mb(obj.stored_bytes)

    def has_add_permission(self, request):
        return False


@admin.register(ReelsBudget)
class ReelsBudgetAdmin(admin.ModelAdmin):
    list_display = (
        "month",
        "spent_this_month_usd",
        "monthly_budget_usd",
        "default_results_limit",
        "default_retention_days",
    )

    def has_add_permission(self, request):
        return not ReelsBudget.objects.exists()


@admin.register(ReelView)
class ReelViewAdmin(admin.ModelAdmin):
    list_display = ("user", "reel", "seen_at", "saved")
    list_filter = ("saved",)
    search_fields = ("user__email", "reel__key")
