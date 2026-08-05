from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from .models import Deck

User = get_user_model()


class DeckSeedViewTests(APITestCase):
    """POST /api/decks/seed/ provisions the Menschen + Oxford starter trees —
    used when the placement test is submitted or skipped (see apps.placement
    and apps.cards.seeding.seed_for_user)."""

    def setUp(self):
        self.user = User.objects.create_user(email="seeder@example.com")
        self.client.force_authenticate(self.user)
        self.url = reverse("deck-seed")

    def test_seeds_starter_decks(self):
        res = self.client.post(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(Deck.objects.filter(user=self.user, name="Menschen").exists())
        self.assertTrue(Deck.objects.filter(user=self.user, name="Oxford Word Skills").exists())

    def test_is_idempotent(self):
        self.client.post(self.url)
        count_after_first = Deck.objects.filter(user=self.user).count()
        self.client.post(self.url)
        self.assertEqual(Deck.objects.filter(user=self.user).count(), count_after_first)

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(self.url).status_code, 401)
