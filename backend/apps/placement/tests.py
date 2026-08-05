from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from .models import PlacementAttempt, PlacementQuestion

User = get_user_model()


class SubmitPlacementDeckLinkTests(APITestCase):
    """Submitting a placement test provisions the starter decks (if the user
    doesn't have them yet) and points the learner at the one matching their
    result (see apps.cards.seeding.find_level_deck)."""

    def setUp(self):
        self.user = User.objects.create_user(email="learner@example.com")
        self.client.force_authenticate(self.user)

    def _attempt(self, language: str, level_tag: str) -> PlacementAttempt:
        attempt = PlacementAttempt.objects.create(
            user=self.user, language=language, length="quick", total_count=1
        )
        PlacementQuestion.objects.create(
            attempt=attempt, order=0, section="reading", level_tag=level_tag,
            passage="x", question_text="?", choices=["a", "b"], correct_choice_index=0,
        )
        return attempt

    def _submit(self, attempt: PlacementAttempt, question: PlacementQuestion, choice_index: int):
        url = reverse("placement-submit", args=[attempt.id])
        return self.client.post(
            url, {"answers": [{"question_id": question.id, "choice_index": choice_index}]},
            format="json",
        )

    def test_german_a1_result_links_to_a1_1_deck(self):
        attempt = self._attempt("de", "A1")
        question = attempt.questions.first()
        res = self._submit(attempt, question, question.correct_choice_index)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["estimated_level"], "A1")
        self.assertIsNotNone(res.data["deck_id"])

        from apps.decks.models import Deck

        deck = Deck.objects.get(id=res.data["deck_id"])
        self.assertEqual(deck.name, "A1.1")
        self.assertEqual(deck.language, "de")

    def test_english_b1_result_links_to_intermediate_deck(self):
        attempt = self._attempt("en", "B1")
        question = attempt.questions.first()
        res = self._submit(attempt, question, question.correct_choice_index)
        self.assertEqual(res.status_code, 200)

        from apps.decks.models import Deck

        deck = Deck.objects.get(id=res.data["deck_id"])
        self.assertEqual(deck.name, "Intermediate")
        self.assertEqual(deck.language, "en")

    def test_submit_seeds_decks_for_a_user_who_never_had_any(self):
        from apps.decks.models import Deck

        self.assertFalse(Deck.objects.filter(user=self.user).exists())
        attempt = self._attempt("de", "A1")
        question = attempt.questions.first()
        res = self._submit(attempt, question, question.correct_choice_index)
        self.assertIsNotNone(res.data["deck_id"])
        self.assertTrue(Deck.objects.filter(user=self.user, name="Menschen").exists())
