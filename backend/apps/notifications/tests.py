from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from pywebpush import WebPushException
from rest_framework.test import APITestCase

from apps.cards.models import Card

from .management.commands.poll_telegram_updates import _process_update_safely, process_telegram_update
from .models import PendingTelegramCard, PushSubscription, TelegramLink, TelegramPollerState
from .tasks import check_study_reminders, send_reminder_push, send_reminder_telegram

User = get_user_model()


class PushSubscribeTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.client.force_authenticate(self.user)

    def test_creates_subscription(self):
        res = self.client.post(
            reverse("push-subscribe"),
            {"endpoint": "https://push.example.com/abc", "p256dh": "key1", "auth": "auth1"},
        )
        self.assertEqual(res.status_code, 201)
        sub = PushSubscription.objects.get(endpoint="https://push.example.com/abc")
        self.assertEqual(sub.user, self.user)

    def test_resubscribing_same_endpoint_updates_not_duplicates(self):
        endpoint = "https://push.example.com/abc"
        self.client.post(reverse("push-subscribe"), {"endpoint": endpoint, "p256dh": "key1", "auth": "auth1"})
        res = self.client.post(reverse("push-subscribe"), {"endpoint": endpoint, "p256dh": "key2", "auth": "auth2"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(PushSubscription.objects.filter(endpoint=endpoint).count(), 1)
        self.assertEqual(PushSubscription.objects.get(endpoint=endpoint).p256dh, "key2")

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        res = self.client.post(
            reverse("push-subscribe"),
            {"endpoint": "https://push.example.com/abc", "p256dh": "key1", "auth": "auth1"},
        )
        self.assertEqual(res.status_code, 401)

    def test_second_user_subscribing_same_endpoint_transfers_not_duplicates(self):
        # A shared/reused browser can hand the same push endpoint to a
        # different account. The old owner's row must be replaced outright
        # — not left behind as an orphaned duplicate, and not silently kept
        # readable/writable by the first user.
        endpoint = "https://push.example.com/shared"
        other_user = User.objects.create_user(email="other@example.com")
        PushSubscription.objects.create(user=other_user, endpoint=endpoint, p256dh="old", auth="old")

        res = self.client.post(
            reverse("push-subscribe"), {"endpoint": endpoint, "p256dh": "new", "auth": "new"},
        )

        self.assertEqual(res.status_code, 201)
        self.assertEqual(PushSubscription.objects.filter(endpoint=endpoint).count(), 1)
        sub = PushSubscription.objects.get(endpoint=endpoint)
        self.assertEqual(sub.user, self.user)
        self.assertEqual(sub.p256dh, "new")
        self.assertFalse(PushSubscription.objects.filter(user=other_user, endpoint=endpoint).exists())

    def test_unsubscribe_deletes_row(self):
        endpoint = "https://push.example.com/abc"
        PushSubscription.objects.create(user=self.user, endpoint=endpoint, p256dh="k", auth="a")
        res = self.client.post(reverse("push-unsubscribe"), {"endpoint": endpoint})
        self.assertEqual(res.status_code, 204)
        self.assertFalse(PushSubscription.objects.filter(endpoint=endpoint).exists())


class CheckStudyRemindersTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="learner@example.com",
            study_reminder_time=time(9, 0),
            study_reminder_timezone="Europe/Berlin",
        )
        PushSubscription.objects.create(user=self.user, endpoint="https://push.example.com/1", p256dh="k", auth="a")

    def _at_berlin_9am(self):
        # 09:00 in Europe/Berlin (CEST, UTC+2 in August).
        return datetime(2026, 8, 1, 7, 0, tzinfo=dt_timezone.utc)

    @patch("apps.notifications.tasks.send_reminder_push.delay")
    def test_dispatches_when_time_matches(self, mock_delay):
        check_study_reminders(now=self._at_berlin_9am())
        mock_delay.assert_called_once_with(self.user.id, "2026-08-01")

    @patch("apps.notifications.tasks.send_reminder_push.delay")
    def test_skips_when_already_sent_today(self, mock_delay):
        self.user.study_reminder_last_sent = date(2026, 8, 1)
        self.user.save(update_fields=["study_reminder_last_sent"])
        check_study_reminders(now=self._at_berlin_9am())
        mock_delay.assert_not_called()

    @patch("apps.notifications.tasks.send_reminder_push.delay")
    def test_skips_when_time_does_not_match(self, mock_delay):
        check_study_reminders(now=datetime(2026, 8, 1, 12, 0, tzinfo=dt_timezone.utc))
        mock_delay.assert_not_called()

    @patch("apps.notifications.tasks.send_reminder_push.delay")
    def test_skips_users_without_subscription(self, mock_delay):
        PushSubscription.objects.all().delete()
        check_study_reminders(now=self._at_berlin_9am())
        mock_delay.assert_not_called()

    @patch("apps.notifications.tasks.send_reminder_push.delay")
    def test_skips_users_without_reminder_time(self, mock_delay):
        self.user.study_reminder_time = None
        self.user.save(update_fields=["study_reminder_time"])
        check_study_reminders(now=self._at_berlin_9am())
        mock_delay.assert_not_called()

    @patch("apps.notifications.tasks.send_reminder_telegram.delay")
    @patch("apps.notifications.tasks.send_reminder_push.delay")
    def test_dispatches_telegram_instead_of_push_for_telegram_channel(self, mock_push_delay, mock_telegram_delay):
        self.user.study_reminder_channel = "telegram"
        self.user.save(update_fields=["study_reminder_channel"])
        TelegramLink.objects.create(user=self.user, chat_id=555)
        check_study_reminders(now=self._at_berlin_9am())
        mock_telegram_delay.assert_called_once_with(self.user.id, "2026-08-01")
        mock_push_delay.assert_not_called()

    @patch("apps.notifications.tasks.send_reminder_telegram.delay")
    def test_skips_telegram_channel_without_linked_chat_id(self, mock_delay):
        self.user.study_reminder_channel = "telegram"
        self.user.save(update_fields=["study_reminder_channel"])
        check_study_reminders(now=self._at_berlin_9am())
        mock_delay.assert_not_called()


class SendReminderPushTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.sub = PushSubscription.objects.create(
            user=self.user, endpoint="https://push.example.com/1", p256dh="k", auth="a"
        )

    @patch("apps.notifications.tasks.webpush")
    def test_sends_to_each_subscription(self, mock_webpush):
        send_reminder_push(self.user.id, "2026-08-01")
        mock_webpush.assert_called_once()
        _, kwargs = mock_webpush.call_args
        self.assertEqual(kwargs["subscription_info"]["endpoint"], self.sub.endpoint)
        self.user.refresh_from_db()
        self.assertEqual(self.user.study_reminder_last_sent, date(2026, 8, 1))

    @patch("apps.notifications.tasks.webpush")
    def test_deletes_subscription_on_expired_response(self, mock_webpush):
        exc = WebPushException("gone")
        exc.response = Mock(status_code=410)
        mock_webpush.side_effect = exc
        send_reminder_push(self.user.id, "2026-08-01")
        self.assertFalse(PushSubscription.objects.filter(id=self.sub.id).exists())


@override_settings(TELEGRAM_BOT_TOKEN="test-token", TELEGRAM_BOT_USERNAME="nemo_anki_bot")
class TelegramConnectViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.client.force_authenticate(self.user)

    def test_returns_deep_link(self):
        res = self.client.post(reverse("telegram-connect"))
        self.assertEqual(res.status_code, 200)
        link = TelegramLink.objects.get(user=self.user)
        self.assertEqual(res.data["deep_link"], f"https://t.me/nemo_anki_bot?start={link.connect_token}")

    def test_rotates_token_on_repeated_calls_while_unconnected(self):
        first = self.client.post(reverse("telegram-connect")).data["deep_link"]
        second = self.client.post(reverse("telegram-connect")).data["deep_link"]
        self.assertNotEqual(first, second)

    def test_does_not_rotate_once_connected(self):
        self.client.post(reverse("telegram-connect"))
        link = TelegramLink.objects.get(user=self.user)
        link.chat_id = 42
        link.save(update_fields=["chat_id"])
        res = self.client.post(reverse("telegram-connect"))
        self.assertEqual(res.data["deep_link"], f"https://t.me/nemo_anki_bot?start={link.connect_token}")

    @override_settings(TELEGRAM_BOT_TOKEN="", TELEGRAM_BOT_USERNAME="")
    def test_returns_503_when_unconfigured(self):
        res = self.client.post(reverse("telegram-connect"))
        self.assertEqual(res.status_code, 503)

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        res = self.client.post(reverse("telegram-connect"))
        self.assertEqual(res.status_code, 401)


class TelegramStatusViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.client.force_authenticate(self.user)

    def test_not_connected_without_link(self):
        res = self.client.get(reverse("telegram-status"))
        self.assertEqual(res.data, {"connected": False})

    def test_not_connected_before_chat_id(self):
        TelegramLink.objects.create(user=self.user)
        res = self.client.get(reverse("telegram-status"))
        self.assertEqual(res.data, {"connected": False})

    def test_connected_once_chat_id_set(self):
        TelegramLink.objects.create(user=self.user, chat_id=123)
        res = self.client.get(reverse("telegram-status"))
        self.assertEqual(res.data, {"connected": True})


class TelegramDisconnectViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.client.force_authenticate(self.user)

    def test_clears_chat_id_but_keeps_the_link_row(self):
        link = TelegramLink.objects.create(user=self.user, chat_id=123, default_language="de")
        res = self.client.post(reverse("telegram-disconnect"))
        self.assertEqual(res.status_code, 204)
        link.refresh_from_db()
        self.assertIsNone(link.chat_id)
        self.assertEqual(link.default_language, "de")

    def test_status_reports_disconnected_afterwards(self):
        TelegramLink.objects.create(user=self.user, chat_id=123)
        self.client.post(reverse("telegram-disconnect"))
        res = self.client.get(reverse("telegram-status"))
        self.assertEqual(res.data, {"connected": False})

    def test_study_reminder_channel_stays_telegram_after_disconnect(self):
        # The user picked Telegram intentionally — disconnecting only drops
        # the chat link, it must never fall back to "push" on its own.
        self.user.study_reminder_channel = "telegram"
        self.user.save(update_fields=["study_reminder_channel"])
        TelegramLink.objects.create(user=self.user, chat_id=123)
        res = self.client.post(reverse("telegram-disconnect"))
        self.assertEqual(res.status_code, 204)
        self.user.refresh_from_db()
        self.assertEqual(self.user.study_reminder_channel, "telegram")

    def test_noop_without_a_link(self):
        res = self.client.post(reverse("telegram-disconnect"))
        self.assertEqual(res.status_code, 204)
        self.assertFalse(TelegramLink.objects.filter(user=self.user).exists())

    def test_noop_when_already_disconnected(self):
        TelegramLink.objects.create(user=self.user)
        res = self.client.post(reverse("telegram-disconnect"))
        self.assertEqual(res.status_code, 204)

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        res = self.client.post(reverse("telegram-disconnect"))
        self.assertEqual(res.status_code, 401)


@override_settings(TELEGRAM_BOT_TOKEN="test-token")
class SendReminderTelegramTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        TelegramLink.objects.create(user=self.user, chat_id=999)

    @patch("apps.notifications.tasks.requests.post")
    def test_sends_message_to_chat_id(self, mock_post):
        send_reminder_telegram(self.user.id, "2026-08-01")
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertIn("test-token", args[0])
        self.assertEqual(kwargs["json"]["chat_id"], 999)
        self.user.refresh_from_db()
        self.assertEqual(self.user.study_reminder_last_sent, date(2026, 8, 1))

    @patch("apps.notifications.tasks.requests.post")
    def test_noop_without_linked_chat_id(self, mock_post):
        self.user.telegram_link.delete()
        send_reminder_telegram(self.user.id, "2026-08-01")
        mock_post.assert_not_called()

    @patch("apps.notifications.tasks.requests.post")
    def test_includes_main_menu_keyboard(self, mock_post):
        send_reminder_telegram(self.user.id, "2026-08-01")
        _, kwargs = mock_post.call_args
        self.assertIn("reply_markup", kwargs["json"])
        button_texts = [
            button["text"]
            for row in kwargs["json"]["reply_markup"]["inline_keyboard"]
            for button in row
        ]
        self.assertIn("🔎 Lookup word", button_texts)
        self.assertIn("📝 Sentence", button_texts)
        self.assertIn("🌐 Language", button_texts)

    @patch("apps.notifications.tasks.requests.post")
    def test_mentions_selected_language_when_set(self, mock_post):
        self.user.telegram_link.default_language = "de"
        self.user.telegram_link.save(update_fields=["default_language"])
        send_reminder_telegram(self.user.id, "2026-08-01")
        _, kwargs = mock_post.call_args
        self.assertIn("German", kwargs["json"]["text"])
        self.assertNotIn("/lang", kwargs["json"]["text"])

    @patch("apps.notifications.tasks.requests.post")
    def test_prompts_for_lang_when_no_default_language(self, mock_post):
        send_reminder_telegram(self.user.id, "2026-08-01")
        _, kwargs = mock_post.call_args
        self.assertIn("/lang", kwargs["json"]["text"])


class ProcessTelegramUpdateTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.link = TelegramLink.objects.create(user=self.user)

    def _start_update(self, token, chat_id=777):
        return {"update_id": 1, "message": {"text": f"/start {token}", "chat": {"id": chat_id}}}

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_links_chat_id_on_matching_token(self, mock_post):
        process_telegram_update(self._start_update(self.link.connect_token), "https://api.telegram.org/botX")
        self.link.refresh_from_db()
        self.assertEqual(self.link.chat_id, 777)
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertIn("Connected!", kwargs["json"]["text"])
        self.assertIn("/lang", kwargs["json"]["text"])
        self.assertIn("reply_markup", kwargs["json"])
        button_texts = [
            button["text"]
            for row in kwargs["json"]["reply_markup"]["inline_keyboard"]
            for button in row
        ]
        self.assertIn("🔎 Lookup word", button_texts)
        self.assertIn("📝 Sentence", button_texts)
        self.assertIn("🌐 Language", button_texts)

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_unmatched_token_does_not_link_and_prompts_connect(self, mock_post):
        # chat 777 has no TelegramLink of its own, so a bad token still
        # can't be mistaken for "already connected" (see PR#7).
        process_telegram_update(self._start_update("not-a-real-token"), "https://api.telegram.org/botX")
        self.link.refresh_from_db()
        self.assertIsNone(self.link.chat_id)
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertIn("Connect", kwargs["json"]["text"])

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_reused_token_does_not_relink_but_this_chat_is_unknown(self, mock_post):
        self.link.chat_id = 111
        self.link.save(update_fields=["chat_id"])
        process_telegram_update(self._start_update(self.link.connect_token, chat_id=222), "https://api.telegram.org/botX")
        self.link.refresh_from_db()
        self.assertEqual(self.link.chat_id, 111)  # unchanged — token was already claimed
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertIn("Connect", kwargs["json"]["text"])  # chat 222 itself isn't linked to anything

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_reused_token_from_the_already_linked_chat_gets_welcome_back(self, mock_post):
        self.link.chat_id = 111
        self.link.save(update_fields=["chat_id"])
        process_telegram_update(self._start_update(self.link.connect_token, chat_id=111), "https://api.telegram.org/botX")
        _, kwargs = mock_post.call_args
        self.assertIn("Welcome back", kwargs["json"]["text"])

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_unlinked_chat_gets_connect_prompt(self, mock_post):
        update = {"update_id": 2, "message": {"text": "hello", "chat": {"id": 12345}}}
        process_telegram_update(update, "https://api.telegram.org/botX")
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertIn("Connect", kwargs["json"]["text"])

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_bare_start_when_unlinked_prompts_connect(self, mock_post):
        update = {"update_id": 3, "message": {"text": "/start", "chat": {"id": 54321}}}
        process_telegram_update(update, "https://api.telegram.org/botX")
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertIn("Connect", kwargs["json"]["text"])

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_bare_start_when_already_linked_shows_welcome_back(self, mock_post):
        self.link.chat_id = 999
        self.link.save(update_fields=["chat_id"])
        update = {"update_id": 4, "message": {"text": "/start", "chat": {"id": 999}}}
        process_telegram_update(update, "https://api.telegram.org/botX")
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertIn("Welcome back", kwargs["json"]["text"])
        self.assertIn("reply_markup", kwargs["json"])
        button_texts = [
            button["text"]
            for row in kwargs["json"]["reply_markup"]["inline_keyboard"]
            for button in row
        ]
        self.assertIn("🔎 Lookup word", button_texts)
        self.assertIn("📝 Sentence", button_texts)
        self.assertIn("🌐 Language", button_texts)

    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card_options")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_bare_start_never_triggers_word_lookup(self, mock_post, mock_enrich):
        # Previously "/start" with no token matched nothing and fell through
        # to word lookup, asking Gemini to "translate" the literal text
        # "/start" — see PR#7.
        self.link.chat_id = 999
        self.link.save(update_fields=["chat_id"])
        update = {"update_id": 5, "message": {"text": "/start", "chat": {"id": 999}}}
        process_telegram_update(update, "https://api.telegram.org/botX")
        mock_enrich.assert_not_called()

    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card_options")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_slashless_start_is_treated_as_the_start_command(self, mock_post, mock_enrich):
        # Typing "start" (or "Start") without the leading slash — e.g. a typo
        # or a client that dropped it — used to fall through to word lookup.
        self.link.chat_id = 999
        self.link.save(update_fields=["chat_id"])
        update = {"update_id": 5, "message": {"text": "Start", "chat": {"id": 999}}}
        process_telegram_update(update, "https://api.telegram.org/botX")
        mock_enrich.assert_not_called()
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertIn("Welcome back", kwargs["json"]["text"])

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_help_returns_onboarding_text(self, mock_post):
        self.link.chat_id = 999
        self.link.default_language = "de"
        self.link.save(update_fields=["chat_id", "default_language"])
        update = {"update_id": 6, "message": {"text": "/help", "chat": {"id": 999}}}
        process_telegram_update(update, "https://api.telegram.org/botX")
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertIn("/lang", kwargs["json"]["text"])
        self.assertIn("/sentence", kwargs["json"]["text"])
        self.assertFalse(PendingTelegramCard.objects.filter(user=self.user).exists())

    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card_options")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_slashless_help_is_treated_as_the_help_command(self, mock_post, mock_enrich):
        self.link.chat_id = 999
        self.link.default_language = "de"
        self.link.save(update_fields=["chat_id", "default_language"])
        update = {"update_id": 6, "message": {"text": "HELP", "chat": {"id": 999}}}
        process_telegram_update(update, "https://api.telegram.org/botX")
        mock_enrich.assert_not_called()
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertIn("/lang", kwargs["json"]["text"])

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_menu_command_returns_main_menu_keyboard(self, mock_post):
        self.link.chat_id = 999
        self.link.save(update_fields=["chat_id"])
        update = {"update_id": 7, "message": {"text": "/menu", "chat": {"id": 999}}}
        process_telegram_update(update, "https://api.telegram.org/botX")
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertIn("reply_markup", kwargs["json"])
        button_texts = [
            button["text"]
            for row in kwargs["json"]["reply_markup"]["inline_keyboard"]
            for button in row
        ]
        self.assertIn("🔎 Lookup word", button_texts)
        self.assertIn("📝 Sentence", button_texts)
        self.assertIn("🌐 Language", button_texts)
        self.assertFalse(PendingTelegramCard.objects.filter(user=self.user).exists())

    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card_options")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_slashless_menu_is_treated_as_the_menu_command(self, mock_post, mock_enrich):
        self.link.chat_id = 999
        self.link.save(update_fields=["chat_id"])
        update = {"update_id": 7, "message": {"text": "Menu", "chat": {"id": 999}}}
        process_telegram_update(update, "https://api.telegram.org/botX")
        mock_enrich.assert_not_called()
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertIn("reply_markup", kwargs["json"])

    def test_word_lookup_for_a_word_that_only_partially_matches_a_command(self):
        # "started"/"helping"/"menus" must still go to word lookup — only an
        # exact (case-insensitive) match is treated as the bare command.
        self.link.chat_id = 999
        self.link.default_language = "de"
        self.link.save(update_fields=["chat_id", "default_language"])
        with patch(
            "apps.notifications.management.commands.poll_telegram_updates._handle_word_lookup"
        ) as mock_lookup:
            update = {"update_id": 8, "message": {"text": "started", "chat": {"id": 999}}}
            process_telegram_update(update, "https://api.telegram.org/botX")
        mock_lookup.assert_called_once()


class ProcessUpdateSafelyTests(APITestCase):
    """_process_update_safely wraps process_telegram_update for the poll
    loop (see Command.handle) — a single bad update must never crash the
    whole long-running poller process."""

    def test_survives_and_swallows_an_unexpected_exception(self):
        update = {"update_id": 42, "message": {"text": "hi", "chat": {"id": 1}}}
        with patch(
            "apps.notifications.management.commands.poll_telegram_updates.process_telegram_update",
            side_effect=RuntimeError("boom"),
        ):
            _process_update_safely(update, "https://api.telegram.org/botX")  # must not raise

    def test_still_processes_a_good_update_normally(self):
        user = User.objects.create_user(email="learner@example.com")
        TelegramLink.objects.create(user=user, chat_id=321)
        with patch("apps.notifications.management.commands.poll_telegram_updates.requests.post") as mock_post:
            update = {"update_id": 1, "message": {"text": "/menu", "chat": {"id": 321}}}
            _process_update_safely(update, "https://api.telegram.org/botX")
        mock_post.assert_called_once()

    def test_does_not_leak_the_bot_token_when_logging_a_failure(self):
        update = {"update_id": 7, "message": {"text": "hi", "chat": {"id": 1}}}
        with override_settings(TELEGRAM_BOT_TOKEN="super-secret-token"):
            with patch(
                "apps.notifications.management.commands.poll_telegram_updates.process_telegram_update",
                side_effect=RuntimeError("failed calling https://api.telegram.org/botsuper-secret-token/sendMessage"),
            ):
                with self.assertLogs(
                    "apps.notifications.management.commands.poll_telegram_updates", level="WARNING"
                ) as logs:
                    _process_update_safely(update, "https://api.telegram.org/botsuper-secret-token")
        self.assertNotIn("super-secret-token", "\n".join(logs.output))


class TelegramPollerStateTests(APITestCase):
    def test_load_creates_and_reuses_a_singleton_row(self):
        state = TelegramPollerState.load()
        self.assertEqual(state.offset, 0)
        state.offset = 555
        state.save(update_fields=["offset"])

        reloaded = TelegramPollerState.load()
        self.assertEqual(reloaded.offset, 555)
        self.assertEqual(TelegramPollerState.objects.count(), 1)


class TelegramApiFailureHandlingTests(APITestCase):
    """Telegram returns HTTP 200 with {"ok": false} for plenty of
    rejections (blocked bot, bad chat_id, message too long) — these must be
    detected and handled, not treated as a silent success."""

    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.link = TelegramLink.objects.create(user=self.user, chat_id=999, default_language="de")

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_reply_returns_false_when_telegram_rejects_the_call(self, mock_post):
        mock_post.return_value = Mock(json=lambda: {"ok": False, "description": "Forbidden: bot was blocked"})
        from apps.notifications.management.commands.poll_telegram_updates import _reply

        result = _reply("https://api.telegram.org/botX", 999, "hello")
        self.assertFalse(result)

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_reply_returns_true_when_telegram_accepts_the_call(self, mock_post):
        mock_post.return_value = Mock(json=lambda: {"ok": True, "result": {}})
        from apps.notifications.management.commands.poll_telegram_updates import _reply

        result = _reply("https://api.telegram.org/botX", 999, "hello")
        self.assertTrue(result)

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_reply_returns_false_on_request_exception(self, mock_post):
        import requests

        mock_post.side_effect = requests.ConnectionError("network down")
        from apps.notifications.management.commands.poll_telegram_updates import _reply

        result = _reply("https://api.telegram.org/botX", 999, "hello")
        self.assertFalse(result)

    @patch("apps.notifications.management.commands.poll_telegram_updates.find_thumbnail_url_for")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_finalize_falls_back_to_text_when_sendphoto_is_rejected(self, mock_post, mock_url):
        mock_url.return_value = ""
        pending = PendingTelegramCard.objects.create(
            user=self.user, card_type="vocab", language="de", front="Haus",
            back="house", awaiting_field="",
        )
        # First call is the auto-thumbnail attach path (none, since mock_url
        # returns "" — no sendPhoto for the proposal). The Create tap below
        # triggers _finalize; attach a fake image so _finalize's sendPhoto
        # branch runs and rejects, forcing the plain-text fallback.
        with patch(
            "apps.notifications.management.commands.poll_telegram_updates.attach_thumbnail_from_url"
        ) as mock_attach:
            fake_image = Mock()
            fake_image.image = Mock()
            fake_image.image.open = Mock()
            fake_image.image.read = Mock(return_value=b"fake-jpeg-bytes")
            fake_image.image.close = Mock()
            mock_attach.return_value = fake_image
            pending.image_url = "https://example.com/house.jpg"
            pending.save(update_fields=["image_url"])
            mock_post.return_value = Mock(json=lambda: {"ok": False, "description": "PHOTO_INVALID_DIMENSIONS"})

            update = {
                "update_id": 1,
                "callback_query": {
                    "id": "cb1", "data": f"create:{pending.id}", "message": {"chat": {"id": 999}},
                },
            }
            process_telegram_update(update, "https://api.telegram.org/botX")

        methods_called = [call.args[0] for call in mock_post.call_args_list]
        self.assertTrue(any(url.endswith("/sendPhoto") for url in methods_called))
        self.assertTrue(any(url.endswith("/sendMessage") for url in methods_called))


class TelegramLangCommandTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.link = TelegramLink.objects.create(user=self.user, chat_id=777)

    def _update(self, text):
        return {"update_id": 1, "message": {"text": text, "chat": {"id": 777}}}

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_sets_default_language(self, mock_post):
        process_telegram_update(self._update("/lang de"), "https://api.telegram.org/botX")
        self.link.refresh_from_db()
        self.assertEqual(self.link.default_language, "de")

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_case_insensitive(self, mock_post):
        process_telegram_update(self._update("/lang DE"), "https://api.telegram.org/botX")
        self.link.refresh_from_db()
        self.assertEqual(self.link.default_language, "de")

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_rejects_unsupported_language(self, mock_post):
        process_telegram_update(self._update("/lang fr"), "https://api.telegram.org/botX")
        self.link.refresh_from_db()
        self.assertEqual(self.link.default_language, "")
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertIn("Usage", kwargs["json"]["text"])


class TelegramPendingLookupTests(APITestCase):
    """A word/sentence sent before /lang is set is remembered on
    TelegramLink (not PendingTelegramCard, not a new model) and resumed
    automatically once /lang succeeds — see poll_telegram_updates
    ._stash_pending_lookup / ._handle_lang."""

    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.link = TelegramLink.objects.create(user=self.user, chat_id=777)

    def _update(self, text):
        return {"update_id": 1, "message": {"text": text, "chat": {"id": 777}}}

    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card_options")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_word_before_lang_is_stashed_on_the_link(self, mock_post, mock_enrich):
        process_telegram_update(self._update("Haus"), "https://api.telegram.org/botX")

        self.link.refresh_from_db()
        self.assertEqual(self.link.pending_lookup_text, "Haus")
        self.assertEqual(self.link.pending_lookup_card_type, "vocab")
        self.assertIsNotNone(self.link.pending_lookup_expires_at)
        mock_enrich.assert_not_called()
        self.assertFalse(PendingTelegramCard.objects.filter(user=self.user).exists())
        _, kwargs = mock_post.call_args
        self.assertIn('"Haus"', kwargs["json"]["text"])

    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_oversized_input_is_truncated_before_stashing(self, mock_post, mock_enrich):
        # pending_lookup_text is max_length=200 — an untruncated write would
        # raise a DataError and crash the whole poller (see PR#8 review).
        long_sentence = "Ich gehe " * 40  # well over 200 characters
        process_telegram_update(
            self._update(f"/sentence {long_sentence}"), "https://api.telegram.org/botX"
        )

        self.link.refresh_from_db()
        self.assertEqual(len(self.link.pending_lookup_text), 200)
        self.assertEqual(self.link.pending_lookup_text, long_sentence.strip()[:200])
        mock_enrich.assert_not_called()

    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_sentence_before_lang_is_stashed_on_the_link(self, mock_post, mock_enrich):
        process_telegram_update(
            self._update("/sentence Ich gehe heute ins Kino."), "https://api.telegram.org/botX"
        )

        self.link.refresh_from_db()
        self.assertEqual(self.link.pending_lookup_text, "Ich gehe heute ins Kino.")
        self.assertEqual(self.link.pending_lookup_card_type, "sentence")
        mock_enrich.assert_not_called()
        self.assertFalse(PendingTelegramCard.objects.filter(user=self.user).exists())

    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card_options")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_lang_automatically_resumes_a_fresh_vocab_stash(self, mock_post, mock_enrich):
        mock_enrich.return_value = {
            "translations": ["house"], "pronunciations": [], "article": "das", "plural": "", "example": "",
        }
        process_telegram_update(self._update("Haus"), "https://api.telegram.org/botX")
        mock_post.reset_mock()

        process_telegram_update(self._update("/lang de"), "https://api.telegram.org/botX")

        mock_enrich.assert_called_once_with("Haus", "de", "vocab", "English")
        self.link.refresh_from_db()
        self.assertEqual(self.link.pending_lookup_text, "")
        self.assertIsNone(self.link.pending_lookup_expires_at)
        pending = PendingTelegramCard.objects.get(user=self.user)
        self.assertEqual(pending.front, "Haus")
        # "Got it" confirmation, then the resumed translation prompt.
        self.assertEqual(mock_post.call_count, 2)

    @patch("apps.notifications.management.commands.poll_telegram_updates.find_thumbnail_url_for")
    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_lang_automatically_resumes_a_fresh_sentence_stash(self, mock_post, mock_enrich, mock_url):
        mock_url.return_value = ""
        mock_enrich.return_value = {
            "back": "I am going to the cinema today.", "reading": "", "article": "none",
            "plural": "", "example": "",
        }
        process_telegram_update(
            self._update("/sentence Ich gehe heute ins Kino."), "https://api.telegram.org/botX"
        )
        mock_post.reset_mock()

        process_telegram_update(self._update("/lang de"), "https://api.telegram.org/botX")

        mock_enrich.assert_called_with("Ich gehe heute ins Kino.", "de", "sentence", "English")
        pending = PendingTelegramCard.objects.get(user=self.user)
        self.assertEqual(pending.card_type, "sentence")
        self.assertEqual(pending.awaiting_field, "")  # straight to proposal, no picker

    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card_options")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_expired_stash_is_cleared_and_not_resumed(self, mock_post, mock_enrich):
        process_telegram_update(self._update("Haus"), "https://api.telegram.org/botX")
        self.link.refresh_from_db()
        self.link.pending_lookup_expires_at = timezone.now() - timedelta(minutes=1)
        self.link.save(update_fields=["pending_lookup_expires_at"])
        mock_post.reset_mock()

        process_telegram_update(self._update("/lang de"), "https://api.telegram.org/botX")

        mock_enrich.assert_not_called()
        self.link.refresh_from_db()
        self.assertEqual(self.link.pending_lookup_text, "")
        self.assertFalse(PendingTelegramCard.objects.filter(user=self.user).exists())
        mock_post.assert_called_once()  # only the "Got it" confirmation, no resumed prompt

    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card_options")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_invalid_lang_code_keeps_the_stash(self, mock_post, mock_enrich):
        process_telegram_update(self._update("Haus"), "https://api.telegram.org/botX")

        process_telegram_update(self._update("/lang fr"), "https://api.telegram.org/botX")

        self.link.refresh_from_db()
        self.assertEqual(self.link.pending_lookup_text, "Haus")
        mock_enrich.assert_not_called()

    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card_options")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_newest_stash_replaces_the_older_one(self, mock_post, mock_enrich):
        process_telegram_update(self._update("Haus"), "https://api.telegram.org/botX")
        process_telegram_update(self._update("Baum"), "https://api.telegram.org/botX")

        self.link.refresh_from_db()
        self.assertEqual(self.link.pending_lookup_text, "Baum")

    @patch("apps.notifications.management.commands.poll_telegram_updates.consume_ai_quota")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_quota_exceeded_at_resume_time_replies_with_quota_message(self, mock_post, mock_quota):
        from rest_framework.exceptions import Throttled

        process_telegram_update(self._update("Haus"), "https://api.telegram.org/botX")
        mock_quota.side_effect = Throttled(detail="You've reached today's AI limit (40).")
        mock_post.reset_mock()

        process_telegram_update(self._update("/lang de"), "https://api.telegram.org/botX")

        self.assertFalse(PendingTelegramCard.objects.filter(user=self.user).exists())
        _, kwargs = mock_post.call_args
        self.assertIn("AI limit", kwargs["json"]["text"])


class TelegramInputLengthTests(APITestCase):
    """A word/sentence over MAX_LOOKUP_TEXT_LENGTH must never reach the
    database unclipped — PendingTelegramCard.front and TelegramLink
    .pending_lookup_text are both max_length=200, and an unclipped write
    would raise a DataError and crash the poller (see PR#9)."""

    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.link = TelegramLink.objects.create(user=self.user, chat_id=777, default_language="de")

    def _update(self, text):
        return {"update_id": 1, "message": {"text": text, "chat": {"id": 777}}}

    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card_options")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_oversized_word_is_truncated_when_language_already_set(self, mock_post, mock_enrich):
        mock_enrich.return_value = {
            "translations": [], "pronunciations": [], "article": "none", "plural": "", "example": "",
        }
        long_word = "Donaudampfschifffahrt" * 15  # well over 200 characters

        process_telegram_update(self._update(long_word), "https://api.telegram.org/botX")

        expected = long_word[:200]
        mock_enrich.assert_called_once_with(expected, "de", "vocab", "English")
        pending = PendingTelegramCard.objects.get(user=self.user)
        self.assertEqual(pending.front, expected)
        self.assertEqual(len(pending.front), 200)

    @patch("apps.notifications.management.commands.poll_telegram_updates.find_thumbnail_url_for")
    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_oversized_sentence_is_truncated_when_language_already_set(self, mock_post, mock_enrich, mock_url):
        mock_url.return_value = ""
        mock_enrich.return_value = {
            "back": "...", "reading": "", "article": "none", "plural": "", "example": "",
        }
        long_sentence = "Ich gehe heute ins Kino " * 15  # well over 200 characters

        process_telegram_update(
            self._update(f"/sentence {long_sentence}"), "https://api.telegram.org/botX"
        )

        expected = long_sentence.strip()[:200]
        mock_enrich.assert_called_once_with(expected, "de", "sentence", "English")
        pending = PendingTelegramCard.objects.get(user=self.user)
        self.assertEqual(pending.front, expected)
        self.assertEqual(len(pending.front), 200)

    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card_options")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_oversized_word_is_truncated_before_stashing_when_language_unset(self, mock_post, mock_enrich):
        self.link.default_language = ""
        self.link.save(update_fields=["default_language"])
        long_word = "Donaudampfschifffahrt" * 15

        process_telegram_update(self._update(long_word), "https://api.telegram.org/botX")

        self.link.refresh_from_db()
        self.assertEqual(self.link.pending_lookup_text, long_word[:200])
        self.assertEqual(len(self.link.pending_lookup_text), 200)
        mock_enrich.assert_not_called()
        self.assertFalse(PendingTelegramCard.objects.filter(user=self.user).exists())


class TelegramWordLookupTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.link = TelegramLink.objects.create(user=self.user, chat_id=777)

    def _update(self, text):
        return {"update_id": 1, "message": {"text": text, "chat": {"id": 777}}}

    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card_options")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_prompts_for_lang_when_unset(self, mock_post, mock_enrich):
        process_telegram_update(self._update("Haus"), "https://api.telegram.org/botX")
        mock_enrich.assert_not_called()
        self.assertFalse(PendingTelegramCard.objects.filter(user=self.user).exists())
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertIn("/lang", kwargs["json"]["text"])

    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card_options")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_translation_options_shown_as_buttons(self, mock_post, mock_enrich):
        self.link.default_language = "de"
        self.link.save(update_fields=["default_language"])
        mock_enrich.return_value = {
            "translations": ["house", "home", "building"], "pronunciations": ["howss"],
            "article": "das", "plural": "Häuser", "example": "Das ist mein Haus.",
        }
        process_telegram_update(self._update("Haus"), "https://api.telegram.org/botX")
        pending = PendingTelegramCard.objects.get(user=self.user)
        self.assertEqual(pending.front, "Haus")
        self.assertEqual(pending.translation_options, ["house", "home", "building"])
        self.assertEqual(pending.awaiting_field, "back")
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        rows = kwargs["json"]["reply_markup"]["inline_keyboard"]
        self.assertEqual([r[0]["text"] for r in rows[:3]], ["house", "home", "building"])
        self.assertEqual(rows[0][0]["callback_data"], f"choose_back:{pending.id}:0")
        self.assertEqual(rows[-1][0]["callback_data"], f"pick_own_back:{pending.id}")
        # No card written yet — only after both fields are resolved.
        self.assertEqual(Card.objects.count(), 0)

    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card_options")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_no_options_falls_back_to_manual_prompt(self, mock_post, mock_enrich):
        self.link.default_language = "de"
        self.link.save(update_fields=["default_language"])
        mock_enrich.return_value = {"translations": [], "pronunciations": [], "article": "none", "plural": "", "example": ""}
        process_telegram_update(self._update("Haus"), "https://api.telegram.org/botX")
        _, kwargs = mock_post.call_args
        self.assertNotIn("reply_markup", kwargs["json"])
        self.assertIn("translation", kwargs["json"]["text"])

    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card_options")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_lookup_upserts_a_single_pending_card_per_user(self, mock_post, mock_enrich):
        # A second lookup only happens once the wizard has fully finished
        # (the pending row is gone) — process_telegram_update always routes
        # to the wizard reply while awaiting_field is set (see
        # test_lookup_upserts... in TelegramWizardFlowTests for that
        # routing). This exercises _handle_word_lookup's update_or_create
        # directly to prove it replaces rather than duplicates.
        from apps.notifications.management.commands.poll_telegram_updates import _handle_word_lookup

        self.link.default_language = "de"
        self.link.save(update_fields=["default_language"])
        mock_enrich.return_value = {"translations": [], "pronunciations": [], "article": "none", "plural": "", "example": ""}
        _handle_word_lookup(self.link, "https://api.telegram.org/botX", 777, "Haus")
        _handle_word_lookup(self.link, "https://api.telegram.org/botX", 777, "Baum")
        self.assertEqual(PendingTelegramCard.objects.filter(user=self.user).count(), 1)
        self.assertEqual(PendingTelegramCard.objects.get(user=self.user).front, "Baum")

    @patch("apps.notifications.management.commands.poll_telegram_updates.consume_ai_quota")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_quota_exceeded_replies_with_message(self, mock_post, mock_quota):
        from rest_framework.exceptions import Throttled

        self.link.default_language = "de"
        self.link.save(update_fields=["default_language"])
        mock_quota.side_effect = Throttled(detail="You've reached today's AI limit (40).")
        process_telegram_update(self._update("Haus"), "https://api.telegram.org/botX")
        self.assertFalse(PendingTelegramCard.objects.filter(user=self.user).exists())
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertIn("AI limit", kwargs["json"]["text"])


class TelegramWizardFlowTests(APITestCase):
    """The translate -> pronunciation -> Create/Edit proposal wizard, once a
    PendingTelegramCard already exists (as it would after a word lookup)."""

    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.link = TelegramLink.objects.create(user=self.user, chat_id=777, default_language="de")
        self.pending = PendingTelegramCard.objects.create(
            user=self.user, language="de", front="Haus",
            article="das", plural="Häuser", example="Das ist mein Haus.",
            translation_options=["house", "home"], pronunciation_options=["howss"],
            awaiting_field="back",
        )

    def _update(self, text):
        return {"update_id": 1, "message": {"text": text, "chat": {"id": 777}}}

    def _callback(self, data):
        return {"update_id": 1, "callback_query": {"id": "cb1", "data": data, "message": {"chat": {"id": 777}}}}

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_choose_back_advances_to_pronunciation_options(self, mock_post):
        process_telegram_update(self._callback(f"choose_back:{self.pending.id}:1"), "https://api.telegram.org/botX")
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.back, "home")
        self.assertEqual(self.pending.awaiting_field, "reading")
        self.assertEqual(Card.objects.count(), 0)
        _, kwargs = mock_post.call_args
        rows = kwargs["json"]["reply_markup"]["inline_keyboard"]
        self.assertEqual(rows[0][0]["callback_data"], f"choose_reading:{self.pending.id}:0")

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_typed_translation_behaves_like_choosing_an_option(self, mock_post):
        process_telegram_update(self._update("apartment"), "https://api.telegram.org/botX")
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.back, "apartment")
        self.assertEqual(self.pending.awaiting_field, "reading")
        self.assertEqual(Card.objects.count(), 0)

    @patch("apps.notifications.management.commands.poll_telegram_updates.find_thumbnail_url_for")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_choose_reading_shows_proposal_without_creating_a_card(self, mock_post, mock_url):
        mock_url.return_value = ""
        self.pending.back = "house"
        self.pending.awaiting_field = "reading"
        self.pending.save(update_fields=["back", "awaiting_field"])
        process_telegram_update(self._callback(f"choose_reading:{self.pending.id}:0"), "https://api.telegram.org/botX")

        self.pending.refresh_from_db()
        self.assertEqual(self.pending.reading, "howss")
        self.assertEqual(self.pending.awaiting_field, "")
        self.assertEqual(Card.objects.count(), 0)
        self.assertTrue(PendingTelegramCard.objects.filter(id=self.pending.id).exists())
        args, kwargs = mock_post.call_args
        self.assertIn("sendMessage", args[0])
        self.assertIn("Meaning: house", kwargs["json"]["text"])
        buttons = kwargs["json"]["reply_markup"]["inline_keyboard"]
        self.assertEqual(buttons[0][0]["callback_data"], f"create:{self.pending.id}")
        self.assertEqual(buttons[1][0]["callback_data"], f"edit:{self.pending.id}")

    @patch("apps.notifications.management.commands.poll_telegram_updates.find_thumbnail_url_for")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_create_button_finalizes_and_saves_exactly_one_card(self, mock_post, mock_url):
        mock_url.return_value = ""
        self.pending.back = "house"
        self.pending.reading = "howss"
        self.pending.awaiting_field = ""
        self.pending.save(update_fields=["back", "reading", "awaiting_field"])

        process_telegram_update(self._callback(f"create:{self.pending.id}"), "https://api.telegram.org/botX")

        card = Card.objects.get(front="Haus", deck__user=self.user)
        self.assertEqual(card.back, "house")
        self.assertEqual(card.reading, "howss")
        self.assertFalse(PendingTelegramCard.objects.filter(id=self.pending.id).exists())
        self.assertEqual(Card.objects.count(), 1)

    @patch("apps.notifications.management.commands.poll_telegram_updates.find_thumbnail_url_for")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_typed_pronunciation_shows_proposal_without_creating_a_card(self, mock_post, mock_url):
        mock_url.return_value = ""
        self.pending.back = "house"
        self.pending.awaiting_field = "reading"
        self.pending.save(update_fields=["back", "awaiting_field"])
        process_telegram_update(self._update("HOWSS"), "https://api.telegram.org/botX")

        self.pending.refresh_from_db()
        self.assertEqual(self.pending.reading, "HOWSS")
        self.assertEqual(Card.objects.count(), 0)

    @patch("apps.notifications.management.commands.poll_telegram_updates.find_thumbnail_url_for")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_skip_shows_proposal_with_blank_reading(self, mock_post, mock_url):
        mock_url.return_value = ""
        self.pending.back = "house"
        self.pending.awaiting_field = "reading"
        self.pending.save(update_fields=["back", "awaiting_field"])
        process_telegram_update(self._update("/skip"), "https://api.telegram.org/botX")

        self.pending.refresh_from_db()
        self.assertEqual(self.pending.reading, "")
        self.assertEqual(Card.objects.count(), 0)

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_pick_own_back_reprompts_manually(self, mock_post):
        process_telegram_update(self._callback(f"pick_own_back:{self.pending.id}"), "https://api.telegram.org/botX")
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.awaiting_field, "back")
        _, kwargs = mock_post.call_args
        self.assertIn("translation", kwargs["json"]["text"])

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_edit_button_reprompts_translation_and_keeps_pending(self, mock_post):
        self.pending.back = "house"
        self.pending.reading = "howss"
        self.pending.awaiting_field = ""
        self.pending.save(update_fields=["back", "reading", "awaiting_field"])

        process_telegram_update(self._callback(f"edit:{self.pending.id}"), "https://api.telegram.org/botX")

        self.pending.refresh_from_db()
        self.assertEqual(self.pending.awaiting_field, "back")
        self.assertTrue(PendingTelegramCard.objects.filter(id=self.pending.id).exists())
        _, kwargs = mock_post.call_args
        self.assertIn("translation", kwargs["json"]["text"])

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_out_of_range_choose_back_index_is_noop(self, mock_post):
        process_telegram_update(self._callback(f"choose_back:{self.pending.id}:9"), "https://api.telegram.org/botX")
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.back, "")
        self.assertEqual(self.pending.awaiting_field, "back")

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_out_of_range_choose_reading_index_is_noop(self, mock_post):
        self.pending.back = "house"
        self.pending.awaiting_field = "reading"
        self.pending.save(update_fields=["back", "awaiting_field"])
        process_telegram_update(self._callback(f"choose_reading:{self.pending.id}:9"), "https://api.telegram.org/botX")
        self.assertFalse(Card.objects.exists())
        self.assertTrue(PendingTelegramCard.objects.filter(id=self.pending.id).exists())

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_unknown_create_id_is_noop(self, mock_post):
        process_telegram_update(self._callback("create:999999"), "https://api.telegram.org/botX")
        self.assertFalse(Card.objects.exists())
        mock_post.assert_called_once()  # only answerCallbackQuery


