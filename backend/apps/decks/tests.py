from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.cards.models import Card

from .models import Deck, DeckConfig, DeckShare

User = get_user_model()


def _config(user) -> DeckConfig:
    cfg, _ = DeckConfig.objects.get_or_create(user=user, name="Default")
    return cfg


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


class DeckShareViewTests(APITestCase):
    """POST/DELETE /api/decks/<pk>/shares/ — mirrors apps.books' BookSharesView."""

    def setUp(self):
        self.owner = User.objects.create_user(email="owner@example.com")
        self.friend = User.objects.create_user(email="friend@example.com")
        self.deck = Deck.objects.create(
            user=self.owner, name="Idioms", config=_config(self.owner), language="de"
        )
        self.client.force_authenticate(self.owner)
        self.url = reverse("deck-shares", args=[self.deck.id])

    def test_owner_can_share_by_email(self):
        res = self.client.post(self.url, {"email": "friend@example.com"})
        self.assertEqual(res.status_code, 201)
        self.assertTrue(DeckShare.objects.filter(deck=self.deck, user=self.friend).exists())
        self.assertEqual(res.data["shared_with"], ["friend@example.com"])

    def test_sharing_is_idempotent(self):
        self.client.post(self.url, {"email": "friend@example.com"})
        self.client.post(self.url, {"email": "friend@example.com"})
        self.assertEqual(DeckShare.objects.filter(deck=self.deck).count(), 1)

    def test_cannot_share_with_self(self):
        res = self.client.post(self.url, {"email": "owner@example.com"})
        self.assertEqual(res.status_code, 400)

    def test_cannot_share_with_unknown_email(self):
        res = self.client.post(self.url, {"email": "nobody@example.com"})
        self.assertEqual(res.status_code, 404)

    def test_non_owner_cannot_share(self):
        self.client.force_authenticate(self.friend)
        res = self.client.post(self.url, {"email": "friend@example.com"})
        self.assertEqual(res.status_code, 404)

    def test_owner_can_unshare(self):
        DeckShare.objects.create(deck=self.deck, user=self.friend)
        res = self.client.delete(self.url, {"email": "friend@example.com"})
        self.assertEqual(res.status_code, 200)
        self.assertFalse(DeckShare.objects.filter(deck=self.deck, user=self.friend).exists())


class DecksSharedViewTests(APITestCase):
    """GET /api/decks/shared/ — decks shared with me, not decks I own."""

    def setUp(self):
        self.owner = User.objects.create_user(email="owner2@example.com")
        self.friend = User.objects.create_user(email="friend2@example.com")
        self.deck = Deck.objects.create(
            user=self.owner, name="Idioms", config=_config(self.owner), language="de"
        )
        DeckShare.objects.create(deck=self.deck, user=self.friend)
        self.url = reverse("deck-shared")

    def test_lists_decks_shared_with_me(self):
        self.client.force_authenticate(self.friend)
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual([d["id"] for d in res.data], [self.deck.id])

    def test_does_not_list_own_decks(self):
        self.client.force_authenticate(self.owner)
        res = self.client.get(self.url)
        self.assertEqual(res.data, [])


class DeckImportViewTests(APITestCase):
    """POST /api/decks/<pk>/import/ — copies a shared deck's subtree into the
    requesting user's own account, under a "Shared by {owner email}" wrapper,
    with fresh SRS state (see apps.decks.sharing.copy_deck_tree)."""

    def setUp(self):
        self.owner = User.objects.create_user(email="owner3@example.com")
        self.friend = User.objects.create_user(email="friend3@example.com")
        cfg = _config(self.owner)
        self.root = Deck.objects.create(user=self.owner, name="Idioms", config=cfg, language="de")
        self.child = Deck.objects.create(
            user=self.owner, parent=self.root, name="Animals", config=cfg, language="de"
        )
        Card.objects.create(deck=self.child, card_type="vocab", front="Hund", back="dog", language="de")
        DeckShare.objects.create(deck=self.root, user=self.friend)
        self.client.force_authenticate(self.friend)
        self.url = reverse("deck-import", args=[self.root.id])

    def test_import_copies_tree_under_wrapper_with_fresh_cards(self):
        res = self.client.post(self.url)
        self.assertEqual(res.status_code, 201)

        imported_root = Deck.objects.get(id=res.data["deck"])
        self.assertEqual(imported_root.name, "Idioms")
        self.assertEqual(imported_root.user, self.friend)
        self.assertEqual(imported_root.parent.name, "Shared by owner3@example.com")

        imported_child = Deck.objects.get(user=self.friend, parent=imported_root, name="Animals")
        cards = Card.objects.filter(deck=imported_child, direction="forward")
        self.assertEqual(cards.count(), 1)
        card = cards.first()
        self.assertEqual(card.front, "Hund")
        self.assertEqual(card.state, "new")
        # Reverse companion is regenerated fresh, never copied cross-user.
        self.assertTrue(
            Card.objects.filter(deck=imported_child, direction="reverse", reverse_of=card).exists()
        )

    def test_reimport_does_not_duplicate_cards(self):
        self.client.post(self.url)
        self.client.post(self.url)
        imported_child = Deck.objects.get(user=self.friend, name="Animals")
        self.assertEqual(Card.objects.filter(deck=imported_child, direction="forward").count(), 1)

    def test_user_without_share_cannot_import(self):
        stranger = User.objects.create_user(email="stranger@example.com")
        self.client.force_authenticate(stranger)
        res = self.client.post(self.url)
        self.assertEqual(res.status_code, 404)
