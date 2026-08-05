"""Seed the Menschen (German) + Oxford Word Skills (English) deck trees and a
small set of sample cards. Idempotent — safe to run repeatedly and used both by
`manage.py seed_decks` and to auto-provision starter decks for a new user.

See docs/BOOK_CONTENT.md for the scope rationale.
"""
from __future__ import annotations

from apps.decks.models import Deck, DeckConfig

# ---- Book structure ------------------------------------------------------

MENSCHEN = {
    "A1.1": range(1, 13),
    "A1.2": range(13, 25),
    "A2.1": range(1, 13),
    "A2.2": range(13, 25),
    "B1.1": range(1, 13),
    "B1.2": range(13, 25),
}

OXFORD = {
    "Basic": [
        "Basic English", "People", "Everyday life", "Food and drink",
        "Getting around", "Places", "Study and work", "Hobbies and interests",
        "Holidays", "Social English", "Language",
    ],
    "Intermediate": [
        "People", "Daily life", "Work", "Leisure", "Society",
        "Collocations", "Phrasal verbs", "Word formation",
    ],
    "Advanced": [
        "Word building", "Connotation", "Idioms", "Register",
        "Academic", "Business",
    ],
}

# ---- Sample cards --------------------------------------------------------

_SEIN_TABLE = {
    "headers": ["Person", "sein"],
    "rows": [
        ["ich", "bin"], ["du", "bist"], ["er/sie/es", "ist"],
        ["wir", "sind"], ["ihr", "seid"], ["sie/Sie", "sind"],
    ],
    "highlight": [0, 1],
}

GERMAN_SAMPLES = [
    dict(card_type="vocab", front="Hallo", back="hello", reading="ˈhaloː", article="none"),
    dict(card_type="vocab", front="Name", back="name", reading="ˈnaːmə", article="der"),
    dict(card_type="vocab", front="Frau", back="woman; Mrs", reading="fʁaʊ", article="die"),
    dict(card_type="vocab", front="Kind", back="child", reading="kɪnt", article="das"),
    dict(card_type="vocab", front="Eltern", back="parents", reading="ˈɛltɐn", article="plural"),
    dict(
        card_type="sentence", front="Wie heißen Sie?", back="What is your name? (formal)",
        reading="viː ˈhaɪsn̩ ziː", example="— Wie heißen Sie? — Ich heiße Anna.",
    ),
    dict(
        card_type="grammar", front="Ich ___ Anna.", back="bin",
        notes="sein (to be) — present tense. 1st person singular: ich bin.",
        example="Ich bin Anna. Du bist Tom.", table=_SEIN_TABLE, tags=["sein", "präsens"],
    ),
]

ENGLISH_SAMPLES = [
    dict(card_type="vocab", front="neighbour", back="someone who lives near you", reading="ˈneɪbə"),
    dict(card_type="vocab", front="colleague", back="someone you work with", reading="ˈkɒliːɡ"),
    dict(card_type="vocab", front="relative", back="a member of your family", reading="ˈrelətɪv"),
    dict(
        card_type="sentence", front="Let me introduce myself.",
        back="a polite phrase to start meeting someone", reading="lɛt miː ˌɪntrəˈdjuːs maɪˈsɛlf",
    ),
]


def _config_for(user) -> DeckConfig:
    cfg, _ = DeckConfig.objects.get_or_create(user=user, name="Default")
    return cfg


def _deck(user, cfg, name, parent=None, language=""):
    deck, _ = Deck.objects.get_or_create(
        user=user, parent=parent, name=name,
        defaults={"config": cfg, "language": language},
    )
    return deck


def _add_samples(deck, samples):
    from .models import Card

    if Card.objects.filter(deck=deck).exists():
        return
    for i, s in enumerate(samples):
        Card.objects.create(deck=deck, language=deck.language, position=i, **s)


# Placement test gives a CEFR level (A1..C1); map it onto the sub-level (or
# tier, for English) actually seeded above. Menschen tops out at B1, so B2/C1
# German learners land on the most advanced material we have rather than
# nothing.
GERMAN_LEVEL_MAP = {"A1": "A1.1", "A2": "A2.1", "B1": "B1.1", "B2": "B1.1", "C1": "B1.1"}
ENGLISH_LEVEL_MAP = {"A1": "Basic", "A2": "Basic", "B1": "Intermediate", "B2": "Intermediate", "C1": "Advanced"}


def find_level_deck(user, language: str, cefr_level: str):
    """The seeded deck matching a placement-test result, e.g. (de, "A2") ->
    the "German :: Menschen :: A2.1" deck. None if seeding hasn't run yet."""
    level_map = GERMAN_LEVEL_MAP if language == "de" else ENGLISH_LEVEL_MAP
    level_name = level_map.get(cefr_level)
    if not level_name:
        return None
    # `name` + `language` is unique per user here: the level-deck names in
    # each map only ever appear under that language's own book tree.
    return Deck.objects.filter(user=user, name=level_name, language=language).first()


def seed_for_user(user) -> dict:
    cfg = _config_for(user)

    # German :: Menschen :: <level> :: Lektion NN
    german = _deck(user, cfg, "German", language="de")
    menschen = _deck(user, cfg, "Menschen", parent=german, language="de")
    first_lesson = None
    for level, lessons in MENSCHEN.items():
        level_deck = _deck(user, cfg, level, parent=menschen, language="de")
        for n in lessons:
            lesson = _deck(user, cfg, f"Lektion {n:02d}", parent=level_deck, language="de")
            if level == "A1.1" and n == 1:
                first_lesson = lesson
    if first_lesson:
        _add_samples(first_lesson, GERMAN_SAMPLES)

    # English :: Oxford Word Skills :: <level> :: <unit>
    english = _deck(user, cfg, "English", language="en")
    oxford = _deck(user, cfg, "Oxford Word Skills", parent=english, language="en")
    people_basic = None
    for level, units in OXFORD.items():
        level_deck = _deck(user, cfg, level, parent=oxford, language="en")
        for unit in units:
            unit_deck = _deck(user, cfg, unit, parent=level_deck, language="en")
            if level == "Basic" and unit == "People":
                people_basic = unit_deck
    if people_basic:
        _add_samples(people_basic, ENGLISH_SAMPLES)

    return {"decks": Deck.objects.filter(user=user).count()}
