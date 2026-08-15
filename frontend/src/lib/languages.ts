/** Language catalogue — mirrors backend/apps/accounts/languages.py.
 *
 * Three different language questions live in this app and must not be
 * conflated:
 *  - `ui_language` — what the interface is written in (en/fa only, that's what
 *    we've translated).
 *  - `learning_languages` — what the user wants to learn.
 *  - `known_languages` — what they already understand.
 *
 * The last two drive which reels reach them: a reel teaches a *target* language
 * *in* a *base* language, and only matches when the target is something they're
 * learning and the base something they already read. Someone learning German
 * who only reads English shouldn't be shown German explained in Persian.
 */

export type LanguageCode =
  | "de" | "en" | "fa" | "ar" | "tr" | "fr" | "es" | "it" | "ru" | "nl";

export type Language = {
  code: LanguageCode;
  /** English name, for the en UI. */
  name: string;
  /** How speakers write it themselves — what someone picking their own
   *  language should see. */
  endonym: string;
};

export const LANGUAGES: Language[] = [
  { code: "de", name: "German", endonym: "Deutsch" },
  { code: "en", name: "English", endonym: "English" },
  { code: "fa", name: "Persian", endonym: "فارسی" },
  { code: "ar", name: "Arabic", endonym: "العربية" },
  { code: "tr", name: "Turkish", endonym: "Türkçe" },
  { code: "fr", name: "French", endonym: "Français" },
  { code: "es", name: "Spanish", endonym: "Español" },
  { code: "it", name: "Italian", endonym: "Italiano" },
  { code: "ru", name: "Russian", endonym: "Русский" },
  { code: "nl", name: "Dutch", endonym: "Nederlands" },
];

export function languageLabel(code: string): string {
  const lang = LANGUAGES.find((l) => l.code === code);
  if (!lang) return code;
  return lang.name === lang.endonym ? lang.name : `${lang.name} (${lang.endonym})`;
}

/** Has the user told us what they're learning? The reels feed asks when this is
 *  false rather than guessing — one extra question beats a feed of videos they
 *  can't follow. */
export function hasLanguagePrefs(user: {
  learning_languages?: string[] | null;
} | null): boolean {
  return !!user?.learning_languages?.length;
}
