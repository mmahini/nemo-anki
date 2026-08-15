"""What Reels costs, and the guard that stops it costing more.

Everything money-related lives here so the admin Costs page, the budget guard
and the monthly roll-up all read from one set of definitions rather than three
slightly different ones.

Two vendors, two very different shapes:
  * Apify — per reel *returned*. Predictable from our own config, and capped
    per-run by `maxTotalChargeUsd` plus the monthly guard below.
  * Cloudflare R2 — per GB-*month* stored, zero egress. That "month" matters:
    the monthly figure is the mean of daily snapshots, not a reading taken on
    the last day, which a purge on the 29th would make look free.
"""

import calendar
import logging
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db.models import Avg, Count, Sum
from django.utils import timezone

from core.telegram import send_telegram_message

from .models import (
    MEDIA_STORED,
    Reel,
    ReelFetchRun,
    ReelsBudget,
    ReelsCostMonth,
    ReelsStorageSnapshot,
)

logger = logging.getLogger(__name__)

GB = 1024**3
# R2 standard storage, $/GB-month, with the first 10 GB free.
R2_USD_PER_GB_MONTH = Decimal("0.015")
R2_FREE_GB = Decimal("10")


def rate_per_reel() -> Decimal:
    """Apify's charge for one reel returned."""
    return Decimal(str(settings.REELS_RATE_PER_1000)) / Decimal("1000")


def estimate_usd(reel_count: int) -> Decimal:
    return (rate_per_reel() * reel_count).quantize(Decimal("0.0001"))


def current_month() -> str:
    return timezone.now().strftime("%Y-%m")


# --- The budget guard --------------------------------------------------------


class BudgetExceeded(RuntimeError):
    """Raised instead of quietly trimming a run. A skipped fetch is logged as a
    ReelFetchRun so a silent no-op never looks like a successful poll."""

    def __init__(self, spent: Decimal, estimate: Decimal, budget: Decimal):
        self.spent, self.estimate, self.budget = spent, estimate, budget
        super().__init__(
            f"reels budget would be exceeded: ${spent} spent + ${estimate} "
            f"estimated > ${budget} budget"
        )


def check_budget(estimate: Decimal) -> ReelsBudget:
    """Raise BudgetExceeded unless this run fits in what's left of the month."""
    budget = ReelsBudget.load()
    if budget.spent_this_month_usd + estimate > budget.monthly_budget_usd:
        raise BudgetExceeded(
            budget.spent_this_month_usd, estimate, budget.monthly_budget_usd
        )
    return budget


def record_spend(actual_usd: Decimal) -> ReelsBudget:
    """Add a finished run's real cost to the month, then fire any newly crossed
    alert threshold."""
    budget = ReelsBudget.load()
    budget.spent_this_month_usd += Decimal(str(actual_usd))
    budget.save(update_fields=["spent_this_month_usd"])
    _maybe_alert(budget)
    return budget


def _maybe_alert(budget: ReelsBudget) -> None:
    """Telegram the team at 50/80/100% of budget — once per threshold per month.

    Nobody opens a dashboard daily, so the page alone isn't a control. 100% also
    means the guard has already stopped scraping, so that message explains an
    outage rather than merely warning about one.
    """
    if budget.monthly_budget_usd <= 0:
        return
    pct = float(budget.spent_this_month_usd / budget.monthly_budget_usd) * 100
    sent = list(budget.alerts_sent or [])
    for threshold in settings.REELS_BUDGET_ALERT_PCT:
        if pct >= threshold and threshold not in sent:
            sent.append(threshold)
            tail = (
                " Scraping is now paused until the budget is raised or the month rolls over."
                if threshold >= 100
                else ""
            )
            send_telegram_message(
                f"📹 Reels budget at {pct:.0f}% — "
                f"${budget.spent_this_month_usd:.2f} of ${budget.monthly_budget_usd:.2f} "
                f"used this month.{tail}"
            )
    if sent != list(budget.alerts_sent or []):
        budget.alerts_sent = sent
        budget.save(update_fields=["alerts_sent"])


# --- Storage -----------------------------------------------------------------


def stored_bytes() -> int:
    return Reel.objects.filter(media_status=MEDIA_STORED).aggregate(
        total=Sum("video_bytes")
    )["total"] or 0


def storage_usd(gb: Decimal | float) -> Decimal:
    """Bill only what's past R2's 10 GB free tier."""
    billable = max(Decimal(str(gb)) - R2_FREE_GB, Decimal("0"))
    return (billable * R2_USD_PER_GB_MONTH).quantize(Decimal("0.0001"))


def snapshot_storage() -> ReelsStorageSnapshot:
    total = stored_bytes()
    count = Reel.objects.filter(media_status=MEDIA_STORED).count()
    snap, _ = ReelsStorageSnapshot.objects.update_or_create(
        day=timezone.now().date(),
        defaults={"stored_bytes": total, "reel_count": count},
    )
    return snap


def month_storage_gb(month: str) -> float:
    """Mean of the month's daily snapshots, in GB — matching how R2 bills."""
    year, mon = (int(p) for p in month.split("-"))
    last = calendar.monthrange(year, mon)[1]
    avg = ReelsStorageSnapshot.objects.filter(
        day__gte=date(year, mon, 1), day__lte=date(year, mon, last)
    ).aggregate(avg=Avg("stored_bytes"))["avg"]
    return float(avg or 0) / GB


