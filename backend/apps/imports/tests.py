import base64
import io
import socket
from unittest.mock import MagicMock, Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.subscriptions.models import AiUsage
from apps.subscriptions.plans import TRIAL_DAILY_AI_LIMIT

from .gemini import _clean_conjugations, enrich_card, extract_text_from_image, transcribe_audio
from .safe_fetch import ImageFetchError, ImageTooLargeError, UnsafeUrlError, fetch_image_safely, normalize_image

User = get_user_model()


def _gemini_response(text):
    return Mock(status_code=200, json=lambda: {"candidates": [{"content": {"parts": [{"text": text}]}}]})


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


def _addrinfo(ip: str):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    sockaddr = (ip, 0, 0, 0) if family == socket.AF_INET6 else (ip, 0)
    return [(family, socket.SOCK_STREAM, 6, "", sockaddr)]


def _mock_response(*, status_code=200, is_redirect=False, headers=None, chunks=None):
    resp = MagicMock()
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    resp.status_code = status_code
    resp.is_redirect = is_redirect
    resp.ok = 200 <= status_code < 400
    resp.headers = headers or {}
    resp.iter_content = lambda chunk_size=None: iter(chunks or [])
    return resp


class FetchImageSafelyTests(TestCase):
    """fetch_image_safely: the SSRF checks a trusted-source fetch (apps.cards
    .image_search, which only ever fetches Openverse's own API results)
    doesn't need, since this one downloads whatever URL the Chrome
    extension's user right-clicked on some arbitrary webpage."""

    def test_rejects_non_http_scheme(self):
        with self.assertRaises(UnsafeUrlError):
            fetch_image_safely("file:///etc/passwd", max_bytes=1000)

    def test_rejects_url_with_no_host(self):
        with self.assertRaises(UnsafeUrlError):
            fetch_image_safely("http:///path", max_bytes=1000)

    @patch("apps.imports.safe_fetch.socket.getaddrinfo")
    def test_rejects_loopback_address(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _addrinfo("127.0.0.1")
        with self.assertRaises(UnsafeUrlError):
            fetch_image_safely("http://localhost/image.jpg", max_bytes=1000)

    @patch("apps.imports.safe_fetch.socket.getaddrinfo")
    def test_rejects_link_local_metadata_address(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _addrinfo("169.254.169.254")
        with self.assertRaises(UnsafeUrlError):
            fetch_image_safely("http://169.254.169.254/latest/meta-data/", max_bytes=1000)

    @patch("apps.imports.safe_fetch.socket.getaddrinfo")
    def test_rejects_private_rfc1918_address(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = _addrinfo("10.0.0.5")
        with self.assertRaises(UnsafeUrlError):
            fetch_image_safely("http://internal.example/x.jpg", max_bytes=1000)

    @patch("apps.imports.safe_fetch.socket.getaddrinfo")
    def test_unresolvable_host_is_rejected(self, mock_getaddrinfo):
        mock_getaddrinfo.side_effect = socket.gaierror("no such host")
        with self.assertRaises(UnsafeUrlError):
            fetch_image_safely("http://does-not-exist.invalid/x.jpg", max_bytes=1000)

    @patch("apps.imports.safe_fetch.requests.get")
    @patch("apps.imports.safe_fetch.socket.getaddrinfo")
    def test_rejects_redirect_to_private_address(self, mock_getaddrinfo, mock_get):
        # First hop resolves public; the redirect target resolves internal —
        # both hops must be checked, not just the URL the caller passed in.
        mock_getaddrinfo.side_effect = [_addrinfo("93.184.216.34"), _addrinfo("127.0.0.1")]
        mock_get.return_value = _mock_response(
            status_code=302, is_redirect=True, headers={"Location": "http://internal.example/x.jpg"}
        )
        with self.assertRaises(UnsafeUrlError):
            fetch_image_safely("http://public.example/x.jpg", max_bytes=1000)

    @patch("apps.imports.safe_fetch.requests.get")
    @patch("apps.imports.safe_fetch.socket.getaddrinfo")
    def test_follows_redirect_to_public_address(self, mock_getaddrinfo, mock_get):
        mock_getaddrinfo.side_effect = [_addrinfo("93.184.216.34"), _addrinfo("93.184.216.35")]
        redirect = _mock_response(
            status_code=302, is_redirect=True, headers={"Location": "http://public2.example/x.jpg"}
        )
        final = _mock_response(status_code=200, chunks=[b"abc"])
        mock_get.side_effect = [redirect, final]

        data = fetch_image_safely("http://public.example/x.jpg", max_bytes=1000)

        self.assertEqual(data, b"abc")

    @patch("apps.imports.safe_fetch.requests.get")
    @patch("apps.imports.safe_fetch.socket.getaddrinfo")
    def test_oversized_download_is_rejected(self, mock_getaddrinfo, mock_get):
        mock_getaddrinfo.return_value = _addrinfo("93.184.216.34")
        mock_get.return_value = _mock_response(status_code=200, chunks=[b"x" * 2000])

        with self.assertRaises(ImageTooLargeError):
            fetch_image_safely("http://public.example/x.jpg", max_bytes=1000)

    def test_normalize_rejects_non_image_bytes(self):
        with self.assertRaises(ImageFetchError):
            normalize_image(b"not an image")

    def test_normalize_returns_a_capped_jpeg(self):
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (10, 10), "red").save(buf, "PNG")

        data, mime_type = normalize_image(buf.getvalue())

        self.assertEqual(mime_type, "image/jpeg")
        self.assertTrue(data.startswith(b"\xff\xd8"))  # JPEG magic bytes


class EnrichImageViewTests(APITestCase):
    """POST /api/import/enrich-image/ — download a webpage image, OCR it,
    then enrich it through the same pipeline as typed/selected text. Mirrors
    EnrichVoiceViewTests' structure. The SSRF/format checks themselves are
    covered by FetchImageSafelyTests above — this class only checks the
    view's own composition (quota, error-status mapping, response shape)."""

    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.client.force_authenticate(self.user)
        self.url = reverse("import-enrich-image")

    def _post(self, **overrides):
        payload = {"image_url": "https://example.com/photo.jpg", "language": "de"}
        payload.update(overrides)
        return self.client.post(self.url, payload, format="json")

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        res = self._post()
        self.assertEqual(res.status_code, 401)

    @patch("apps.imports.views.normalize_image")
    @patch("apps.imports.views.fetch_image_safely")
    def test_unsafe_url_returns_400(self, mock_fetch, mock_normalize):
        mock_fetch.side_effect = UnsafeUrlError("blocked host")

        res = self._post()

        self.assertEqual(res.status_code, 400)
        mock_normalize.assert_not_called()

    @patch("apps.imports.views.normalize_image")
    @patch("apps.imports.views.fetch_image_safely")
    def test_oversized_image_returns_413(self, mock_fetch, mock_normalize):
        mock_fetch.side_effect = ImageTooLargeError("too big")

        res = self._post()

        self.assertEqual(res.status_code, 413)
        mock_normalize.assert_not_called()

    @patch("apps.imports.views.normalize_image")
    @patch("apps.imports.views.fetch_image_safely")
    def test_invalid_image_bytes_returns_400(self, mock_fetch, mock_normalize):
        mock_fetch.return_value = b"raw"
        mock_normalize.side_effect = ImageFetchError("not an image")

        res = self._post()

        self.assertEqual(res.status_code, 400)

    @patch("apps.imports.views.enrich_card")
    @patch("apps.imports.views.extract_text_from_image")
    @patch("apps.imports.views.normalize_image")
    @patch("apps.imports.views.fetch_image_safely")
    def test_empty_ocr_returns_empty_proposal_with_image(
        self, mock_fetch, mock_normalize, mock_extract, mock_enrich
    ):
        mock_fetch.return_value = b"raw-bytes"
        mock_normalize.return_value = (b"jpeg-bytes", "image/jpeg")
        mock_extract.return_value = {"text": "", "kind": "word", "ok": True, "status_code": 200}

        res = self._post()

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["front"], "")
        self.assertEqual(
            res.data["image_data_url"],
            f"data:image/jpeg;base64,{base64.b64encode(b'jpeg-bytes').decode('ascii')}",
        )
        # Gemini genuinely ran and reported no text — not a service failure.
        self.assertFalse(res.data["ocr_failed"])
        mock_enrich.assert_not_called()

    @patch("apps.imports.views.enrich_card")
    @patch("apps.imports.views.extract_text_from_image")
    @patch("apps.imports.views.normalize_image")
    @patch("apps.imports.views.fetch_image_safely")
    def test_successful_ocr_flows_into_enrichment(
        self, mock_fetch, mock_normalize, mock_extract, mock_enrich
    ):
        mock_fetch.return_value = b"raw-bytes"
        mock_normalize.return_value = (b"jpeg-bytes", "image/jpeg")
        mock_extract.return_value = {"text": "Haus", "kind": "word", "ok": True, "status_code": 200}
        mock_enrich.return_value = {
            "card_type": "vocab", "back": "house", "reading": "", "article": "das",
            "plural": "Häuser", "example": "Das ist mein Haus.",
        }

        res = self._post(language="de", back_language="English")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["front"], "Haus")
        self.assertEqual(res.data["back"], "house")
        self.assertIn("image_data_url", res.data)
        self.assertFalse(res.data["ocr_failed"])
        # OCR runs on the normalized (already size-capped) bytes, the same
        # ones returned/stored — not the raw download.
        mock_extract.assert_called_once_with(b"jpeg-bytes", mime_type="image/jpeg", language="de")
        # kind falls back to the request's card_type ("vocab", the default)
        # when OCR's own "kind" isn't "sentence" — same as EnrichVoiceView.
        mock_enrich.assert_called_once_with("Haus", "de", "vocab", "English")

    @patch("apps.imports.views.enrich_card")
    @patch("apps.imports.views.extract_text_from_image")
    @patch("apps.imports.views.normalize_image")
    @patch("apps.imports.views.fetch_image_safely")
    def test_quota_consumed_exactly_once(self, mock_fetch, mock_normalize, mock_extract, mock_enrich):
        mock_fetch.return_value = b"raw-bytes"
        mock_normalize.return_value = (b"jpeg-bytes", "image/jpeg")
        mock_extract.return_value = {"text": "Haus", "kind": "word", "ok": True, "status_code": 200}
        mock_enrich.return_value = {
            "card_type": "vocab", "back": "house", "reading": "", "article": "none",
            "plural": "", "example": "",
        }

        res = self._post()

        self.assertEqual(res.status_code, 200)
        usage = AiUsage.objects.get(user=self.user, day=timezone.now().date())
        self.assertEqual(usage.count, 1)

    @patch("apps.imports.views.fetch_image_safely")
    def test_quota_still_consumed_when_url_is_blocked(self, mock_fetch):
        # AiQuotaMixin.initial() fires before post()'s body runs — matches
        # EnrichVoiceView's existing oversized-audio precedent, not a new
        # behavior introduced here.
        mock_fetch.side_effect = UnsafeUrlError("blocked host")

        self._post()

        usage = AiUsage.objects.get(user=self.user, day=timezone.now().date())
        self.assertEqual(usage.count, 1)

    @patch("apps.imports.views.fetch_image_safely")
    def test_returns_429_once_quota_exhausted(self, mock_fetch):
        AiUsage.objects.create(user=self.user, day=timezone.now().date(), count=TRIAL_DAILY_AI_LIMIT)

        res = self._post()

        self.assertEqual(res.status_code, 429)
        mock_fetch.assert_not_called()

    @patch("apps.imports.views.time.sleep")
    @patch("apps.imports.views.enrich_card")
    @patch("apps.imports.views.extract_text_from_image")
    @patch("apps.imports.views.normalize_image")
    @patch("apps.imports.views.fetch_image_safely")
    def test_ocr_retries_on_503_and_succeeds(
        self, mock_fetch, mock_normalize, mock_extract, mock_enrich, mock_sleep
    ):
        mock_fetch.return_value = b"raw-bytes"
        mock_normalize.return_value = (b"jpeg-bytes", "image/jpeg")
        mock_extract.side_effect = [
            {"text": "", "kind": "word", "ok": False, "status_code": 503},
            {"text": "Haus", "kind": "word", "ok": True, "status_code": 200},
        ]
        mock_enrich.return_value = {
            "card_type": "vocab", "back": "house", "reading": "", "article": "none",
            "plural": "", "example": "",
        }

        res = self._post()

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["front"], "Haus")
        self.assertFalse(res.data["ocr_failed"])
        self.assertEqual(mock_extract.call_count, 2)
        mock_sleep.assert_called_once_with(0.5)

    @patch("apps.imports.views.time.sleep")
    @patch("apps.imports.views.enrich_card")
    @patch("apps.imports.views.extract_text_from_image")
    @patch("apps.imports.views.normalize_image")
    @patch("apps.imports.views.fetch_image_safely")
    def test_ocr_gives_up_after_exhausting_retries(
        self, mock_fetch, mock_normalize, mock_extract, mock_enrich, mock_sleep
    ):
        mock_fetch.return_value = b"raw-bytes"
        mock_normalize.return_value = (b"jpeg-bytes", "image/jpeg")
        mock_extract.return_value = {"text": "", "kind": "word", "ok": False, "status_code": 503}

        res = self._post()

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["front"], "")
        # Distinguishes "Gemini said there's no text" from "Gemini's call
        # kept failing" — same graceful, still-200, image-still-attached
        # shape either way, just an honest flag for the caption.
        self.assertTrue(res.data["ocr_failed"])
        # 3 attempts total (1 original + 2 retries), matching the two-entry
        # backoff schedule.
        self.assertEqual(mock_extract.call_count, 3)
        self.assertEqual([c.args[0] for c in mock_sleep.call_args_list], [0.5, 1.5])
        mock_enrich.assert_not_called()

    @patch("apps.imports.views.time.sleep")
    @patch("apps.imports.views.enrich_card")
    @patch("apps.imports.views.extract_text_from_image")
    @patch("apps.imports.views.normalize_image")
    @patch("apps.imports.views.fetch_image_safely")
    def test_ocr_429_is_not_retried(self, mock_fetch, mock_normalize, mock_extract, mock_enrich, mock_sleep):
        mock_fetch.return_value = b"raw-bytes"
        mock_normalize.return_value = (b"jpeg-bytes", "image/jpeg")
        mock_extract.return_value = {"text": "", "kind": "word", "ok": False, "status_code": 429}

        res = self._post()

        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["ocr_failed"])
        # 429 means "slow down," not "try again in half a second" — a
        # single attempt, no sleep, no retry.
        mock_extract.assert_called_once()
        mock_sleep.assert_not_called()
        mock_enrich.assert_not_called()


