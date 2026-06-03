# Development

Everything runs in Docker; you only need Docker Desktop.

## First run

```bash
cp .env.example .env   # a working .env (with the dev Gemini key) is already committed-as-example
make up                # build + start db, backend, frontend
```

- App: <http://localhost:5176>
- API: <http://localhost:8004/api/>
- Admin: <http://localhost:8004/admin/> (`make createsuperuser` first)

Sign in with any email; the OTP is shown on the verify screen. First sign-in
auto-seeds the Menschen + Oxford deck trees and sample cards.

## Common commands

| Command | What |
| ------- | ---- |
| `make up` / `make down` | start / stop the stack |
| `make logs` | tail backend + frontend logs |
| `make verify` | run Django tests (incl. scheduler suite) + frontend typecheck |
| `make test-backend` | Django tests |
| `make typecheck-frontend` | `tsc --noEmit` |
| `make migrate` / `make makemigrations` | DB migrations |
| `make seed-decks` | (re)seed the book deck trees |
| `make shell-backend` / `make shell-db` | shells |

## Where things live

- **Scheduler** — `backend/apps/cards/scheduler.py` (pure SM-2; see ANKI_RESEARCH.md).
  Tests in `backend/apps/cards/tests.py`.
- **Queue / daily limits** — `backend/apps/cards/queue.py`.
- **Import (Gemini)** — `backend/apps/imports/gemini.py`.
- **Seeding** — `backend/apps/cards/seeding.py`.
- **Review UI** — `frontend/src/pages/Study.tsx`.
- **Card rendering + article colours** — `frontend/src/components/CardFace.tsx`,
  `frontend/src/lib/article.ts`.

## Adding a model field

1. Edit the model in `backend/apps/<app>/models.py`.
2. `make makemigrations && make migrate`.
3. Update the serializer + the TS type in `frontend/src/auth/api.ts`.

## Auth

Email OTP → JWT (SimpleJWT). 15-min access, 7-day refresh; the client refreshes
transparently. No password. OTP delivery is stubbed (`dev_code` in the response)
until an email provider is wired.
