/**
 * Wiser CDP first-party pixel — a tiny typed client that emits `page` / `identify`
 * / `track` events to the Wiser CDP ingest endpoint (the nemo-anki org, SaaS vertical).
 *
 * Config (Vite build-time env, set in Vercel):
 *   VITE_CDP_WRITE_KEY   — nemo-anki's public CDP write-key (e.g. wcdp_nemo_anki_public_key)
 *   VITE_CDP_INGEST_URL  — full ingest URL (e.g. https://api.wiserstudio.ai/cdp/ingest)
 *
 * No-ops unless BOTH are set, so dev/preview builds without them emit nothing.
 *
 * Identity: a stable `anonymousId` (localStorage) rides on every event, and once
 * `cdpIdentify` runs, `external_id` (the nemo-anki user id) + `email` ride on every
 * event too — so a user folds into a single CDP profile (no split).
 */

const WRITE_KEY = (import.meta as any).env?.VITE_CDP_WRITE_KEY ?? "";
const INGEST_URL = (import.meta as any).env?.VITE_CDP_INGEST_URL ?? "";
const ANON_KEY = "wcdp_anon";

type Identifiers = { external_id?: string; email?: string };
let identifiers: Identifiers = {};

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

function send(type: "page" | "identify" | "track", extra: Record<string, unknown> = {}): void {
  if (!WRITE_KEY || !INGEST_URL || typeof window === "undefined") return; // no-op when unconfigured
  const body = {
    type,
    anonymousId: anonymousId(),
    identifiers: { ...identifiers },
    context: {
      source: "nemo-anki",
      ts: new Date().toISOString(),
      page: { url: window.location.href },
    },
    ...extra,
  };
  try {
    void fetch(INGEST_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CDP-Write-Key": WRITE_KEY },
      body: JSON.stringify(body),
      keepalive: true,
    }).catch(() => {});
  } catch {
    // tracking must never throw into the app
  }
}

/** Attach the signed-in user to subsequent events + post an identify. */
export function cdpIdentify(traits: { external_id?: string; email?: string; name?: string }): void {
  if (traits.external_id) identifiers.external_id = traits.external_id;
  if (traits.email) identifiers.email = traits.email;
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

/** Clear identity on sign-out (keeps the anonymousId for the device). */
export function cdpReset(): void {
  identifiers = {};
}
