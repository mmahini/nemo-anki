# Grammar cards — design

Vocab and sentence cards map cleanly onto flashcards. Grammar is harder: a rule
isn't a single term, and rote-reciting a rule doesn't build the *productive*
skill you actually need. This is the "good idea for grammar cards" the project
asked for.

## The problem with naïve grammar cards

A card with front "Akkusativ" and back "the direct-object case" tests *naming*,
not *using*. You can ace it and still build wrong sentences.

## Our approach: **pattern + cloze + table**

A grammar card combines three complementary recall modes, picked per card via a
`grammar_mode` hint:

1. **Cloze production** (default, strongest). The front is a sentence with a gap;
   you must produce the correct form.
   - Front: `Ich gebe ___ Mann das Buch.` (dative) → Back: `dem` + the rule
     "indirect object → Dativ; der→dem".
   - This is active recall of the *form*, which is what transfers to speaking.
2. **Transformation prompt.** Front gives a base form + an instruction; back is
   the result.
   - Front: `"gehen" → ich (Perfekt)` → Back: `ich bin gegangen` (+ note: motion
     verb ⇒ *sein*).
3. **Reference table** (always on the back). A compact declension/conjugation
   table so the single card teaches the whole pattern, not one cell.
   - e.g. the definite-article table (Nom/Akk/Dat/Gen × m/f/n/pl), with the
     answered cell highlighted.

So one grammar card = a focused cloze/transformation **question** on the front,
and **explanation + full table + 1–2 examples** on the back. The card still flows
through the identical SM-2 scheduler.

## Data model

Grammar cards reuse `Card` with `card_type = "grammar"` and these fields:

| Field | Use |
| ----- | --- |
| `front` | the cloze/transformation prompt (gap marked `___`) |
| `back` | the answer (the form that fills the gap / the transformed result) |
| `notes` | the rule explanation ("Dativ after *mit, nach, aus…*") |
| `table` | optional JSON: `{headers: [...], rows: [[...]]}` rendered as the reference table, with `highlight: [r,c]` for the answered cell |
| `example` | a full correct sentence using the pattern |
| `tags` | e.g. `dativ`, `perfekt`, `adjective-endings` |

The Gemini importer, when told a section is grammar, is prompted to emit cards in
exactly this shape (cloze front, rule in `notes`, a small table when relevant).

## Why this works

- **Cloze = production**, the skill that actually matters.
- **Table on the back** turns each review into a re-exposure to the whole
  paradigm, so 10 article cards reinforce one table from 10 angles.
- **One scheduler** — grammar, vocab and sentences interleave naturally in a
  session, which is itself good for retention (interleaving > blocking).
