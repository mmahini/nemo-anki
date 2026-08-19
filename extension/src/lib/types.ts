export type AuthTokens = { access: string; refresh: string };

export type AuthUser = {
  id: number;
  email: string;
  display_name: string;
  learning_languages: string[];
  known_languages: string[];
};

export type StoredAuth = AuthTokens & { user: AuthUser };

/** What the card teaches — mirrors the backend's CardType (apps/cards/models.py). */
export type CardType =
  | "vocab"
  | "sentence"
  | "grammar"
  | "verb"
  | "adjective"
  | "adverb"
  | "preposition";

export type Article = "none" | "der" | "die" | "das" | "plural";

export type Deck = {
  id: number;
  name: string;
  full_name: string;
  language: "de" | "en" | "";
};

export type EnrichPayload = {
  front: string;
  language?: "de" | "en" | "";
  card_type?: CardType;
  back_language?: string;
};

/** Response shape from POST /api/import/enrich/ — a proposal, never persisted. */
export type EnrichResult = {
  card_type?: CardType;
  back: string;
  reading: string;
  article: Article;
  plural: string;
  example: string;
};

export type CreateCardPayload = {
  deck: number;
  card_type: CardType;
  language: string;
  front: string;
  back: string;
  reading: string;
  article: Article;
  plural: string;
  example: string;
};

export type Card = {
  id: number;
  deck: number;
  card_type: CardType;
  front: string;
  back: string;
};

/** A pending text capture handed off from the background worker (context menu
 * or keyboard shortcut) to the proposal window via chrome.storage.session. */
export type PendingCapture = {
  id: string;
  text: string;
  sourceUrl: string;
  sourceTitle: string;
  createdAt: number;
};
