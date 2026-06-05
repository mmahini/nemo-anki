import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { answerCard, fetchCardForReview, type Card } from "../auth/api";
import { CardBack, CardFront } from "../components/CardFace";
import { promptSpeech } from "../lib/cardSpeech";
import { speak } from "../lib/tts";

type Rating = 1 | 2 | 3 | 4;

const RATING_META: { rating: Rating; label: string; key: string; cls: string }[] = [
  { rating: 1, label: "Again", key: "1", cls: "grade grade--again" },
  { rating: 2, label: "Hard", key: "2", cls: "grade grade--hard" },
  { rating: 3, label: "Good", key: "3", cls: "grade grade--good" },
  { rating: 4, label: "Easy", key: "4", cls: "grade grade--easy" },
];

/** Study a single card on its own (the per-card Review button). */
export default function StudyCard() {
  const { cardId } = useParams();
  const navigate = useNavigate();
  const id = Number(cardId);
  const [card, setCard] = useState<Card | null>(null);
  const [flipped, setFlipped] = useState(false);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const shownAt = useRef<number>(Date.now());

  useEffect(() => {
    fetchCardForReview(id)
      .then((c) => {
        setCard(c);
        shownAt.current = Date.now();
        const s = promptSpeech(c); // auto-read the front aloud
        if (s) speak(s.text, s.lang);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Couldn't load the card."))
      .finally(() => setLoading(false));
  }, [id]);

  const back = useCallback(() => {
    navigate(card ? `/app/decks/${card.deck}` : "/app");
  }, [navigate, card]);

  const grade = useCallback(
    async (rating: Rating) => {
      if (!card || busy) return;
      setBusy(true);
      try {
        await answerCard(card.id, rating, Date.now() - shownAt.current);
        setDone(true);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not save answer.");
      } finally {
        setBusy(false);
      }
    },
    [card, busy],
  );

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
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
  }, [card, flipped, done, grade, back]);

  if (loading) return <div className="study"><div className="panel">Loading…</div></div>;

  return (
    <div className="study">
      <header className="study__bar">
        <button className="btn btn--ghost btn--sm" onClick={back}>← Deck</button>
        <span className="study__progress"><span className="count count--due">single card</span></span>
        <span />
      </header>

      {error && <div className="panel panel--error">{error}</div>}

      {done || !card ? (
        <div className="study__done">
          <div className="study__done-emoji">✅</div>
          <h2>Card reviewed</h2>
          <p>Its schedule has been updated.</p>
          <button className="btn btn--primary" onClick={back}>Back to deck</button>
        </div>
      ) : (
        <div className="study__stage">
          <div className={`reviewcard ${flipped ? "is-flipped" : ""}`}>
            <CardFront card={card} />
            {flipped && <hr className="reviewcard__rule" />}
            {flipped && <CardBack card={card} />}
          </div>

          {!flipped ? (
            <button className="btn btn--primary btn--lg study__show" onClick={() => setFlipped(true)}>
              Show answer <kbd>Space</kbd>
            </button>
          ) : (
            <div className="grades">
              {RATING_META.map((m) => (
                <button key={m.rating} className={m.cls} disabled={busy} onClick={() => grade(m.rating)}>
                  <span className="grade__label">{m.label}</span>
                  <span className="grade__interval">{card.intervals?.[String(m.rating)] ?? ""}</span>
                  <kbd>{m.key}</kbd>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