class TelegramProposalImageTests(APITestCase):
    """The Create/Edit proposal auto-suggests a picture by URL only (no
    download) — see apps.cards.image_search.find_thumbnail_url_for. The
    actual download happens exactly once, if/when Create is tapped, via
    apps.cards.image_search.attach_thumbnail_from_url."""

    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.link = TelegramLink.objects.create(user=self.user, chat_id=777, default_language="de")
        self.pending = PendingTelegramCard.objects.create(
            user=self.user, language="de", front="Haus", back="house",
            article="das", plural="Häuser", example="Das ist mein Haus.",
            awaiting_field="reading",
        )

    def _update(self, text):
        return {"update_id": 1, "message": {"text": text, "chat": {"id": 777}}}

    def _callback(self, data):
        return {"update_id": 1, "callback_query": {"id": "cb1", "data": data, "message": {"chat": {"id": 777}}}}

    @patch("apps.notifications.management.commands.poll_telegram_updates.find_thumbnail_url_for")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_proposal_sends_photo_by_url_when_found(self, mock_post, mock_url):
        mock_url.return_value = "https://images.example/apple.jpg"
        process_telegram_update(self._update("/skip"), "https://api.telegram.org/botX")

        mock_url.assert_called_once_with("Haus", "house", "de", "vocab")
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.image_url, "https://images.example/apple.jpg")
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertIn("sendPhoto", args[0])
        self.assertEqual(kwargs["json"]["photo"], "https://images.example/apple.jpg")
        self.assertEqual(kwargs["json"]["chat_id"], 777)

    @patch("apps.notifications.management.commands.poll_telegram_updates.find_thumbnail_url_for")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_proposal_falls_back_to_plain_text_when_no_url_found(self, mock_post, mock_url):
        mock_url.return_value = ""
        process_telegram_update(self._update("/skip"), "https://api.telegram.org/botX")

        self.pending.refresh_from_db()
        self.assertEqual(self.pending.image_url, "")
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertIn("sendMessage", args[0])
        self.assertIn("Word: Haus", kwargs["json"]["text"])

    @patch("apps.notifications.management.commands.poll_telegram_updates.attach_thumbnail_from_url")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_create_downloads_the_stored_url_exactly_once(self, mock_post, mock_attach):
        image = Mock()
        mock_attach.return_value = image
        self.pending.image_url = "https://images.example/apple.jpg"
        self.pending.awaiting_field = ""
        self.pending.save(update_fields=["image_url", "awaiting_field"])

        process_telegram_update(self._callback(f"create:{self.pending.id}"), "https://api.telegram.org/botX")

        card = Card.objects.get(front="Haus", deck__user=self.user)
        mock_attach.assert_called_once_with(card, "https://images.example/apple.jpg")
        self.assertEqual(mock_post.call_count, 2)  # answerCallbackQuery + sendPhoto
        args, _ = mock_post.call_args
        self.assertIn("sendPhoto", args[0])

    @patch("apps.notifications.management.commands.poll_telegram_updates.attach_thumbnail_from_url")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_create_skips_download_when_no_image_url_was_stored(self, mock_post, mock_attach):
        self.pending.awaiting_field = ""
        self.pending.save(update_fields=["awaiting_field"])

        process_telegram_update(self._callback(f"create:{self.pending.id}"), "https://api.telegram.org/botX")

        mock_attach.assert_not_called()
        self.assertEqual(mock_post.call_count, 2)  # answerCallbackQuery + sendMessage
        args, kwargs = mock_post.call_args
        self.assertIn("sendMessage", args[0])
        self.assertIn("Added to", kwargs["json"]["text"])


