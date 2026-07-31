/**
 * Centralised API client. Token state lives in module scope so every
 * request can attach the bearer header and transparently refresh + retry
 * on 401. AuthContext is the only writer via `configureAuth(...)`.
 */

import { cdpTrack } from "../lib/cdp-pixel";

export type AuthTokens = { access: string; refresh: string };

type AuthConfig = {
  tokens: AuthTokens | null;
  onTokensChange: ((tokens: AuthTokens) => void) | null;
  onAuthFailed: (() => void) | null;
};

const _state: AuthConfig = {
  tokens: null,
  onTokensChange: null,
  onAuthFailed: null,
};

const API_BASE_URL = ((import.meta as any).env.VITE_API_URL ?? "") as string;

// The backend runs on a free instance that sleeps after inactivity and takes a
// while to wake. Rather than failing the first request with a scary error, we
// retry transparently with backoff and broadcast a "waking" status so the UI
// can show a friendly banner.
const WAKE_RETRY_DELAYS = [1200, 2500, 4000, 5000, 6000, 8000, 8000]; // ~35s total

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function emitWaking(on: boolean) {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("nemo:waking", { detail: on }));
  }
}

/** fetch() that rides out a cold start: retries when the network call fails
 * (the proxy 502s before CORS headers, so fetch rejects) or on 502/503/504. */
async function fetchResilient(url: string, init: RequestInit): Promise<Response> {
  const isGet = (init.method ?? "GET").toUpperCase() === "GET";
  let waking = false;
  try {
    for (let attempt = 0; ; attempt++) {
      try {
        const res = await fetch(url, init);
        if (isGet && [502, 503, 504].includes(res.status) && attempt < WAKE_RETRY_DELAYS.length) {
          if (!waking) emitWaking((waking = true));
          await sleep(WAKE_RETRY_DELAYS[attempt]);
          continue;
        }
        return res;
      } catch (err) {
        if (attempt >= WAKE_RETRY_DELAYS.length) throw err;
        if (!waking) emitWaking((waking = true));
        await sleep(WAKE_RETRY_DELAYS[attempt]);
      }
    }
  } finally {
    if (waking) emitWaking(false);
  }
}

export function configureAuth(opts: Partial<AuthConfig>) {
  if (opts.tokens !== undefined) _state.tokens = opts.tokens;
  if (opts.onTokensChange !== undefined) _state.onTokensChange = opts.onTokensChange;
  if (opts.onAuthFailed !== undefined) _state.onAuthFailed = opts.onAuthFailed;
}

export function getAccessToken(): string | null {
  return _state.tokens?.access ?? null;
}

export class NetworkError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NetworkError";
    Object.setPrototypeOf(this, NetworkError.prototype);
  }
}

export class ServerError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ServerError";
    this.status = status;
    Object.setPrototypeOf(this, ServerError.prototype);
  }
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