@override_settings(GEMINI_API_KEY="test-key")
class ExtractTextFromImageTests(TestCase):
    """extract_text_from_image: photo bytes are sent to Gemini via inline_data
    (no separate OCR service or preprocessing step) and the parsed text/kind
    drive the Telegram photo lookup; every failure mode degrades "text"/
    "kind" to ""/"word" exactly as before. "ok"/"status_code" are additive —
    Telegram's own callers only read "text"/"kind" and are unaffected; they
    exist so a caller like EnrichImageView can tell a genuine "no text found"
    apart from "the Gemini call itself failed" and decide whether to retry."""

    @patch("requests.post")
    def test_posts_inline_image_and_parses_word(self, mock_post):
        mock_post.return_value = _gemini_response('{"text": "Haus", "kind": "word"}')

        result = extract_text_from_image(b"\x00image", mime_type="image/jpeg", language="de")

        self.assertEqual(result, {"text": "Haus", "kind": "word", "ok": True, "status_code": 200})
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

        self.assertEqual(
            result, {"text": "Ich gehe ins Kino.", "kind": "sentence", "ok": True, "status_code": 200}
        )

    @patch("requests.post")
    def test_skips_the_call_when_unconfigured(self, mock_post):
        with self.settings(GEMINI_API_KEY=""):
            self.assertEqual(
                extract_text_from_image(b"image"),
                {"text": "", "kind": "word", "ok": False, "status_code": None},
            )
        mock_post.assert_not_called()

    @patch("requests.post")
    def test_skips_the_call_without_image(self, mock_post):
        self.assertEqual(
            extract_text_from_image(b""), {"text": "", "kind": "word", "ok": False, "status_code": None}
        )
        mock_post.assert_not_called()

    @patch("requests.post")
    def test_network_failure_degrades_to_empty(self, mock_post):
        mock_post.side_effect = Exception("timeout")

        self.assertEqual(
            extract_text_from_image(b"image"), {"text": "", "kind": "word", "ok": False, "status_code": None}
        )

    @patch("requests.post")
    def test_missing_text_field_degrades_to_empty(self, mock_post):
        # _extract_json_object degrades unparseable content to {} rather than
        # raising, so this is Gemini genuinely answering with nothing usable
        # — "ok" is True (a completed round-trip), not a call failure.
        mock_post.return_value = _gemini_response("not json at all")

        self.assertEqual(
            extract_text_from_image(b"image"), {"text": "", "kind": "word", "ok": True, "status_code": 200}
        )

    @patch("requests.post")
    def test_http_error_reports_status_code(self, mock_post):
        # A real HTTPError (e.g. from res.raise_for_status()) carries its
        # response's status code through — this is what a caller like
        # EnrichImageView's retry loop keys its retry-or-not decision on.
        response = Mock(status_code=503)
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
        mock_post.return_value = response

        result = extract_text_from_image(b"image")

        self.assertEqual(result, {"text": "", "kind": "word", "ok": False, "status_code": 503})

    @patch("requests.post")
    def test_http_error_429_reports_status_code(self, mock_post):
        response = Mock(status_code=429)
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
        mock_post.return_value = response

        result = extract_text_from_image(b"image")

        self.assertEqual(result, {"text": "", "kind": "word", "ok": False, "status_code": 429})


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
