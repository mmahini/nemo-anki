# Nemo Anki — Chrome Extension (MVP)

Select text on any page, get an AI-enriched flashcard proposal from the existing
Nemo Anki backend, edit it, and save it to your account. No AI logic lives in this
extension — it only calls the existing `/api/import/enrich/` and `/api/cards/`
endpoints the web app and Telegram bot already use.

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

- Trigger: right-click a text selection → "Add to Nemo Anki", or the keyboard
  shortcut (configurable at `chrome://extensions/shortcuts`).
- No content script — the context menu gets selected text natively; the keyboard
  shortcut does a one-off `chrome.scripting.executeScript` read of the current
  selection, scoped to that single user gesture (`activeTab`), then discards
  itself. Nothing is injected into pages persistently.
- No Regenerate, no card images for this MVP — every proposal field is freely
  editable instead, and both features remain intentionally deferred (not
  unsupported — see the approved plan for what a follow-up would reuse).
- Deck selection is a plain dropdown (`GET /api/decks/`), remembering the last
  deck used per language in `chrome.storage.local`. No auto-deck-creation.
- Zero backend changes — reuses `/api/auth/*`, `/api/me`, `/api/decks/`,
  `/api/import/enrich/`, `/api/cards/` exactly as they exist today. The Telegram
  bot (`backend/apps/notifications/`) is untouched by this extension.

## Files

- `src/background.ts` — context menu + keyboard command, opens the proposal window.
- `src/popup/` — toolbar-icon popup: sign in / sign out.
- `src/proposal/` — the capture → enrich → edit → create window.
- `src/lib/` — API client, `chrome.storage.local` auth persistence, shared types.
- `public/manifest.json` — MV3 manifest (copied verbatim into `dist/` by Vite).