# --- Roll-up + reporting -----------------------------------------------------


def rollup_month(month: str | None = None) -> ReelsCostMonth:
    """Freeze a month's numbers into ReelsCostMonth. Kept separate from
    ReelFetchRun so the spend record outlives the reels it paid for — retention
    purges content, never cost history."""
    month = month or current_month()
    runs = ReelFetchRun.objects.filter(started_at__year=int(month[:4]), started_at__month=int(month[5:]))
    agg = runs.aggregate(
        billed=Sum("items_returned"), new=Sum("items_new"), spend=Sum("cost_usd")
    )
    gb = month_storage_gb(month)
    apify = Decimal(str(agg["spend"] or 0))
    storage = storage_usd(gb)
    obj, _ = ReelsCostMonth.objects.update_or_create(
        month=month,
        defaults={
            "reels_billed": agg["billed"] or 0,
            "reels_new": agg["new"] or 0,
            "apify_usd": apify,
            "storage_gb_month": gb,
            "storage_usd": storage,
            "total_usd": apify + storage,
        },
    )
    return obj


def month_projection(budget: ReelsBudget) -> Decimal:
    """Straight run-rate to month end. This is what turns the Costs page from a
    report into a control — it flags a coming breach while there's still time to
    lower a results_limit."""
    now = timezone.now()
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    elapsed = now.day
    if elapsed <= 0:
        return budget.spent_this_month_usd
    rate = budget.spent_this_month_usd / Decimal(elapsed)
    return (rate * Decimal(days_in_month)).quantize(Decimal("0.01"))


def per_source_costs(since=None) -> list[dict]:
    """Cost per source, sorted worst-first. This is the Costs page's real job:
    naming the account whose results_limit is set too high."""
    from .models import ReelSource

    runs = ReelFetchRun.objects.filter(status="succeeded")
    if since:
        runs = runs.filter(started_at__gte=since)

    rows = []
    for source in ReelSource.objects.all():
        source_runs = runs.filter(sources=source)
        # A batched run covers several sources; split its cost evenly rather
        # than attributing all of it to whichever source we look at first.
        billed = new = 0
        spend = Decimal("0")
        for run in source_runs.annotate(n_sources=Count("sources")):
            share = Decimal(run.n_sources or 1)
            billed += (run.items_returned or 0) // (run.n_sources or 1)
            new += (run.items_new or 0) // (run.n_sources or 1)
            spend += (run.cost_usd or Decimal("0")) / share
        stored = Reel.objects.filter(source=source, media_status=MEDIA_STORED).aggregate(
            b=Sum("video_bytes"), c=Count("id")
        )
        gb = float(stored["b"] or 0) / GB
        rows.append(
            {
                "source": source,
                "billed": billed,
                "new": new,
                "apify_usd": spend.quantize(Decimal("0.0001")),
                "stored_gb": gb,
                "stored_count": stored["c"] or 0,
                "per_new_usd": (spend / new).quantize(Decimal("0.0001")) if new else None,
            }
        )
    rows.sort(key=lambda r: r["apify_usd"], reverse=True)
    return rows


def reconcile() -> dict:
    """Our arithmetic vs what the vendors actually report. Without this, a
    silent billing surprise is possible; with it, the number on the page is
    trustworthy. A missing vendor figure stays None — never zero."""
    from . import apify as apify_client

    budget = ReelsBudget.load()
    ours = Decimal(budget.spent_this_month_usd)
    theirs = apify_client.account_usage_usd()
    drift = None
    if theirs is not None and ours > 0:
        drift = abs(float(ours) - theirs) / float(ours) * 100
    return {
        "apify_ours": ours,
        "apify_theirs": theirs,
        "apify_drift_pct": drift,
        "apify_diverged": drift is not None and drift > 5,
    }


def dashboard_summary() -> dict:
    """Everything the admin header and Costs page need, in one query pass."""
    budget = ReelsBudget.load()
    gb = Decimal(str(stored_bytes())) / Decimal(GB)
    store_usd = storage_usd(gb)
    month = current_month()
    runs = ReelFetchRun.objects.filter(
        started_at__year=int(month[:4]), started_at__month=int(month[5:])
    )
    agg = runs.aggregate(billed=Sum("items_returned"), new=Sum("items_new"))
    billed, new = agg["billed"] or 0, agg["new"] or 0
    pct = (
        float(budget.spent_this_month_usd / budget.monthly_budget_usd * 100)
        if budget.monthly_budget_usd
        else 0.0
    )
    return {
        "budget": budget,
        "month": month,
        "spent": budget.spent_this_month_usd,
        "budget_usd": budget.monthly_budget_usd,
        "budget_pct": min(pct, 100.0),
        "over_budget": pct >= 100,
        "projection": month_projection(budget),
        "reels_billed": billed,
        "reels_new": new,
        "per_new_usd": (
            (Decimal(budget.spent_this_month_usd) / new).quantize(Decimal("0.0001"))
            if new
            else None
        ),
        "stored_gb": float(gb),
        "storage_usd": store_usd,
        "total_usd": budget.spent_this_month_usd + store_usd,
    }
