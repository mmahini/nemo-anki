from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.decks.models import Deck, DeckConfig
from apps.subscriptions.models import AiUsage
from apps.subscriptions.plans import TRIAL_DAILY_AI_LIMIT

from . import scheduler
from .activity import streak_summary
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


class CardMnemonicViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.client.force_authenticate(self.user)
        self.config = DeckConfig.objects.create(user=self.user)
        self.deck = Deck.objects.create(user=self.user, name="German", config=self.config)
        self.card = Card.objects.create(deck=self.deck, front="Tisch", back="table", language="de")
        self.url = reverse("card-mnemonic", args=[self.card.id])

    @patch("apps.imports.gemini.mnemonic_for")
    def test_generates_and_caches_on_first_call(self, mock_mnemonic):
        mock_mnemonic.return_value = "Think of a 'desk' — TISCH sounds like 'desk' backwards-ish."
        res = self.client.post(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["mnemonic"], mock_mnemonic.return_value)
        self.card.refresh_from_db()
        self.assertEqual(self.card.mnemonic, mock_mnemonic.return_value)
        mock_mnemonic.assert_called_once_with("Tisch", "table", "de", "vocab")

    @patch("apps.imports.gemini.mnemonic_for")
    def test_second_call_returns_cached_value_without_calling_gemini_again(self, mock_mnemonic):
        self.card.mnemonic = "Already have one."
        self.card.save(update_fields=["mnemonic"])
        res = self.client.post(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["mnemonic"], "Already have one.")
        mock_mnemonic.assert_not_called()

    @patch("apps.imports.gemini.mnemonic_for")
    def test_cache_hit_does_not_consume_quota(self, mock_mnemonic):
        self.card.mnemonic = "Already have one."
        self.card.save(update_fields=["mnemonic"])
        AiUsage.objects.create(user=self.user, day=timezone.now().date(), count=TRIAL_DAILY_AI_LIMIT)
        res = self.client.post(self.url)
        self.assertEqual(res.status_code, 200)

    @patch("apps.imports.gemini.mnemonic_for")
    def test_returns_429_once_quota_exhausted(self, mock_mnemonic):
        AiUsage.objects.create(user=self.user, day=timezone.now().date(), count=TRIAL_DAILY_AI_LIMIT)
        res = self.client.post(self.url)
        self.assertEqual(res.status_code, 429)
        mock_mnemonic.assert_not_called()
        self.card.refresh_from_db()
        self.assertEqual(self.card.mnemonic, "")

    @patch("apps.imports.gemini.mnemonic_for")
    def test_writes_land_on_primary_when_called_via_reverse_card(self, mock_mnemonic):
        mock_mnemonic.return_value = "A memory trick."
        reverse_card = Card.objects.create(
            deck=self.deck, front="table", back="Tisch", language="de",
            direction="reverse", reverse_of=self.card,
        )
        url = reverse("card-mnemonic", args=[reverse_card.id])
        res = self.client.post(url)
        self.assertEqual(res.status_code, 200)
        self.card.refresh_from_db()
        reverse_card.refresh_from_db()
        self.assertEqual(self.card.mnemonic, "A memory trick.")
        self.assertEqual(reverse_card.mnemonic, "A memory trick.")

    def test_404_for_another_users_card(self):
        other = User.objects.create_user(email="other@example.com")
        self.client.force_authenticate(other)
        res = self.client.post(self.url)
        self.assertEqual(res.status_code, 404)

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        res = self.client.post(self.url)
        self.assertEqual(res.status_code, 401)


class StreakSummaryTests(TestCase):
    """apps.cards.activity.streak_summary — shared by ReviewActivityView (the
    Stats page) and apps.buddy's progress comparison."""

    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.config = DeckConfig.objects.create(user=self.user)
        self.deck = Deck.objects.create(user=self.user, name="German", config=self.config)
        self.card = Card.objects.create(deck=self.deck, front="Tisch")
        self.today = date(2026, 8, 10)  # a Monday, arbitrary fixed anchor

    def _log_on(self, day: date):
        log = ReviewLog.objects.create(
            card=self.card, user=self.user, rating=3,
            state_before="new", state_after="review", prev_snapshot={},
        )
        ReviewLog.objects.filter(pk=log.pk).update(
            reviewed_at=timezone.make_aware(datetime.combine(day, datetime.min.time()))
        )

    def test_no_activity_is_zero_today_and_zero_streak(self):
        self.assertEqual(streak_summary(self.user, self.today), {"today": 0, "streak": 0})

    def test_counts_todays_reviews(self):
        self._log_on(self.today)
        self._log_on(self.today)
        self.assertEqual(streak_summary(self.user, self.today)["today"], 2)

    def test_streak_counts_consecutive_days_ending_today(self):
        for d in (self.today, self.today - timedelta(days=1), self.today - timedelta(days=2)):
            self._log_on(d)
        self.assertEqual(streak_summary(self.user, self.today)["streak"], 3)

    def test_streak_survives_before_todays_review_using_yesterday(self):
        # Studied every day through yesterday, hasn't opened the app yet today.
        for d in (self.today - timedelta(days=1), self.today - timedelta(days=2)):
            self._log_on(d)
        self.assertEqual(streak_summary(self.user, self.today)["streak"], 2)

    def test_gap_breaks_the_streak(self):
        self._log_on(self.today)
        self._log_on(self.today - timedelta(days=2))  # gap at yesterday
        self.assertEqual(streak_summary(self.user, self.today)["streak"], 1)


class CardTypeReverseTests(TestCase):
    """Single-word notes are drilled both ways. Adjectives, adverbs and
    prepositions are words like any other, so they earn a reverse card;
    verbs, sentences and grammar cards stay one-directional."""

    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        config = DeckConfig.objects.create(user=self.user)
        self.deck = Deck.objects.create(user=self.user, name="German", config=config)

    def _card(self, card_type):
        return Card.objects.create(deck=self.deck, front="x", back="y", card_type=card_type)

    def test_word_types_want_a_reverse(self):
        for card_type in ("vocab", "adjective", "adverb", "preposition"):
            with self.subTest(card_type=card_type):
                self.assertTrue(self._card(card_type).wants_reverse())

    def test_verbs_sentences_and_grammar_do_not(self):
        for card_type in ("verb", "sentence", "grammar"):
            with self.subTest(card_type=card_type):
                self.assertFalse(self._card(card_type).wants_reverse())

    def test_add_reverse_cards_creates_the_companion_for_an_adjective(self):
        from .models import add_reverse_cards

        card = self._card("adjective")

        add_reverse_cards([card])

        reverse = Card.objects.filter(reverse_of=card).first()
        self.assertIsNotNone(reverse)
        self.assertEqual(reverse.card_type, "adjective")
