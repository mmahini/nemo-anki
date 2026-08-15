"""Scheduled and on-demand Reels jobs.

Phase 1 arms none of these on a schedule — the only way to spend money is a
staff member clicking "Fetch now" in the admin. `poll_reel_sources` and
`purge_expired_reel_media` are wired into CELERY_BEAT_SCHEDULE but gated behind
REELS_SCRAPING_ENABLED / REELS_RETENTION_DAYS, both unset by default.

Note the deployment can run with CELERY_TASK_ALWAYS_EAGER, so every task here
must be safe to run inline in a web request.
"""

import logging
from decimal import Decimal

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import apify, costs, ingest
from .models import (
    INSTAGRAM,
    MEDIA_PURGED,
    MEDIA_STORED,
    OWN,
    Reel,
    ReelFetchRun,
    ReelPurgeLog,
    ReelSource,
)

logger = logging.getLogger(__name__)


@shared_task
def poll_reel_sources(force_source_ids=None, triggered_by="cron"):
    """Fetch new reels for every source that's due.

    Sources are batched into one Apify run per `results_limit` group — the actor
    takes a list of usernames, so N accounts cost the same as N separate runs
    with far less overhead.
    """
    if force_source_ids is None and not settings.REELS_SCRAPING_ENABLED:
        logger.info("reels: scraping disabled, skipping poll")
        return {"skipped": "disabled"}

    if force_source_ids:
        due = list(ReelSource.objects.filter(id__in=force_source_ids, kind=INSTAGRAM))
    else:
        now = timezone.now()
        due = [s for s in ReelSource.objects.filter(kind=INSTAGRAM, is_active=True) if s.is_due(now)]

    if not due:
        return {"sources": 0}

    results = []
    groups: dict[int, list[ReelSource]] = {}
    for source in due:
        groups.setdefault(source.results_limit, []).append(source)
    for limit, sources in groups.items():
        results.append(_run_batch(sources, limit, triggered_by))
    return {"sources": len(due), "runs": results}


def _run_batch(sources: list[ReelSource], results_limit: int, triggered_by: str) -> dict:
    """One Apify run covering several usernames at the same results_limit."""
    estimate = costs.estimate_usd(len(sources) * results_limit)
    run = ReelFetchRun.objects.create(estimated_usd=estimate, triggered_by=triggered_by)
    run.sources.set(sources)

    try:
        costs.check_budget(estimate)
    except costs.BudgetExceeded as exc:
        # Skipped and logged, never silently trimmed — a no-op must not look
        # like a successful poll.
        run.status = "skipped"
        run.error = str(exc)
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "finished_at"])
        logger.warning("reels: %s", exc)
        return {"run": run.pk, "status": "skipped"}

    usernames = [s.username for s in sources]
    try:
        items, apify_run_id, cost = apify.run_reel_scraper(
            usernames,
            results_limit,
            # 20% headroom over the estimate: enough that a slightly fatter
            # response isn't truncated, low enough to bound a runaway.
            max_total_charge_usd=float(estimate) * 1.2,
        )
    except apify.ApifyError as exc:
        run.status = "failed"
        run.error = str(exc)
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "finished_at"])
        ReelSource.objects.filter(id__in=[s.id for s in sources]).update(
            last_status="failed", last_error=str(exc)[:500], last_polled_at=timezone.now()
        )
        logger.warning("reels: fetch failed for %s: %s", usernames, exc)
        return {"run": run.pk, "status": "failed"}

    # Record the charge the moment we know we've been charged, before any of
    # the work that could still fail. Apify has already billed us by this point;
    # if item processing or queueing blows up afterwards the money must still be
    # in the ledger, or the Costs page quietly under-reports real spend.
    run.apify_run_id = apify_run_id
    run.cost_usd = Decimal(str(cost))
    run.save(update_fields=["apify_run_id", "cost_usd"])
    costs.record_spend(run.cost_usd)

    by_username = {s.username.lower(): s for s in sources}
    pending_ingest = []
    new_ids = []
    for raw in items:
        parsed = apify.normalise_item(raw)
        if not parsed:
            continue
        source = by_username.get(parsed["owner_username"]) or sources[0]
        reel, created = Reel.objects.get_or_create(
            key=parsed["key"],
            defaults={
                "source": source,
                "url": parsed["url"],
                "caption": parsed["caption"],
                "hashtags": parsed["hashtags"],
                "duration_seconds": parsed["duration_seconds"],
                "view_count": parsed["view_count"],
                "like_count": parsed["like_count"],
                "comment_count": parsed["comment_count"],
                "posted_at": parsed["posted_at"],
                "language": source.language,
                "level": source.level,
                "topics": source.topics,
            },
        )
        if created:
            new_ids.append(reel.pk)
            pending_ingest.append((reel.pk, parsed["video_url"], parsed["poster_url"]))

    run.status = "succeeded"
    run.items_returned = len(items)
    run.items_new = len(new_ids)
    run.finished_at = timezone.now()
    run.save()

    ReelSource.objects.filter(id__in=[s.id for s in sources]).update(
        last_status="succeeded", last_error="", last_polled_at=timezone.now()
    )

    # Best-effort, and deliberately last. Signed CDN links expire within days so
    # this wants to run now, but a broker outage must not undo a fetch we've
    # already paid for — the reels stay `pending` and can be re-ingested.
    transaction.on_commit(lambda: _queue_ingest(pending_ingest))
    return {
        "run": run.pk,
        "status": "succeeded",
        "returned": len(items),
        "new": len(new_ids),
        "cost": float(cost),
    }


