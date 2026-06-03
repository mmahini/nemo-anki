# German article colours

German nouns carry a grammatical gender that you must memorise *with* the word.
A widely-used learner mnemonic is to colour the noun by its article. nemo-anki
bakes this in: every German vocab card stores its `article`, and the UI tints the
term accordingly.

## The palette

| Article | Gender | Colour | Token |
| ------- | ------ | ------ | ----- |
| **der** | masculine | **blue** | `--art-der` `#2f6fed` |
| **die** | feminine | **red** | `--art-die` `#e23b54` |
| **das** | neuter | **green** | `--art-das` `#1f9d57` |
| **die** (plural) | plural | **purple/neutral** | `--art-plural` `#8a63d2` |
| — | not a noun / no article | default ink | `--ink` |

(These three — der=blue, die=red, das=green — are the most common convention in
German-teaching materials and apps, so learners who've seen it elsewhere feel at
home. The values are defined once in `styles.css` and reused everywhere.)

## Where it shows

- **Vocab card front/back**: the noun is rendered in its article colour, and the
  article itself is shown as a coloured pill (`der` / `die` / `das`).
- **Deck/card lists**: a small coloured dot precedes German noun cards.
- **Deck header legend**: a compact key (der/die/das) appears on German decks so
  the colour code is always self-explanatory.

## Sentences: only articles + their nouns

On German **sentence** (and grammar) cards we colour *only* the articles and the
nouns they govern — verbs, prepositions, conjunctions and adjectives stay in the
default ink. Two modes (see `frontend/src/components/GermanText.tsx`):

- **Heuristic** (default): colour comes from the article's surface form. Fast,
  but a dative/genitive like *der Frau* shows in the der-colour (wrong gender).
- **Accurate** (the **🎨 Colour genders** button on the editor): calls
  `POST /api/import/analyze-de/` (Gemini), which returns each noun's *true*
  dictionary gender. The result is stored on `Card.genders`
  (`[{noun, gender}]`) and used to colour the noun **and** its governing article
  by the real gender — so *der Frau* becomes red. The editor shows the mapping
  ("Frau (die), …") so the flow is transparent.

## Data model

`Card.article` is an enum: `der | die | das | plural | none`. It is only meaningful
for German (`language = "de"`) vocab cards that are nouns; everything else is
`none` and renders in the default colour. The Gemini importer fills `article` for
German nouns automatically. `Card.genders` stores per-noun true genders for
sentence colouring (above).
