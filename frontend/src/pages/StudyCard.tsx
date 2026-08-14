import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { answerCard, colourizeCard, fetchCardForReview, findCardImage, type Card } from "../auth/api";
import { CardBack, CardFront } from "../components/CardFace";
import CardEditModal from "../components/CardEditModal";
import { promptSpeech } from "../lib/cardSpeech";
import { CARD_IMAGE_SEARCH_ENABLED } from "../lib/features";
import { speak } from "../lib/tts";

type Rating = 1 | 2 | 3 | 4;

const RATING_KEYS: { rating: Rating; key: string; cls: string }[] = [
  { rating: 1, key: "study.again", cls: "grade grade--again" },
  { rating: 2, key: "study.hard", cls: "grade grade--hard" },
  { rating: 3, key: "study.good", cls: "grade grade--good" },
  { rating: 4, key: "study.easy", cls: "grade grade--easy" },
];

/** Study a single card on its own (the per-card Review button). */
export default function StudyCard() {
  const { cardId } = useParams();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const id = Number(cardId);
  const [card, setCard] = useState<Card | null>(null);
  const [flipped, setFlipped] = useState(false);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const shownAt = useRef<number>(Date.now());

  useEffect(() => {
    fetchCardForReview(id)
      .then((c) => {
        setCard(c);
        shownAt.current = Date.now();
        const s = promptSpeech(c);
        if (s) speak(s.text, s.lang, { auto: true });
      })
      .catch((e) => setError(e instanceof Error ? e.message : t("common.error")))
      .finally(() => setLoading(false));
  }, [id]);

  const back = useCallback(() => {
    navigate(card ? `/app/decks/${card.deck}` : "/app");
  }, [navigate, card]);

  async function colourise() {
    if (!card || busy) return;
    setBusy(true);
    try {
      const u = await colourizeCard(card.id);
      setCard({ ...card, article: u.article, genders: u.genders, language: u.language });
    } finally {
      setBusy(false);
    }
  }

  async function findImage() {
    if (!card || busy) return;
    setBusy(true);
    try {
      const img = await findCardImage(card.id);
      setCard({ ...card, images: [...(card.images ?? []), img] });
    } catch {
      /* no image found */
    } finally {
      setBusy(false);
    }
  }

  const grade = useCallback(
    async (rating: Rating) => {
      if (!card || busy) return;
      setBusy(true);
      try {
        await answerCard(card.id, rating, Date.now() - shownAt.current);
        setDone(true);
      } catch (e) {
        setError(e instanceof Error ? e.message : t("common.error"));
      } finally {
        setBusy(false);
      }
    },
    [card, busy],
  );

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (editing) return;
      if (e.key === "Escape") return back();
      if (done || !card) return;
      if (!flipped) {
        if (e.key === " " || e.key === "Enter") {
          e.preventDefault();
          setFlipped(true);
        }
        return;
      }
      if (e.key === " " || e.key === "Enter") {
        e.preventDefault();
        void grade(3);
      } else if (["1", "2", "3", "4"].includes(e.key)) {
        void grade(Number(e.key) as Rating);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [card, flipped, done, grade, back, editing]);

  if (loading) return <div className="study"><div className="panel">{t("study.loading")}</div></div>;

  return (
    <div className="study">
      <header className="study__bar">
        <button className="btn btn--ghost btn--sm" onClick={back}>{t("studyCard.backBtn")}</button>
        <span className="study__progress"><span className="count count--due">{t("studyCard.singleCard")}</span></span>
        <span />
      </header>

      {error && <div className="panel panel--error">{error}</div>}

      {done || !card ? (
        <div className="study__done">
          <div className="study__done-emoji">✅</div>
          <h2>{t("studyCard.done")}</h2>
          <p>{t("studyCard.doneHint")}</p>
          <button className="btn btn--primary" onClick={back}>{t("studyCard.backToDeck")}</button>
        </div>
      ) : (
        <div className="study__stage">
          <div className="cardtools">
            <button className="cardtools__btn" title={t("review.colourise")} disabled={busy} onClick={colourise}>🎨</button>
            {CARD_IMAGE_SEARCH_ENABLED && (
              <button className="cardtools__btn" title={t("review.findImage")} disabled={busy} onClick={findImage}>🖼️</button>
            )}
            <button className="cardtools__btn" title={t("review.editCard")} onClick={() => setEditing(true)}>✎</button>
          </div>
          <div className={`reviewcard ${flipped ? "is-flipped" : ""}`}>
            <CardFront card={card} />
            {flipped && <hr className="reviewcard__rule" />}
            {flipped && <CardBack card={card} />}
          </div>

          {/* Pinned to the bottom of the viewport — see Study.tsx. */}
          <div className="reviewbar">
            {!flipped ? (
              <button className="btn btn--primary btn--lg study__show" onClick={() => setFlipped(true)}>
                {t("study.showAnswer")} <kbd>{t("review.spaceKey")}</kbd>
              </button>
            ) : (
              <div className="grades">
                {RATING_KEYS.map((m) => (
                  <button key={m.rating} className={m.cls} disabled={busy} onClick={() => grade(m.rating)}>
                    <span className="grade__label">{t(m.key)}</span>
                    <span className="grade__interval">{card.intervals?.[String(m.rating)] ?? ""}</span>
                    <kbd>{m.rating}</kbd>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {editing && card && (
        <CardEditModal
          card={card}
          onClose={() => setEditing(false)}
          onSaved={(u) => setCard((c) => (c ? { ...u, intervals: c.intervals } : u))}
        />
      )}
    </div>
  );
}
