import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  answerCard,
  fetchStudyQueue,
  undoLastAnswer,
  type Card,
} from "../auth/api";
import { CardBack, CardFront } from "../components/CardFace";

type Rating = 1 | 2 | 3 | 4;

const RATING_META: { rating: Rating; label: string; key: string; cls: string }[] = [
  { rating: 1, label: "Again", key: "1", cls: "grade grade--again" },
  { rating: 2, label: "Hard", key: "2", cls: "grade grade--hard" },
  { rating: 3, label: "Good", key: "3", cls: "grade grade--good" },
  { rating: 4, label: "Easy", key: "4", cls: "grade grade--easy" },
];

export default function Study() {
  const { deckId } = useParams();
  const navigate = useNavigate();
  const [queue, setQueue] = useState<Card[]>([]);
  const [flipped, setFlipped] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [canUndo, setCanUndo] = useState(false);
  const shownAt = useRef<number>(Date.now());

  const id = Number(deckId);
  const current = queue[0];

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const q = await fetchStudyQueue(id);
      setQueue(q);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load cards.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    shownAt.current = Date.now();
  }, [current?.id, flipped]);

  const grade = useCallback(
    async (rating: Rating) => {
      if (!current || busy) return;
      setBusy(true);
      try {
        const updated = await answerCard(current.id, rating, Date.now() - shownAt.current);
        setCanUndo(true);
        setFlipped(false);
        setQueue((q) => {
          const rest = q.slice(1);
          // Learning/relearning cards come back later in the session.
          if (updated.state === "learning" || updated.state === "relearning") {
            return [...rest, updated];
          }
          return rest;
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not save answer.");
      } finally {
        setBusy(false);
      }
    },
    [current, busy],
  );

  const undo = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    try {
      const restored = await undoLastAnswer();
      setQueue((q) => [restored, ...q.filter((c) => c.id !== restored.id)]);
      setFlipped(false);
      setCanUndo(false);
    } catch {
      setCanUndo(false);
    } finally {
      setBusy(false);
    }
  }, [busy]);

  // When the working queue empties, try to pull more (learning steps may be due).
  useEffect(() => {
    if (!loading && queue.length === 0) {
      (async () => {
        const q = await fetchStudyQueue(id).catch(() => [] as Card[]);
        if (q.length) setQueue(q);
      })();
    }
  }, [queue.length, loading, id]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") return void navigate("/app");
      if (e.key === "u" || e.key === "U") return void undo();
      if (e.key === "e" || e.key === "E") {
        if (current) navigate(`/app/decks/${current.deck}`);
        return;
      }
      if (!current) return;
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
  }, [current, flipped, grade, undo, navigate]);

  const counts = {
    new: queue.filter((c) => c.state === "new").length,
    learning: queue.filter((c) => c.state === "learning" || c.state === "relearning").length,
    due: queue.filter((c) => c.state === "review").length,
  };

  if (loading) return <div className="study"><div className="panel">Loading…</div></div>;

  return (
    <div className="study">
      <header className="study__bar">
        <button className="btn btn--ghost btn--sm" onClick={() => navigate("/app")}>← Decks</button>
        <div className="study__progress">
          <span className="count count--new">{counts.new}</span>
          <span className="count count--learn">{counts.learning}</span>
          <span className="count count--due">{counts.due}</span>
        </div>
        <button className="btn btn--ghost btn--sm" onClick={undo} disabled={!canUndo}>
          ↶ Undo
        </button>
      </header>

      {error && <div className="panel panel--error">{error}</div>}

      {!current ? (
        <div className="study__done">
          <div className="study__done-emoji">🎉</div>
          <h2>All done for now</h2>
          <p>No more cards due in this deck. Come back later — or add more.</p>
          <button className="btn btn--primary" onClick={() => navigate("/app")}>Back to decks</button>
        </div>
      ) : (
        <div className="study__stage">
          <div className={`reviewcard ${flipped ? "is-flipped" : ""}`}>
            <CardFront card={current} />
            {flipped && <hr className="reviewcard__rule" />}
            {flipped && <CardBack card={current} />}
          </div>

          {!flipped ? (
            <button className="btn btn--primary btn--lg study__show" onClick={() => setFlipped(true)}>
              Show answer <kbd>Space</kbd>
            </button>
          ) : (
            <div className="grades">
              {RATING_META.map((m) => (
                <button
                  key={m.rating}
                  className={m.cls}
                  disabled={busy}
                  onClick={() => grade(m.rating)}
                >
                  <span className="grade__label">{m.label}</span>
                  <span className="grade__interval">{current.intervals?.[String(m.rating)] ?? ""}</span>
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
