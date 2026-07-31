from django.contrib.auth import get_user_model
from django.urls import reverse
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
