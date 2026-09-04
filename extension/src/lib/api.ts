import { clearStoredAuth, loadStoredAuth, saveStoredAuth, updateStoredTokens } from "./auth";
import type {
  AuthUser,
  Card,
  CreateCardPayload,
  Deck,
  EnrichImagePayload,
  EnrichImageResult,
  EnrichPayload,
  EnrichResult,
  EnrichVoicePayload,
  EnrichVoiceResult,
  StoredAuth,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8004";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Thrown when a call needs a signed-in user and none (or no longer valid one)
 * is available — callers route this to a "sign in first" prompt. */
export class AuthRequiredError extends Error {
  constructor() {
    super("Sign in to Nemo Anki to continue.");
    this.name = "AuthRequiredError";
  }
}

async function refreshAccessToken(): Promise<string | null> {
  const stored = await loadStoredAuth();
  if (!stored?.refresh) return null;
  const res = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh: stored.refresh }),
  });
  if (!res.ok) return null;
  const data = (await res.json().catch(() => ({}))) as { access?: string };
  if (!data.access) return null;
  await updateStoredTokens({ access: data.access, refresh: stored.refresh });
  return data.access;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  opts: { auth?: boolean } = {},
): Promise<T> {
  const needsAuth = opts.auth !== false;
  const stored = needsAuth ? await loadStoredAuth() : null;
  if (needsAuth && !stored) throw new AuthRequiredError();

  const buildHeaders = (token: string | null): HeadersInit => ({
    // A FormData body (voice upload) must NOT get an explicit Content-Type —
    // the browser sets its own multipart boundary automatically, and an
    // explicit header here would override that and break the upload.
    ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    ...(init.headers ?? {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  });

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers: buildHeaders(stored?.access ?? null) });
  } catch {
    throw new ApiError("Couldn't reach Nemo Anki — check your connection.", 0);
  }

  if (res.status === 401 && stored?.refresh) {
    const fresh = await refreshAccessToken();
    if (fresh) {
      res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers: buildHeaders(fresh) });
    } else {
      await clearStoredAuth();
      throw new AuthRequiredError();
    }
  }

  const isNoContent = res.status === 204;
  const body = isNoContent ? ({} as unknown) : await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401) {
      await clearStoredAuth();
      throw new AuthRequiredError();
    }
    const detail = (body as { detail?: string }).detail ?? `Request failed (${res.status})`;
    throw new ApiError(detail, res.status);
  }
  return body as T;
}

// ---- Auth ----

export function requestOtp(email: string) {
  return request<{ otp_id: string; expires_at: string; emailed?: boolean; dev_code?: string }>(
    "/api/auth/request-otp",
    { method: "POST", body: JSON.stringify({ email }) },
    { auth: false },
  );
}

export async function verifyOtp(otpId: string, code: string): Promise<AuthUser> {
  const data = await request<StoredAuth & { is_new_user: boolean }>(
    "/api/auth/verify-otp",
    { method: "POST", body: JSON.stringify({ otp_id: otpId, code }) },
    { auth: false },
  );
  await saveStoredAuth({ access: data.access, refresh: data.refresh, user: data.user });
  return data.user;
}

export async function signOut(): Promise<void> {
  await clearStoredAuth();
}

export function fetchMe() {
  return request<AuthUser>("/api/me", { method: "GET" });
}

// ---- Decks ----

export function fetchDecks() {
  return request<Deck[]>("/api/decks/", { method: "GET" });
}

// ---- Enrichment / cards ----

export function enrichCard(payload: EnrichPayload) {
  return request<EnrichResult>("/api/import/enrich/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Voice variant: transcribes the recording and enriches it server-side in
 * one request, so it consumes one AI quota unit — see backend/apps/imports
 * /views.py's EnrichVoiceView for why this isn't two separate calls. */
export function enrichVoice(payload: EnrichVoicePayload) {
  const form = new FormData();
  const ext = payload.audio.type.split("/")[1]?.split(";")[0] || "webm";
  form.append("audio", payload.audio, `voice.${ext}`);
  if (payload.language) form.append("language", payload.language);
  if (payload.card_type) form.append("card_type", payload.card_type);
  if (payload.back_language) form.append("back_language", payload.back_language);
  return request<EnrichVoiceResult>("/api/import/enrich-voice/", {
    method: "POST",
    body: form,
  });
}

/** Image variant: downloads and OCRs a webpage image server-side (SSRF-
 * checked — see backend/apps/imports/safe_fetch.py) and enriches it in one
 * request, so it consumes one AI quota unit — same shape as enrichVoice. */
export function enrichImage(payload: EnrichImagePayload) {
  return request<EnrichImageResult>("/api/import/enrich-image/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createCard(payload: CreateCardPayload) {
  return request<Card>("/api/cards/", { method: "POST", body: JSON.stringify(payload) });
}

/** Attaches an image to an already-created card (apps.cards.views
 * .CardImageView) — used right after createCard() to persist an image-mode
 * proposal's source image, since that endpoint only ever operates on a card
 * that already exists. */
export function attachCardImage(cardId: number, image: Blob) {
  const form = new FormData();
  form.append("image", image, "image.jpg");
  return request<{ id: number; url: string }>(`/api/cards/${cardId}/images/`, {
    method: "POST",
    body: form,
  });
}
