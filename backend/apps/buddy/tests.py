from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.notifications.models import PushSubscription, TelegramLink

from .models import BuddyLink

User = get_user_model()


class BuddyInviteViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="me@example.com")
        self.friend = User.objects.create_user(email="friend@example.com")
        self.client.force_authenticate(self.user)
        self.url = reverse("buddy-invite")

    def test_creates_pending_link(self):
        res = self.client.post(self.url, {"email": "friend@example.com"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data, {"status": "pending_sent", "email": "friend@example.com"})
        link = BuddyLink.objects.get()
        self.assertEqual(link.requester, self.user)
        self.assertEqual(link.recipient, self.friend)
        self.assertEqual(link.status, "pending")

    def test_cannot_invite_self(self):
        res = self.client.post(self.url, {"email": "me@example.com"})
        self.assertEqual(res.status_code, 400)

    def test_cannot_invite_unknown_email(self):
        res = self.client.post(self.url, {"email": "nobody@example.com"})
        self.assertEqual(res.status_code, 404)

    def test_cannot_invite_while_already_having_an_active_link(self):
        BuddyLink.objects.create(requester=self.user, recipient=self.friend)
        third = User.objects.create_user(email="third@example.com")
        res = self.client.post(self.url, {"email": "third@example.com"})
        self.assertEqual(res.status_code, 400)

    def test_cannot_invite_someone_who_already_has_a_buddy(self):
        other = User.objects.create_user(email="other@example.com")
        BuddyLink.objects.create(requester=self.friend, recipient=other, status="accepted")
        res = self.client.post(self.url, {"email": "friend@example.com"})
        self.assertEqual(res.status_code, 400)

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        res = self.client.post(self.url, {"email": "friend@example.com"})
        self.assertEqual(res.status_code, 401)


class BuddyViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="me@example.com")
        self.friend = User.objects.create_user(email="friend@example.com")
        self.client.force_authenticate(self.user)
        self.url = reverse("buddy")

    def test_status_none_without_a_link(self):
        res = self.client.get(self.url)
        self.assertEqual(res.data, {"status": "none"})

    def test_status_pending_sent_as_requester(self):
        BuddyLink.objects.create(requester=self.user, recipient=self.friend)
        res = self.client.get(self.url)
        self.assertEqual(res.data, {"status": "pending_sent", "email": "friend@example.com"})

    def test_status_pending_received_as_recipient(self):
        BuddyLink.objects.create(requester=self.friend, recipient=self.user)
        res = self.client.get(self.url)
        self.assertEqual(res.data, {"status": "pending_received", "email": "friend@example.com"})

    def test_status_accepted_includes_both_streak_summaries(self):
        BuddyLink.objects.create(requester=self.user, recipient=self.friend, status="accepted")
        res = self.client.get(self.url)
        self.assertEqual(res.data["status"], "accepted")
        self.assertEqual(res.data["buddy_email"], "friend@example.com")
        self.assertEqual(res.data["me"], {"today": 0, "streak": 0})
        self.assertEqual(res.data["buddy"], {"today": 0, "streak": 0})
        self.assertFalse(res.data["nudged_today"])

    def test_delete_removes_link_regardless_of_side_or_status(self):
        BuddyLink.objects.create(requester=self.friend, recipient=self.user)
        res = self.client.delete(self.url)
        self.assertEqual(res.status_code, 204)
        self.assertFalse(BuddyLink.objects.exists())

    def test_delete_is_idempotent(self):
        res = self.client.delete(self.url)
        self.assertEqual(res.status_code, 204)

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 401)


class BuddyAcceptViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="me@example.com")
        self.friend = User.objects.create_user(email="friend@example.com")
        self.url = reverse("buddy-accept")

    def test_recipient_can_accept(self):
        BuddyLink.objects.create(requester=self.friend, recipient=self.user)
        self.client.force_authenticate(self.user)
        res = self.client.post(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "accepted")
        link = BuddyLink.objects.get()
        self.assertEqual(link.status, "accepted")
        self.assertIsNotNone(link.responded_at)

    def test_requester_cannot_accept_their_own_invite(self):
        BuddyLink.objects.create(requester=self.user, recipient=self.friend)
        self.client.force_authenticate(self.user)
        res = self.client.post(self.url)
        self.assertEqual(res.status_code, 404)

    def test_404_without_a_pending_invite(self):
        self.client.force_authenticate(self.user)
        res = self.client.post(self.url)
        self.assertEqual(res.status_code, 404)


class BuddyNudgeViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="me@example.com", display_name="Ali")
        self.friend = User.objects.create_user(email="friend@example.com")
        self.client.force_authenticate(self.user)
        self.url = reverse("buddy-nudge")

    def test_404_without_an_accepted_buddy(self):
        res = self.client.post(self.url)
        self.assertEqual(res.status_code, 404)

    def test_404_while_only_pending_not_yet_accepted(self):
        BuddyLink.objects.create(requester=self.user, recipient=self.friend)
        res = self.client.post(self.url)
        self.assertEqual(res.status_code, 404)

    @patch("apps.notifications.tasks.send_buddy_nudge_push.delay")
    def test_sends_push_and_stamps_last_nudge(self, mock_delay):
        PushSubscription.objects.create(
            user=self.friend, endpoint="https://push.example.com/1", p256dh="k", auth="a"
        )
        link = BuddyLink.objects.create(requester=self.user, recipient=self.friend, status="accepted")
        res = self.client.post(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["nudged_today"])
        mock_delay.assert_called_once()
        args, _ = mock_delay.call_args
        self.assertEqual(args[0], self.friend.id)
        self.assertIn("Ali", args[1])
        link.refresh_from_db()
        self.assertIsNotNone(link.last_nudge_at)

    @patch("apps.notifications.tasks.send_buddy_nudge_telegram.delay")
    def test_uses_telegram_when_thats_the_buddys_channel(self, mock_delay):
        self.friend.study_reminder_channel = "telegram"
        self.friend.save(update_fields=["study_reminder_channel"])
        TelegramLink.objects.create(user=self.friend, chat_id=555)
        BuddyLink.objects.create(requester=self.user, recipient=self.friend, status="accepted")
        res = self.client.post(self.url)
        self.assertEqual(res.status_code, 200)
        mock_delay.assert_called_once()

    def test_400_when_buddy_has_no_notification_channel(self):
        BuddyLink.objects.create(requester=self.user, recipient=self.friend, status="accepted")
        res = self.client.post(self.url)
        self.assertEqual(res.status_code, 400)

    @patch("apps.notifications.tasks.send_buddy_nudge_push.delay")
    def test_rate_limited_to_once_per_day(self, mock_delay):
        PushSubscription.objects.create(
            user=self.friend, endpoint="https://push.example.com/1", p256dh="k", auth="a"
        )
        BuddyLink.objects.create(
            requester=self.user, recipient=self.friend, status="accepted", last_nudge_at=timezone.now()
        )
        res = self.client.post(self.url)
        self.assertEqual(res.status_code, 400)
        mock_delay.assert_not_called()

    @patch("apps.notifications.tasks.send_buddy_nudge_push.delay")
    def test_either_side_can_nudge(self, mock_delay):
        # self.user is the recipient of the original invite — nudging still
        # works in this direction, targeting self.friend (the requester).
        PushSubscription.objects.create(
            user=self.friend, endpoint="https://push.example.com/1", p256dh="k", auth="a"
        )
        BuddyLink.objects.create(requester=self.friend, recipient=self.user, status="accepted")
        res = self.client.post(self.url)
        self.assertEqual(res.status_code, 200)
        mock_delay.assert_called_once()
        args, _ = mock_delay.call_args
        self.assertEqual(args[0], self.friend.id)
