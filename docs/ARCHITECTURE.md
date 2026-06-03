# Architecture

Three Docker services, same shape as the sibling nemo-* projects.

```
┌────────────┐    /api proxy    ┌────────────┐     ┌────────────┐
│  frontend  │ ───────────────▶ │  backend   │ ──▶ │  postgres  │
│ Vite/React │   :5176 → :5173  │ Django/DRF │     │    :5436   │
└────────────┘                  │  :8004     │     └────────────┘
                                └────────────┘
                                      │
                                      ▼  Import flow
                                 Gemini API
```

## Backend apps

| App | Responsibility |
| --- | -------------- |
| `accounts` | Custom email User + email-OTP auth (JWT via SimpleJWT) |
| `decks` | `Deck` (hierarchical via `parent`) + `DeckConfig` (Anki deck options) |
| `cards` | `Card` (3 types + SRS state) + `ReviewLog`, the SM-2 `scheduler`, the study `queue` |
| `imports` | Gemini-backed text → draft-card parser (with deterministic fallback) |

## Key endpoints

| Method + path | Purpose |
| ------------- | ------- |
| `POST /api/auth/request-otp` · `/verify-otp` · `/refresh` | auth |
| `GET /api/me` | current user |
| `GET/POST /api/decks/` · `GET/PATCH/DELETE /api/decks/<id>/` | decks (with study counts) |
| `GET /api/decks/<id>/stats/` | new/learning/due counts |
| `GET /api/decks/<id>/study/` | next due queue (with interval previews) |
| `GET/POST /api/cards/` · `/cards/<id>/` | card CRUD |
| `POST /api/cards/<id>/answer/` | grade a card (1-4) → reschedule |
| `POST /api/cards/bulk/` | bulk-create (import "Proceed") |
| `POST /api/cards/undo/` | undo last answer |
| `POST /api/import/parse/` | text → draft cards |
| `GET /api/health/` | liveness |

## Scheduling model

A `Card` carries its SRS state (`state`, `due`, `interval_days`, `ease`, `reps`,
`lapses`, `step_index`). Answering routes through `scheduler.answer(card, rating,
config, now)`, a pure SM-2 transition (see [ANKI_RESEARCH.md](./ANKI_RESEARCH.md)).
Every answer writes a `ReviewLog` with a pre-answer snapshot, enabling one-step
undo and stats.

## Data scoping

Everything is per-user. Decks/cards are filtered by `request.user`; a new user's
first `GET /api/decks/` auto-provisions the Menschen + Oxford trees via
`apps.cards.seeding.seed_for_user`.

## Production

Backend on Render (gunicorn, free tier), frontend on Vercel, shared Render
Postgres with a dedicated `nemo_anki` schema. See [DEPLOY.md](./DEPLOY.md).
