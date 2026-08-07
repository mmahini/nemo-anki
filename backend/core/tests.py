from unittest.mock import Mock, patch

from django.test import TestCase

from .telegram import download_telegram_file, send_telegram_message


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


class DownloadTelegramFileTests(TestCase):
    """download_telegram_file: the two-step Telegram dance (getFile to resolve
    the server file_path, then GET from the /file/bot... host) with a size cap
    — best-effort, returning None rather than raising on any failure."""

    def _file_response(self, chunks):
        fr = Mock()
        fr.raise_for_status.return_value = None
        fr.iter_content.return_value = iter(chunks)
        return fr

    @patch("requests.get")
    @patch("requests.post")
    def test_downloads_via_getfile_then_file_host(self, mock_post, mock_get):
        mock_post.return_value = Mock(json=lambda: {"ok": True, "result": {"file_path": "voices/voice1.ogg"}})
        mock_get.return_value = self._file_response([b"abc", b"def"])

        data = download_telegram_file("https://api.telegram.org/botX", "voice1")

        self.assertEqual(data, b"abcdef")
        mock_post.assert_called_once_with(
            "https://api.telegram.org/botX/getFile", json={"file_id": "voice1"}, timeout=10
        )
        mock_get.assert_called_once_with(
            "https://api.telegram.org/file/botX/voices/voice1.ogg", timeout=30, stream=True
        )

    @patch("requests.get")
    @patch("requests.post")
    def test_noop_without_file_id(self, mock_post, mock_get):
        self.assertIsNone(download_telegram_file("https://api.telegram.org/botX", ""))
        mock_post.assert_not_called()
        mock_get.assert_not_called()

    @patch("requests.get")
    @patch("requests.post")
    def test_getfile_rejection_returns_none(self, mock_post, mock_get):
        mock_post.return_value = Mock(json=lambda: {"ok": False, "description": "wrong file id"})

        self.assertIsNone(download_telegram_file("https://api.telegram.org/botX", "voice1"))
        mock_get.assert_not_called()

    @patch("requests.get")
    @patch("requests.post")
    def test_getfile_without_file_path_returns_none(self, mock_post, mock_get):
        mock_post.return_value = Mock(json=lambda: {"ok": True, "result": {}})

        self.assertIsNone(download_telegram_file("https://api.telegram.org/botX", "voice1"))
        mock_get.assert_not_called()

    @patch("requests.get")
    @patch("requests.post")
    def test_download_failure_returns_none(self, mock_post, mock_get):
        mock_post.return_value = Mock(json=lambda: {"ok": True, "result": {"file_path": "voices/voice1.ogg"}})
        mock_get.side_effect = Exception("connection reset")

        self.assertIsNone(download_telegram_file("https://api.telegram.org/botX", "voice1"))

    @patch("requests.get")
    @patch("requests.post")
    def test_oversized_file_returns_none(self, mock_post, mock_get):
        mock_post.return_value = Mock(json=lambda: {"ok": True, "result": {"file_path": "voices/big.ogg"}})
        # Two 6-byte chunks exceed a 10-byte cap mid-stream.
        mock_get.return_value = self._file_response([b"aaaaaa", b"bbbbbb"])

        self.assertIsNone(download_telegram_file("https://api.telegram.org/botX", "voice1", max_bytes=10))