class TelegramSentenceInputTests(APITestCase):
    """/sentence <text> skips the translation/pronunciation picker entirely
    (unlike a plain word lookup) and lands directly on a proposal, using
    enrich_card the same way _regenerate does."""

    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.link = TelegramLink.objects.create(
            user=self.user, chat_id=777, default_language="de", default_back_language="English",
        )

    def _update(self, text):
        return {"update_id": 1, "message": {"text": text, "chat": {"id": 777}}}

    @patch("apps.notifications.management.commands.poll_telegram_updates.find_thumbnail_url_for")
    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_sentence_lands_directly_on_a_proposal(self, mock_post, mock_enrich, mock_url):
        mock_url.return_value = ""
        mock_enrich.return_value = {
            "back": "I am going to the cinema today.", "reading": "", "article": "none",
            "plural": "", "example": "",
        }
        process_telegram_update(self._update("/sentence Ich gehe heute ins Kino."), "https://api.telegram.org/botX")

        pending = PendingTelegramCard.objects.get(user=self.user)
        self.assertEqual(pending.card_type, "sentence")
        self.assertEqual(pending.front, "Ich gehe heute ins Kino.")
        self.assertEqual(pending.back, "I am going to the cinema today.")
        self.assertEqual(pending.awaiting_field, "")
        self.assertEqual(Card.objects.count(), 0)
        mock_enrich.assert_called_once_with(
            "Ich gehe heute ins Kino.", "de", "sentence", "English",
        )
        # A single message — no translation/pronunciation picker in between.
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertIn("Sentence: Ich gehe heute ins Kino.", kwargs["json"]["text"])
        self.assertNotIn("Which translation is correct?", kwargs["json"]["text"])

    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_requires_language_first(self, mock_post, mock_enrich):
        self.link.default_language = ""
        self.link.save(update_fields=["default_language"])
        process_telegram_update(self._update("/sentence Ich gehe heute ins Kino."), "https://api.telegram.org/botX")

        mock_enrich.assert_not_called()
        self.assertFalse(PendingTelegramCard.objects.filter(user=self.user).exists())
        _, kwargs = mock_post.call_args
        self.assertIn("/lang", kwargs["json"]["text"])

    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_bare_command_shows_usage(self, mock_post, mock_enrich):
        process_telegram_update(self._update("/sentence"), "https://api.telegram.org/botX")

        mock_enrich.assert_not_called()
        self.assertFalse(PendingTelegramCard.objects.filter(user=self.user).exists())
        _, kwargs = mock_post.call_args
        self.assertIn("Usage: /sentence", kwargs["json"]["text"])

    @patch("apps.notifications.management.commands.poll_telegram_updates.consume_ai_quota")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_quota_exceeded_replies_with_message(self, mock_post, mock_quota):
        from rest_framework.exceptions import Throttled

        mock_quota.side_effect = Throttled(detail="You've reached today's AI limit (40).")
        process_telegram_update(self._update("/sentence Ich gehe heute ins Kino."), "https://api.telegram.org/botX")

        self.assertFalse(PendingTelegramCard.objects.filter(user=self.user).exists())
        _, kwargs = mock_post.call_args
        self.assertIn("AI limit", kwargs["json"]["text"])

    @patch("apps.notifications.management.commands.poll_telegram_updates.find_thumbnail_url_for")
    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_create_files_a_sentence_card_in_the_sentences_deck(self, mock_post, mock_enrich, mock_url):
        mock_url.return_value = ""
        mock_enrich.return_value = {"back": "I am going to the cinema.", "reading": "", "article": "none", "plural": "", "example": ""}
        process_telegram_update(self._update("/sentence Ich gehe ins Kino."), "https://api.telegram.org/botX")
        pending = PendingTelegramCard.objects.get(user=self.user)

        update = {"update_id": 2, "callback_query": {"id": "cb1", "data": f"create:{pending.id}", "message": {"chat": {"id": 777}}}}
        process_telegram_update(update, "https://api.telegram.org/botX")

        card = Card.objects.get(front="Ich gehe ins Kino.", deck__user=self.user)
        self.assertEqual(card.card_type, "sentence")
        self.assertEqual(card.deck.full_name, "Sentences (de)")
        self.assertFalse(PendingTelegramCard.objects.filter(id=pending.id).exists())

    @patch("apps.notifications.management.commands.poll_telegram_updates.find_thumbnail_url_for")
    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_a_later_word_lookup_resets_card_type_back_to_vocab(self, mock_post, mock_enrich, mock_url):
        mock_url.return_value = ""
        mock_enrich.return_value = {"back": "I am going.", "reading": "", "article": "none", "plural": "", "example": ""}
        process_telegram_update(self._update("/sentence Ich gehe."), "https://api.telegram.org/botX")
        self.assertEqual(PendingTelegramCard.objects.get(user=self.user).card_type, "sentence")

        with patch(
            "apps.notifications.management.commands.poll_telegram_updates.enrich_card_options"
        ) as mock_options:
            mock_options.return_value = {"translations": [], "pronunciations": [], "article": "none", "plural": "", "example": ""}
            process_telegram_update(self._update("Baum"), "https://api.telegram.org/botX")

        pending = PendingTelegramCard.objects.get(user=self.user)
        self.assertEqual(pending.card_type, "vocab")
        self.assertEqual(pending.front, "Baum")

    @patch("apps.notifications.management.commands.poll_telegram_updates.find_thumbnail_url_for")
    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card_options")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_sentence_input_clears_stale_options_from_a_previous_word_lookup(self, mock_post, mock_options, mock_url):
        mock_options.return_value = {
            "translations": ["tree", "wood"], "pronunciations": ["baʊm"],
            "article": "der", "plural": "die Bäume", "example": "",
        }
        process_telegram_update(self._update("Baum"), "https://api.telegram.org/botX")
        pending = PendingTelegramCard.objects.get(user=self.user)
        self.assertTrue(pending.translation_options)

        # Finish the vocab wizard so awaiting_field is cleared, then switch to /sentence.
        pending.awaiting_field = ""
        pending.save(update_fields=["awaiting_field"])
        mock_url.return_value = ""
        with patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card") as mock_enrich:
            mock_enrich.return_value = {"back": "I am going.", "reading": "", "article": "none", "plural": "", "example": ""}
            process_telegram_update(self._update("/sentence Ich gehe."), "https://api.telegram.org/botX")

        pending.refresh_from_db()
        self.assertEqual(pending.card_type, "sentence")
        self.assertEqual(pending.translation_options, [])
        self.assertEqual(pending.pronunciation_options, [])

    @patch("apps.notifications.management.commands.poll_telegram_updates.find_thumbnail_url_for")
    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_regenerate_passes_sentence_card_type_to_enrich_card(self, mock_post, mock_enrich, mock_url):
        mock_url.return_value = ""
        mock_enrich.return_value = {"back": "I am going.", "reading": "", "article": "none", "plural": "", "example": ""}
        process_telegram_update(self._update("/sentence Ich gehe."), "https://api.telegram.org/botX")
        pending = PendingTelegramCard.objects.get(user=self.user)
        mock_enrich.reset_mock()
        mock_enrich.return_value = {"back": "I'm on my way.", "reading": "", "article": "none", "plural": "", "example": ""}

        update = {"update_id": 2, "callback_query": {"id": "cb1", "data": f"regenerate:{pending.id}", "message": {"chat": {"id": 777}}}}
        process_telegram_update(update, "https://api.telegram.org/botX")

        args, _ = mock_enrich.call_args
        self.assertEqual(args[2], "sentence")

    @patch("apps.notifications.management.commands.poll_telegram_updates.find_thumbnail_url_for")
    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_image_search_receives_sentence_card_type(self, mock_post, mock_enrich, mock_url):
        mock_url.return_value = ""
        mock_enrich.return_value = {"back": "I am going.", "reading": "", "article": "none", "plural": "", "example": ""}
        process_telegram_update(self._update("/sentence Ich gehe."), "https://api.telegram.org/botX")

        mock_url.assert_called_once_with("Ich gehe.", "I am going.", "de", "sentence")


