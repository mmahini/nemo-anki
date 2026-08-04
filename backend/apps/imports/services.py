from apps.cards.models import Card
from apps.decks.models import Deck, DeckConfig


def create_vocab_card(user, word: str, language: str, enriched: dict) -> Card:
    """Turns one AI-enriched word/phrase into a vocab card in the
    per-language deck "Vocabulary (<lang>)" (created on demand). Shared by
    the web app's WordToCardView and the Telegram bot's text-to-card flow
    (apps.notifications.management.commands.poll_telegram_updates) so both
    surfaces file cards the same way."""
    cfg, _ = DeckConfig.objects.get_or_create(user=user, name="Default")
    deck, _ = Deck.objects.get_or_create(
        user=user,
        parent=None,
        name=f"Vocabulary ({language or '?'})",
        defaults={"config": cfg, "language": language},
    )
    last = Card.objects.filter(deck=deck).order_by("-position").first()
    return Card.objects.create(
        deck=deck,
        card_type="vocab",
        language=language,
        front=word,
        back=enriched.get("back", ""),
        reading=enriched.get("reading", ""),
        article=enriched.get("article", "none"),
        plural=enriched.get("plural", ""),
        example=enriched.get("example", ""),
        position=(last.position + 1) if last else 0,
    )


def create_sentence_card(user, sentence: str, language: str, enriched: dict) -> Card:
    """Turns one AI-enriched sentence into a sentence card in the
    per-language deck "Sentences (<lang>)" (created on demand) — the
    Telegram bot's /sentence flow (apps.notifications.management.commands
    .poll_telegram_updates). Mirrors create_vocab_card's shape rather than
    generalizing it, since the two types file into different decks."""
    cfg, _ = DeckConfig.objects.get_or_create(user=user, name="Default")
    deck, _ = Deck.objects.get_or_create(
        user=user,
        parent=None,
        name=f"Sentences ({language or '?'})",
        defaults={"config": cfg, "language": language},
    )
    last = Card.objects.filter(deck=deck).order_by("-position").first()
    return Card.objects.create(
        deck=deck,
        card_type="sentence",
        language=language,
        front=sentence,
        back=enriched.get("back", ""),
        reading=enriched.get("reading", ""),
        article=enriched.get("article", "none"),
        plural=enriched.get("plural", ""),
        example=enriched.get("example", ""),
        position=(last.position + 1) if last else 0,
    )
