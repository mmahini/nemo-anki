import { Fragment } from "react";

/**
 * Renders German text with only the meaningful vocabulary coloured: the
 * articles and the nouns they govern, by gender (der=blue, die=red,
 * das=green). Verbs, prepositions, adjectives and everything else stay in
 * the default ink. Non-German text is returned as-is.
 *
 * Gender is taken from the article's surface form (the learner mnemonic the
 * rest of the app uses). Note: oblique forms are mapped to their most common
 * gender group, so a dative "der Frau" is shown in the der-colour — a known,
 * pragmatic simplification, not a grammatical claim.
 */
const ARTICLE_GROUP: Record<string, "der" | "die" | "das"> = {
  der: "der", den: "der", dem: "der", des: "der",
  ein: "der", einen: "der", einem: "der", eines: "der",
  die: "die", eine: "die", einer: "die",
  das: "das",
};

const SENTENCE_END = /[.!?;:]/;

function isNoun(token: string): boolean {
  // German nouns are capitalised; allow umlauts.
  return /^[A-ZÄÖÜ][\wäöüÄÖÜß-]*$/.test(token);
}

export default function GermanText({ text, lang }: { text: string; lang: string }) {
  if (lang !== "de" || !text) return <>{text}</>;

  // Keep whitespace + punctuation as their own tokens so we can re-emit verbatim.
  const tokens = text.split(/(\s+|[.,!?;:„""'»«()\[\]\-])/).filter((t) => t !== "");

  let pending: "der" | "die" | "das" | null = null; // gender awaiting its noun
  let wordsSincePending = 0;

  const nodes = tokens.map((tok, i) => {
    const isWord = /[A-Za-zÄÖÜäöüß]/.test(tok);
    if (!isWord) {
      if (SENTENCE_END.test(tok)) pending = null;
      return <Fragment key={i}>{tok}</Fragment>;
    }

    const group = ARTICLE_GROUP[tok.toLowerCase()];
    if (group) {
      pending = group;
      wordsSincePending = 0;
      return <span key={i} className={`art-${group}`}>{tok}</span>;
    }

    if (pending) {
      wordsSincePending += 1;
      if (isNoun(tok)) {
        const g = pending;
        pending = null;
        return <span key={i} className={`art-${g}`}>{tok}</span>;
      }
      if (wordsSincePending > 2) pending = null; // adjective run too long — give up
    }

    return <Fragment key={i}>{tok}</Fragment>;
  });

  return <>{nodes}</>;
}
