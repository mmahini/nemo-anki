"""The daily Reels job, as a management command.

Production has no Celery worker — the deployment is a single free-tier web
service (see core.settings CELERY_TASK_ALWAYS_EAGER), so `celery beat` never
runs there. This command is what the GitHub Actions schedule invokes instead
(.github/workflows/reels-poll.yml), the same way keepalive.yml already stands in
for a cron daemon.

Running it on the Actions runner rather than through an HTTP endpoint matters:
downloading ~60 videos and pushing them to R2 would blow straight past gunicorn's
30s request timeout, and the runner has both the time budget and the bandwidth.

    python manage.py poll_reels --dry-run     # what's due, and what it'd cost
    python manage.py poll_reels               # fetch, ingest, purge, snapshot
"""

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.reels import costs, tasks
from apps.reels.models import INSTAGRAM, ReelsBudget, ReelSource


class Command(BaseCommand):
    help = "Fetch new reels for every due source, then purge and snapshot."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what's due and the estimated cost. Spends nothing.",
        )
        parser.add_argument(
            "--skip-purge", action="store_true", help="Don't run the retention purge."
        )

    def handle(self, *args, **options):
        budget = ReelsBudget.load()
        now = timezone.now()
        due = [s for s in ReelSource.objects.filter(kind=INSTAGRAM, is_active=True) if s.is_due(now)]
        estimate = costs.estimate_usd(sum(s.results_limit for s in due))

        self.stdout.write(f"Due sources     : {len(due)}")
        for source in due:
            self.stdout.write(f"  @{source.username} (limit {source.results_limit})")
        self.stdout.write(f"Estimated cost  : ${estimate}")
        self.stdout.write(
            f"Budget          : ${budget.spent_this_month_usd} / "
            f"${budget.monthly_budget_usd} used this month"
        )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — nothing spent."))
            return

        if not settings.REELS_SCRAPING_ENABLED:
            self.stdout.write(
                self.style.WARNING("REELS_SCRAPING_ENABLED is not True — skipping the fetch.")
            )
        elif due:
            result = tasks.poll_reel_sources(triggered_by="github-actions")
            failed = []
            for run in result.get("runs", []):
                self.stdout.write(f"  run {run.get('run')}: {run}")
                if run.get("status") == "failed":
                    failed.append(run)
                elif run.get("status") == "skipped":
                    self.stdout.write(
                        self.style.WARNING("  budget guard stopped this run — nothing spent.")
                    )
            if failed:
                # Non-zero exit so the workflow goes red; a skipped-for-budget
                # run is expected behaviour and stays green.
                raise SystemExit(f"{len(failed)} fetch run(s) failed")

        if not options["skip_purge"]:
            self.stdout.write(f"Purge           : {tasks.purge_expired_reel_media()}")

        snap = tasks.snapshot_reels_storage()
        self.stdout.write(f"Snapshot        : {snap}")

        summary = costs.dashboard_summary()
        self.stdout.write(
            self.style.SUCCESS(
                f"Month to date   : Apify ${summary['spent']} + storage "
                f"${summary['storage_usd']} = ${summary['total_usd']} "
                f"(projected ${summary['projection']})"
            )
        )
