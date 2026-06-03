import type { Article } from "../auth/api";

/** CSS class that tints a German noun by its article (see docs/GERMAN_COLORS.md). */
export function articleClass(article: Article): string {
  switch (article) {
    case "der":
      return "art-der";
    case "die":
      return "art-die";
    case "das":
      return "art-das";
    case "plural":
      return "art-plural";
    default:
      return "";
  }
}

export function articlePillClass(article: Article): string {
  switch (article) {
    case "der":
      return "pill pill--der";
    case "die":
      return "pill pill--die";
    case "das":
      return "pill pill--das";
    case "plural":
      return "pill pill--plural";
    default:
      return "pill";
  }
}

export function articleLabel(article: Article): string {
  return article === "plural" ? "die (pl)" : article;
}

/**
 * Pull a leading German article off a typed term, e.g. "der Tisch" ->
 * { article: "der", rest: "Tisch" }. Returns null when there's no article.
 */
export function detectArticle(front: string): { article: Article; rest: string } | null {
  const m = /^\s*(der|die|das)\s+(.+)$/i.exec(front);
  if (!m) return null;
  return { article: m[1].toLowerCase() as Article, rest: m[2].trim() };
}
