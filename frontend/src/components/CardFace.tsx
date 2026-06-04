import type { Card, DraftCard } from "../auth/api";
import { articleClass, articlePillClass, articleLabel } from "../lib/article";
import CaseTable from "./CaseTable";
import GermanText from "./GermanText";
import GrammarTable from "./GrammarTable";
import SpeakButton from "./SpeakButton";

type AnyCard = Card | DraftCard;

function cardDirection(card: AnyCard): "forward" | "reverse" {
  return "direction" in card ? card.direction : "forward";
}

/** The article-tinted term (German word) with its gender pill + audio. Used as
 * the prompt on forward vocab and as the answer on reverse vocab. */
function TermReveal({ card }: { card: AnyCard }) {
  const tint = card.article !== "none" ? articleClass(card.article) : "";
  return (
    <>
      {card.article !== "none" && (
        <span className={articlePillClass(card.article)}>{articleLabel(card.article)}</span>
      )}
      <div className="face__termrow">
        <div className={`face__term ${tint}`}>{card.front}</div>
        <SpeakButton text={card.front} lang={card.language} title="Hear the word" />
      </div>
    </>
  );
}

/** The front of a card (the recall prompt). Article-tinted for German nouns.
 * On a reverse vocab card the prompt is the meaning instead of the term. */
export function CardFront({ card }: { card: AnyCard }) {
  const isVocab = card.card_type === "vocab";

  // Reverse vocab: prompt with the meaning, recall the (tinted) word.
  if (isVocab && cardDirection(card) === "reverse") {
    return (
      <div className="face face--front">
        <span className="face__dirbadge">⇄ recall the word</span>
        <div className="face__termrow">
          <div className="face__term face__term--meaning" dir="auto">{card.back}</div>
        </div>
      </div>
    );
  }

  // Forward vocab: tint the whole single term by its article. Sentence/grammar:
  // only the articles + their nouns are coloured (verbs etc. stay plain).
  const vocabTint = isVocab && card.article !== "none" ? articleClass(card.article) : "";
  return (
    <div className="face face--front">
      {isVocab && card.article !== "none" && (
        <span className={articlePillClass(card.article)}>{articleLabel(card.article)}</span>
      )}
      <div className="face__termrow">
        <div className={`face__term ${vocabTint}`}>
          {isVocab ? (
            card.front
          ) : (
            <GermanText text={card.front} lang={card.language} genders={card.genders} />
          )}
        </div>
        <SpeakButton text={card.front} lang={card.language} title="Hear the word" />
      </div>
      {card.card_type === "grammar" && card.notes && (
        <div className="face__hint">complete the sentence</div>
      )}
    </div>
  );
}

/** The back of a card: answer + reading + example (+ grammar table/notes).
 * On a reverse vocab card the answer is the tinted term itself. */
export function CardBack({ card }: { card: AnyCard }) {
  const isReverseVocab = card.card_type === "vocab" && cardDirection(card) === "reverse";
  return (
    <div className="face face--back">
      {isReverseVocab ? (
        <TermReveal card={card} />
      ) : (
        card.back && <div className="face__answer" dir="auto">{card.back}</div>
      )}
      {card.reading && (
        <div className="face__readingrow">
          <span className="face__reading">/{card.reading}/</span>
          <SpeakButton text={card.front} lang={card.language} small title="Hear pronunciation" />
        </div>
      )}
      {card.card_type === "vocab" && card.plural && (
        <div className="face__plural">
          plural: <span className="art-plural">{card.plural}</span>
          <SpeakButton text={card.plural} lang={card.language} small title="Hear the plural" />
        </div>
      )}
      {card.notes && <div className="face__notes">{card.notes}</div>}
      {card.table && <GrammarTable table={card.table} />}
      {card.card_type === "sentence" && card.genders.length > 0 && (
        <CaseTable items={card.genders} />
      )}
      {card.example && (
        <div className="face__example">
          “<GermanText text={card.example} lang={card.language} />”
        </div>
      )}
      {card.tags.length > 0 && (
        <div className="face__tags">
          {card.tags.map((t) => (
            <span key={t} className="tag">{t}</span>
          ))}
        </div>
      )}
    </div>
  );
}
