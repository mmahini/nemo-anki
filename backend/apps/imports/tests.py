import base64
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings

from .gemini import extract_text_from_image, transcribe_audio


def _gemini_response(text):
    return Mock(json=lambda: {"candidates": [{"content": {"parts": [{"text": text}]}}]})


@override_settings(GEMINI_API_KEY="test-key")
class TranscribeAudioTests(TestCase):
    """transcribe_audio: audio bytes are sent to Gemini via inline_data (no
    ffmpeg/transcoding step) and the parsed text/kind drive the Telegram voice
    lookup; every failure mode degrades to {"text": "", "kind": "word"}."""

    @patch("requests.post")
    def test_posts_inline_audio_and_parses_word(self, mock_post):
        mock_post.return_value = _gemini_response('{"text": "Haus", "kind": "word"}')

        result = transcribe_audio(b"\x00audio", mime_type="audio/ogg", language="de")

        self.assertEqual(result, {"text": "Haus", "kind": "word"})
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertIn("test-key", args[0])
        parts = kwargs["json"]["contents"][0]["parts"]
        self.assertIn("German", parts[0]["text"])
        self.assertEqual(parts[1]["inline_data"]["mime_type"], "audio/ogg")
        self.assertEqual(
            parts[1]["inline_data"]["data"], base64.b64encode(b"\x00audio").decode("ascii")
        )

    @patch("requests.post")
    def test_parses_sentence_kind(self, mock_post):
        mock_post.return_value = _gemini_response('{"text": "Ich gehe ins Kino.", "kind": "sentence"}')

        result = transcribe_audio(b"audio", mime_type="audio/ogg")

        self.assertEqual(result, {"text": "Ich gehe ins Kino.", "kind": "sentence"})

    @patch("requests.post")
    def test_skips_the_call_when_unconfigured(self, mock_post):
        with self.settings(GEMINI_API_KEY=""):
            self.assertEqual(transcribe_audio(b"audio"), {"text": "", "kind": "word"})
        mock_post.assert_not_called()

    @patch("requests.post")
    def test_skips_the_call_without_audio(self, mock_post):
        self.assertEqual(transcribe_audio(b""), {"text": "", "kind": "word"})
        mock_post.assert_not_called()

    @patch("requests.post")
    def test_network_failure_degrades_to_empty(self, mock_post):
        mock_post.side_effect = Exception("timeout")

        self.assertEqual(transcribe_audio(b"audio"), {"text": "", "kind": "word"})

    @patch("requests.post")
    def test_missing_text_field_degrades_to_empty(self, mock_post):
        mock_post.return_value = _gemini_response("not json at all")

        self.assertEqual(transcribe_audio(b"audio"), {"text": "", "kind": "word"})


@override_settings(GEMINI_API_KEY="test-key")
class ExtractTextFromImageTests(TestCase):
    """extract_text_from_image: photo bytes are sent to Gemini via inline_data
    (no separate OCR service or preprocessing step) and the parsed text/kind
    drive the Telegram photo lookup; every failure mode degrades to
    {"text": "", "kind": "word"}."""

    @patch("requests.post")
    def test_posts_inline_image_and_parses_word(self, mock_post):
        mock_post.return_value = _gemini_response('{"text": "Haus", "kind": "word"}')

        result = extract_text_from_image(b"\x00image", mime_type="image/jpeg", language="de")

        self.assertEqual(result, {"text": "Haus", "kind": "word"})
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertIn("test-key", args[0])
        parts = kwargs["json"]["contents"][0]["parts"]
        self.assertIn("German", parts[0]["text"])
        self.assertEqual(parts[1]["inline_data"]["mime_type"], "image/jpeg")
        self.assertEqual(
            parts[1]["inline_data"]["data"], base64.b64encode(b"\x00image").decode("ascii")
        )

    @patch("requests.post")
    def test_parses_sentence_kind(self, mock_post):
        mock_post.return_value = _gemini_response('{"text": "Ich gehe ins Kino.", "kind": "sentence"}')

        result = extract_text_from_image(b"image", mime_type="image/jpeg")

        self.assertEqual(result, {"text": "Ich gehe ins Kino.", "kind": "sentence"})

    @patch("requests.post")
    def test_skips_the_call_when_unconfigured(self, mock_post):
        with self.settings(GEMINI_API_KEY=""):
            self.assertEqual(extract_text_from_image(b"image"), {"text": "", "kind": "word"})
        mock_post.assert_not_called()

    @patch("requests.post")
    def test_skips_the_call_without_image(self, mock_post):
        self.assertEqual(extract_text_from_image(b""), {"text": "", "kind": "word"})
        mock_post.assert_not_called()

    @patch("requests.post")
    def test_network_failure_degrades_to_empty(self, mock_post):
        mock_post.side_effect = Exception("timeout")

        self.assertEqual(extract_text_from_image(b"image"), {"text": "", "kind": "word"})

    @patch("requests.post")
    def test_missing_text_field_degrades_to_empty(self, mock_post):
        mock_post.return_value = _gemini_response("not json at all")

        self.assertEqual(extract_text_from_image(b"image"), {"text": "", "kind": "word"})
