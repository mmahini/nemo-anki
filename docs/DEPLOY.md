# Deployment Plan — Nemo Anki

Mirrors the `nemo-map` / `nemo-gardening` setup so we reuse the same Render
workspace, the same shared Postgres instance, and the same Vercel/Cloudflare
keys. Only the things specific to this project (schema, R2 bucket, Gemini key,
domain) are new.

## Topology

| Layer    | Host                | Plan       | Notes                                                  |
| -------- | ------------------- | ---------- | ------------------------------------------------------ |
| Backend  | Render web service  | Free       | Sleeps after ~15 min idle; cold start ~30 s            |
| Database | Render Postgres     | Existing   | Reuses `toloo` DB; nemo-anki lives in schema `nemo_anki` |
| Frontend | Vercel              | Free hobby | `rootDir: frontend`                                    |
| Media    | Cloudflare R2       | Free       | Optional — cards are text-only for now (no uploads)    |
| AI       | Gemini API          | Free tier  | Powers the Import flow                                  |

## Phase 0 — Inputs

Most secrets are copied verbatim from `nemo-map/.secrets/deploy.env` (Render API
key, owner id, Vercel token, database URL, Cloudflare API token) and are already
staged in [`.secrets/deploy.env`](../.secrets/deploy.env). What's new:

1. **Schema** — `DATABASE_SCHEMA=nemo_anki` (created automatically on first
   migrate by the `render.yaml` bootstrap step).
2. **Gemini key** — `GEMINI_API_KEY` (the shared key is already in the secrets).
3. **Domain choice**
   - Option A — default URLs: `nemo-anki-backend.onrender.com` +
     `nemo-anki.vercel.app`. Zero config, ships today.
   - Option B — custom domain. Adds a Cloudflare DNS step and sets
     `CSRF_TRUSTED_ORIGINS` accordingly.
4. **R2** — only needed once we add images/audio to cards. Bucket name reserved
   as `nemo-anki`; keys left blank in the secrets until then.

## Phase 1 — Backend code prep (local, no deploy)

Already landed in this repo:

- `backend/core/settings.py` — parses `DATABASE_URL`, pins `search_path` to
  `DATABASE_SCHEMA` (no `public` fallback), env-gated R2 storage, CORS/CSRF env
  parsing, `GEMINI_API_KEY`.
- `render.yaml` — schema bootstrap + `collectstatic` + `migrate` +
  idempotent `createsuperuser`; `gunicorn core.wsgi:application` start command.
- `frontend/vercel.json` — SPA rewrites + Vite framework hint.
- `.secrets/{deploy,runtime}.env` — gitignored credential stubs.

Sanity check before provisioning: `docker compose up` works locally (all
production switches are env-gated, so dev behaviour is unchanged).

## Phase 2 — Provision Render + Vercel

Using the Render and Vercel APIs with the existing credentials:

1. Create web service `nemo-anki-backend`
   - Region: Frankfurt (matches siblings)
   - Root dir: `backend`
   - Health check: `/api/health/`
   - Env vars: see Phase 4 table
2. **Don't create a new database** — point `DATABASE_URL` at the existing
   `toloo` instance and set `DATABASE_SCHEMA=nemo_anki`. First migrate creates
   the schema and the Django tables inside it.
3. Trigger first deploy. Watch logs until `/api/health/` returns 200.
4. Create Vercel project `nemo-anki`
   - Root dir: `frontend`
   - Build command: `npm run build`
   - Env var: `VITE_API_URL=https://nemo-anki-backend.onrender.com`

## Phase 3 — Smoke test

1. Open the Vercel URL, sign in (the dev OTP is shown on the verify screen).
2. Confirm the deck list starts empty and you can create a deck. (Optionally run
   `seed_decks` on the service to load the Menschen + Oxford trees.)
3. Study a few sample cards in a seeded `Lektion`; confirm the
   grade buttons show next-intervals and scheduling persists across reloads.
4. Open **Import**, paste a small German word list, confirm Gemini returns draft
   cards, edit one, pick a deck, **Proceed**, and verify the cards land.

## Phase 4 — Env var matrix (single source of truth)

### Render web service env vars
| Key                         | Source                                              |
| --------------------------- | --------------------------------------------------- |
| `PYTHON_VERSION`            | `"3.12.3"`                                           |
| `DJANGO_SETTINGS_MODULE`    | `core.settings`                                     |
| `DJANGO_DEBUG`              | `"False"`                                            |
| `DJANGO_SECRET_KEY`         | Render `generateValue: true`                        |
| `DJANGO_ALLOWED_HOSTS`      | `nemo-anki-backend.onrender.com[,<custom>]`         |
| `CORS_ALLOWED_ORIGINS`      | `https://nemo-anki.vercel.app[,<custom-frontend>]`  |
| `CSRF_TRUSTED_ORIGINS`      | `https://nemo-anki-backend.onrender.com[,<custom>]` |
| `DATABASE_URL`              | Copy from sibling secrets (`DATABASE_URL_PROD`)     |
| `DATABASE_SCHEMA`           | `nemo_anki`                                          |
| `GEMINI_API_KEY`            | From `.secrets/deploy.env`                           |
| `GEMINI_MODEL`              | `gemini-2.0-flash`                                  |
| `DJANGO_SUPERUSER_USERNAME` | `admin`                                              |
| `DJANGO_SUPERUSER_EMAIL`    | your address                                        |
| `DJANGO_SUPERUSER_PASSWORD` | auto-generated, saved to `.secrets/deploy.env`      |

### Vercel project env vars
| Key            | Value                                     |
| -------------- | ----------------------------------------- |
| `VITE_API_URL` | `https://nemo-anki-backend.onrender.com`  |

## Phase 5 — Hardening (after first successful deploy)

- Pin `ALLOWED_HOSTS` / `CORS_ALLOWED_ORIGINS` to the exact prod origins.
- Confirm WhiteNoise serves Django admin's CSS (visit `/admin/`).
- Wire real email delivery for OTP (currently surfaced as `dev_code`).
- Add R2 only when cards gain images/audio.
- Add a Sentry DSN later if we want error visibility — deferred.

## Notes & caveats

- **Cold starts**: Render free spins down after 15 min idle; first request after
  sleep takes ~30 s. Fine for a personal app.
- **Schema isolation**: pinning `search_path` to `nemo_anki` keeps this
  project's `django_migrations`, `auth_user`, etc. separate from the siblings.
- **Gemini fallback**: if `GEMINI_API_KEY` is unset, Import degrades gracefully
  to a deterministic line parser, so the feature never hard-fails.
- **No automated tests in the build**: siblings skip tests in the build; local
  `make verify` (which runs the scheduler suite) stays the pre-deploy gate.

## Ready check

Pick a domain option (Phase 0 item 3). Once chosen, land any origin tweaks and
provision Render + Vercel in one pass.
