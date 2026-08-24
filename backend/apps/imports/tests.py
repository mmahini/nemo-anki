import base64
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.subscriptions.models import AiUsage
from apps.subscriptions.plans import TRIAL_DAILY_AI_LIMIT

from .gemini import _clean_conjugations, enrich_card, extract_text_from_image, transcribe_audio

User = get_user_model()


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


class EnrichVoiceViewTests(APITestCase):
    """POST /api/import/enrich-voice/ — transcribe an uploaded recording, then
    enrich it through the same pipeline as typed/selected text. Mirrors the
    Telegram bot's voice flow (apps.notifications.management.commands
    .poll_telegram_updates._handle_voice_message) over HTTP instead of
    Telegram's own transport — see that module's tests, especially
    test_voice_consumes_quota_exactly_once, for the precedent this preserves."""

    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.client.force_authenticate(self.user)
        self.url = reverse("import-enrich-voice")

    def _audio(self, size=10, content_type="audio/webm"):
        return SimpleUploadedFile("voice.webm", b"x" * size, content_type=content_type)

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        res = self.client.post(self.url, {"audio": self._audio()}, format="multipart")
        self.assertEqual(res.status_code, 401)

    @patch("apps.imports.views.transcribe_audio")
    def test_oversized_audio_is_rejected(self, mock_transcribe):
        oversized = SimpleUploadedFile(
            "voice.webm", b"x" * (10 * 1024 * 1024 + 1), content_type="audio/webm"
        )
        res = self.client.post(self.url, {"audio": oversized}, format="multipart")
        self.assertEqual(res.status_code, 413)
        mock_transcribe.assert_not_called()

    @patch("apps.imports.views.enrich_card")
    @patch("apps.imports.views.transcribe_audio")
    def test_empty_transcription_returns_empty_proposal(self, mock_transcribe, mock_enrich):
        mock_transcribe.return_value = {"text": "", "kind": "word"}

        res = self.client.post(self.url, {"audio": self._audio(), "language": "de"}, format="multipart")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            res.data,
            {
                "front": "", "card_type": "vocab", "back": "", "reading": "",
                "article": "none", "plural": "", "example": "",
            },
        )
        mock_enrich.assert_not_called()

    @patch("apps.imports.views.enrich_card")
    @patch("apps.imports.views.transcribe_audio")
    def test_successful_transcription_flows_into_enrichment(self, mock_transcribe, mock_enrich):
        mock_transcribe.return_value = {"text": "Haus", "kind": "word"}
        mock_enrich.return_value = {
            "card_type": "vocab", "back": "house", "reading": "haus",
            "article": "das", "plural": "Häuser", "example": "Das ist mein Haus.",
        }

        res = self.client.post(
            self.url,
            {"audio": self._audio(), "language": "de", "back_language": "English"},
            format="multipart",
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            res.data,
            {
                "front": "Haus", "card_type": "vocab", "back": "house", "reading": "haus",
                "article": "das", "plural": "Häuser", "example": "Das ist mein Haus.",
            },
        )

    @patch("apps.imports.views.enrich_card")
    @patch("apps.imports.views.transcribe_audio")
    def test_transcribe_audio_receives_the_uploaded_bytes(self, mock_transcribe, mock_enrich):
        mock_transcribe.return_value = {"text": "Haus", "kind": "word"}
        mock_enrich.return_value = {
            "card_type": "vocab", "back": "house", "reading": "", "article": "none",
            "plural": "", "example": "",
        }
        # Django's multipart parser strips MIME parameters from
        # UploadedFile.content_type, so a browser-recorded
        # "audio/webm;codecs=opus" blob arrives server-side as bare
        # "audio/webm" — assert what the view actually receives and forwards.
        audio = SimpleUploadedFile("voice.webm", b"real-bytes", content_type="audio/webm")

        self.client.post(self.url, {"audio": audio, "language": "de"}, format="multipart")

        mock_transcribe.assert_called_once_with(b"real-bytes", mime_type="audio/webm", language="de")

    @patch("apps.imports.views.enrich_card")
    @patch("apps.imports.views.transcribe_audio")
    def test_enrich_card_receives_the_transcript(self, mock_transcribe, mock_enrich):
        mock_transcribe.return_value = {"text": "Ich gehe ins Kino.", "kind": "sentence"}
        mock_enrich.return_value = {
            "card_type": "sentence", "back": "I am going to the cinema.", "reading": "",
            "article": "none", "plural": "", "example": "",
        }

        self.client.post(
            self.url,
            {"audio": self._audio(), "language": "de", "back_language": "English"},
            format="multipart",
        )

        mock_enrich.assert_called_once_with("Ich gehe ins Kino.", "de", "sentence", "English")

    @patch("apps.imports.views.enrich_card")
    @patch("apps.imports.views.transcribe_audio")
    def test_quota_consumed_exactly_once(self, mock_transcribe, mock_enrich):
        # Transcription + enrichment are two Gemini calls but one logical
        # lookup — mirrors apps.notifications.tests
        # .test_voice_consumes_quota_exactly_once for the Telegram bot.
        mock_transcribe.return_value = {"text": "Haus", "kind": "word"}
        mock_enrich.return_value = {
            "card_type": "vocab", "back": "house", "reading": "", "article": "none",
            "plural": "", "example": "",
        }

        res = self.client.post(self.url, {"audio": self._audio(), "language": "de"}, format="multipart")

        self.assertEqual(res.status_code, 200)
        usage = AiUsage.objects.get(user=self.user, day=timezone.now().date())
        self.assertEqual(usage.count, 1)

    @patch("apps.imports.views.transcribe_audio")
    def test_returns_429_once_quota_exhausted(self, mock_transcribe):
        AiUsage.objects.create(user=self.user, day=timezone.now().date(), count=TRIAL_DAILY_AI_LIMIT)

        res = self.client.post(self.url, {"audio": self._audio(), "language": "de"}, format="multipart")

        self.assertEqual(res.status_code, 429)
        mock_transcribe.assert_not_called()


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


