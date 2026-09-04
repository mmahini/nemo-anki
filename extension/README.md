# Nemo Anki — Chrome Extension (MVP)

Select text on any page, record/upload a voice clip, or right-click an image, and
get an AI-enriched flashcard proposal from the Nemo Anki backend, edit it, and
save it to your account. No AI logic lives in this extension — it calls
`/api/import/enrich/`, `/api/import/enrich-voice/`, `/api/import/enrich-image/`,
and `/api/cards/`, the same backend that powers the web app and Telegram bot
(the enrich-voice/enrich-image endpoints reuse the exact Gemini functions the
Telegram bot's own voice/photo handling already uses).

## Develop

```
cp .env.example .env   # point VITE_API_URL at your backend (defaults to :8004)
npm install
npm run build           # one-off build into dist/
npm run dev              # rebuilds dist/ on file change (no live-reload — reload
                          # the unpacked extension manually after each rebuild)
```

Then in Chrome: `chrome://extensions` → enable Developer mode → **Load unpacked** →
select `extension/dist`.

## Scope (MVP)

- Trigger: right-click a text selection → "Add to Nemo Anki", right-click an
  image → "Add image to Nemo Anki", or the keyboard shortcut for text
  (configurable at `chrome://extensions/shortcuts`).
- No content script — the context menus get selected text / the clicked
  image's URL natively; the keyboard shortcut does a one-off
  `chrome.scripting.executeScript` read of the current selection, scoped to
  that single user gesture (`activeTab`), then discards itself. Nothing is
  injected into pages persistently.
- Voice: record via `getUserMedia`/`MediaRecorder`, or pick an audio file from
  disk — both paths post the same Blob to `/api/import/enrich-voice/`, which
  transcribes and enriches in one request/one AI-quota unit.
- Image: right-clicking an image sends its URL (never the extension's own
  fetch — see Files below) to `/api/import/enrich-image/`, which downloads it
  server-side (SSRF-checked), OCRs it, and enriches the result in one
  request/one AI-quota unit. The image is always attached to the card once
  created, even if no text could be read from it.
- No Regenerate for this MVP — every proposal field is freely editable
  instead (not unsupported — see the approved plan for what a follow-up
  would reuse).
- Deck selection is a plain dropdown (`GET /api/decks/`), remembering the last
  deck used per language in `chrome.storage.local`. No auto-deck-creation.
- Auth persists via `chrome.storage.local` (access + refresh tokens), auto-
  refreshed on a 401 — no repeat OTP prompts until the refresh token itself
  goes invalid (backend: 1-day access / 365-day refresh, no rotation).
- Backend changes are limited to what `enrich-voice`/`enrich-image` needed —
  this extension otherwise reuses `/api/auth/*`, `/api/me`, `/api/decks/`,
  `/api/import/enrich/`, `/api/cards/`, and `/api/cards/<id>/images/` exactly
  as they exist today. The Telegram bot (`backend/apps/notifications/`) is
  untouched by this extension.

## Future work (investigated, not implemented)

- **Tab/video audio capture**: needs MV3 `tabCapture` + an offscreen document
  (a service worker can't hold a `MediaStream`). The captured audio would
  still just become a `Blob` fed into the existing `enrichVoice()` call — no
  new pipeline needed.

## Files

- `src/background.ts` — context menus (text selection + image) + keyboard
  command, opens the proposal window.
- `src/popup/` — toolbar-icon popup: sign in / sign out.
- `src/proposal/` — the capture → enrich → edit → create window. For images,
  the extension never downloads the clicked image itself (no broad
  `host_permissions` needed) — it sends the image's URL to the backend, which
  downloads it, and hands back a data URL the proposal window holds until
  Create Card, then attaches via `POST /api/cards/<id>/images/`.
- `src/lib/` — API client, `chrome.storage.local` auth persistence, shared types.
- `public/manifest.json` — MV3 manifest (copied verbatim into `dist/` by Vite).
