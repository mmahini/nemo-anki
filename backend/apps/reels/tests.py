"""Tests for the parts of Reels where being wrong costs money or loses content:
the budget guard, the purge exclusions, and the cost arithmetic.
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.languages import clean_codes

from . import costs, matching, tasks
from .forms import ManualReelForm
from .models import (
    INSTAGRAM,
    MEDIA_PURGED,
    MEDIA_STORED,
    OWN,
    Reel,
    ReelFetchRun,
    ReelPurgeLog,
    ReelsBudget,
    ReelSource,
    ReelsStorageSnapshot,
    ReelView,
)

User = get_user_model()

# Minimal valid-looking MP4 header: 4 size bytes, 'ftyp', then a known brand.
MP4_HEAD = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64


def make_source(**kwargs):
    defaults = {
        "username": "deutsch", "kind": INSTAGRAM, "results_limit": 3,
        "target_language": "de", "base_language": "",
    }
    return ReelSource.objects.create(**{**defaults, **kwargs})


def make_reel(source, key="abc", days_old=200, **kwargs):
    defaults = {
        "posted_at": timezone.now() - timedelta(days=days_old),
        "media_status": MEDIA_STORED,
        "video_bytes": 6 * 1024 * 1024,
    }
    return Reel.objects.create(source=source, key=key, **{**defaults, **kwargs})


class BudgetGuardTests(TestCase):
    def test_estimate_uses_the_configured_rate(self):
        with override_settings(REELS_RATE_PER_1000=2.60):
            self.assertEqual(costs.estimate_usd(1000), Decimal("2.6000"))
            self.assertEqual(costs.estimate_usd(60), Decimal("0.1560"))

    def test_check_budget_raises_once_the_month_is_spent(self):
        budget = ReelsBudget.load()
        budget.monthly_budget_usd = Decimal("5.00")
        budget.spent_this_month_usd = Decimal("4.90")
        budget.save()
        costs.check_budget(Decimal("0.05"))  # fits
        with self.assertRaises(costs.BudgetExceeded):
            costs.check_budget(Decimal("0.50"))

    def test_over_budget_poll_is_skipped_and_logged_not_silently_trimmed(self):
        """A no-op must not look like a successful poll."""
        source = make_source()
        budget = ReelsBudget.load()
        budget.monthly_budget_usd = Decimal("0.001")
        budget.save()

        with patch("apps.reels.apify.run_reel_scraper") as scraper:
            tasks.poll_reel_sources(force_source_ids=[source.pk], triggered_by="test")
        scraper.assert_not_called()

        run = ReelFetchRun.objects.get()
        self.assertEqual(run.status, "skipped")
        self.assertIn("budget", run.error)

    def test_spend_is_recorded_and_rolls_over_with_the_month(self):
        costs.record_spend(Decimal("1.25"))
        self.assertEqual(ReelsBudget.load().spent_this_month_usd, Decimal("1.2500"))

        budget = ReelsBudget.load()
        budget.month = "1999-01"
        budget.save(update_fields=["month"])
        self.assertEqual(ReelsBudget.load().spent_this_month_usd, Decimal("0"))

    @override_settings(REELS_BUDGET_ALERT_PCT=[50, 100])
    def test_each_alert_threshold_fires_once(self):
        budget = ReelsBudget.load()
        budget.monthly_budget_usd = Decimal("1.00")
        budget.save()
        with patch("apps.reels.costs.send_telegram_message") as send:
            costs.record_spend(Decimal("0.60"))  # crosses 50%
            costs.record_spend(Decimal("0.10"))  # still 50%, no new alert
            costs.record_spend(Decimal("0.40"))  # crosses 100%
        self.assertEqual(send.call_count, 2)
        self.assertIn("paused", send.call_args_list[-1].args[0])


class PollTests(TestCase):
    @override_settings(REELS_SCRAPING_ENABLED=False)
    def test_scheduled_poll_is_inert_until_explicitly_armed(self):
        make_source()
        with patch("apps.reels.apify.run_reel_scraper") as scraper:
            result = tasks.poll_reel_sources()
        scraper.assert_not_called()
        self.assertEqual(result, {"skipped": "disabled"})

    def test_own_sources_are_never_polled(self):
        own = make_source(username="nemo", kind=OWN)
        self.assertFalse(own.is_due())
        with patch("apps.reels.apify.run_reel_scraper") as scraper:
            tasks.poll_reel_sources(force_source_ids=[own.pk], triggered_by="test")
        scraper.assert_not_called()

    def test_fetch_stores_new_reels_and_the_runs_real_cost(self):
        source = make_source(username="deutsch")
        item = {
            "shortCode": "XYZ1",
            "url": "https://www.instagram.com/reel/XYZ1/",
            "caption": "Der Dativ",
            "videoUrl": "https://cdn.example/v.mp4",
            "displayUrl": "https://cdn.example/p.jpg",
            "timestamp": "2026-08-01T10:00:00Z",
            "ownerUsername": "deutsch",
            "likesCount": 12,
        }
        with patch("apps.reels.apify.run_reel_scraper", return_value=([item], "run1", 0.0078)), \
             patch("apps.reels.tasks.ingest_reel_media.delay") as ingest_task:
            # Ingest is queued via transaction.on_commit — outside a test that
            # fires immediately, but TestCase's wrapping transaction never
            # commits, so the callbacks have to be run explicitly.
            with self.captureOnCommitCallbacks(execute=True):
                tasks.poll_reel_sources(force_source_ids=[source.pk], triggered_by="test")

        reel = Reel.objects.get(key="XYZ1")
        self.assertEqual(reel.source, source)
        self.assertEqual(reel.caption, "Der Dativ")
        ingest_task.assert_called_once()

        run = ReelFetchRun.objects.get()
        self.assertEqual(run.status, "succeeded")
        self.assertEqual((run.items_returned, run.items_new), (1, 1))
        # The ledger records what Apify charged, not our estimate.
        self.assertEqual(run.cost_usd, Decimal("0.0078"))
        self.assertEqual(ReelsBudget.load().spent_this_month_usd, Decimal("0.0078"))

    def test_a_reel_we_already_have_is_billed_but_not_duplicated(self):
        source = make_source(username="deutsch")
        make_reel(source, key="XYZ1")
        item = {"shortCode": "XYZ1", "ownerUsername": "deutsch", "videoUrl": "u"}
        with patch("apps.reels.apify.run_reel_scraper", return_value=([item], "run1", 0.0026)):
            tasks.poll_reel_sources(force_source_ids=[source.pk], triggered_by="test")
        self.assertEqual(Reel.objects.filter(key="XYZ1").count(), 1)
        run = ReelFetchRun.objects.get()
        self.assertEqual(run.items_returned, 1)
        self.assertEqual(run.items_new, 0)  # paid for, kept nothing

    def test_spend_is_still_recorded_when_the_broker_is_down(self):
        """Apify has already charged us by the time ingest is queued. A broker
        outage must not leave the run stuck at $0 — that under-reports real
        spend and silently defeats the budget guard."""
        source = make_source(username="deutsch")
        item = {"shortCode": "XYZ1", "ownerUsername": "deutsch", "videoUrl": "u"}
        with patch("apps.reels.apify.run_reel_scraper", return_value=([item], "run1", 0.0078)), \
             patch("apps.reels.tasks.ingest_reel_media.delay", side_effect=OSError("redis down")):
            with self.captureOnCommitCallbacks(execute=True):
                tasks.poll_reel_sources(force_source_ids=[source.pk], triggered_by="test")

        run = ReelFetchRun.objects.get()
        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.cost_usd, Decimal("0.0078"))
        self.assertEqual(run.apify_run_id, "run1")
        self.assertEqual(ReelsBudget.load().spent_this_month_usd, Decimal("0.0078"))
        # The reel is kept and flagged, so it can be re-ingested rather than
        # re-scraped — we already paid for it once.
        self.assertIn("broker", Reel.objects.get(key="XYZ1").media_error)

    def test_max_total_charge_is_capped_above_the_estimate(self):
        source = make_source(username="deutsch", results_limit=3)
        with patch("apps.reels.apify.run_reel_scraper", return_value=([], "r", 0.0)) as scraper:
            tasks.poll_reel_sources(force_source_ids=[source.pk], triggered_by="test")
        cap = scraper.call_args.kwargs["max_total_charge_usd"]
        self.assertAlmostEqual(cap, float(costs.estimate_usd(3)) * 1.2, places=6)


class PurgeTests(TestCase):
    def setUp(self):
        self.ig = make_source(username="deutsch")
        self.own = make_source(username="nemo", kind=OWN)
        self.cutoff = timezone.now() - timedelta(days=90)

    def test_old_scraped_media_is_purged_but_the_row_survives(self):
        """The row is the dedupe tombstone — delete it and the next poll
        re-scrapes, and re-bills, the same reel."""
        reel = make_reel(self.ig, key="old", days_old=200)
        result = tasks.purge_expired_reel_media(cutoff=self.cutoff, triggered_by="test")

        reel.refresh_from_db()
        self.assertEqual(result["purged"], 1)
        self.assertEqual(reel.media_status, MEDIA_PURGED)
        self.assertIsNotNone(reel.media_purged_at)
        self.assertEqual(reel.video_bytes, 0)
        self.assertTrue(Reel.objects.filter(key="old").exists())
        self.assertEqual(ReelPurgeLog.objects.count(), 1)

    def test_our_own_reels_are_never_purged(self):
        make_reel(self.own, key="ours", days_old=500)
        tasks.purge_expired_reel_media(cutoff=self.cutoff, triggered_by="test")
        self.assertEqual(Reel.objects.get(key="ours").media_status, MEDIA_STORED)

    def test_evergreen_and_saved_reels_are_skipped(self):
        make_reel(self.ig, key="evergreen", days_old=500, is_evergreen=True)
        saved = make_reel(self.ig, key="saved", days_old=500)
        user = User.objects.create_user("a@b.com")
        ReelView.objects.create(user=user, reel=saved, saved=True)

        tasks.purge_expired_reel_media(cutoff=self.cutoff, triggered_by="test")
        self.assertEqual(Reel.objects.get(key="evergreen").media_status, MEDIA_STORED)
        self.assertEqual(Reel.objects.get(key="saved").media_status, MEDIA_STORED)

    def test_recent_reels_are_left_alone(self):
        make_reel(self.ig, key="fresh", days_old=5)
        tasks.purge_expired_reel_media(cutoff=self.cutoff, triggered_by="test")
        self.assertEqual(Reel.objects.get(key="fresh").media_status, MEDIA_STORED)

    def test_preview_matches_what_the_purge_would_do(self):
        make_reel(self.ig, key="old", days_old=200)
        make_reel(self.own, key="ours", days_old=200)
        make_reel(self.ig, key="green", days_old=200, is_evergreen=True)

        preview = tasks.purge_preview(self.cutoff)
        self.assertEqual(preview["count"], 1)
        self.assertEqual(preview["skipped_own"], 1)
        self.assertEqual(preview["skipped_evergreen"], 1)

        result = tasks.purge_expired_reel_media(cutoff=self.cutoff, triggered_by="test")
        self.assertEqual(result["purged"], preview["count"])

    @override_settings(REELS_RETENTION_DAYS=0)
    def test_retention_is_opt_in(self):
        make_reel(self.ig, key="old", days_old=900)
        self.assertEqual(tasks.purge_expired_reel_media(), {"skipped": "retention disabled"})


class StorageCostTests(TestCase):
    def test_only_storage_past_the_free_tier_is_billed(self):
        self.assertEqual(costs.storage_usd(8), Decimal("0.0000"))
        self.assertEqual(costs.storage_usd(43), Decimal("0.4950"))

    def test_monthly_storage_is_the_mean_of_daily_snapshots(self):
        """R2 bills GB-month, so a purge late in the month must not make the
        whole month look free."""
        today = timezone.now().date()
        month = today.strftime("%Y-%m")
        for day, gb in ((1, 40), (2, 40), (3, 0)):
            ReelsStorageSnapshot.objects.create(
                day=today.replace(day=day), stored_bytes=gb * costs.GB
            )
        self.assertAlmostEqual(costs.month_storage_gb(month), 80 / 3, places=3)

    def test_rollup_sums_apify_and_storage(self):
        ReelFetchRun.objects.create(
            status="succeeded", items_returned=100, items_new=30, cost_usd=Decimal("0.26")
        )
        month = costs.rollup_month()
        self.assertEqual(month.reels_billed, 100)
        self.assertEqual(month.reels_new, 30)
        self.assertEqual(month.total_usd, Decimal("0.2600"))


class ManualReelTests(TestCase):
    def setUp(self):
        self.own = make_source(username="nemo", kind=OWN)

    def _form(self, **overrides):
        data = {
            "source": self.own.pk,
            "title": "Der Dativ",
            "target_language": "de",
            "base_language": "",
            "level": "",
            **overrides,
        }
        files = {
            "video": SimpleUploadedFile("clip.mp4", MP4_HEAD, content_type="video/mp4"),
        }
        return ManualReelForm(data, files)

    def test_upload_creates_a_playable_reel_with_no_apify_call(self):
        form = self._form()
        self.assertTrue(form.is_valid(), form.errors)
        reel = form.save()
        self.assertEqual(reel.media_status, MEDIA_STORED)
        self.assertTrue(reel.key.startswith("nemo-der-dativ-"))
        # Stored under the key, like scraped reels — not the uploaded filename.
        self.assertIn(f"reels/{reel.key}", reel.video.name)
        self.assertEqual(ReelFetchRun.objects.count(), 0)

    def test_own_reels_default_to_evergreen(self):
        reel = make_reel(self.own, key="ours")
        self.assertTrue(reel.is_evergreen)

    def test_non_mp4_is_rejected_before_it_reaches_an_iphone(self):
        form = ManualReelForm(
            {"source": self.own.pk, "title": "x", "target_language": "de",
             "base_language": "", "level": ""},
            {"video": SimpleUploadedFile("clip.mp4", b"not an mp4 at all", content_type="video/mp4")},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("MP4 container", str(form.errors))

    def test_an_instagram_reel_added_by_hand_reuses_its_shortcode(self):
        """So a later scrape of that account doesn't duplicate it."""
        ig = make_source(username="deutsch")
        form = self._form(source=ig.pk, original_url="https://www.instagram.com/reel/ABC123/")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().key, "ABC123")

    def test_someone_elses_reel_requires_attribution(self):
        ig = make_source(username="deutsch")
        form = self._form(source=ig.pk)
        self.assertFalse(form.is_valid())
        self.assertIn("original_url", form.errors)


