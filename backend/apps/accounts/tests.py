import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db.models import F
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.subscriptions.models import Subscription
from apps.subscriptions.plans import BASIC, REFERRAL_BONUS_DAYS

from .models import EmailOTP

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


class ReferralTests(APITestCase):
    """Signing up through an invite link records the inviter and gifts a month
    of Basic — but only on account creation, and never for a bad code."""

    def setUp(self):
        self.referrer = User.objects.create_user(email="inviter@example.com")
        self.url = reverse("auth-verify-otp")

    def _verify(self, email: str, referral_code: str = ""):
        otp = EmailOTP.issue(email=email)
        payload = {"otp_id": str(otp.id), "code": otp.code}
        if referral_code:
            payload["referral_code"] = referral_code
        return self.client.post(self.url, payload)

    def test_signup_with_invite_grants_a_month_of_basic(self):
        res = self._verify("invited@example.com", self.referrer.referral_code)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["referral_applied"])

        invited = User.objects.get(email="invited@example.com")
        self.assertEqual(invited.referred_by, self.referrer)
        sub = Subscription.for_user(invited)
        self.assertEqual(sub.computed_state, Subscription.ACTIVE)
        self.assertEqual(sub.active_tier, BASIC)
        expected_end = timezone.now() + datetime.timedelta(days=REFERRAL_BONUS_DAYS)
        self.assertAlmostEqual(
            sub.current_period_end.timestamp(), expected_end.timestamp(), delta=60
        )
        # A gift, not a purchase — no plan recorded.
        self.assertEqual(sub.plan, "")

    def test_unknown_code_still_signs_up_without_reward(self):
        res = self._verify("invited@example.com", "nosuchcode")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data["referral_applied"])
        invited = User.objects.get(email="invited@example.com")
        self.assertIsNone(invited.referred_by)
        self.assertEqual(Subscription.for_user(invited).computed_state, Subscription.TRIAL)


    def test_returning_user_gets_no_reward(self):
        existing = User.objects.create_user(email="veteran@example.com")
        res = self._verify("veteran@example.com", self.referrer.referral_code)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data["referral_applied"])
        existing.refresh_from_db()
        self.assertIsNone(existing.referred_by)
        self.assertEqual(Subscription.for_user(existing).computed_state, Subscription.TRIAL)

    def test_every_user_gets_a_unique_referral_code(self):
        another = User.objects.create_user(email="other@example.com")
        self.assertTrue(self.referrer.referral_code)
        self.assertTrue(another.referral_code)
        self.assertNotEqual(self.referrer.referral_code, another.referral_code)

    def test_referral_code_is_exposed_but_read_only_on_me(self):
        self.client.force_authenticate(self.referrer)
        me = reverse("me")
        res = self.client.get(me)
        self.assertEqual(res.data["referral_code"], self.referrer.referral_code)
        self.client.patch(me, {"referral_code": "hacked123"})
        self.referrer.refresh_from_db()
        self.assertNotEqual(self.referrer.referral_code, "hacked123")


class NewUserTelegramNotificationTests(APITestCase):
    def setUp(self):
        self.url = reverse("auth-verify-otp")

    def _verify(self, email: str):
        otp = EmailOTP.issue(email=email)
        return self.client.post(self.url, {"otp_id": str(otp.id), "code": otp.code})

    @patch("apps.accounts.views.notify_new_user_signup")
    def test_first_signup_notifies(self, mock_notify):
        self._verify("brandnew@example.com")
        mock_notify.assert_called_once()
        notified_user = mock_notify.call_args.args[0]
        self.assertEqual(notified_user.email, "brandnew@example.com")

    @patch("apps.accounts.views.notify_new_user_signup")
    def test_returning_signin_does_not_notify(self, mock_notify):
        User.objects.create_user(email="already@example.com")
        self._verify("already@example.com")
        mock_notify.assert_not_called()


class SignupCdpTests(TestCase):
    """`signup` is emitted server-side at the moment the account row is
    created — the client only mirrors `is_new_user` for its welcome flow."""

    def _verify(self, email):
        from rest_framework.test import APIClient

        client = APIClient()
        res = client.post(reverse("auth-request-otp"), {"email": email})
        otp_id, code = res.data["otp_id"], res.data["dev_code"]
        return client.post(reverse("auth-verify-otp"), {"otp_id": otp_id, "code": code})

    def test_signup_once_login_every_time(self):
        from unittest.mock import patch

        with patch("apps.accounts.views.cdp.track") as track:
            first = self._verify("brand.new@x.com")
            self.assertTrue(first.data["is_new_user"])
            again = self._verify("brand.new@x.com")
            self.assertFalse(again.data["is_new_user"])

        events = [c.args[1] for c in track.call_args_list]
        # First verification: the account is born and signed in. Second: just a login.
        self.assertEqual(events, ["signup", "login", "login"])
