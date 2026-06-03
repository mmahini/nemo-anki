# AnkiWeb — Features & Scheduling Logic (Research)

This document captures how [AnkiWeb / Anki](https://ankiweb.net/) works so that
nemo-anki can reproduce its card model, deck structure, and **spaced-repetition
review logic faithfully**. It is the spec the backend scheduler implements.

Sources: the official [Anki manual](https://docs.ankiweb.net/) (Studying, Deck
Options, Getting Started) plus the well-documented behaviour of Anki's classic
**SM-2** scheduler (the historical default that we copy here). Anki also ships a
newer ML-based scheduler called **FSRS** — see [§7](#7-fsrs-the-modern-option).

---

## 1. Core objects

| Anki object | What it is | nemo-anki equivalent |
| ----------- | ---------- | -------------------- |
| **Collection** | Everything a user owns | the user's account |
| **Deck** | A named, **hierarchically nestable** group of cards (`German::Menschen::A1.1`) | `decks.Deck` (self-referential `parent`) |
| **Note** | The raw facts you typed (fields) | the editable fields on `cards.Card` |
| **Note Type / Model** | The template that turns a note into one or more cards | `card_type` enum on the card (`vocab` / `sentence` / `grammar`) |
| **Card** | One question→answer the scheduler tracks independently | `cards.Card` |
| **Review log** | One row per answer, for stats & undo | `cards.ReviewLog` |
| **Deck Options (preset)** | The knobs that drive scheduling | `decks.DeckConfig` |

**Decks are hierarchical.** In Anki the `::` separator builds a tree
(`German::Menschen::A1.1`). Studying a parent studies all descendants. We model
this with a self-referential `parent` FK and expose a computed `full_name`.

---

## 2. Card states (queues)

Every card lives in exactly one state. This is the heart of the scheduler.

| State | Meaning |
| ----- | ------- |
| **New** | Never studied. Introduced up to *new cards/day* per deck. |
| **Learning** | Being learned right now, stepping through short intervals (minutes). |
| **Review** | Graduated. Interval measured in **days**; this is the long-term SRS queue. |
| **Relearning** | A review card you got wrong ("lapsed"); re-stepping through minutes before returning to review. |
| **Suspended** | Manually or automatically (leech) removed from study until un-suspended. |
| **Buried** | Hidden until the next day (e.g. siblings of a card you just saw). |

---

## 3. The four answer buttons

After revealing the answer the user rates recall. The button set and meaning are
**identical to Anki**:

| Button | Key | Meaning | Target frequency |
| ------ | --- | ------- | ---------------- |
| **Again** | `1` | Wrong / couldn't recall | 5–20% |
| **Hard**  | `2` | Correct but with difficulty / slow | small |
| **Good**  | `3` / `Space` / `Enter` | Correct with some effort | **80–95% (the default)** |
| **Easy**  | `4` | Correct, effortless | small |

What each button *does* depends on the card's current state (below).

---

## 4. Default deck options (the numbers we ship)

These are Anki's classic SM-2 defaults. They live in `decks.DeckConfig` and are
the values seeded for every new deck.

| Option | Default | Notes |
| ------ | ------- | ----- |
| Learning steps | `1m 10m` | two steps: 1 minute, then 10 minutes |
| Graduating interval | `1 day` | interval when a card leaves learning via *Good* |
| Easy interval | `4 days` | interval when a new/learning card is answered *Easy* |
| Starting ease | `2.50` (250%) | initial ease factor |
| New cards/day | `20` | per deck |
| Maximum reviews/day | `200` | per deck |
| Easy bonus | `1.30` | extra multiplier applied on *Easy* in review |
| Interval modifier | `1.00` | global multiplier on all review intervals |
| Hard interval | `1.20` | multiplier for *Hard* in review |
| New interval | `0.00` | fraction of interval kept after a lapse (0 = reset) |
| Minimum interval | `1 day` | floor after a lapse |
| Relearning steps | `10m` | one step |
| Leech threshold | `8 lapses` | mark/suspend after this many lapses |
| Leech action | `suspend` | (Anki's other option is "tag only") |
| Maximum interval | `36500 days` | 100 years |

We store ease as an **integer in permille** (`2500` = 250%) exactly like Anki, to
avoid float drift. The ease floor is **`1300` (130%)**.

---

## 5. Scheduling logic (exact algorithm we implement)

`fuzz` = a small ± randomisation Anki applies to day-intervals so cards reviewed
together don't clump forever. Applied to review intervals ≥ 3 days.

### 5.1 New card → first answer
A new card is pulled into **Learning** and answered against the learning steps:

- **Again** → step 0, due in `1m`.
- **Hard** → (only meaningful with ≥2 steps) repeat first step, due ~`1m`.
- **Good** → advance one step. If steps remain, due in next step (`10m`). If it
  was the last step, **graduate** to Review with interval = *graduating interval*
  (`1 day`), ease = *starting ease* (`2500`).
- **Easy** → **graduate immediately** to Review with interval = *easy interval*
  (`4 days`), ease = *starting ease*.

### 5.2 Learning card → answer
- **Again** → back to step 0 (`1m`).
- **Good** → next step; graduate (interval `1 day`) if no steps left.
- **Easy** → graduate now with *easy interval* (`4 days`).

### 5.3 Review card → answer
Let `I` = current interval (days), `E` = ease (permille), `IM` = interval modifier.

- **Again** → **lapse**: `lapses += 1`; ease `E = max(1300, E − 200)`; card enters
  **Relearning** at relearning step 0 (`10m`). Its post-relearn interval becomes
  `max(minInterval, round(I × newInterval))` (newInterval `0` ⇒ floored to
  `minInterval = 1 day`). If `lapses ≥ leechThreshold` → **leech** (suspend).
- **Hard** → `E = max(1300, E − 150)`; `I' = I × 1.2 × IM`.
- **Good** → ease unchanged; `I' = I × (E/1000) × IM`.
- **Easy** → `E = E + 150`; `I' = I × (E/1000) × easyBonus × IM`.

New interval is `max(I+1, round(I'))` then `fuzz`'d and clamped to `maxInterval`.
(`I+1` guarantees monotonic growth.)

### 5.4 Relearning card → answer
- **Again** → back to relearning step 0 (`10m`).
- **Good** → if steps remain, next step; else **return to Review** with the
  lapse interval computed in 5.3.
- **Easy** → return to Review immediately, lapse interval + 1 day bonus.

### 5.5 Daily limits & queue order
Per deck per day: at most *new cards/day* new + *max reviews/day* reviews. Order
shown: **learning due now → review due today → new** (Anki's default gather/sort).
Learning cards with a due time in the future (e.g. the `10m` step) re-appear once
that time passes within the session.

---

## 6. Other Anki behaviours we honour

- **Leeches**: at `8` lapses the card is suspended and tagged `leech`.
- **Fuzz**: ±~5–25% on review intervals ≥ 3 days, so siblings spread out.
- **Bury siblings**: optional; one card per note per day. (Phase-2 nicety.)
- **Undo**: the `ReviewLog` row lets us restore the previous card state.
- **Timezones**: "today" is computed in the user's day, with a configurable
  rollover hour (Anki default 4 AM). We use UTC midnight for v1, documented as a
  known simplification.

---

## 7. FSRS (the modern option)

Modern Anki defaults new users to **FSRS** (Free Spaced Repetition Scheduler), an
ML model that predicts recall probability and schedules to a target retention
(e.g. 90%). It replaces ease/interval heuristics with per-card memory parameters
(stability, difficulty). It is **out of scope for v1** — we ship the classic SM-2
described above (which Anki still supports and which is fully deterministic and
easy to verify). The scheduler is isolated in `apps/cards/scheduler.py` so FSRS
can be added later behind a `DeckConfig.scheduler` flag without touching the API.

---

## 8. Mapping to our API

| Concept | Endpoint |
| ------- | -------- |
| List/CRUD decks | `/api/decks/` |
| Deck study counts | `/api/decks/<id>/stats/` |
| Pull next due queue | `/api/decks/<id>/study/` |
| Answer a card (1–4) | `/api/cards/<id>/answer/` |
| CRUD cards | `/api/cards/`, `/api/cards/<id>/` |
| Bulk create (import) | `/api/cards/bulk/` |
| Parse text → draft cards | `/api/import/parse/` |

The scheduler is a pure function (`scheduler.answer(card, rating, config, now)`)
returning the mutated card + a review-log row, so it is unit-testable in isolation
and mirrors §5 line-for-line.
