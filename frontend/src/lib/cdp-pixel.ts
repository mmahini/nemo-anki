/**
 * Wiser CDP first-party pixel — a tiny typed client that emits `page` / `identify`
 * / `track` events to the Wiser CDP ingest endpoint (the nemo-anki org, SaaS vertical).
 *
 * Config (Vite build-time env, set in Vercel):
 *   VITE_CDP_WRITE_KEY   — nemo-anki's public CDP write-key (e.g. wcdp_nemo_anki_public_key)
 *   VITE_CDP_INGEST_URL  — full ingest URL (e.g. https://cdp-api.wisry.ai/cdp/ingest)
 *
 * No-ops unless BOTH are set, so dev/preview builds without them emit nothing.
 *
 * Identity: a stable `anonymousId` (localStorage) rides on every event, and once
 * `cdpIdentify` runs, `external_id` (the nemo-anki user id) + `email` ride on every
 * event too — so a user folds into a single CDP profile (no split).
 *
 * Session duration (CDP-9.1): the backend derived duration from event timestamps, so
 * single-page visits collapsed to 0 and last-page dwell was never counted. The pixel
 * now (a) owns the session via a `session_id` (sessionStorage, 30-min sliding window),
 * (b) accrues active foreground time via the Page Visibility API and ships it as
 * `engagement_time_ms` on every event, and (c) fires a debounced terminal `page_leave`
 * on `visibilitychange→hidden` / `pagehide` with the final engagement delta. The beacon
 * uses `fetch(keepalive)` (not `navigator.sendBeacon`, which can't set the
 * `X-CDP-Write-Key` header) — the documented equivalent that survives unload.
 */

const WRITE_KEY = (import.meta as any).env?.VITE_CDP_WRITE_KEY ?? "";
const INGEST_URL = (import.meta as any).env?.VITE_CDP_INGEST_URL ?? "";
const ANON_KEY = "wcdp_anon";
const IDENT_KEY = "wcdp_ident";
const SESSION_KEY = "wcdp_session";
const SESSION_TIMEOUT_MS = 30 * 60 * 1000; // matches the backend SessionConfig default (1800s)
const MIN_LEAVE_MS = 1000; // don't beacon a sub-second tab-flick (debounce + load guard)

type EventType = "page" | "identify" | "track" | "page_leave";
type Identifiers = { external_id?: string; email?: string };

/** Identity is persisted next to the anonymousId and hydrated at module load.
 * Kept in memory only, a returning signed-in user's first events (the initial
 * pageview, a bounce's page_leave, anything before fetchMe resolves and
 * identify re-runs) all went out anonymous — CDP showed a ghost profile for
 * someone we knew perfectly well. The email already lives in localStorage as
 * part of the stored auth payload, so this adds no new exposure; sign-out
 * clears it (cdpReset). */
function loadIdentifiers(): Identifiers {
  try {
    const raw = localStorage.getItem(IDENT_KEY);
    return raw ? (JSON.parse(raw) as Identifiers) : {};
  } catch {
    return {};
  }
}

let identifiers: Identifiers = loadIdentifiers();

function anonymousId(): string {
  try {
    let id = localStorage.getItem(ANON_KEY);
    if (!id) {
      id =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `anon_${Date.now()}_${Math.floor(Math.random() * 1e9)}`;
      localStorage.setItem(ANON_KEY, id);
    }
    return id;
  } catch {
    return "";
  }
}

// ── client-owned sessionization (CDP-9.1) ──────────────────────────────────────
// sessionStorage holds `{ id, lastTs }`; a >30-min gap (or a fresh tab) rolls a new
// session id (event-time epoch ms). The first event of a session carries `session_start`.

function touchSession(): { id: string; isNew: boolean } {
  try {
    const now = Date.now();
    const raw = sessionStorage.getItem(SESSION_KEY);
    const parsed = raw ? (JSON.parse(raw) as { id?: string; lastTs?: number }) : null;
    let id = parsed?.id || "";
    let isNew = false;
    if (!id || now - (parsed?.lastTs || 0) > SESSION_TIMEOUT_MS) {
      id = String(now);
      isNew = true;
    }
    sessionStorage.setItem(SESSION_KEY, JSON.stringify({ id, lastTs: now }));
    return { id, isNew };
  } catch {
    return { id: "", isNew: false };
  }
}

function currentSessionId(): string {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as { id?: string }).id || "" : "";
  } catch {
    return "";
  }
}

// ── engagement time (active foreground ms, GA4-style) ──────────────────────────

let accruedMs = 0;
let visibleSince = 0;
let listenersBound = false;

function flushEngagementMs(): number {
  if (visibleSince) {
    const now = Date.now();
    accruedMs += now - visibleSince;
    visibleSince = now; // keep accruing for the next delta
  }
  const ms = accruedMs;
  accruedMs = 0;
  return ms;
}

function onVisibilityChange(): void {
  if (typeof document === "undefined") return;
  if (document.visibilityState === "hidden") {
    sendLeave();
    visibleSince = 0; // stop accruing while hidden
  } else if (!visibleSince) {
    visibleSince = Date.now(); // visible again — resume
  }
}

