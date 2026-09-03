export type AuthTokens = { access: string; refresh: string };

export type AuthUser = {
  id: number;
  email: string;
  display_name: string;
  learning_languages: string[];
  known_languages: string[];
};

export type StoredAuth = AuthTokens & { user: AuthUser };

/** An in-progress OTP login — kept in chrome.storage.session (not .local,
 * since it's only useful for the current browser session) so the popup
 * reopening mid-flow (Chrome unloads it on every outside click) lands back
 * on the code screen instead of losing the email and starting over. */
export type PendingOtp = { email: string; otpId: string; devCode?: string };

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

export type EnrichVoicePayload = {
  audio: Blob;
  language?: "de" | "en" | "";
  card_type?: CardType;
  back_language?: string;
};

/** Response shape from POST /api/import/enrich-voice/ — EnrichResult plus the
 * transcript itself, since (unlike text capture) the proposal window doesn't
 * already know what "front" is before this call returns. */
export type EnrichVoiceResult = EnrichResult & { front: string };

export type EnrichImagePayload = {
  image_url: string;
  language?: "de" | "en" | "";
  card_type?: CardType;
  back_language?: string;
};

/** Response shape from POST /api/import/enrich-image/ — EnrichResult plus the
 * OCR'd transcript (like voice) and a data URL of the backend-downloaded,
 * size-capped source image. The proposal window holds onto that data URL and
 * attaches it to the card (via CardImageView) only once the user actually
 * creates it — nothing is persisted before that. */
export type EnrichImageResult = EnrichResult & { front: string; image_data_url: string };

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

/** Same handoff as PendingCapture, but for the image context menu — carries
 * the clicked image's source URL instead of selected text. */
export type PendingImageCapture = {
  id: string;
  imageUrl: string;
  sourceUrl: string;
  sourceTitle: string;
  createdAt: number;
};
