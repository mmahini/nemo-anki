# Seeded book structure — Menschen & Oxford Word Skills

The project asked to "put Menschen books for German and Oxford Word Skills for
English (find all items of these book series)". Per the agreed scope we seed the
**complete deck tree** for both series plus a **representative sample of real
cards** in selected decks; the bulk of cards is meant to be added via the Gemini
**Import** flow (paste a book section → draft cards → edit → commit).

Decks are hierarchical (`German::Menschen::A1.1::Lektion 01`).

## Menschen (Hueber) — German

Six split-edition levels; each level = **12 Lektionen** grouped into **4 modules**
of 3 lessons. ([Hueber](https://www.hueber.de/reihe/menschen/lernen))

| Level | Lessons | CEFR |
| ----- | ------- | ---- |
| A1.1 | Lektion 01–12 | A1 |
| A1.2 | Lektion 13–24 | A1 |
| A2.1 | Lektion 01–12 | A2 |
| A2.2 | Lektion 13–24 | A2 |
| B1.1 | Lektion 01–12 | B1 |
| B1.2 | Lektion 13–24 | B1 |

→ `German::Menschen::<level>::Lektion NN` for all 72 lessons. German vocab cards
carry an `article` (der/die/das) and are colour-coded
([GERMAN_COLORS.md](./GERMAN_COLORS.md)).

## Oxford Word Skills — English

Three levels (~80–100 topic units each, >2000 words/level). Units are grouped by
topic. ([OUP](https://elt.oup.com/catalogue/items/global/grammar_vocabulary/oxford-word-skills/))

| Level | CEFR | Sample topic units |
| ----- | ---- | ------------------ |
| Basic | A1–A2 | Basic English, People, Everyday life, Food and drink, Getting around, Places, Study and work, Hobbies and interests, Holidays, Social English, Language |
| Intermediate | B1–B2 | People, Daily life, Work, Leisure, Society, Collocations, Phrasal verbs, Word formation |
| Advanced | C1 | Word building, Connotation, Idioms, Register, Academic, Business |

→ `English::Oxford Word Skills::<level>::<topic unit>`.

## Sample cards seeded

To prove the three card types + colours + grammar table end-to-end, we seed a
small set of real cards into:

- `German::Menschen::A1.1::Lektion 01` — greetings & intros: vocab (with der/die/
  das colours), a sentence card with reading, and a grammar card (verb position /
  "sein" conjugation table).
- `English::Oxford Word Skills::Basic::People` — vocab + a sentence card.

Everything else is an empty, correctly-placed deck ready for import. The seed is
idempotent (`make seed-decks` / runs on deploy) and lives in
`backend/apps/cards/management/commands/seed_decks.py` + `data/seed.json`.