/** Attach lifecycle listeners + start the engagement clock. Idempotent. */
export function initCdpPixel(): void {
  if (listenersBound || typeof document === "undefined") return;
  listenersBound = true;
  visibleSince = document.visibilityState === "visible" ? Date.now() : 0;
  document.addEventListener("visibilitychange", onVisibilityChange);
  // pagehide is the reliable terminal signal that doesn't break bfcache (unlike unload).
  window.addEventListener("pagehide", sendLeave);
}

function post(body: Record<string, unknown>): void {
  try {
    void fetch(INGEST_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CDP-Write-Key": WRITE_KEY },
      body: JSON.stringify(body),
      keepalive: true, // survive a navigation away (and the page_leave beacon)
    }).catch(() => {});
  } catch {
    // tracking must never throw into the app
  }
}

/** How the app is being run — browser tab vs installed PWA. Standalone is the
 * install signal on Android/desktop; iOS Safari exposes `navigator.standalone`
 * instead of matching the media query. Evaluated per event: a user can install
 * mid-session and the switch should show up in the stream. */
function displayMode(): string {
  try {
    if ((navigator as { standalone?: boolean }).standalone === true) return "standalone";
    for (const mode of ["standalone", "fullscreen", "minimal-ui"]) {
      if (window.matchMedia(`(display-mode: ${mode})`).matches) return mode;
    }
  } catch {
    // matchMedia missing (ancient browser) — report as a plain tab
  }
  return "browser";
}

function buildEvent(type: EventType, extra: Record<string, unknown>, contextExtra: Record<string, unknown>) {
  const mode = displayMode();
  return {
    type,
    anonymousId: anonymousId(),
    identifiers: { ...identifiers },
    context: {
      source: "nemo-anki",
      ts: new Date().toISOString(),
      page: { url: window.location.href },
      // PWA vs browser rides on every event, so any funnel can split by it.
      app: { display_mode: mode, pwa: mode !== "browser" },
      ...contextExtra,
    },
    ...extra,
  };
}

function send(type: EventType, extra: Record<string, unknown> = {}): void {
  if (!WRITE_KEY || !INGEST_URL || typeof window === "undefined") return; // no-op when unconfigured
  const { id, isNew } = touchSession();
  const ctx: Record<string, unknown> = { engagement_time_ms: flushEngagementMs() };
  if (id) ctx.session_id = id;
  if (isNew) ctx.session_start = true;
  post(buildEvent(type, extra, ctx));
}

/** Terminal page-leave beacon — flushes remaining engagement; debounced by the flush. */
function sendLeave(): void {
  if (!WRITE_KEY || !INGEST_URL || typeof window === "undefined") return;
  const ms = flushEngagementMs();
  if (ms < MIN_LEAVE_MS) return; // sub-second flick / nothing accrued → don't beacon
  const ctx: Record<string, unknown> = { engagement_time_ms: ms };
  const id = currentSessionId();
  if (id) ctx.session_id = id; // current session only — never starts a new one
  post(buildEvent("page_leave", {}, ctx));
}

/** Attach the signed-in user to subsequent events + post an identify. The
 * identity is also persisted so the NEXT page load's very first events carry
 * it too (see loadIdentifiers). */
export function cdpIdentify(traits: { external_id?: string; email?: string; name?: string }): void {
  if (traits.external_id) identifiers.external_id = traits.external_id;
  if (traits.email) identifiers.email = traits.email;
  try {
    localStorage.setItem(IDENT_KEY, JSON.stringify(identifiers));
  } catch {
    // storage full/blocked — in-memory identity still covers this load
  }
  send("identify", { traits: { ...traits } });
}

/** Pageview. */
export function cdpPage(properties: Record<string, unknown> = {}): void {
  send("page", { properties });
}

/** Behavioural event — use Wiser CDP SaaS catalog event names (login, feature_used, …). */
export function cdpTrack(event: string, properties: Record<string, unknown> = {}): void {
  send("track", { event, properties });
}

/** Sign-out: close this identity's world completely.
 *
 * Three things must not leak into whoever uses this device next:
 *  - the identifiers themselves (obvious),
 *  - the SESSION — sign-out ends it, so a re-login (even seconds later, same
 *    tab) starts a fresh one instead of stitching two identities into one
 *    session's analytics,
 *  - the anonymousId — Wiser CDP folds profiles through it, so keeping it
 *    would merge two different users who share a device into one profile.
 *
 * A terminal `logout` event goes out first (only when someone was actually
 * identified), attributed to the old identity and closing its session. */
export function cdpReset(): void {
  if (identifiers.external_id || identifiers.email) {
    send("track", { event: "logout" });
  }
  identifiers = {};
  try {
    localStorage.removeItem(IDENT_KEY);
    localStorage.removeItem(ANON_KEY); // next event mints a fresh anonymousId
  } catch {
    // best effort
  }
  try {
    sessionStorage.removeItem(SESSION_KEY); // next event starts a new session
  } catch {
    // best effort
  }
}
