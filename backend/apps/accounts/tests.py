import datetime

from django.contrib.auth import get_user_model
from django.db.models import F
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

User = get_user_model()


class MeOnboardingTests(APITestCase):
    """`onboarded` is the flag the client uses to route a fresh account into the
    welcome flow, so its read/write behaviour is worth pinning down."""

    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.client.force_authenticate(self.user)
        self.url = reverse("me")

    def test_new_account_is_not_onboarded(self):
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data["onboarded"])

    def test_completing_onboarding_stamps_the_time(self):
        res = self.client.patch(self.url, {"onboarded": True})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["onboarded"])
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.onboarded_at)

    def test_replaying_onboarding_keeps_the_original_time(self):
        self.client.patch(self.url, {"onboarded": True})
        self.user.refresh_from_db()
        first = self.user.onboarded_at
        self.client.patch(self.url, {"onboarded": True})
        self.user.refresh_from_db()
        self.assertEqual(self.user.onboarded_at, first)

    def test_onboarding_can_be_reset(self):
        self.client.patch(self.url, {"onboarded": True})
        res = self.client.patch(self.url, {"onboarded": False})
        self.assertFalse(res.data["onboarded"])
        self.user.refresh_from_db()
        self.assertIsNone(self.user.onboarded_at)

    def test_welcome_flow_saves_name_and_language_together(self):
        res = self.client.patch(
            self.url, {"display_name": "Mohammad", "ui_language": "fa", "onboarded": True}
        )
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.display_name, "Mohammad")
        self.assertEqual(self.user.ui_language, "fa")
        self.assertIsNotNone(self.user.onboarded_at)

    def test_feature_flags_stay_read_only(self):
        # A user must not be able to grant themselves a gated capability.
        self.client.patch(self.url, {"feature_flags": ["book_upload"]})
        self.user.refresh_from_db()
        self.assertEqual(self.user.feature_flags, [])

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 401)


class OnboardingBackfillQueryTests(TestCase):
    """Migration 0006 resets the accounts migration 0005 had grandfathered, and
    tells them apart by `onboarded_at == date_joined` — the exact stamp 0005
    wrote. Getting that predicate wrong would either miss existing users or wipe
    a real completion, so it's pinned here rather than only living in a migration.
    """

    QUERY = {"onboarded_at": F("date_joined")}

    def _user(self, email, *, joined_days_ago, onboarded_at="same"):
        user = User.objects.create_user(email=email)
        joined = timezone.now() - datetime.timedelta(days=joined_days_ago)
        stamp = joined if onboarded_at == "same" else onboarded_at
        User.objects.filter(pk=user.pk).update(date_joined=joined, onboarded_at=stamp)
        return user

    def test_resets_only_the_grandfathered_accounts(self):
        # Stamped by 0005 with its own date_joined.
        grandfathered = self._user("old@example.com", joined_days_ago=30)
        # Actually walked the flow: stamped with "now", never equal to date_joined.
        completed = self._user("done@example.com", joined_days_ago=2, onboarded_at=timezone.now())
        # Signed up after 0005 and still waiting — already NULL.
        pending = self._user("new@example.com", joined_days_ago=0, onboarded_at=None)

        reset = User.objects.filter(**self.QUERY).update(onboarded_at=None)

        self.assertEqual(reset, 1)
        grandfathered.refresh_from_db()
        completed.refresh_from_db()
        pending.refresh_from_db()
        self.assertIsNone(grandfathered.onboarded_at, "existing user should see the intro")
        self.assertIsNotNone(completed.onboarded_at, "a real completion must survive")
        self.assertIsNone(pending.onboarded_at)

    def test_is_idempotent(self):
        self._user("old@example.com", joined_days_ago=30)
        self.assertEqual(User.objects.filter(**self.QUERY).update(onboarded_at=None), 1)
        # Re-running (a replayed migration, a re-deploy) must not reset anyone
        # who has since finished the flow.
        self.assertEqual(User.objects.filter(**self.QUERY).update(onboarded_at=None), 0)