class TelegramRegenerateTests(APITestCase):
    """Regenerate asks Gemini for a fresh take on the whole card — not a pick
    among candidates already fetched — and lands directly on a new proposal,
    with no intermediate translation/pronunciation prompt."""

    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.link = TelegramLink.objects.create(
            user=self.user, chat_id=777, default_language="de", default_back_language="English",
        )
        self.pending = PendingTelegramCard.objects.create(
            user=self.user, language="de", front="Haus", back="house", reading="haʊs",
            article="das", plural="die Häuser", example="Das ist mein Haus.",
            awaiting_field="",
        )

    def _callback(self, data, chat_id=777):
        return {"update_id": 1, "callback_query": {"id": "cb1", "data": data, "message": {"chat": {"id": chat_id}}}}

    @patch("apps.notifications.management.commands.poll_telegram_updates.find_thumbnail_url_for")
    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_regenerate_lands_directly_on_a_new_proposal(self, mock_post, mock_enrich, mock_url):
        mock_url.return_value = ""
        mock_enrich.return_value = {
            "back": "home", "reading": "hoʊm", "article": "das",
            "plural": "die Häuser", "example": "Ich bin zu Hause.",
        }
        process_telegram_update(self._callback(f"regenerate:{self.pending.id}"), "https://api.telegram.org/botX")

        self.pending.refresh_from_db()
        self.assertEqual(self.pending.back, "home")
        self.assertEqual(self.pending.reading, "hoʊm")
        self.assertEqual(self.pending.example, "Ich bin zu Hause.")
        self.assertEqual(Card.objects.count(), 0)
        # answerCallbackQuery + the new proposal — no picker screens in between.
        self.assertEqual(mock_post.call_count, 2)
        args, kwargs = mock_post.call_args
        self.assertIn("sendMessage", args[0])
        self.assertIn("Meaning: home", kwargs["json"]["text"])
        buttons = kwargs["json"]["reply_markup"]["inline_keyboard"]
        self.assertEqual(buttons[2][0]["callback_data"], f"regenerate:{self.pending.id}")

    @patch("apps.notifications.management.commands.poll_telegram_updates.find_thumbnail_url_for")
    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_regenerate_passes_the_full_previous_proposal(self, mock_post, mock_enrich, mock_url):
        mock_url.return_value = ""
        mock_enrich.return_value = {"back": "home", "reading": "", "article": "das", "plural": "", "example": ""}
        process_telegram_update(self._callback(f"regenerate:{self.pending.id}"), "https://api.telegram.org/botX")

        mock_enrich.assert_called_once_with(
            "Haus", "de", "vocab", "English",
            previous_proposal={
                "back": "house", "reading": "haʊs", "article": "das",
                "plural": "die Häuser", "example": "Das ist mein Haus.",
            },
        )

    @patch("apps.notifications.management.commands.poll_telegram_updates.find_thumbnail_url_for")
    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_blank_translation_keeps_the_previous_meaning(self, mock_post, mock_enrich, mock_url):
        mock_url.return_value = ""
        mock_enrich.return_value = {"back": "", "reading": "", "article": "none", "plural": "", "example": ""}
        process_telegram_update(self._callback(f"regenerate:{self.pending.id}"), "https://api.telegram.org/botX")

        self.pending.refresh_from_db()
        self.assertEqual(self.pending.back, "house")  # unchanged — never blanked on a weak AI response
        self.assertEqual(self.pending.reading, "")     # other fields still take the fresh (blank) value

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_unknown_pending_id_is_noop(self, mock_post):
        process_telegram_update(self._callback("regenerate:999999"), "https://api.telegram.org/botX")
        mock_post.assert_called_once()  # only answerCallbackQuery

    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_noop_while_wizard_still_in_progress(self, mock_post, mock_enrich):
        self.pending.awaiting_field = "reading"
        self.pending.save(update_fields=["awaiting_field"])
        process_telegram_update(self._callback(f"regenerate:{self.pending.id}"), "https://api.telegram.org/botX")
        mock_enrich.assert_not_called()
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.awaiting_field, "reading")

    @patch("apps.notifications.management.commands.poll_telegram_updates.consume_ai_quota")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_quota_exceeded_leaves_the_existing_proposal_untouched(self, mock_post, mock_quota):
        from rest_framework.exceptions import Throttled

        mock_quota.side_effect = Throttled(detail="You've reached today's AI limit (40).")
        process_telegram_update(self._callback(f"regenerate:{self.pending.id}"), "https://api.telegram.org/botX")

        self.pending.refresh_from_db()
        self.assertEqual(self.pending.back, "house")
        _, kwargs = mock_post.call_args
        self.assertIn("AI limit", kwargs["json"]["text"])

    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_noop_for_pending_card_belonging_to_different_user(self, mock_post, mock_enrich):
        other_user = User.objects.create_user(email="other@example.com")
        TelegramLink.objects.create(user=other_user, chat_id=888)
        process_telegram_update(
            self._callback(f"regenerate:{self.pending.id}", chat_id=888), "https://api.telegram.org/botX"
        )
        mock_enrich.assert_not_called()
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.back, "house")