class CleanConjugationsTests(TestCase):
    """German tense labels drift ("Präsens (er/sie/es)", "Partizip II"), which
    makes every verb card look slightly different. _clean_conjugations maps them
    onto a canonical ladder; other languages are passed through untouched."""

    def _rows(self, *tenses):
        return [{"tense": t, "form": "f", "meaning": "m"} for t in tenses]

    def test_normalises_and_orders_german_labels(self):
        rows = _clean_conjugations(self._rows("Partizip II", "Präsens (er/sie/es)", "Infinitiv"), "de")

        self.assertEqual([r["tense"] for r in rows], ["Infinitiv", "Präsens", "Perfekt"])

    def test_drops_duplicates_keeping_the_first(self):
        rows = [
            {"tense": "Präsens", "form": "er macht", "meaning": "he makes"},
            {"tense": "Präsens - 3rd person", "form": "er tut", "meaning": "he does"},
        ]

        self.assertEqual(_clean_conjugations(rows, "de"), [rows[0]])

    def test_keeps_an_unrecognised_label_after_the_canonical_ones(self):
        rows = _clean_conjugations(self._rows("Plusquamperfekt", "Präsens"), "de")

        self.assertEqual([r["tense"] for r in rows], ["Präsens", "Plusquamperfekt"])

    def test_leaves_other_languages_alone(self):
        rows = self._rows("past participle", "base form")

        self.assertEqual(_clean_conjugations(rows, "en"), rows)

    def test_drops_fully_empty_rows_and_non_dicts(self):
        rows = [{"tense": "", "form": "", "meaning": ""}, "nope", {"tense": "Präsens", "form": "er macht", "meaning": "x"}]

        self.assertEqual([r["tense"] for r in _clean_conjugations(rows, "de")], ["Präsens"])


@override_settings(GEMINI_API_KEY="test-key")
class EnrichCardTypeDetectionTests(TestCase):
    """enrich_card classifies the word itself — the card_type the caller sends
    is only a hint, so "kompliziert" comes back as an adjective, not vocab."""

    @patch("requests.post")
    def test_returns_the_detected_part_of_speech(self, mock_post):
        mock_post.return_value = _gemini_response(
            '{"card_type": "adjective", "back": "complicated", "reading": "", '
            '"article": "none", "plural": "", "example": ""}'
        )

        result = enrich_card("kompliziert", "de", "vocab")

        self.assertEqual(result["card_type"], "adjective")

    @patch("requests.post")
    def test_falls_back_to_the_callers_type_when_the_answer_is_unusable(self, mock_post):
        mock_post.return_value = _gemini_response(
            '{"card_type": "Adjektiv", "back": "complicated", "reading": "", '
            '"article": "none", "plural": "", "example": ""}'
        )

        result = enrich_card("kompliziert", "de", "sentence")

        self.assertEqual(result["card_type"], "sentence")
