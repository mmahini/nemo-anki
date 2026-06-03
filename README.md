# Nemo Anki

A spaced-repetition flashcard app with Anki's proven scheduling, built for
learning **German** (Menschen) and **English** (Oxford Word Skills). Cards come
in three types — **vocab**, **sentence**, **grammar** — with phonetic readings,
German article colour-coding (der/die/das), and an AI **Import** flow that turns
a pasted book section into editable cards.

- **Backend**: Django 5 + Django REST Framework
- **Frontend**: React 18 + TypeScript (Vite)
- **Database**: PostgreSQL 16
- **Local orchestration**: Docker Compose (Docker Desktop)

## Quick start

```bash
cp .env.example .env   # (a working .env with the dev Gemini key is included)
docker compose up --build
```

Then open:

- App: <http://localhost:5176>
- API: <http://localhost:8004/api/>
- Health check: <http://localhost:8004/api/health/>
- Django admin: <http://localhost:8004/admin/> (`make createsuperuser` first)

Sign in with any email — the 5-digit code is shown on the verify screen (email
delivery isn't wired yet). New accounts start with an empty deck list; create
your own decks (and nest them) from the Decks page, or run
`make seed-decks` to load the ready-made Menschen + Oxford Word Skills trees.

## Repo layout

```
backend/    Django project + accounts / decks / cards / imports apps
frontend/   Vite + React + TS — auth, deck list, review UI, import
docs/       Anki research, review-UX research, deploy plan, design notes
```

## How it works

- **Scheduling** is a faithful re-implementation of Anki's classic **SM-2**
  algorithm (states, four buttons, learning steps, ease, lapses, leeches). It
  lives in [`backend/apps/cards/scheduler.py`](backend/apps/cards/scheduler.py)
  and is covered by a unit-test suite. See [docs/ANKI_RESEARCH.md](docs/ANKI_RESEARCH.md).
- **Review UI** is keyboard-first (`Space` flip, `1-4` grade, `u` undo, `Esc`
  exit) with predicted next-intervals on each button. See
  [docs/REVIEW_UX_RESEARCH.md](docs/REVIEW_UX_RESEARCH.md).
- **Import** (`/app/import`) parses pasted text into draft cards via Gemini, you
  edit them, pick a deck, and click **Proceed** to bulk-create.

## Documentation

- [docs/ANKI_RESEARCH.md](docs/ANKI_RESEARCH.md) — AnkiWeb features + the exact SM-2 logic we ship
- [docs/REVIEW_UX_RESEARCH.md](docs/REVIEW_UX_RESEARCH.md) — review-screen UX research & decisions
- [docs/GERMAN_COLORS.md](docs/GERMAN_COLORS.md) — der/die/das colour system
- [docs/GRAMMAR_CARDS.md](docs/GRAMMAR_CARDS.md) — the grammar-card design (cloze + table)
- [docs/BOOK_CONTENT.md](docs/BOOK_CONTENT.md) — Menschen & Oxford deck structure
- [docs/DEPLOY.md](docs/DEPLOY.md) — Render + Vercel + shared Postgres deployment plan
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) — day-to-day workflow
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — services, endpoints, structure
