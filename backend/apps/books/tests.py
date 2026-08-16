from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.cards.models import Card
from apps.decks.models import Deck

from .models import Book, BookCard, BookLesson, BookShare

User = get_user_model()


def _book(owner, title="Menschen A1", lessons=2, processed=True, published=False, cards=2):
    """A book with `lessons` units, each holding `cards` template cards."""
    book = Book.objects.create(
        user=owner, title=title, source_language="de",
        translation_language="English", status="ready",
    )
    for i in range(lessons):
        lesson = BookLesson.objects.create(
            book=book, title=f"Unit {i + 1}", position=i,
            raw_text="text", processed=processed, published=published,
        )
        for j in range(cards):
            BookCard.objects.create(
                lesson=lesson, position=j, card_type="vocab",
                front=f"Wort {i + 1}.{j + 1}", back=f"word {i + 1}.{j + 1}",
            )
    return book


class BookLessonPublishViewTests(APITestCase):
    """POST /api/books/<pk>/lessons/<lid>/publish/ — a processed unit joins
    (or leaves) the public deck library."""

    def setUp(self):
        self.owner = User.objects.create_user(email="owner@example.com")
        self.book = _book(self.owner)
        self.lesson = self.book.lessons.first()
        self.client.force_authenticate(self.owner)

    def _url(self, lesson=None):
        return reverse("book-lesson-publish", args=[self.book.id, (lesson or self.lesson).id])

    def test_owner_publishes_processed_unit(self):
        res = self.client.post(self._url(), {"published": True}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["published"])
        self.lesson.refresh_from_db()
        self.assertTrue(self.lesson.published)

    def test_unpublish(self):
        self.lesson.published = True
        self.lesson.save(update_fields=["published"])
        res = self.client.post(self._url(), {"published": False}, format="json")
        self.assertEqual(res.status_code, 200)
        self.lesson.refresh_from_db()
        self.assertFalse(self.lesson.published)

    def test_unprocessed_unit_rejected(self):
        self.lesson.processed = False
        self.lesson.save(update_fields=["processed"])
        res = self.client.post(self._url(), {"published": True}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_unit_without_cards_rejected(self):
        self.lesson.cards.all().delete()
        res = self.client.post(self._url(), {"published": True}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_shared_user_can_publish(self):
        friend = User.objects.create_user(email="friend@example.com")
        BookShare.objects.create(book=self.book, user=friend)
        self.client.force_authenticate(friend)
        res = self.client.post(self._url(), {"published": True}, format="json")
        self.assertEqual(res.status_code, 200)

    def test_stranger_gets_404(self):
        stranger = User.objects.create_user(email="stranger@example.com")
        self.client.force_authenticate(stranger)
        res = self.client.post(self._url(), {"published": True}, format="json")
        self.assertEqual(res.status_code, 404)


class LibraryViewsTests(APITestCase):
    """GET /api/library/ + /api/library/<pk>/ — any signed-in user browses
    books that have published units; only the published units show."""

    def setUp(self):
        self.owner = User.objects.create_user(email="owner@example.com")
        self.browser = User.objects.create_user(email="browser@example.com")
        self.book = _book(self.owner, published=True)
        self.hidden = _book(self.owner, title="Unpublished B1")  # nothing published
        # One extra unit that stays private in the published book.
        self.private_lesson = BookLesson.objects.create(
            book=self.book, title="Unit 99", position=99, processed=True,
        )
        self.client.force_authenticate(self.browser)

    def test_lists_only_books_with_published_units(self):
        res = self.client.get(reverse("library-list"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual([b["id"] for b in res.data], [self.book.id])
        self.assertEqual(res.data[0]["deck_count"], 2)
        self.assertEqual(res.data[0]["card_count"], 4)

    def test_detail_shows_only_published_units(self):
        res = self.client.get(reverse("library-book", args=[self.book.id]))
        self.assertEqual(res.status_code, 200)
        titles = [l["title"] for l in res.data["lessons"]]
        self.assertEqual(titles, ["Unit 1", "Unit 2"])

    def test_book_without_published_units_is_404(self):
        res = self.client.get(reverse("library-book", args=[self.hidden.id]))
        self.assertEqual(res.status_code, 404)

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        res = self.client.get(reverse("library-list"))
        self.assertEqual(res.status_code, 401)


class LibraryAddViewTests(APITestCase):
    """POST /api/library/<pk>/add/ — copy published unit(s) into the caller's
    own decks: a root deck named after the book, one sub-deck per unit."""

    def setUp(self):
        self.owner = User.objects.create_user(email="owner@example.com")
        self.user = User.objects.create_user(email="learner@example.com")
        self.book = _book(self.owner, published=True)
        self.client.force_authenticate(self.user)
        self.url = reverse("library-add", args=[self.book.id])

    def test_add_one_deck(self):
        lesson = self.book.lessons.first()
        res = self.client.post(self.url, {"lesson": lesson.id}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["cards"], 2)
        book_deck = Deck.objects.get(user=self.user, name=self.book.title)
        lesson_deck = Deck.objects.get(user=self.user, parent=book_deck, name=lesson.title)
        self.assertEqual(res.data["lesson_deck"], lesson_deck.id)
        # Forward + reverse directions both exist; content came from the unit.
        self.assertEqual(Card.objects.filter(deck=lesson_deck, direction="forward").count(), 2)

    def test_add_whole_book(self):
        res = self.client.post(self.url, {}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["cards"], 4)
        book_deck = Deck.objects.get(user=self.user, name=self.book.title)
        self.assertEqual(Deck.objects.filter(user=self.user, parent=book_deck).count(), 2)

    def test_re_add_does_not_duplicate_cards(self):
        self.client.post(self.url, {}, format="json")
        res = self.client.post(self.url, {}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["cards"], 0)
        book_deck = Deck.objects.get(user=self.user, name=self.book.title)
        decks = Deck.objects.filter(user=self.user, parent=book_deck)
        total = Card.objects.filter(deck__in=decks, direction="forward").count()
        self.assertEqual(total, 4)

    def test_unpublished_lesson_is_404(self):
        private = BookLesson.objects.create(
            book=self.book, title="Unit 99", position=99, processed=True,
        )
        res = self.client.post(self.url, {"lesson": private.id}, format="json")
        self.assertEqual(res.status_code, 404)

    def test_book_without_published_units_is_404(self):
        hidden = _book(self.owner, title="Hidden")
        res = self.client.post(reverse("library-add", args=[hidden.id]), {}, format="json")
        self.assertEqual(res.status_code, 404)
