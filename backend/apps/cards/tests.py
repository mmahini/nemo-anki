from datetime import timedelta
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.decks.models import Deck, DeckConfig

from . import scheduler
from .models import Card, ReviewLog

User = get_user_model()


def _config(**overrides):
    base = dict(
        learning_steps="1 10",
        relearning_steps="10",
        graduating_interval=1,
        easy_interval=4,
        starting_ease=2500,
        easy_bonus=1300,
        hard_interval=1200,
        interval_modifier=1000,
        new_interval=0,
        minimum_interval=1,
        maximum_interval=36500,
        leech_threshold=8,
        leech_suspend=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _new_card():
    return SimpleNamespace(
        state="new", due=timezone.now(), interval_days=0, ease=2500,
        reps=0, lapses=0, step_index=0, is_leech=False, last_reviewed_at=None,
    )


class SchedulerTests(TestCase):
    def setUp(self):
        self.cfg = _config()
        self.now = timezone.now()

    def test_new_good_advances_through_learning_then_graduates(self):
        c = _new_card()
        # Good on a new card -> second learning step (10m), still learning.
        scheduler.answer(c, scheduler.GOOD, self.cfg, self.now)
        self.assertEqual(c.state, "learning")
        self.assertEqual(c.step_index, 1)
        # Good again -> graduates to review at graduating interval (1 day).
        scheduler.answer(c, scheduler.GOOD, self.cfg, self.now)
        self.assertEqual(c.state, "review")
        self.assertEqual(c.interval_days, 1)
        self.assertEqual(c.ease, 2500)

    def test_new_easy_graduates_immediately(self):
        c = _new_card()
        scheduler.answer(c, scheduler.EASY, self.cfg, self.now)
        self.assertEqual(c.state, "review")
        self.assertEqual(c.interval_days, 4)

    def test_new_again_stays_first_step(self):
        c = _new_card()
        scheduler.answer(c, scheduler.AGAIN, self.cfg, self.now)
        self.assertEqual(c.state, "learning")
        self.assertEqual(c.step_index, 0)

    def test_review_good_multiplies_by_ease(self):
        c = _new_card()
        c.state, c.interval_days, c.ease, c.reps = "review", 10, 2500, 3
        scheduler.answer(c, scheduler.GOOD, _config(), self.now)
        # 10 * 2.5 = 25 (fuzz may shift; assert in a sane band).
        self.assertGreaterEqual(c.interval_days, 20)
        self.assertLessEqual(c.interval_days, 30)
        self.assertEqual(c.ease, 2500)

    def test_review_hard_lowers_ease_and_uses_hard_multiplier(self):
        c = _new_card()
        c.state, c.interval_days, c.ease, c.reps = "review", 10, 2500, 3
        scheduler.answer(c, scheduler.HARD, _config(), self.now)
        self.assertEqual(c.ease, 2350)  # 2500 - 150
        # 10 * 1.2 = 12, then ± fuzz; never drops below the original interval.
        self.assertGreaterEqual(c.interval_days, 10)

    def test_review_again_lapses_into_relearning(self):
        c = _new_card()
        c.state, c.interval_days, c.ease, c.reps, c.lapses = "review", 30, 2500, 5, 0
        scheduler.answer(c, scheduler.AGAIN, _config(), self.now)
        self.assertEqual(c.state, "relearning")
        self.assertEqual(c.ease, 2300)  # -200
        self.assertEqual(c.lapses, 1)

    def test_leech_suspends_at_threshold(self):
        c = _new_card()
        c.state, c.interval_days, c.ease, c.lapses = "review", 10, 1500, 7
        scheduler.answer(c, scheduler.AGAIN, _config(leech_threshold=8), self.now)
        self.assertTrue(c.is_leech)
        self.assertEqual(c.state, "suspended")

    def test_ease_never_below_floor(self):
        c = _new_card()
        c.state, c.interval_days, c.ease, c.reps = "review", 10, 1300, 3
        scheduler.answer(c, scheduler.HARD, _config(), self.now)
        self.assertEqual(c.ease, scheduler.EASE_FLOOR)

    def test_preview_intervals_does_not_mutate(self):
        c = _new_card()
        c.state, c.interval_days, c.ease, c.reps = "review", 10, 2500, 3
        before = (c.state, c.interval_days, c.ease)
        out = scheduler.preview_intervals(c, _config(), self.now)
        self.assertEqual((c.state, c.interval_days, c.ease), before)
        self.assertEqual(set(out.keys()), {"1", "2", "3", "4"})

    def test_relearning_good_returns_to_review(self):
        c = _new_card()
        c.state, c.interval_days, c.ease, c.step_index = "relearning", 15, 2300, 0
        scheduler.answer(c, scheduler.GOOD, _config(), self.now)
        self.assertEqual(c.state, "review")
        self.assertGreaterEqual(c.interval_days, 1)


class StatsOverviewTests(APITestCase):
    """The performance page's single data source."""

    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.client.force_authenticate(self.user)
        self.url = reverse("stats-overview")
        self.config = DeckConfig.objects.create(user=self.user)
        self.deck = Deck.objects.create(user=self.user, name="German", config=self.config)
        self.now = timezone.now()

    def _card(self, **kw):
        return Card.objects.create(deck=self.deck, front=kw.pop("front", "Tisch"), **kw)

    def _log(self, card, rating, state_before="review", **kw):
        log = ReviewLog.objects.create(
            card=card,
            user=self.user,
            rating=rating,
            state_before=state_before,
            state_after="review",
            prev_snapshot={},
            **kw,
        )
        return log

    def test_empty_collection_returns_zeroed_shape(self):
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["range"]["reviews"], 0)
        self.assertIsNone(res.data["range"]["retention"])
        self.assertEqual(res.data["collection"]["total"], 0)
        self.assertEqual(len(res.data["forecast"]), 30)
        self.assertEqual(len(res.data["range"]["hours"]), 24)
        self.assertEqual(res.data["decks"], [])

    def test_retention_counts_only_answers_on_review_cards(self):
        card = self._card()
        # Good/Easy/Hard all pass, Again lapses -> 3 of 4. The failed *learning*
        # answer is excluded from the ratio entirely.
        for rating in (3, 4, 2, 1):
            self._log(card, rating)
        self._log(card, 1, state_before="learning")
        res = self.client.get(self.url)
        self.assertEqual(res.data["range"]["mature_answers"], 4)
        self.assertEqual(res.data["range"]["retention"], 0.75)
        self.assertEqual(res.data["range"]["reviews"], 5)

    def test_rating_and_maturity_breakdowns(self):
        card = self._card()
        self._log(card, 1, state_before="new")
        self._log(card, 3, state_before="learning")
        self._log(card, 3, state_before="relearning")
        self._log(card, 4)
        res = self.client.get(self.url)
        self.assertEqual(res.data["range"]["ratings"], {"again": 1, "hard": 0, "good": 2, "easy": 1})
        today = [d for d in res.data["range"]["days"] if d["count"]][0]
        self.assertEqual((today["new"], today["learning"], today["review"]), (1, 2, 1))

    def test_collection_splits_young_and_mature(self):
        self._card(state="new")
        self._card(state="learning")
        self._card(state="review", interval_days=5)
        self._card(state="review", interval_days=40)
        self._card(state="suspended", is_leech=True, lapses=9)
        res = self.client.get(self.url)
        c = res.data["collection"]
        self.assertEqual(
            (c["total"], c["new"], c["learning"], c["young"], c["mature"], c["suspended"]),
            (5, 1, 1, 1, 1, 1),
        )
        self.assertEqual(c["leeches"], 1)

    def test_forecast_folds_overdue_cards_into_today(self):
        self._card(state="review", interval_days=10, due=self.now - timedelta(days=5))
        self._card(state="review", interval_days=10, due=self.now + timedelta(days=2))
        res = self.client.get(self.url)
        forecast = res.data["forecast"]
        self.assertEqual(forecast[0]["count"], 1)  # the overdue one, today
        self.assertEqual(forecast[2]["count"], 1)
        self.assertEqual(forecast[-1]["cumulative"], 2)

    def test_interval_histogram_buckets_review_cards(self):
        self._card(state="review", interval_days=1)
        self._card(state="review", interval_days=3)
        self._card(state="review", interval_days=400)
        self._card(state="new")  # new cards have no interval to bucket
        buckets = {b["label"]: b["count"] for b in self.client.get(self.url).data["intervals"]}
        self.assertEqual(buckets["1d"], 1)
        self.assertEqual(buckets["2-3d"], 1)
        self.assertEqual(buckets["1y+"], 1)
        self.assertEqual(sum(buckets.values()), 3)

    def test_range_days_is_clamped_to_allowed_presets(self):
        self.assertEqual(self.client.get(self.url, {"days": 90}).data["range_days"], 90)
        self.assertEqual(len(self.client.get(self.url, {"days": 7}).data["range"]["days"]), 7)
        # Anything unsupported falls back to 30 rather than erroring.
        self.assertEqual(self.client.get(self.url, {"days": 5000}).data["range_days"], 30)
        self.assertEqual(self.client.get(self.url, {"days": "abc"}).data["range_days"], 30)

    def test_reviews_outside_the_range_are_excluded(self):
        card = self._card()
        old = self._log(card, 3)
        ReviewLog.objects.filter(pk=old.pk).update(reviewed_at=self.now - timedelta(days=40))
        self.assertEqual(self.client.get(self.url, {"days": 7}).data["range"]["reviews"], 0)
        self.assertEqual(self.client.get(self.url, {"days": 90}).data["range"]["reviews"], 1)

    def test_deck_row_carries_counts_and_retention(self):
        card = self._card(state="review", interval_days=30)
        self._log(card, 3, time_ms=4000)
        self._log(card, 1, time_ms=2000)
        row = self.client.get(self.url).data["decks"][0]
        self.assertEqual(row["full_name"], "German")
        self.assertEqual((row["cards"], row["mature"], row["reviews"]), (1, 1, 2))
        self.assertEqual(row["retention"], 0.5)  # one Good, one Again
        self.assertEqual(row["seconds"], 6)

    def test_leeches_list_only_primary_direction(self):
        forward = self._card(front="Tisch", lapses=9, is_leech=True)
        Card.objects.create(deck=self.deck, front="table", lapses=9, reverse_of=forward)
        self._card(front="Stuhl", lapses=0)  # never lapsed — not listed
        leeches = self.client.get(self.url).data["leeches"]
        self.assertEqual([l["front"] for l in leeches], ["Tisch"])

    def test_scoped_to_the_requesting_user(self):
        card = self._card()
        self._log(card, 3)
        other = User.objects.create_user(email="other@example.com")
        self.client.force_authenticate(other)
        res = self.client.get(self.url)
        self.assertEqual(res.data["range"]["reviews"], 0)
        self.assertEqual(res.data["collection"]["total"], 0)

    def test_unauthenticated_request_is_rejected(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 401)


class FindLevelDeckTests(TestCase):
    def setUp(self):
        from .seeding import seed_for_user

        self.user = get_user_model().objects.create_user(email="leveltest@example.com")
        seed_for_user(self.user)

    def test_maps_german_cefr_level_to_sub_level_deck(self):
        from .seeding import find_level_deck

        deck = find_level_deck(self.user, "de", "A2")
        self.assertEqual(deck.name, "A2.1")

    def test_german_above_b1_falls_back_to_highest_available(self):
        from .seeding import find_level_deck

        deck = find_level_deck(self.user, "de", "C1")
        self.assertEqual(deck.name, "B1.1")

    def test_maps_english_cefr_level_to_tier_deck(self):
        from .seeding import find_level_deck

        self.assertEqual(find_level_deck(self.user, "en", "A1").name, "Basic")
        self.assertEqual(find_level_deck(self.user, "en", "C1").name, "Advanced")

    def test_returns_none_when_user_has_no_decks(self):
        from .seeding import find_level_deck

        other = get_user_model().objects.create_user(email="nodecks@example.com")
        self.assertIsNone(find_level_deck(other, "de", "A1"))
