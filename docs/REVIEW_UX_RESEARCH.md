# Card Review — UX Research & Design Decisions

Goal: keep Anki's proven *scheduling* (see [ANKI_RESEARCH.md](./ANKI_RESEARCH.md))
but give nemo-anki a **modern, calm, keyboard-first** review screen — the single
most-used surface in the app. This doc surveys what good review UIs do and records
the decisions we ship.

## What the field does well (survey)

The recurring criticism of Anki is that scheduling is great but the UI feels
dated; the apps people praise (Mochi, Quizlet, RemNote, Brainscape, Flashrecall)
win on **clarity, speed, and delight**, not on a different algorithm.

Patterns worth copying:

- **One card, centred, nothing else.** Mochi/Quizlet strip the screen to a single
  card. No nav chrome during review. Reduces decision load.
- **Reveal in two beats.** Show the prompt → user self-tests → press Space to flip
  → grade. The deliberate pause is the whole point of active recall.
- **Keyboard-first.** `Space`/`Enter` flips and = Good; `1234` grade; `e` edit;
  `u` undo. Power users never touch the mouse. (Anki, RemNote, Mochi.)
- **Show the payoff of each button.** Anki prints the *next interval* above each
  answer button ("<1m", "1d", "4d"). Hugely reassuring; we copy it.
- **Big, distinct grading targets on mobile.** Tap zones / swipes for Again↔Easy.
- **Progress, not pressure.** A slim "X left today" counter (new/learning/due
  split) beats a big "23/100". Brainscape uses confidence-based pacing.
- **Immediate, quiet feedback.** A subtle colour pulse on grade, then the next
  card slides in. No modal, no "correct!" celebration spam.
- **AI card creation** is now table-stakes (Flashrecall, Space, RemNote) — which
  is exactly our Gemini import flow.

## Decisions for nemo-anki

1. **Distraction-free review view.** Full-bleed card, deck name + remaining-count
   chip top-left, `Esc` to exit. Everything else hidden.
2. **Two-beat flip.** Front shown; `Space` reveals the back (translation +
   reading + example). Flip is an animated card turn.
3. **Four buttons with predicted intervals.** Again / Hard / Good / Easy, each
   labelled with the interval it would produce (computed by the same scheduler
   the server uses, so the preview never lies). Colour-coded
   red→amber→green→blue.
4. **Keyboard map:** `Space`/`Enter` = flip then Good · `1` Again · `2` Hard ·
   `3` Good · `4` Easy · `e` edit · `u` undo last · `Esc` leave.
5. **Reading & example always on the back**, never the front (so the front stays
   a clean recall prompt). Reading rendered in a muted monospace.
6. **German article colour cues.** der = **blue**, die = **red**, das = **green**
   (the common Café-/poster mnemonic many German learners already use). The noun
   on vocab cards is tinted by its article; a legend appears in the deck header.
   See [GERMAN_COLORS.md](./GERMAN_COLORS.md).
7. **Card-type-aware layout.**
   - *vocab*: term (article-tinted) ↔ translation + reading.
   - *sentence*: full sentence ↔ translation + reading; clozeable later.
   - *grammar*: a rule/pattern prompt ↔ explanation + conjugation/declension
     table + examples. See [GRAMMAR_CARDS.md](./GRAMMAR_CARDS.md).
8. **Quiet feedback + progress.** Grade → brief colour pulse → next card. A slim
   top progress bar shows new/learning/due remaining for the session.
9. **Undo** restores the previous card state from the last `ReviewLog` row.
10. **Mobile:** buttons become a full-width 2×2 grid; horizontal swipe maps to
    Again/Good as a fast path.

## Why not just clone Anki's look?

Anki's desktop review screen is functional but visually heavy and inconsistent
across platforms. Since our scheduling is identical, we get Anki's effectiveness
for free and can spend the UI budget on the calm, fast surface above — which is
the exact gap every "Anki alternative" article points to.

---

Sources:
- [Flashcard Apps Like Anki — FlashRecall](https://flashrecall.app/blog/flashcard-apps-like-anki)
- [Anki vs RemNote vs Quizlet 2025 — Notigo](https://notigo.ai/blog/best-flashcard-apps-students-anki-remnote-quizlet-2025)
- [5 Open-Source Spaced Repetition Tools Compared — QuizCat](https://www.quizcat.ai/blog/5-open-source-spaced-repetition-tools-compared)
- [Best Spaced Repetition Apps 2026 — Mindoma](https://www.mindomax.com/best-spaced-repetition-apps-2026-anki-alternatives)
- [Brainscape vs Anki](https://www.brainscape.com/academy/brainscape-vs-anki/)
- [Mochi — Spaced repetition flashcards](https://mochi.cards/)