def _queue_ingest(jobs: list[tuple[int, str, str]]) -> None:
    """Hand each new reel to the ingest task, surviving a broker that's down."""
    for reel_id, video_url, poster_url in jobs:
        try:
            ingest_reel_media.delay(reel_id, video_url, poster_url)
        except Exception:  # noqa: BLE001 — the fetch is already paid for and saved
            logger.warning("reels: could not queue ingest for reel %s", reel_id, exc_info=True)
            Reel.objects.filter(pk=reel_id).update(
                media_error="ingest not queued — broker unavailable"
            )


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def ingest_reel_media(self, reel_id: int, video_url: str, poster_url: str):
    reel = Reel.objects.filter(pk=reel_id).first()
    if reel is None:
        return {"missing": reel_id}
    if ingest.store_media(reel, video_url, poster_url):
        return {"reel": reel_id, "bytes": reel.video_bytes}
    if self.request.retries < self.max_retries:
        raise self.retry()
    return {"reel": reel_id, "failed": True}


def purge_queryset(cutoff, source=None):
    """Reels eligible for a media purge before `cutoff`.

    Three exclusions, in order of how badly getting them wrong would hurt:
      * our own reels — no re-upload path if we delete them, so this is enforced
        at the query, not via a flag someone can bulk-toggle;
      * evergreen — the hand-picked "best of" that outlives the TTL;
      * saved by a user — purging out from under someone's saved list is a bad
        trade for a rounding error of storage.
    """
    qs = Reel.objects.filter(media_status=MEDIA_STORED, posted_at__lt=cutoff)
    qs = qs.exclude(source__kind=OWN).exclude(is_evergreen=True).exclude(views__saved=True)
    if source is not None:
        qs = qs.filter(source=source)
    return qs.distinct()


def purge_preview(cutoff) -> dict:
    """What a purge *would* do. The admin runs this before offering Confirm —
    the same queryset, so the preview can't drift from the action."""
    qs = purge_queryset(cutoff)
    from django.db.models import Count, Sum

    agg = qs.aggregate(n=Count("id"), b=Sum("video_bytes"))
    candidates = Reel.objects.filter(media_status=MEDIA_STORED, posted_at__lt=cutoff)
    return {
        "count": agg["n"] or 0,
        "bytes": agg["b"] or 0,
        "skipped_own": candidates.filter(source__kind=OWN).count(),
        "skipped_evergreen": candidates.exclude(source__kind=OWN).filter(is_evergreen=True).count(),
        "skipped_saved": candidates.exclude(source__kind=OWN)
        .exclude(is_evergreen=True)
        .filter(views__saved=True)
        .distinct()
        .count(),
    }


@shared_task
def purge_expired_reel_media(cutoff=None, triggered_by="cron"):
    """Delete stored media past the retention window, keeping the rows."""
    if cutoff is None:
        days = settings.REELS_RETENTION_DAYS
        if not days:
            return {"skipped": "retention disabled"}
        cutoff = timezone.now() - timezone.timedelta(days=days)

    freed = count = 0
    for reel in purge_queryset(cutoff).iterator():
        freed += ingest.delete_media(reel)
        reel.media_status = MEDIA_PURGED
        reel.media_purged_at = timezone.now()
        reel.save(update_fields=["video", "poster", "video_bytes", "media_status", "media_purged_at"])
        count += 1

    ReelPurgeLog.objects.create(
        cutoff_date=cutoff, reels_purged=count, bytes_freed=freed, triggered_by=triggered_by
    )
    return {"purged": count, "bytes_freed": freed}


@shared_task
def snapshot_reels_storage():
    """Daily storage reading + a refresh of this month's roll-up."""
    snap = costs.snapshot_storage()
    month = costs.rollup_month()
    return {"bytes": snap.stored_bytes, "month": month.month, "total_usd": float(month.total_usd)}