class TelegramMainMenuCallbackTests(APITestCase):
    """The /start menu's buttons (see _main_menu_keyboard) — each is a plain
    prompt with no side effects; the user's next message continues through
    the existing word-lookup/sentence/lang flows unchanged."""

    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.link = TelegramLink.objects.create(user=self.user, chat_id=777)

    def _callback(self, data):
        return {"update_id": 1, "callback_query": {"id": "cb1", "data": data, "message": {"chat": {"id": 777}}}}

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_menu_lookup_prompts_without_creating_any_state(self, mock_post):
        process_telegram_update(self._callback("menu:lookup"), "https://api.telegram.org/botX")

        self.assertEqual(mock_post.call_count, 2)  # answerCallbackQuery + the prompt
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["text"], "Send me a word to look up.")
        self.assertFalse(PendingTelegramCard.objects.filter(user=self.user).exists())

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_menu_sentence_prompts_without_creating_any_state(self, mock_post):
        process_telegram_update(self._callback("menu:sentence"), "https://api.telegram.org/botX")

        self.assertEqual(mock_post.call_count, 2)
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["text"], "Send me a sentence.")
        self.assertFalse(PendingTelegramCard.objects.filter(user=self.user).exists())

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_menu_lang_shows_usage(self, mock_post):
        process_telegram_update(self._callback("menu:lang"), "https://api.telegram.org/botX")

        self.assertEqual(mock_post.call_count, 2)
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["text"], "Usage: /lang de or /lang en")
        self.link.refresh_from_db()
        self.assertEqual(self.link.default_language, "")

    @patch("apps.notifications.management.commands.poll_telegram_updates.enrich_card_options")
    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_menu_lookup_then_word_continues_through_existing_flow(self, mock_post, mock_enrich):
        self.link.default_language = "de"
        self.link.save(update_fields=["default_language"])
        mock_enrich.return_value = {
            "translations": [], "pronunciations": [], "article": "none", "plural": "", "example": "",
        }

        process_telegram_update(self._callback("menu:lookup"), "https://api.telegram.org/botX")
        mock_enrich.assert_not_called()

        update = {"update_id": 2, "message": {"text": "Haus", "chat": {"id": 777}}}
        process_telegram_update(update, "https://api.telegram.org/botX")

        mock_enrich.assert_called_once_with("Haus", "de", "vocab", "English")
        self.assertTrue(PendingTelegramCard.objects.filter(user=self.user, front="Haus").exists())


class TelegramCallbackQueryEdgeCaseTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.link = TelegramLink.objects.create(user=self.user, chat_id=777)
        self.pending = PendingTelegramCard.objects.create(
            user=self.user, language="de", front="Haus", back="house",
            article="das", plural="Häuser", example="Das ist mein Haus.",
            awaiting_field="reading",
        )

    @patch("apps.notifications.management.commands.poll_telegram_updates.requests.post")
    def test_noop_for_pending_card_belonging_to_different_user(self, mock_post):
        other_user = User.objects.create_user(email="other@example.com")
        TelegramLink.objects.create(user=other_user, chat_id=888)
        update = {
            "update_id": 1,
            "callback_query": {
                "id": "cb1", "data": f"choose_reading:{self.pending.id}:0",
                "message": {"chat": {"id": 888}},
            },
        }
        process_telegram_update(update, "https://api.telegram.org/botX")
        self.assertTrue(PendingTelegramCard.objects.filter(id=self.pending.id).exists())
        self.assertFalse(Card.objects.filter(front="Haus").exists())
