# Future work / deferred ideas

A running backlog of things intentionally deferred. Not committed to a timeline
— just parked here so they're not forgotten.

## Books / processing
- **Background processing for large books.** Today `Process` runs inline (one
  HTTP request per lesson). For a full real coursebook this can be slow and, on
  Render's free tier, risks long requests. Move extraction to a background task
  (queue/worker or a polled job) so the request returns immediately and the UI
  reflects status as lessons finish. *(Requested 2026-06-03.)*
- **"Process all" progress indicator** — show `2/5 done` while batch-processing
  a book's lessons, instead of just per-button spinners.
- **PDF robustness** — current pypdf text extraction is best-effort; real PDFs
  (columns, page headers/footers, hyphenation) need cleanup before segmentation.
- **Smarter lesson segmentation** — fall back to an LLM segmenter when no
  `Lektion/Unit/…` headings are detected.

## Import
- Bring the single-card power tools into the **bulk Import review table**:
  per-row **🌐 Translate**, **🎨 Colour genders**, and **plural** (today only the
  single Add-Card editor has them).

## Audio / TTS
- **Server-side TTS** (e.g. Google/Gemini TTS) with clips stored on **R2**, for
  consistent, high-quality pronunciation across devices. Current 🔊 uses the
  browser Web Speech API (free, instant, but voice quality depends on the OS).

## Scheduling
- **FSRS** as an optional scheduler alongside the classic SM-2 we ship (gate via
  `DeckConfig.scheduler`). See docs/ANKI_RESEARCH.md §7.

## Auth / infra
- **Real email delivery for OTP** — currently the code is surfaced as `dev_code`
  on the verify screen. Wire an email/SMTP provider and gate the dev code on
  `DEBUG`.
- **Cloudflare R2** wiring is in place (env-gated) but unused until cards gain
  images/audio.

## Anki parity niceties
- Bury siblings, deck rename / drag-reorder, custom study, per-note multiple
  card templates, stats/heatmap.
