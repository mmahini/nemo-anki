import type { Card, DraftCard } from "../auth/api";
import { articleClass, articlePillClass, articleLabel } from "../lib/article";
import GermanText from "./GermanText";
import GrammarTable from "./GrammarTable";
import SpeakButton from "./SpeakButton";

type AnyCard = Card | DraftCard;

/** The front of a card (the recall prompt). Article-tinted for German nouns. */
export function CardFront({ card }: { card: AnyCard }) {
  // Vocab: tint the whole single term by its article. Sentence/grammar: only
  // the articles + their nouns are coloured (verbs etc. stay plain).
  const isVocab = card.card_type === "vocab";
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

/** The back of a card: answer + reading + example (+ grammar table/notes). */
export function CardBack({ card }: { card: AnyCard }) {
  return (
    <div className="face face--back">
      {card.back && <div className="face__answer">{card.back}</div>}
      {card.reading && (
        <div className="face__readingrow">
          <span className="face__reading">/{card.reading}/</span>
          <SpeakButton text={card.front} lang={card.language} small title="Hear pronunciation" />
        </div>
      )}
      {card.notes && <div className="face__notes">{card.notes}</div>}
      {card.table && <GrammarTable table={card.table} />}
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
