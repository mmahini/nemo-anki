import { Fragment } from "react";

import type { NounGender } from "../auth/api";

/**
 * Renders German text with only the meaningful vocabulary coloured: the
 * articles and the nouns they govern, by gender (der=blue, die=red,
 * das=green, plural=purple). Verbs, prepositions, adjectives and everything
 * else stay in the default ink. Non-German text is returned as-is.
 *
 * Two modes:
 *  - Accurate: when `genders` is supplied (from the "Colour genders" button,
 *    LLM-derived), each noun is coloured by its TRUE dictionary gender,
 *    matched by word in order — so a dative "der Frau" is correctly red.
 *  - Heuristic (no genders): the article's surface form decides the colour,
 *    a learner mnemonic that can mis-colour oblique cases.
 */
const ARTICLE_GROUP: Record<string, "der" | "die" | "das"> = {
  der: "der", den: "der", dem: "der", des: "der",
  ein: "der", einen: "der", einem: "der", eines: "der",
  die: "die", eine: "die", einer: "die",
  das: "das",
};

const ARTICLE_WORDS = new Set(Object.keys(ARTICLE_GROUP));
const SENTENCE_END = /[.!?;:]/;

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
  if (lang !== "de" || !text) return <>{text}</>;

  const tokens = text.split(/(\s+|[.,!?;:„""'»«()\[\]\-])/).filter((t) => t !== "");
  const cls = new Array<string>(tokens.length).fill("");

  if (genders && genders.length) {
    // Accurate mode: walk the LLM's noun list in order, match by word.
    const queue = [...genders];
    const wordIdx: number[] = []; // indices of word tokens, to scan back for articles
    tokens.forEach((tok, i) => {
      if (!/[A-Za-zÄÖÜäöüß]/.test(tok)) return;
      wordIdx.push(i);
      if (queue.length && isNoun(tok) && norm(tok) === norm(queue[0].noun)) {
        const g = queue.shift()!.gender;
        cls[i] = `art-${g}`;
        // colour the governing article (nearest preceding article word)
        for (let k = wordIdx.length - 2; k >= 0 && k >= wordIdx.length - 3; k--) {
          const j = wordIdx[k];
          if (ARTICLE_WORDS.has(norm(tokens[j]))) {
            cls[j] = `art-${g}`;
            break;
          }
        }
      }
    });
  } else {
    // Heuristic mode: colour by the article's surface form.
    let pending: "der" | "die" | "das" | null = null;
    let since = 0;
    tokens.forEach((tok, i) => {
      const isWord = /[A-Za-zÄÖÜäöüß]/.test(tok);
      if (!isWord) {
        if (SENTENCE_END.test(tok)) pending = null;
        return;
      }
      const group = ARTICLE_GROUP[tok.toLowerCase()];
      if (group) {
        pending = group;
        since = 0;
        cls[i] = `art-${group}`;
        return;
      }
      if (pending) {
        since += 1;
        if (isNoun(tok)) {
          cls[i] = `art-${pending}`;
          pending = null;
        } else if (since > 2) {
          pending = null;
        }
      }
    });
  }

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