export async function refreshAccessToken(): Promise<string | null> {
  const refresh = _state.tokens?.refresh;
  if (!refresh) return null;

  let res: Response;
  try {
    res = await fetchResilient(API_BASE_URL + "/api/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    });
  } catch (err) {
    throw new NetworkError(
      "Network error during token refresh: " +
        (err instanceof Error ? err.message : String(err)),
    );
  }

  if (res.status >= 500) {
    throw new ServerError("Server error during token refresh", res.status);
  }
  if (!res.ok) return null;

  const data = (await res.json().catch(() => ({}))) as { access?: string };
  if (!data.access) return null;

  const newTokens = { access: data.access, refresh };
  _state.tokens = newTokens;
  _state.onTokensChange?.(newTokens);
  return data.access;
}

async function jsonRequest<T>(path: string, init: RequestInit): Promise<T> {
  const buildHeaders = (token: string | null): HeadersInit => ({
    ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    ...(init.headers ?? {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  });

  let res: Response;
  try {
    res = await fetchResilient(API_BASE_URL + path, { ...init, headers: buildHeaders(getAccessToken()) });
  } catch (err) {
    throw new NetworkError(
      "Network error: " + (err instanceof Error ? err.message : String(err)),
    );
  }

  if (res.status === 401 && _state.tokens?.refresh && !path.startsWith("/api/auth/")) {
    const fresh = await refreshAccessToken();
    if (fresh) {
      res = await fetchResilient(API_BASE_URL + path, { ...init, headers: buildHeaders(fresh) });
    } else {
      _state.onAuthFailed?.();
    }
  }

  const isNoContent = res.status === 204;
  const body = isNoContent ? ({} as any) : await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401) _state.onAuthFailed?.();
    const detail =
      (body as { detail?: string }).detail ?? `Request failed (${res.status})`;
    if (res.status >= 500) throw new ServerError(detail, res.status);
    throw new ApiError(detail, res.status);
  }
  return body as T;
}

// ====== Types ======

export type SubscriptionState = "trial" | "active" | "expired";

export type SubscriptionSummary = {
  state: SubscriptionState;
  is_active: boolean;
  access_until: string | null;
  days_left: number;
  plan: string | null;
  /** Active paid tier ("basic"/"pro"), or null on trial/expired. */
  tier: string | null;
  /** AI actions used in the current 1-day window. */
  ai_used: number;
  /** Daily AI limit, or null when unlimited (staff). */
  ai_limit: number | null;
  /** A submitted "I've transferred" claim is awaiting admin verification. */
  pending: boolean;
};

export type SubscriptionPlan = { key: string; label: string; price_usd: string; days: number };

export type SubscriptionTier = {
  key: string;
  label: string;
  daily_ai_limit: number;
  plans: SubscriptionPlan[];
};

export type SubscriptionPlans = {
  tiers: SubscriptionTier[];
  payment: { method: string; network: string; address: string };
};

export type AuthUser = {
  id: number;
  email: string;
  display_name: string;
  ui_language: "en" | "fa";
  date_joined: string;
  /** Feature flags this user holds (see lib/features.ts). */
  feature_flags: string[];
  /** Subscription status for the top-of-page banner. */
  subscription: SubscriptionSummary;
  /** Has the welcome flow been completed? False routes into /welcome. */
  onboarded: boolean;
};

export type RequestOtpResponse = {
  otp_id: string;
  expires_at: string;
  emailed?: boolean;
  dev_code?: string;
};

export type VerifyOtpResponse = AuthTokens & { user: AuthUser; is_new_user: boolean };

export type CardType = "vocab" | "sentence" | "grammar" | "verb";
export type Article = "none" | "der" | "die" | "das" | "plural";

/** One row of a verb card's conjugation table: a tense/situation, the
 * conjugated form in the card's language, and its meaning. */
export type Conjugation = { tense: string; form: string; meaning: string };
export type CardState = "new" | "learning" | "review" | "relearning" | "suspended";

export type GrammarTable = {
  headers: string[];
  rows: string[][];
  highlight?: [number, number];
};

/**
 * A noun's analysis for a German sentence: its true gender (for colouring)
 * plus the article as used, its grammatical case, and why — for the case table.
 */
export type NounGender = {
  noun: string;
  gender: "der" | "die" | "das" | "plural";
  article?: string;
  case?: string; // Nominativ | Akkusativ | Dativ | Genitiv
  reason?: string;
  trigger?: string; // the word that forces the case (preposition/verb)
};

export type DeckCounts = { new: number; learning: number; due: number; total: number };

export type Deck = {
  id: number;
  name: string;
  full_name: string;
  parent: number | null;
  language: "de" | "en" | "";
  color: string;
  config: number;
  counts: DeckCounts;
  created_at: string;
};

export type CardImage = { id: number; url: string };

export type Card = {
  id: number;
  deck: number;
  deck_name?: string;
  deck_language?: string;
  card_type: CardType;
  direction: "forward" | "reverse";
  has_reverse?: boolean;
  images?: CardImage[];
  language: string;
  front: string;
  back: string;
  reading: string;
  article: Article;
  plural: string;
  example: string;
  notes: string;
  table: GrammarTable | null;
  genders: NounGender[];
  conjugations: Conjugation[];
  tags: string[];
  state: CardState;
  due: string;
  interval_days: number;
  ease: number;
  reps: number;
  lapses: number;
  is_leech: boolean;
  intervals?: Record<string, string> | null;
  created_at: string;
  updated_at: string;
};

/** A draft card straight out of the importer (no scheduling fields yet). */
export type DraftCard = {
  card_type: CardType;
  language: string;
  front: string;
  back: string;
  reading: string;
  article: Article;
  plural: string;
  example: string;
  notes: string;
  table: GrammarTable | null;
  genders: NounGender[];
  conjugations: Conjugation[];
  tags: string[];
};

// ====== Auth ======

export function requestOtp(email: string): Promise<RequestOtpResponse> {
  return jsonRequest<RequestOtpResponse>("/api/auth/request-otp", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export function verifyOtp(otpId: string, code: string): Promise<VerifyOtpResponse> {
  return jsonRequest<VerifyOtpResponse>("/api/auth/verify-otp", {
    method: "POST",
    body: JSON.stringify({ otp_id: otpId, code }),
  });
}

export function fetchMe(): Promise<AuthUser> {
  return jsonRequest<AuthUser>("/api/me", { method: "GET" });
}

export function updateMe(
  payload: Partial<Pick<AuthUser, "display_name" | "ui_language" | "onboarded">>,
): Promise<AuthUser> {
  return jsonRequest<AuthUser>("/api/me", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

// ====== Subscription ======

export function fetchSubscriptionPlans(): Promise<SubscriptionPlans> {
  return jsonRequest<SubscriptionPlans>("/api/subscription/plans", { method: "GET" });
}

/** Current subscription status incl. AI usage — used by the top banner. */
export function fetchSubscription(): Promise<SubscriptionSummary> {
  return jsonRequest<SubscriptionSummary>("/api/subscription", { method: "GET" });
}

/** "I've transferred" — records a pending claim (with the user's source wallet
 * or transaction hash) for admin verification (Phase 1). */
export function submitSubscriptionClaim(
  plan: string,
  txReference: string,
): Promise<{ ok: boolean; status: string }> {
  return jsonRequest("/api/subscription/claim", {
    method: "POST",
    body: JSON.stringify({ plan, tx_reference: txReference }),
  });
}

// ====== Decks ======

export function fetchDecks(): Promise<Deck[]> {
  return jsonRequest<Deck[]>("/api/decks/", { method: "GET" });
}

export function createDeck(payload: {
  name: string;
  parent?: number | null;
  language?: "de" | "en" | "";
}): Promise<Deck> {
  return jsonRequest<Deck>("/api/decks/", {
    method: "POST",
    body: JSON.stringify(payload),
  }).then((deck) => {
    cdpTrack("feature_used", { feature: "deck_create" });
    return deck;
  });
}

export function updateDeck(
  id: number,
  payload: Partial<{ name: string; parent: number | null; language: "de" | "en" | "" }>,
): Promise<Deck> {
  return jsonRequest<Deck>(`/api/decks/${id}/`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function deleteDeck(id: number): Promise<void> {
  return jsonRequest<void>(`/api/decks/${id}/`, { method: "DELETE" });
}

/** Bulk-run German colouring over a deck (article for vocab, genders for
 * sentence/grammar). Capped batch per call; re-run while `remaining > 0`. */
export function colourizeDeck(id: number): Promise<{ colourized: number; remaining: number }> {
  return jsonRequest(`/api/decks/${id}/colourize/`, { method: "POST" });
}

/** Auto-detect every card's type from its content and update it. */
export function autotypeDeck(
  id: number,
): Promise<{ changed: number; total: number; counts: Record<string, number> }> {
  return jsonRequest(`/api/decks/${id}/autotype/`, { method: "POST" });
}

// ====== Cards ======

export type Paginated<T> = {
  results: T[];
  count: number;
  page: number;
  page_size: number;
  num_pages: number;
};

/** A page of a deck's cards, optionally filtered by a search term / type. */
export function fetchCards(
  deckId: number,
  opts?: { page?: number; pageSize?: number; q?: string; type?: CardType },
): Promise<Paginated<Card>> {
  const p = new URLSearchParams({ deck: String(deckId) });
  if (opts?.page) p.set("page", String(opts.page));
  if (opts?.pageSize) p.set("page_size", String(opts.pageSize));
  if (opts?.q) p.set("q", opts.q);
  if (opts?.type) p.set("type", opts.type);
  return jsonRequest<Paginated<Card>>(`/api/cards/?${p.toString()}`, { method: "GET" });
}

export function createCard(payload: Partial<Card> & { deck: number; front: string }): Promise<Card> {
  return jsonRequest<Card>("/api/cards/", {
    method: "POST",
    body: JSON.stringify(payload),
  }).then((card) => {
    cdpTrack("feature_used", { feature: "card_create" });
    return card;
  });
}

export function updateCard(id: number, payload: Partial<Card>): Promise<Card> {
  return jsonRequest<Card>(`/api/cards/${id}/`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteCard(id: number): Promise<void> {
  return jsonRequest<void>(`/api/cards/${id}/`, { method: "DELETE" });
}

/** Colour a single card (article for vocab, noun genders for sentence/grammar). */
export function colourizeCard(id: number): Promise<Card> {
  return jsonRequest<Card>(`/api/cards/${id}/colourize/`, { method: "POST" });
}

/** Fetch one card (with grade-interval previews) to study it on its own. */
export function fetchCardForReview(id: number): Promise<Card> {
  return jsonRequest<Card>(`/api/cards/${id}/review/`, { method: "GET" });
}

/** Auto-find a small image for a card and attach it. */
export function findCardImage(cardId: number): Promise<CardImage> {
  return jsonRequest<CardImage>(`/api/cards/${cardId}/find-image/`, { method: "POST" });
}

export function addCardImage(cardId: number, file: File): Promise<CardImage> {
  const fd = new FormData();
  fd.append("image", file);
  return jsonRequest<CardImage>(`/api/cards/${cardId}/images/`, { method: "POST", body: fd });
}

export function deleteCardImage(cardId: number, imageId: number): Promise<void> {
  return jsonRequest<void>(`/api/cards/${cardId}/images/${imageId}/`, { method: "DELETE" });
}

export function bulkCreateCards(deck: number, cards: DraftCard[]): Promise<{ created: number; deck: number }> {
  return jsonRequest<{ created: number; deck: number }>("/api/cards/bulk/", {
    method: "POST",
    body: JSON.stringify({ deck, cards }),
  }).then((res) => {
    cdpTrack("feature_used", { feature: "import", count: res.created });
    return res;
  });
}

// ====== Study ======

export function fetchStudyQueue(deckId: number): Promise<Card[]> {
  return jsonRequest<Card[]>(`/api/decks/${deckId}/study/`, { method: "GET" });
}

export function answerCard(cardId: number, rating: 1 | 2 | 3 | 4, timeMs = 0): Promise<Card> {
  return jsonRequest<Card>(`/api/cards/${cardId}/answer/`, {
    method: "POST",
    body: JSON.stringify({ rating, time_ms: timeMs }),
  });
}

export function undoLastAnswer(): Promise<Card> {
  return jsonRequest<Card>("/api/cards/undo/", { method: "POST" });
}

// ====== Activity / stats ======

export type ActivityDay = { date: string; count: number; seconds: number };
export type ReviewActivity = {
  days: ActivityDay[];
  streak: number;
  longest_streak: number;
  active_days: number;
  today: { count: number; seconds: number };
  total_reviews: number;
};

export function fetchActivity(): Promise<ReviewActivity> {
  return jsonRequest<ReviewActivity>("/api/stats/activity/", { method: "GET" });
}

/** Ranges the performance page offers; the backend rejects anything else. */
export type StatsRange = 7 | 30 | 90 | 365;

/** One day of the review-log series. `new`/`learning`/`review` split `count` by
 * how far along the card was when answered. */
export type StatsDay = {
  date: string;
  count: number;
  seconds: number;
  new: number;
  learning: number;
  review: number;
};

export type StatsHour = { hour: number; count: number; retention: number | null };

export type StatsRatings = { again: number; hard: number; good: number; easy: number };

export type StatsCollection = {
  total: number;
  new: number;
  learning: number;
  young: number;
  mature: number;
  suspended: number;
  due_now: number;
  leeches: number;
  avg_ease: number | null;
  avg_interval: number | null;
};

export type StatsForecastDay = { date: string; count: number; cumulative: number };

export type StatsDeckRow = {
  id: number;
  name: string;
  full_name: string;
  language: string;
  cards: number;
  new: number;
  mature: number;
  due: number;
  reviews: number;
  seconds: number;
  retention: number | null;
};

export type StatsLeech = {
  id: number;
  front: string;
  back: string;
  deck: string;
  lapses: number;
  state: CardState;
  interval_days: number;
  is_leech: boolean;
};

export type StatsOverview = {
  range_days: StatsRange;
  range: {
    reviews: number;
    seconds: number;
    active_days: number;
    avg_per_active_day: number;
    avg_seconds_per_card: number;
    /** True retention (0–1) over review-state answers, or null with none yet. */
    retention: number | null;
    mature_answers: number;
    ratings: StatsRatings;
    days: StatsDay[];
    hours: StatsHour[];
  };
  collection: StatsCollection;
  forecast: StatsForecastDay[];
  intervals: { label: string; count: number }[];
  decks: StatsDeckRow[];
  leeches: StatsLeech[];
};

/** Everything the performance page renders, for the given trailing window. */
export function fetchStatsOverview(days: StatsRange): Promise<StatsOverview> {
  return jsonRequest<StatsOverview>(`/api/stats/overview/?days=${days}`, { method: "GET" });
}

// ====== Import ======

export function parseImport(payload: {
  text: string;
  language?: "de" | "en" | "";
  default_type?: CardType;
}): Promise<{ cards: DraftCard[]; source: string }> {
  return jsonRequest("/api/import/parse/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export type EnrichResult = {
  back: string;
  reading: string;
  article: Article;
  plural: string;
  example: string;
};

/** Translate one term + fill reading/article/example (the Translate button). */
export function enrichCard(payload: {
  front: string;
  language?: "de" | "en" | "";
  card_type?: CardType;
  back_language?: string;
}): Promise<EnrichResult> {
  return jsonRequest<EnrichResult>("/api/import/enrich/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export type ConjugateResult = { back: string; conjugations: Conjugation[] };

/** Conjugate a verb across the tenses a learner needs (the Fill button). */
export function conjugateVerb(payload: {
  front: string;
  language?: "de" | "en" | "";
  back_language?: string;
}): Promise<ConjugateResult> {
  return jsonRequest<ConjugateResult>("/api/import/conjugate/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export type AnkiImportResult = {
  decks: number;
  notes: number;
  cards: number;
  reversed: number;
  truncated: boolean;
  max_notes: number;
};

/** Import an Anki .apkg/.colpkg export: rebuild decks + create cards. */
export function importAnki(file: File, parentDeck: number | null): Promise<AnkiImportResult> {
  const fd = new FormData();
  fd.append("file", file);
  if (parentDeck != null) fd.append("parent_deck", String(parentDeck));
  return jsonRequest<AnkiImportResult>("/api/import/anki/", { method: "POST", body: fd });
}

// ====== Books ======

export type BookLesson = {
  id: number;
  title: string;
  position: number;
  card_count: number;
  processed: boolean;
  page_start: number | null;
  page_end: number | null;
  pdf_url: string | null;
};

export type BookLessonDetail = BookLesson & { raw_text: string; cards: DraftCard[] };

export type Book = {
  id: number;
  title: string;
  source_language: "de" | "en" | "";
  translation_language: string;
  status: "processing" | "ready" | "failed";
  color: string;
  note: string;
  lessons: BookLesson[];
  lesson_count: number;
  card_count: number;
  has_pdf: boolean;
  is_owner: boolean;
  owner_email: string;
  shared_with: string[];
  created_at: string;
};

export type PageMapItem = { num: number; start_page: number };

export function fetchBooks(): Promise<Book[]> {
  return jsonRequest<Book[]>("/api/books/", { method: "GET" });
}

export function fetchSharedBooks(): Promise<Book[]> {
  return jsonRequest<Book[]>("/api/books/shared/", { method: "GET" });
}

export function fetchBook(id: number): Promise<Book> {
  return jsonRequest<Book>(`/api/books/${id}/`, { method: "GET" });
}

export function shareBook(id: number, email: string): Promise<Book> {
  return jsonRequest<Book>(`/api/books/${id}/shares/`, {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export function unshareBook(id: number, email: string): Promise<Book> {
  return jsonRequest<Book>(`/api/books/${id}/shares/`, {
    method: "DELETE",
    body: JSON.stringify({ email }),
  });
}

/** Per-page scan of a PDF → editable unit→start-page map (saves nothing). */
export function analyzeBook(payload: {
  file: File;
  lesson_label?: string;
  from_lesson: number;
  to_lesson: number;
  pages_per_unit?: number | null;
}): Promise<{ page_count: number; detected_count: number; units: PageMapItem[] }> {
  const fd = new FormData();
  fd.append("file", payload.file);
  if (payload.lesson_label) fd.append("lesson_label", payload.lesson_label);
  fd.append("from_lesson", String(payload.from_lesson));
  fd.append("to_lesson", String(payload.to_lesson));
  if (payload.pages_per_unit != null) fd.append("pages_per_unit", String(payload.pages_per_unit));
  return jsonRequest("/api/books/analyze/", { method: "POST", body: fd });
}

export function uploadBook(payload: {
  title: string;
  source_language: "de" | "en" | "";
  translation_language: string;
  text?: string;
  file?: File | null;
  lesson_label?: string;
  from_lesson?: number | null;
  to_lesson?: number | null;
  pages_per_unit?: number | null;
  start_page?: number | null;
  page_map?: PageMapItem[] | null;
}): Promise<Book> {
  const fd = new FormData();
  fd.append("title", payload.title);
  fd.append("source_language", payload.source_language);
  fd.append("translation_language", payload.translation_language);
  if (payload.text) fd.append("text", payload.text);
  if (payload.file) fd.append("file", payload.file);
  if (payload.lesson_label) fd.append("lesson_label", payload.lesson_label);
  if (payload.from_lesson != null) fd.append("from_lesson", String(payload.from_lesson));
  if (payload.to_lesson != null) fd.append("to_lesson", String(payload.to_lesson));
  if (payload.pages_per_unit != null) fd.append("pages_per_unit", String(payload.pages_per_unit));
  if (payload.start_page != null) fd.append("start_page", String(payload.start_page));
  if (payload.page_map) fd.append("page_map", JSON.stringify(payload.page_map));
  return jsonRequest<Book>("/api/books/", { method: "POST", body: fd });
}

export function deleteBook(id: number): Promise<void> {
  return jsonRequest<void>(`/api/books/${id}/`, { method: "DELETE" });
}

/** Edit a book's language / translation / title. */
export function updateBook(
  id: number,
  payload: Partial<{ source_language: "de" | "en" | ""; translation_language: string; title: string }>,
): Promise<Book> {
  return jsonRequest<Book>(`/api/books/${id}/`, { method: "PATCH", body: JSON.stringify(payload) });
}

/** Re-split the book's stored PDF with new page settings. Replaces only the
 * lessons whose unit number falls in [from_lesson..to_lesson]; every other
 * lesson is kept, so a book can be re-split range-by-range. */
export function regenerateBook(
  bookId: number,
  payload: {
    from_lesson: number;
    to_lesson: number;
    pages_per_unit?: number | null;
    start_page?: number | null;
    lesson_label?: string;
  },
): Promise<Book> {
  return jsonRequest<Book>(`/api/books/${bookId}/regenerate/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** A lesson's content — the page text assigned to it, plus any cards. */
export function fetchBookLesson(bookId: number, lessonId: number): Promise<BookLessonDetail> {
  return jsonRequest<BookLessonDetail>(`/api/books/${bookId}/lessons/${lessonId}/`, { method: "GET" });
}

/** Extract one lesson's vocabulary (the per-lesson Process button). */
export function processBookLesson(bookId: number, lessonId: number): Promise<BookLesson> {
  return jsonRequest<BookLesson>(`/api/books/${bookId}/lessons/${lessonId}/process/`, {
    method: "POST",
  });
}

export function importBookLesson(
  bookId: number,
  lessonId: number,
  parentDeck: number | null,
): Promise<{ book_deck: number; lesson_deck: number; cards: number }> {
  return jsonRequest(`/api/books/${bookId}/lessons/${lessonId}/import/`, {
    method: "POST",
    body: JSON.stringify({ parent_deck: parentDeck }),
  });
}

/** Get each noun's true gender for a German sentence (Colour-genders button). */
export function analyzeGerman(text: string): Promise<{ nouns: NounGender[]; source: string }> {
  return jsonRequest("/api/import/analyze-de/", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

// ====== Writing practice ======

export type WritingIssue = {
  original: string;
  correction: string;
  type: string;
  explanation: string;
};

export type WritingPrompt = {
  text: string;
  source: "books" | "auto";
  book_title?: string;
  lesson_title?: string;
};

export type WritingBook = { id: number; title: string };

export function writingBooks(): Promise<WritingBook[]> {
  return jsonRequest("/api/writing/books/", { method: "GET" });
}

export function writingPrompt(payload: {
  language: string;
  translation_language: string;
  source: "books" | "auto";
  book_id?: number;
}): Promise<WritingPrompt> {
  return jsonRequest("/api/writing/prompt/", { method: "POST", body: JSON.stringify(payload) });
}

export function writingTopic(language: string): Promise<{ topic: string; en: string }> {
  return jsonRequest("/api/writing/topic/", { method: "POST", body: JSON.stringify({ language }) });
}

export function writingCheck(
  text: string,
  language: string,
): Promise<{ feedback: string; issues: WritingIssue[] }> {
  return jsonRequest("/api/writing/check/", { method: "POST", body: JSON.stringify({ text, language }) });
}

export function writingToCard(payload: {
  language: string;
  front: string;
  back?: string;
  notes?: string;
}): Promise<{ card_id: number; deck_id: number; deck_name: string }> {
  return jsonRequest("/api/writing/card/", { method: "POST", body: JSON.stringify(payload) });
}

// ====== Conversation ======

export type ConvCorrection = { original: string; correction: string; explanation: string };
export type ConvReply = { response: string; corrections: ConvCorrection[] };
export type ConvMessage = { role: "user" | "ai"; text: string; corrections?: ConvCorrection[] };

export function conversationReply(payload: {
  language: string;
  text: string;
  history: { role: string; text: string }[];
}): Promise<ConvReply> {
  return jsonRequest("/api/conversation/reply/", { method: "POST", body: JSON.stringify(payload) });
}

export function conversationText(payload: {
  language: string;
  book_id?: number;
}): Promise<{ text: string; source: string; book_title?: string; lesson_title?: string }> {
  return jsonRequest("/api/conversation/text/", { method: "POST", body: JSON.stringify(payload) });
}

// ====== Support ======

export type SupportMessage = { id: number; from_admin: boolean; body: string; created_at: string };
export type SupportThread = {
  id: number;
  messages: SupportMessage[];
  created_at: string;
  updated_at: string;
};

export function fetchSupportThread(): Promise<SupportThread> {
  return jsonRequest("/api/support/thread/", { method: "GET" });
}

export function sendSupportMessage(body: string): Promise<SupportThread> {
  return jsonRequest("/api/support/thread/", { method: "POST", body: JSON.stringify({ body }) });
}

// ====== Placement Test ======

export type PlacementLevel = "A1" | "A2" | "B1" | "B2" | "C1";

export type PlacementQuestion = {
  id: number;
  order: number;
  section: "reading" | "listening";
  level_tag: PlacementLevel;
  /** Reading: shown up front. Listening: "" — only read aloud via speak(). */
  passage: string;
  audio_text: string;
  question_text: string;
  choices: string[];
};

export type StartPlacementResult = { attempt_id: number; questions: PlacementQuestion[] };

export function startPlacementTest(
  language: "de" | "en",
  length: "quick" | "full",
): Promise<StartPlacementResult> {
  return jsonRequest<StartPlacementResult>("/api/placement/start/", {
    method: "POST",
    body: JSON.stringify({ language, length }),
  });
}

export type PlacementResult = {
  estimated_level: PlacementLevel;
  correct_count: number;
  total_count: number;
  by_level: Record<PlacementLevel, { correct: number; total: number }>;
};

export function submitPlacementTest(
  attemptId: number,
  answers: { question_id: number; choice_index: number }[],
): Promise<PlacementResult> {
  return jsonRequest<PlacementResult>(`/api/placement/${attemptId}/submit/`, {
    method: "POST",
    body: JSON.stringify({ answers }),
  });
}
