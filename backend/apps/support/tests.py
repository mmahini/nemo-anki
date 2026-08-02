from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from .models import PushSubscription, SupportMessage, SupportThread

User = get_user_model()


class SupportThreadTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.client.force_authenticate(self.user)
        self.url = reverse("support-thread")

    def test_get_creates_thread_on_first_use(self):
        self.assertEqual(SupportThread.objects.count(), 0)
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(SupportThread.objects.count(), 1)
        self.assertEqual(res.data["messages"], [])

    def test_post_creates_message_from_user(self):
        res = self.client.post(self.url, {"body": "How do I import an Anki deck?"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(len(res.data["messages"]), 1)
        msg = res.data["messages"][0]
        self.assertEqual(msg["body"], "How do I import an Anki deck?")
        self.assertFalse(msg["from_admin"])

    def test_post_rejects_empty_body(self):
        res = self.client.post(self.url, {"body": "   "})
        self.assertEqual(res.status_code, 400)

    def test_thread_is_scoped_per_user(self):
        self.client.post(self.url, {"body": "hi"})
        other = User.objects.create_user(email="other@example.com")
        self.client.force_authenticate(other)
        res = self.client.get(self.url)
        self.assertEqual(res.data["messages"], [])

    def test_admin_reply_is_visible_to_user(self):
        thread = SupportThread.objects.create(user=self.user)
        SupportMessage.objects.create(thread=thread, from_admin=True, body="Sure, here's how...")
        res = self.client.get(self.url)
        self.assertEqual(len(res.data["messages"]), 1)
        self.assertTrue(res.data["messages"][0]["from_admin"])

    def test_awaiting_reply_reflects_last_message_sender(self):
        thread = SupportThread.objects.create(user=self.user)
        self.assertFalse(thread.awaiting_reply)
        SupportMessage.objects.create(thread=thread, from_admin=False, body="hi")
        self.assertTrue(thread.awaiting_reply)
        SupportMessage.objects.create(thread=thread, from_admin=True, body="hey")
        self.assertFalse(thread.awaiting_reply)

    def test_unauthenticated_request_is_rejected(self):
        self.client.force_authenticate(None)
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 401)

    @patch("apps.support.views.notify_staff_of_message")
    def test_new_message_triggers_staff_notification(self, mock_notify):
        self.client.post(self.url, {"body": "hello"})
        mock_notify.assert_called_once()

    @patch("apps.support.views.notify_telegram_of_message")
    def test_new_message_triggers_telegram_notification(self, mock_notify):
        self.client.post(self.url, {"body": "hello"})
        mock_notify.assert_called_once()


class PushSubscribeTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(email="staff@example.com", is_staff=True)
        self.user = User.objects.create_user(email="learner2@example.com")
        self.url = reverse("support-push-subscribe")
        self.payload = {
            "endpoint": "https://fcm.googleapis.com/fcm/send/abc123",
            "keys": {"p256dh": "p256dh-value", "auth": "auth-value"},
        }

    def test_staff_can_subscribe(self):
        self.client.force_authenticate(self.staff)
        res = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(res.status_code, 204)
        sub = PushSubscription.objects.get(endpoint=self.payload["endpoint"])
        self.assertEqual(sub.user, self.staff)

    def test_non_staff_cannot_subscribe(self):
        self.client.force_authenticate(self.user)
        res = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(PushSubscription.objects.count(), 0)

    def test_resubscribing_same_endpoint_updates_not_duplicates(self):
        self.client.force_authenticate(self.staff)
        self.client.post(self.url, self.payload, format="json")
        updated = {**self.payload, "keys": {"p256dh": "new-p256dh", "auth": "new-auth"}}
        self.client.post(self.url, updated, format="json")
        self.assertEqual(PushSubscription.objects.count(), 1)
        self.assertEqual(PushSubscription.objects.first().p256dh, "new-p256dh")

    def test_unsubscribe_removes_it(self):
        self.client.force_authenticate(self.staff)
        self.client.post(self.url, self.payload, format="json")
        res = self.client.delete(self.url, {"endpoint": self.payload["endpoint"]}, format="json")
        self.assertEqual(res.status_code, 204)
        self.assertEqual(PushSubscription.objects.count(), 0)


class NotifyStaffOfMessageTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(email="staff2@example.com", is_staff=True)
        self.learner = User.objects.create_user(email="learner3@example.com")
        self.thread = SupportThread.objects.create(user=self.learner)
        self.message = SupportMessage.objects.create(thread=self.thread, body="hi")
        self.sub = PushSubscription.objects.create(
            user=self.staff, endpoint="https://fcm.googleapis.com/fcm/send/xyz",
            p256dh="p", auth="a",
        )

    @patch("django.conf.settings.VAPID_PRIVATE_KEY", "")
    def test_skips_silently_when_vapid_unconfigured(self):
        from .notifications import notify_staff_of_message

        notify_staff_of_message(self.thread, self.message)  # must not raise

    @patch("django.conf.settings.VAPID_PRIVATE_KEY", "test-key")
    @patch("pywebpush.webpush")
    def test_sends_to_each_staff_subscription(self, mock_webpush):
        from .notifications import notify_staff_of_message

        notify_staff_of_message(self.thread, self.message)
        mock_webpush.assert_called_once()
        kwargs = mock_webpush.call_args.kwargs
        self.assertEqual(kwargs["subscription_info"]["endpoint"], self.sub.endpoint)

    @patch("django.conf.settings.VAPID_PRIVATE_KEY", "test-key")
    @patch("pywebpush.webpush")
    def test_expired_subscription_is_deleted(self, mock_webpush):
        from pywebpush import WebPushException

        from .notifications import notify_staff_of_message

        class _Resp:
            status_code = 410

        mock_webpush.side_effect = WebPushException("gone", response=_Resp())
        notify_staff_of_message(self.thread, self.message)
        self.assertEqual(PushSubscription.objects.count(), 0)


class NotifyTelegramOfMessageTests(APITestCase):
    def setUp(self):
        self.learner = User.objects.create_user(email="learner4@example.com")
        self.thread = SupportThread.objects.create(user=self.learner)
        self.message = SupportMessage.objects.create(thread=self.thread, body="hi there")

    @patch("django.conf.settings.TELEGRAM_BOT_TOKEN", "")
    def test_skips_silently_when_unconfigured(self):
        from .notifications import notify_telegram_of_message

        notify_telegram_of_message(self.thread, self.message)  # must not raise

    @patch("django.conf.settings.TELEGRAM_CHAT_ID", "-123")
    @patch("django.conf.settings.TELEGRAM_BOT_TOKEN", "test-token")
    @patch("requests.post")
    def test_posts_message_body_to_telegram(self, mock_post):
        from .notifications import notify_telegram_of_message

        mock_post.return_value.ok = True
        notify_telegram_of_message(self.thread, self.message)
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertIn("test-token", args[0])
        self.assertEqual(kwargs["json"]["chat_id"], "-123")
        self.assertIn("hi there", kwargs["json"]["text"])
        self.assertIn(self.learner.email, kwargs["json"]["text"])

    @patch("django.conf.settings.TELEGRAM_CHAT_ID", "-123")
    @patch("django.conf.settings.TELEGRAM_BOT_TOKEN", "test-token")
    @patch("requests.post", side_effect=Exception("network down"))
    def test_network_failure_does_not_raise(self, mock_post):
        from .notifications import notify_telegram_of_message

        notify_telegram_of_message(self.thread, self.message)  # must not raise
