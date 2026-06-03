from datetime import timedelta
from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone

from . import scheduler


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
