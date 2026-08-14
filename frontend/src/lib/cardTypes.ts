import type { CardType } from "../auth/api";

/** Every card type, in the order the type pickers list them: the parts of
 * speech first, then the two non-word formats. Mirrors the backend CardType
 * enum in apps/cards/models.py. */
export const CARD_TYPES: CardType[] = [
  "vocab",
  "verb",
  "adjective",
  "adverb",
  "preposition",
  "sentence",
  "grammar",
];

/** Single-word cards, whatever the part of speech — as opposed to the
 * "sentence" and "grammar" formats. Mirrors backend WORD_TYPES. */
const WORD_TYPES = new Set<CardType>(["vocab", "verb", "adjective", "adverb", "preposition"]);

export function isWordType(t: CardType): boolean {
  return WORD_TYPES.has(t);
}
