import { Fragment } from "react";

import type { NounGender } from "../auth/api";

/**
 * Renders German text. Words are coloured ONLY once the noun genders have been
 * resolved by the "Colour genders" button (LLM-derived) — until then the
 * sentence is shown in plain black, so nothing is guessed/mis-coloured. When
 * `genders` is present, each noun is coloured by its true dictionary gender
 * (der=blue, die=red, das=green, plural=purple), matched by word in order, and
 * its governing article is tinted the same — so a dative "der Frau" is red.
 * Non-German text is returned as-is.
 */
const ARTICLE_WORDS = new Set([
  "der", "die", "das", "den", "dem", "des",
  "ein", "eine", "einen", "einem", "einer", "eines",
]);

function isNoun(token: string): boolean {
  return /^[A-ZÄÖÜ][\wäöüÄÖÜß-]*$/.test(token);
}

function norm(s: string): string {
  return s.replace(/[.,!?;:„""'»«()[\]]/g, "").toLowerCase();
}

export default function GermanText({
  text,
  lang,
  genders,
}: {
  text: string;
  lang: string;
  genders?: NounGender[];
}) {
  // Black until analysed (or non-German): render verbatim.
  if (lang !== "de" || !text || !genders || genders.length === 0) {
    return <>{text}</>;
  }

  const tokens = text.split(/(\s+|[.,!?;:„""'»«()\[\]\-])/).filter((t) => t !== "");
  const cls = new Array<string>(tokens.length).fill("");

  // Words that force a case (prepositions / governing verbs) — highlighted in a
  // distinct colour so the learner sees *why* a noun is Akkusativ/Dativ/etc.
  const triggers = new Set<string>();
  for (const g of genders) {
    for (const w of (g.trigger || "").split(/\s+/)) {
      const n = norm(w);
      if (n && !ARTICLE_WORDS.has(n)) triggers.add(n);
    }
  }

  const queue = [...genders];
  const wordIdx: number[] = []; // indices of word tokens, to scan back for the article
  tokens.forEach((tok, i) => {
    if (!/[A-Za-zÄÖÜäöüß]/.test(tok)) return;
    wordIdx.push(i);
    if (queue.length && isNoun(tok) && norm(tok) === norm(queue[0].noun)) {
      const g = queue.shift()!.gender;
      cls[i] = `art-${g}`;
      // colour the governing article (nearest preceding article word, within 2)
      for (let k = wordIdx.length - 2; k >= 0 && k >= wordIdx.length - 3; k--) {
        const j = wordIdx[k];
        if (ARTICLE_WORDS.has(norm(tokens[j]))) {
          cls[j] = `art-${g}`;
          break;
        }
      }
    } else if (!cls[i] && triggers.has(norm(tok))) {
      cls[i] = "trigger-word";
    }
  });

  return (
    <>
      {tokens.map((tok, i) =>
        cls[i] ? (
          <span key={i} className={cls[i]}>{tok}</span>
        ) : (
          <Fragment key={i}>{tok}</Fragment>
        ),
      )}
    </>
  );
}
