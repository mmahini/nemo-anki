import { useTranslation } from "react-i18next";

import { useAuth } from "../auth/AuthContext";
import type { Card, DraftCard } from "../auth/api";
import { articleClass, articlePillClass, articleLabel } from "../lib/article";
import CaseTable from "./CaseTable";
import ConjTable from "./ConjTable";
import GermanText from "./GermanText";
import GrammarTable from "./GrammarTable";
import PronunciationCheck from "./PronunciationCheck";
import SpeakButton from "./SpeakButton";

type AnyCard = Card | DraftCard;

function cardDirection(card: AnyCard): "forward" | "reverse" {
  return "direction" in card ? card.direction : "forward";
}

/** The language to read/colour the card in: the card's own, else the deck's,
 * else (when neither is set) the caller-supplied fallback — the user's own
 * first learning language, so TTS never silently falls back to the browser's
 * default voice just because a card/deck never had its language set. */
function cardLang(card: AnyCard, fallback = ""): string {
  return card.language || ("deck_language" in card ? card.deck_language ?? "" : "") || fallback;
}

/** The article-tinted term (German word) with its gender pill + audio. Used as
 * the prompt on forward vocab and as the answer on reverse vocab. */
function TermReveal({ card }: { card: AnyCard }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const lang = cardLang(card, user?.learning_languages?.[0] ?? "");
  const tint = card.article !== "none" ? articleClass(card.article) : "";
  return (
    <>
      {card.article !== "none" && (
        <span className={articlePillClass(card.article)}>{articleLabel(card.article)}</span>
      )}
      <div className="face__termrow">
        <div className={`face__term ${tint}`}>{card.front}</div>
        <SpeakButton text={card.front} lang={lang} title={t("cardEditor.hearWord")} />
        <PronunciationCheck text={card.front} lang={lang} />
      </div>
    </>
  );
}

/** The front of a card (the recall prompt). Article-tinted for German nouns.
 * On a reverse vocab card the prompt is the meaning instead of the term. */
export function CardFront({ card }: { card: AnyCard }) {
  const { t } = useTranslation();
  const { user } = useAuth();
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
  const lang = cardLang(card, user?.learning_languages?.[0] ?? "");
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
            <GermanText text={card.front} lang={lang} genders={card.genders} />
          )}
        </div>
        <SpeakButton text={card.front} lang={lang} title={t("cardEditor.hearWord")} />
        <PronunciationCheck text={card.front} lang={lang} />
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
  const { t } = useTranslation();
  const { user } = useAuth();
  const lang = cardLang(card, user?.learning_languages?.[0] ?? "");
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
          <SpeakButton text={card.front} lang={lang} small title={t("cardEditor.hearPronunciation")} />
        </div>
      )}
      {"images" in card && card.images && card.images.length > 0 && (
        <div className="face__images">
          {card.images.map((im) => (
            <img key={im.id} className="face__img" src={im.url} alt="" loading="lazy" />
          ))}
        </div>
      )}
      {card.card_type === "vocab" && card.plural && (
        <div className="face__plural">
          plural: <span className="art-plural">{card.plural}</span>
          <SpeakButton text={card.plural} lang={lang} small title={t("cardEditor.hearPlural")} />
        </div>
      )}
      {card.notes && <div className="face__notes">{card.notes}</div>}
      {card.table && <GrammarTable table={card.table} />}
      {/* Not gated on card_type: conjugations that survive a type change should
        * stay visible rather than silently disappearing from the card. */}
      {card.conjugations?.length > 0 && (
        <ConjTable rows={card.conjugations} lang={lang} />
      )}
      {card.card_type === "sentence" && card.genders.length > 0 && (
        <CaseTable items={card.genders} />
      )}
      {card.example && (
        <div className="face__examplerow">
          <div className="face__example">
            <GermanText text={card.example} lang={lang} />
          </div>
          <SpeakButton text={card.example} lang={lang} small title={t("cardEditor.hearExample")} />
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
