import type { Card, DraftCard } from "../auth/api";
import { articleClass, articlePillClass, articleLabel } from "../lib/article";
import GrammarTable from "./GrammarTable";

type AnyCard = Card | DraftCard;

/** The front of a card (the recall prompt). Article-tinted for German nouns. */
export function CardFront({ card }: { card: AnyCard }) {
  const tint = card.article !== "none" ? articleClass(card.article) : "";
  return (
    <div className="face face--front">
      {card.article !== "none" && (
        <span className={articlePillClass(card.article)}>{articleLabel(card.article)}</span>
      )}
      <div className={`face__term ${tint}`}>{card.front}</div>
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
      {card.reading && <div className="face__reading">/{card.reading}/</div>}
      {card.notes && <div className="face__notes">{card.notes}</div>}
      {card.table && <GrammarTable table={card.table} />}
      {card.example && <div className="face__example">“{card.example}”</div>}
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
