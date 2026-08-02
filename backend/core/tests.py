from unittest.mock import patch

from django.test import TestCase

from .telegram import send_telegram_message


class SendTelegramMessageTests(TestCase):
    @patch("django.conf.settings.TELEGRAM_BOT_TOKEN", "")
    def test_skips_silently_when_unconfigured(self):
        send_telegram_message("hello")  # must not raise

    @patch("django.conf.settings.TELEGRAM_CHAT_ID", "-123")
    @patch("django.conf.settings.TELEGRAM_BOT_TOKEN", "test-token")
    @patch("requests.post")
    def test_posts_to_the_configured_chat(self, mock_post):
        mock_post.return_value.ok = True
        send_telegram_message("hello there")
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertIn("test-token", args[0])
        self.assertEqual(kwargs["json"]["chat_id"], "-123")
        self.assertEqual(kwargs["json"]["text"], "hello there")

    @patch("django.conf.settings.TELEGRAM_CHAT_ID", "-123")
    @patch("django.conf.settings.TELEGRAM_BOT_TOKEN", "test-token")
    @patch("requests.post", side_effect=Exception("network down"))
    def test_network_failure_does_not_raise(self, mock_post):
        send_telegram_message("hello")  # must not raise
