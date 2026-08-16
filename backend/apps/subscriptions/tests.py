"""Subscription tests — currently the Wiser CDP server-side events: the two
money moments must be reported from the backend, where they actually happen
and where no ad-blocker can eat them."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .models import Subscription

User = get_user_model()


class SubscriptionCdpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("payer@x.com")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_claim_emits_subscription_requested(self):
        with patch("apps.subscriptions.views.cdp.track") as track:
            res = self.client.post(
                reverse("subscription-claim"),
                {"plan": "basic_monthly", "tx_reference": "0xabc"},
            )
        self.assertEqual(res.status_code, 201)
        track.assert_called_once()
        user, event = track.call_args.args[:2]
        self.assertEqual((user, event), (self.user, "subscription_requested"))
        self.assertEqual(
            track.call_args.args[2],
            {"plan": "basic_monthly", "has_tx_reference": True},
        )

    def test_activate_emits_subscription_activated(self):
        sub = Subscription.for_user(self.user)
        with patch("core.cdp.track") as track:
            sub.activate("pro_monthly")
        track.assert_called_once()
        self.assertEqual(track.call_args.args[1], "subscription_activated")
        props = track.call_args.args[2]
        self.assertEqual((props["plan"], props["tier"]), ("pro_monthly", "pro"))

    def test_cdp_is_a_noop_without_config(self):
        """The module must not even spawn a thread when unconfigured — dev,
        CI and tests all run without the env vars."""
        from core import cdp

        with patch("core.cdp.threading.Thread") as thread:
            cdp.track(self.user, "anything")
        thread.assert_not_called()
