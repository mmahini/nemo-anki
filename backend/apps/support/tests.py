from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from .models import SupportMessage, SupportThread

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
