/**
 * Centralised API client. Token state lives in module scope so every
 * request can attach the bearer header and transparently refresh + retry
 * on 401. AuthContext is the only writer via `configureAuth(...)`.
 */

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
    res = await fetch(API_BASE_URL + "/api/auth/refresh", {
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
    res = await fetch(API_BASE_URL + path, { ...init, headers: buildHeaders(getAccessToken()) });
  } catch (err) {
    throw new NetworkError(
      "Network error: " + (err instanceof Error ? err.message : String(err)),
    );
  }

  if (res.status === 401 && _state.tokens?.refresh && !path.startsWith("/api/auth/")) {
    const fresh = await refreshAccessToken();
    if (fresh) {
      res = await fetch(API_BASE_URL + path, { ...init, headers: buildHeaders(fresh) });
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

export type AuthUser = {
  id: number;
  email: string;
  display_name: string;
  date_joined: string;
};

export type RequestOtpResponse = {
  otp_id: string;
  expires_at: string;
  dev_code?: string;
};

export type VerifyOtpResponse = AuthTokens & { user: AuthUser };

export type CardType = "vocab" | "sentence" | "grammar";
export type Article = "none" | "der" | "die" | "das" | "plural";
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

export function fetchCards(deckId: number): Promise<Card[]> {
  return jsonRequest<Card[]>(`/api/cards/?deck=${deckId}`, { method: "GET" });
}

export function createCard(payload: Partial<Card> & { deck: number; front: string }): Promise<Card> {
  return jsonRequest<Card>("/api/cards/", {
    method: "POST",
    body: JSON.stringify(payload),
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
  return jsonRequest("/api/cards/bulk/", {
    method: "POST",
    body: JSON.stringify({ deck, cards }),
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

/** Re-split the book's stored PDF with new page settings (replaces lessons). */
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
