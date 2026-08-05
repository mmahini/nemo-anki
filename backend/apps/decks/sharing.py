"""Deck Sharing: unlike Book sharing (a live read-only link — safe because
Book/BookLesson/BookCard hold no per-user state), Deck/Card scheduling fields
(state, due, ease, ...) live directly on the Card row with a single owner, so
two users can never safely review the same Card. Sharing a deck therefore
grants the recipient a one-click Import that deep-copies the deck's subtree
into their own account, with fresh SRS state — see apps.books.views for the
analogous BookLessonImportView this mirrors.
"""
from __future__ import annotations

from django.core.files.base import ContentFile

from .models import Deck


def _default_config(user):
    from .models import DeckConfig

    cfg, _ = DeckConfig.objects.get_or_create(user=user, name="Default")
    return cfg


def copy_deck_tree(source_root: Deck, target_user, wrapper_name: str) -> Deck:
    """Recursively copy source_root + all descendants (decks, forward cards,
    and their images) into target_user's account, nested under a top-level
    `wrapper_name` deck — so a shared "Menschen" deck, say, never merges into
    the recipient's own pre-seeded "Menschen" tree by name collision.

    Idempotent per deck node (get_or_create by name+parent); a leaf deck that
    already has cards is left alone on repeat import rather than duplicating
    them. Returns the copy of `source_root` itself (nested under the
    wrapper), not the wrapper — that's the deck the frontend should land on.
    """
    # Imported lazily to keep decks decoupled from the cards app (see
    # DeckSeedView for the same convention).
    from apps.cards.models import CONTENT_FIELDS, Card, CardImage, add_reverse_cards

    cfg = _default_config(target_user)

    def copy_node(src: Deck, parent: Deck) -> Deck:
        new_deck, _ = Deck.objects.get_or_create(
            user=target_user, parent=parent, name=src.name,
            defaults={"config": cfg, "language": src.language},
        )

        if not Card.objects.filter(deck=new_deck).exists():
            src_cards = list(src.cards.filter(direction="forward").order_by("position"))
            new_cards = [
                Card(deck=new_deck, position=i, **{f: getattr(c, f) for f in CONTENT_FIELDS})
                for i, c in enumerate(src_cards)
            ]
            created = Card.objects.bulk_create(new_cards)
            add_reverse_cards(created)

            for src_card, new_card in zip(src_cards, created):
                for img in src_card.images.all():
                    new_img = CardImage(card=new_card, position=img.position, auto=img.auto)
                    new_img.image.save(
                        img.image.name.rsplit("/", 1)[-1], ContentFile(img.image.read()), save=True
                    )

        for child in src.children.all():
            copy_node(child, new_deck)
        return new_deck

    wrapper, _ = Deck.objects.get_or_create(
        user=target_user, parent=None, name=wrapper_name,
        defaults={"config": cfg, "language": ""},
    )
    return copy_node(source_root, wrapper)
