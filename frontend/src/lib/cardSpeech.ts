import type { Card } from "../auth/api";

/** What to read aloud on the FRONT (prompt) of a card during review, or null
 * when it shouldn't auto-play. We read the front term in the card's language
 * (falling back to the deck's). A reverse vocab card's prompt is the meaning,
 * not the target-language term, so we skip auto-reading it. */
export function promptSpeech(card: Card): { text: string; lang: string } | null {
  if (card.card_type === "vocab" && card.direction === "reverse") return null;
  const text = (card.front || "").trim();
  if (!text) return null;
  return { text, lang: card.language || card.deck_language || "" };
}