class LanguageMatchingTests(TestCase):
    """A reel teaches one language *in* another. Both halves have to match the
    user, or we hand a learner explanations they can't read."""

    def setUp(self):
        # German taught in Persian, in English, and immersively.
        self.de_fa = make_source(username="de_fa", target_language="de", base_language="fa")
        self.de_en = make_source(username="de_en", target_language="de", base_language="en")
        self.de_only = make_source(username="de_de", target_language="de", base_language="")
        self.tr_fa = make_source(username="tr_fa", target_language="tr", base_language="fa")
        for src in (self.de_fa, self.de_en, self.de_only, self.tr_fa):
            make_reel(
                src,
                key=f"r-{src.username}",
                days_old=1,
                target_language=src.target_language,
                base_language=src.base_language,
            )

    def _user(self, learning, known):
        user = User.objects.create_user(f"{'-'.join(learning + known)}@x.com")
        user.learning_languages = learning
        user.known_languages = known
        user.save()
        return user

    def keys(self, user):
        return set(matching.feed_for(user).values_list("key", flat=True))

    def test_persian_speaker_learning_german_skips_the_english_narrated_reel(self):
        user = self._user(["de"], ["fa"])
        self.assertEqual(self.keys(user), {"r-de_fa", "r-de_de"})

    def test_english_speaker_learning_german_skips_the_persian_narrated_reel(self):
        user = self._user(["de"], ["en"])
        self.assertEqual(self.keys(user), {"r-de_en", "r-de_de"})

    def test_knowing_both_base_languages_widens_the_feed(self):
        user = self._user(["de"], ["en", "fa"])
        self.assertEqual(self.keys(user), {"r-de_fa", "r-de_en", "r-de_de"})

    def test_immersive_reels_reach_every_learner_of_the_target(self):
        """No translation language means nothing extra to require."""
        user = self._user(["de"], [])
        self.assertEqual(self.keys(user), {"r-de_de"})

    def test_learning_two_languages_gets_both(self):
        user = self._user(["de", "tr"], ["fa"])
        self.assertEqual(self.keys(user), {"r-de_fa", "r-de_de", "r-tr_fa"})

    def test_a_language_the_user_is_not_learning_never_appears(self):
        user = self._user(["tr"], ["fa"])
        self.assertEqual(self.keys(user), {"r-tr_fa"})

    def test_unplayable_and_unpublished_reels_stay_out(self):
        user = self._user(["de"], ["fa"])
        Reel.objects.filter(key="r-de_fa").update(media_status="pending")
        Reel.objects.filter(key="r-de_de").update(is_published=False)
        self.assertEqual(self.keys(user), set())

    def test_prefs_are_unset_until_asked(self):
        blank = User.objects.create_user("blank@x.com")
        self.assertFalse(matching.has_language_prefs(blank))
        self.assertEqual(self.keys(blank), set())
        self.assertTrue(matching.has_language_prefs(self._user(["de"], ["fa"])))

    def test_ui_language_is_the_suggested_default_for_known(self):
        user = User.objects.create_user("fa@x.com", ui_language="fa")
        self.assertEqual(matching.default_known_languages(user), ["fa"])

    def test_pinned_reels_lead_the_feed(self):
        user = self._user(["de"], ["fa"])
        Reel.objects.filter(key="r-de_de").update(
            pin_until=timezone.now() + timedelta(days=1)
        )
        self.assertEqual(matching.feed_for(user).first().key, "r-de_de")

    def test_unseen_excludes_what_the_user_watched(self):
        user = self._user(["de"], ["fa"])
        ReelView.objects.create(user=user, reel=Reel.objects.get(key="r-de_fa"))
        self.assertEqual(
            set(matching.unseen_for(user).values_list("key", flat=True)), {"r-de_de"}
        )


