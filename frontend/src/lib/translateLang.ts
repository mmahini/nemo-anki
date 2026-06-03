/** Target language for the card's *back* (the translation). Persisted so the
 * user's last choice becomes the default next time. */

export const TRANSLATE_LANGS = [
  "English",
  "Persian",
  "German",
  "French",
  "Spanish",
  "Italian",
  "Turkish",
  "Arabic",
  "Russian",
  "Chinese",
] as const;

const KEY = "nemo-anki.translateLang";

export function getTranslateLang(): string {
  try {
    return localStorage.getItem(KEY) || "English";
  } catch {
    return "English";
  }
}

export function setTranslateLang(lang: string): void {
  try {
    localStorage.setItem(KEY, lang);
  } catch {
    /* ignore */
  }
}