class LanguageProfileTests(TestCase):
    def test_unknown_codes_are_dropped_not_rejected(self):
        """A stale code from an old client should cost that entry, not the save."""
        self.assertEqual(clean_codes(["de", "klingon", "FA", "de"]), ["de", "fa"])
        self.assertEqual(clean_codes("de"), [])

    def test_profile_api_round_trips_the_pair(self):
        from rest_framework.test import APIClient

        user = User.objects.create_user("u@x.com")
        client = APIClient()
        client.force_authenticate(user=user)  # the API is JWT-only, not session
        res = client.patch(
            reverse("me"),
            data={"learning_languages": ["de", "en"], "known_languages": ["fa", "nope"]},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content)
        user.refresh_from_db()
        self.assertEqual(user.learning_languages, ["de", "en"])
        self.assertEqual(user.known_languages, ["fa"])  # unknown code dropped
        self.assertEqual(res.data["learning_languages"], ["de", "en"])


class AdminPageTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_superuser("staff@nemo.test", "pw12345!")
        self.client.force_login(self.staff)

    def test_dashboard_renders(self):
        make_source()
        res = self.client.get(reverse("admin:reels_dashboard"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Purge media before a date")

    def test_costs_page_renders(self):
        with patch("apps.reels.apify.account_usage_usd", return_value=None):
            res = self.client.get(reverse("admin:reels_costs"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Projected month-end")

    def test_purge_preview_does_not_delete(self):
        source = make_source()
        make_reel(source, key="old", days_old=300)
        cutoff = (timezone.now() - timedelta(days=90)).date().isoformat()
        res = self.client.post(
            reverse("admin:reels_dashboard"),
            {"action": "purge_preview", "cutoff": cutoff},
        )
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Confirm purge")
        self.assertEqual(Reel.objects.get(key="old").media_status, MEDIA_STORED)

    def test_costs_page_flags_divergence_from_the_vendor(self):
        costs.record_spend(Decimal("1.00"))
        with patch("apps.reels.apify.account_usage_usd", return_value=3.0):
            res = self.client.get(reverse("admin:reels_costs"))
        self.assertContains(res, "diverges")


class SourceLanguageSyncTests(TestCase):
    """Reels copy the source's language pair at ingest, so correcting a source
    afterwards has to be able to catch its existing reels up."""

    def test_applying_languages_updates_the_channels_reels(self):
        staff = User.objects.create_superuser("s@x.com", "pw12345!")
        self.client.force_login(staff)

        source = make_source(username="deutsch", target_language="de", base_language="")
        make_reel(source, key="a", target_language="de", base_language="")
        other = make_source(username="other", target_language="tr", base_language="fa")
        make_reel(other, key="b", target_language="tr", base_language="fa")

        source.base_language = "en"  # it actually teaches German in English
        source.save()

        res = self.client.post(
            reverse("admin:reels_reelsource_changelist"),
            {"action": "apply_languages", "_selected_action": [str(source.pk)]},
            follow=True,
        )
        self.assertEqual(res.status_code, 200)

        self.assertEqual(Reel.objects.get(key="a").base_language, "en")
        # Untouched: only the selected channel's reels move.
        self.assertEqual(Reel.objects.get(key="b").base_language, "fa")


class ReelApiTests(TestCase):
    """The feed's contract: only reels this user can follow, and an honest
    answer when we've never asked what they're learning."""

    def setUp(self):
        from rest_framework.test import APIClient

        self.de_en = make_source(username="de_en", target_language="de", base_language="en")
        self.de_fa = make_source(username="de_fa", target_language="de", base_language="fa")
        make_reel(self.de_en, key="en1", days_old=1, target_language="de", base_language="en")
        make_reel(self.de_fa, key="fa1", days_old=2, target_language="de", base_language="fa")

        self.user = User.objects.create_user("api@x.com", ui_language="en")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def set_langs(self, learning, known):
        self.user.learning_languages = learning
        self.user.known_languages = known
        self.user.save()

    def test_feed_asks_for_languages_before_guessing_one(self):
        res = self.client.get(reverse("reel-feed"))
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["needs_language_prefs"])
        self.assertEqual(res.data["results"], [])
        # ui_language is a suggested default to confirm, not an assumption.
        self.assertEqual(res.data["suggested_known_languages"], ["en"])

    def test_feed_returns_only_reels_the_user_can_follow(self):
        self.set_langs(["de"], ["en"])
        res = self.client.get(reverse("reel-feed"))
        self.assertFalse(res.data["needs_language_prefs"])
        self.assertEqual([r["key"] for r in res.data["results"]], ["en1"])

    def test_feed_serialises_what_the_card_needs(self):
        self.set_langs(["de"], ["en"])
        reel = self.client.get(reverse("reel-feed")).data["results"][0]
        self.assertEqual(reel["source_username"], "de_en")
        self.assertEqual(reel["teaches"], "German (Deutsch) · English")
        self.assertFalse(reel["is_ours"])
        self.assertFalse(reel["saved"])

    def test_seen_is_idempotent_and_removes_the_reel_from_the_feed(self):
        self.set_langs(["de"], ["en", "fa"])
        first = self.client.get(reverse("reel-feed")).data["results"][0]
        for _ in range(2):
            self.assertEqual(
                self.client.post(reverse("reel-seen", args=[first["id"]])).status_code, 200
            )
        self.assertEqual(ReelView.objects.filter(user=self.user).count(), 1)
        keys = [r["key"] for r in self.client.get(reverse("reel-feed")).data["results"]]
        self.assertNotIn(first["key"], keys)

    def test_caught_up_replays_the_library_instead_of_an_empty_screen(self):
        self.set_langs(["de"], ["en"])
        reel = self.client.get(reverse("reel-feed")).data["results"][0]
        self.client.post(reverse("reel-seen", args=[reel["id"]]))
        res = self.client.get(reverse("reel-feed"))
        self.assertTrue(res.data["caught_up"])
        self.assertEqual(len(res.data["results"]), 1)

    def test_save_toggles_and_shows_up_in_the_saved_list(self):
        self.set_langs(["de"], ["en"])
        reel = self.client.get(reverse("reel-feed")).data["results"][0]
        self.assertTrue(self.client.post(reverse("reel-save", args=[reel["id"]])).data["saved"])
        saved = self.client.get(reverse("reel-saved")).data["results"]
        self.assertEqual([r["key"] for r in saved], ["en1"])
        self.assertTrue(saved[0]["saved"])
        self.assertFalse(self.client.post(reverse("reel-save", args=[reel["id"]])).data["saved"])
        self.assertEqual(self.client.get(reverse("reel-saved")).data["results"], [])

    def test_saving_a_reel_protects_it_from_the_retention_purge(self):
        """The saved list is a promise; the purge has to honour it."""
        self.set_langs(["de"], ["en"])
        old = make_reel(self.de_en, key="old", days_old=300, target_language="de", base_language="en")
        self.client.post(reverse("reel-save", args=[old.id]))
        tasks.purge_expired_reel_media(
            cutoff=timezone.now() - timedelta(days=90), triggered_by="test"
        )
        self.assertEqual(Reel.objects.get(key="old").media_status, MEDIA_STORED)

    def test_the_feed_requires_a_signed_in_user(self):
        from rest_framework.test import APIClient

        self.assertEqual(APIClient().get(reverse("reel-feed")).status_code, 401)


class MediaUrlTests(TestCase):
    """The frontend is served from a different origin than the backend, so a
    relative /media/ path would resolve against the wrong host."""

    def test_media_urls_are_absolute_even_without_r2(self):
        from rest_framework.test import APIClient

        source = make_source(target_language="de", base_language="en")
        reel = make_reel(source, key="abs", days_old=1, target_language="de", base_language="en")
        reel.video.save("abs.mp4", ContentFile(b"x"), save=True)

        user = User.objects.create_user("abs@x.com")
        user.learning_languages, user.known_languages = ["de"], ["en"]
        user.save()
        client = APIClient()
        client.force_authenticate(user=user)

        url = client.get(reverse("reel-feed")).data["results"][0]["video_url"]
        self.assertTrue(url.startswith("http"), url)


class SelfHealTests(TestCase):
    """A reel whose media never landed is dead weight: excluded from the feed,
    but its row blocks a re-fetch because the row is what dedupes. The next
    poll — already paid for — has to retry it."""

    def test_a_reel_with_missing_media_is_re_ingested_on_the_next_poll(self):
        source = make_source(username="deutsch")
        stuck = make_reel(source, key="XYZ1", media_status="pending", video_bytes=0)
        item = {
            "shortCode": "XYZ1",
            "ownerUsername": "deutsch",
            "videoUrl": "https://cdn.example/fresh.mp4",
            "displayUrl": "https://cdn.example/fresh.jpg",
        }
        with patch("apps.reels.apify.run_reel_scraper", return_value=([item], "r", 0.002)), \
             patch("apps.reels.tasks.ingest_reel_media.delay") as ingest_task:
            with self.captureOnCommitCallbacks(execute=True):
                tasks.poll_reel_sources(force_source_ids=[source.pk], triggered_by="test")

        ingest_task.assert_called_once_with(
            stuck.pk, "https://cdn.example/fresh.mp4", "https://cdn.example/fresh.jpg"
        )
        # Still not counted as new — we already had the row, and paid for it.
        self.assertEqual(ReelFetchRun.objects.get().items_new, 0)

    def test_a_reel_already_stored_is_not_re_ingested(self):
        source = make_source(username="deutsch")
        make_reel(source, key="XYZ1", media_status=MEDIA_STORED)
        item = {"shortCode": "XYZ1", "ownerUsername": "deutsch", "videoUrl": "https://x/v.mp4"}
        with patch("apps.reels.apify.run_reel_scraper", return_value=([item], "r", 0.002)), \
             patch("apps.reels.tasks.ingest_reel_media.delay") as ingest_task:
            with self.captureOnCommitCallbacks(execute=True):
                tasks.poll_reel_sources(force_source_ids=[source.pk], triggered_by="test")
        ingest_task.assert_not_called()


class UnseenCountTests(TestCase):
    """The home-page card's number. It must respect the same language match as
    the feed and drop to zero as reels get watched — a stale badge that says
    "3 new" over an empty feed erodes trust in every other number we show."""

    def setUp(self):
        from rest_framework.test import APIClient

        self.source = make_source(username="deutsch", base_language="en")
        self.user = User.objects.create_user("count@x.com")
        self.user.learning_languages = ["de"]
        self.user.known_languages = ["en"]
        self.user.save()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = reverse("reel-unseen-count")

    def test_counts_only_matching_unseen_reels(self):
        a = make_reel(self.source, key="A1", days_old=1, base_language="en")
        make_reel(self.source, key="B2", days_old=2, base_language="en")
        # Wrong base language — the user can't follow it, so it must not count.
        make_reel(self.source, key="C3", days_old=3, base_language="fa")
        # Watched — no longer "new".
        ReelView.objects.create(user=self.user, reel=a)

        self.assertEqual(self.client.get(self.url).data["count"], 1)

    def test_zero_without_language_prefs(self):
        make_reel(self.source, key="A1", days_old=1, base_language="en")
        self.user.learning_languages = []
        self.user.save()
        self.assertEqual(self.client.get(self.url).data["count"], 0)

    def test_unplayable_media_does_not_count(self):
        make_reel(self.source, key="A1", days_old=1, base_language="en", media_status="pending")
        self.assertEqual(self.client.get(self.url).data["count"], 0)


class MakeCardsTests(TestCase):
    """"Make cards from this reel." The invariants that matter:

    Gemini runs ONCE per reel (the drafts are cached on the row), but every
    user who takes the cards pays one unit of their own daily AI quota —
    including cache hits. The cache protects our Gemini bill, not the user's
    quota. A repeat tap by the same user is free and idempotent, and a
    staff-linked deck bypasses AI (and quota) entirely.
    """

    def setUp(self):
        from rest_framework.test import APIClient

        self.source = make_source(username="deutsch", base_language="en")
        self.reel = make_reel(
            self.source, key="MC1", days_old=1, base_language="en",
            caption="Learn: der Tisch (the table)",
        )
        self.drafts = [{
            "card_type": "vocab", "front": "der Tisch", "back": "the table",
            "reading": "", "article": "der", "example": "Der Tisch ist neu.",
        }]
        self.alice = User.objects.create_user("alice@x.com")
        self.bob = User.objects.create_user("bob@x.com")
        self.client_a = APIClient()
        self.client_a.force_authenticate(user=self.alice)
        self.client_b = APIClient()
        self.client_b.force_authenticate(user=self.bob)
        self.url = reverse("reel-make-cards", args=[self.reel.pk])

    def _usage(self, user) -> int:
        from apps.subscriptions.models import AiUsage

        return (
            AiUsage.objects.filter(user=user, day=timezone.now().date())
            .values_list("count", flat=True)
            .first()
            or 0
        )

    def test_first_use_generates_caches_and_charges(self):
        from apps.cards.models import Card

        with patch("apps.reels.cards.generate_card_drafts", return_value=self.drafts) as gen:
            res = self.client_a.post(self.url)

        self.assertEqual(res.status_code, 201)
        gen.assert_called_once()
        self.reel.refresh_from_db()
        self.assertEqual(self.reel.cards_cache, self.drafts)
        self.assertIsNotNone(self.reel.cards_generated_at)
        self.assertEqual(self._usage(self.alice), 1)
        # Forward + reverse (vocab is reviewed both ways).
        self.assertEqual(Card.objects.filter(deck_id=res.data["deck"]).count(), 2)

    def test_second_user_reuses_cache_but_is_still_charged(self):
        """The user's core rule: cache hit → no new AI call, usage recorded."""
        with patch("apps.reels.cards.generate_card_drafts", return_value=self.drafts):
            self.client_a.post(self.url)

        with patch("apps.reels.cards.generate_card_drafts") as gen:
            res = self.client_b.post(self.url)

        self.assertEqual(res.status_code, 201)
        gen.assert_not_called()  # served from Reel.cards_cache
        self.assertEqual(self._usage(self.bob), 1)  # ...but still metered

    def test_repeat_tap_by_same_user_is_free_and_idempotent(self):
        with patch("apps.reels.cards.generate_card_drafts", return_value=self.drafts):
            first = self.client_a.post(self.url)
        again = self.client_a.post(self.url)

        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.data["deck"], first.data["deck"])
        self.assertEqual(self._usage(self.alice), 1)  # no second charge

    def test_linked_deck_imports_without_touching_quota(self):
        from apps.cards.models import Card
        from apps.decks.models import Deck
        from apps.decks.sharing import _default_config

        staff = User.objects.create_user("staff@x.com")
        curated = Deck.objects.create(
            user=staff, name="Der Dativ", config=_default_config(staff), language="de"
        )
        Card.objects.create(deck=curated, front="dem Mann", back="to the man", card_type="vocab")
        self.reel.linked_deck = curated
        self.reel.save(update_fields=["linked_deck"])

        with patch("apps.reels.cards.generate_card_drafts") as gen:
            res = self.client_a.post(self.url)

        self.assertEqual(res.status_code, 201)
        gen.assert_not_called()
        self.assertEqual(self._usage(self.alice), 0)
        self.assertTrue(Card.objects.filter(deck_id=res.data["deck"]).exists())

    def test_nothing_to_work_with_is_a_422_not_a_500(self):
        with patch("apps.reels.cards.generate_card_drafts", return_value=[]):
            res = self.client_a.post(self.url)
        self.assertEqual(res.status_code, 422)

    def test_unpublished_reel_404s(self):
        self.reel.is_published = False
        self.reel.save(update_fields=["is_published"])
        self.assertEqual(self.client_a.post(self.url).status_code, 404)

    def test_serializer_reports_the_path(self):
        from .serializers import ReelSerializer

        self.assertEqual(ReelSerializer(self.reel).data["make_cards"], "ai")
        bare = make_reel(self.source, key="MC2", days_old=1, caption="", title="")
        self.assertIsNone(ReelSerializer(bare).data["make_cards"])


class FeedLanguageFilterTests(TestCase):
    """?lang= narrows the feed to one target language — a user learning both
    English and German switches between per-language feeds instead of getting
    the two shuffled together."""

    def setUp(self):
        from rest_framework.test import APIClient

        de = make_source(username="deutsch", target_language="de")
        en = make_source(username="english", target_language="en")
        make_reel(de, key="DE1", days_old=1, target_language="de")
        make_reel(en, key="EN1", days_old=2, target_language="en")

        self.user = User.objects.create_user("multi@x.com")
        self.user.learning_languages = ["de", "en"]
        self.user.known_languages = ["fa"]
        self.user.save()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = reverse("reel-feed")

    def _keys(self, res):
        return {r["key"] for r in res.data["results"]}

    def test_lang_filters_the_feed(self):
        self.assertEqual(self._keys(self.client.get(self.url, {"lang": "de"})), {"DE1"})
        self.assertEqual(self._keys(self.client.get(self.url, {"lang": "en"})), {"EN1"})
        self.assertEqual(self._keys(self.client.get(self.url)), {"DE1", "EN1"})

    def test_a_language_the_user_is_not_learning_is_ignored(self):
        # Ignored, not 400: a stale client must not break the feed.
        self.assertEqual(self._keys(self.client.get(self.url, {"lang": "fr"})), {"DE1", "EN1"})

    def test_caught_up_replay_stays_per_language(self):
        ReelView.objects.create(user=self.user, reel=Reel.objects.get(key="DE1"))
        res = self.client.get(self.url, {"lang": "de"})
        self.assertTrue(res.data["caught_up"])
        self.assertEqual(self._keys(res), {"DE1"})  # replays German, not English


class SuggestSourceTests(TestCase):
    """User-suggested Instagram accounts: honest answers for duplicates, a
    daily cap against scripts, and an admin approval that actually creates
    the source."""

    def setUp(self):
        from rest_framework.test import APIClient

        self.user = User.objects.create_user("suggest@x.com")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = reverse("reel-suggest-source")

    def _post(self, username, target="de", base=""):
        return self.client.post(
            self.url,
            {"username": username, "target_language": target, "base_language": base},
        )

    def test_creates_a_pending_suggestion_and_normalises_the_handle(self):
        from .models import ReelSourceSuggestion

        res = self._post("@Deutsch.Daily", "de", "fa")
        self.assertEqual(res.status_code, 201)
        s = ReelSourceSuggestion.objects.get()
        self.assertEqual((s.username, s.status), ("deutsch.daily", "pending"))

    def test_an_account_we_already_watch_answers_exists(self):
        make_source(username="easytodeutsch")
        res = self._post("easytodeutsch")
        self.assertEqual((res.status_code, res.data["status"]), (200, "exists"))

    def test_resuggesting_is_idempotent(self):
        from .models import ReelSourceSuggestion

        self._post("neuekanal")
        res = self._post("neuekanal")
        self.assertEqual((res.status_code, res.data["status"]), (200, "pending"))
        self.assertEqual(ReelSourceSuggestion.objects.count(), 1)

    def test_garbage_usernames_and_languages_are_rejected(self):
        self.assertEqual(self._post("not a handle!").status_code, 400)
        self.assertEqual(self._post("fine.handle", target="xx").status_code, 400)

    def test_daily_cap(self):
        for i in range(5):
            self.assertEqual(self._post(f"kanal{i}").status_code, 201)
        self.assertEqual(self._post("kanal5").status_code, 429)

    def test_admin_approve_creates_the_source(self):
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory
        from unittest.mock import MagicMock

        from .admin import ReelSourceSuggestionAdmin
        from .models import ReelSourceSuggestion

        self._post("neuekanal", "de", "fa")
        admin_obj = ReelSourceSuggestionAdmin(ReelSourceSuggestion, AdminSite())
        request = RequestFactory().post("/")
        admin_obj.message_user = MagicMock()
        admin_obj.approve_and_add(request, ReelSourceSuggestion.objects.all())

        src = ReelSource.objects.get(username="neuekanal")
        self.assertEqual((src.target_language, src.base_language), ("de", "fa"))
        s = ReelSourceSuggestion.objects.get()
        self.assertEqual(s.status, "approved")
        self.assertIsNotNone(s.handled_at)


class ReelViewQuotaTests(TestCase):
    """Watching reels spends daily AI quota: 5 units per FIRST view, so
    Basic's 80/day buys exactly 16 reels. Replays are free — the charge
    guards row creation, so a refused view leaves no row behind."""

    def setUp(self):
        from rest_framework.test import APIClient

        self.source = make_source(username="deutsch", base_language="en")
        self.user = User.objects.create_user("watcher@x.com")
        self.user.learning_languages, self.user.known_languages = ["de"], ["en"]
        self.user.save()
        # A fresh account is on trial (40/day); this class reasons in Basic
        # numbers (80/day → 16 reels), so pin the tier explicitly.
        from apps.subscriptions.models import Subscription

        Subscription.for_user(self.user).activate("basic_monthly")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _usage(self) -> int:
        from apps.subscriptions.models import AiUsage

        return (
            AiUsage.objects.filter(user=self.user, day=timezone.now().date())
            .values_list("count", flat=True)
            .first()
            or 0
        )

    def _seen(self, reel):
        return self.client.post(reverse("reel-seen", args=[reel.pk]))

    def test_first_view_charges_five_replay_is_free(self):
        reel = make_reel(self.source, key="Q1", days_old=1)
        self.assertEqual(self._seen(reel).status_code, 200)
        self.assertEqual(self._usage(), 5)
        self.assertEqual(self._seen(reel).status_code, 200)  # replay
        self.assertEqual(self._usage(), 5)  # ...still 5

    def test_a_refused_view_leaves_no_row(self):
        """No row on 429 — otherwise tomorrow's replay of this reel would be
        free despite never having been paid for."""
        from apps.subscriptions.models import AiUsage

        AiUsage.objects.create(user=self.user, day=timezone.now().date(), count=78)
        reel = make_reel(self.source, key="Q2", days_old=1)
        res = self._seen(reel)
        self.assertEqual(res.status_code, 429)
        self.assertFalse(ReelView.objects.filter(user=self.user, reel=reel).exists())
        self.assertEqual(self._usage(), 78)  # nothing charged

    def test_basic_buys_exactly_sixteen_reels(self):
        for i in range(16):
            reel = make_reel(self.source, key=f"R{i}", days_old=1)
            self.assertEqual(self._seen(reel).status_code, 200)
        self.assertEqual(self._usage(), 80)
        seventeenth = make_reel(self.source, key="R16", days_old=1)
        self.assertEqual(self._seen(seventeenth).status_code, 429)

    def test_single_unit_actions_still_fit_at_79(self):
        """The weighted check must not break the old exact-limit behaviour."""
        from apps.subscriptions.models import AiUsage
        from apps.subscriptions.quota import consume_ai_quota
        from rest_framework.exceptions import Throttled

        AiUsage.objects.create(user=self.user, day=timezone.now().date(), count=79)
        consume_ai_quota(self.user)  # 79 → 80: allowed, as before
        self.assertEqual(self._usage(), 80)
        with self.assertRaises(Throttled):
            consume_ai_quota(self.user)
