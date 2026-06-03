import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  bulkCreateCards,
  fetchDecks,
  parseImport,
  type CardType,
  type Deck,
  type DraftCard,
} from "../auth/api";
import CardEditor from "../components/CardEditor";

type Stage = "input" | "review";

export default function ImportPage() {
  const navigate = useNavigate();
  const [stage, setStage] = useState<Stage>("input");
  const [decks, setDecks] = useState<Deck[]>([]);
  const [deckId, setDeckId] = useState<number | "">("");
  const [text, setText] = useState("");
  const [language, setLanguage] = useState<"de" | "en" | "">("");
  const [defaultType, setDefaultType] = useState<CardType>("vocab");
  const [drafts, setDrafts] = useState<DraftCard[]>([]);
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchDecks().then(setDecks);
  }, []);

  // Only leaf decks (no children) can hold cards.
  const leafDecks = useMemo(() => {
    const parents = new Set(decks.map((d) => d.parent).filter(Boolean));
    return decks.filter((d) => !parents.has(d.id));
  }, [decks]);

  const selectedDeck = decks.find((d) => d.id === deckId);

  async function onParse() {
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await parseImport({ text, language, default_type: defaultType });
      setDrafts(res.cards);
      setSource(res.source);
      setStage("review");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not parse text.");
    } finally {
      setBusy(false);
    }
  }

  function updateDraft(i: number, next: DraftCard) {
    setDrafts((d) => d.map((c, idx) => (idx === i ? next : c)));
  }

  function removeDraft(i: number) {
    setDrafts((d) => d.filter((_, idx) => idx !== i));
  }

  async function onProceed() {
    if (!deckId || drafts.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const res = await bulkCreateCards(Number(deckId), drafts);
      navigate(`/app/decks/${res.deck}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create cards.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="import">
      <div className="import__head">
        <h1>Import a book section</h1>
        <p className="import__sub">
          Paste text from Menschen or Oxford Word Skills. We turn it into draft
          cards you can edit before adding them to a deck.
        </p>
      </div>

      {error && <div className="panel panel--error">{error}</div>}

      {stage === "input" ? (
        <div className="import__input">
          <div className="import__controls">
            <label>
              Language
              <select className="input" value={language} onChange={(e) => setLanguage(e.target.value as any)}>
                <option value="">Auto / other</option>
                <option value="de">German</option>
                <option value="en">English</option>
              </select>
            </label>
            <label>
              Default type
              <select className="input" value={defaultType} onChange={(e) => setDefaultType(e.target.value as CardType)}>
                <option value="vocab">vocab</option>
                <option value="sentence">sentence</option>
                <option value="grammar">grammar</option>
              </select>
            </label>
          </div>
          <textarea
            className="import__textarea"
            placeholder={"Paste a word list or passage, e.g.\nder Tisch — table\ndie Lampe — lamp\nWie geht es Ihnen?"}
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={14}
          />
          <button className="btn btn--primary btn--lg" disabled={busy || !text.trim()} onClick={onParse}>
            {busy ? "Parsing…" : "Generate cards →"}
          </button>
        </div>
      ) : (
        <div className="import__review">
          <div className="import__reviewbar">
            <div>
              <strong>{drafts.length}</strong> draft cards
              <span className="import__source"> · via {source}</span>
            </div>
            <div className="import__commit">
              <select className="input" value={deckId} onChange={(e) => setDeckId(e.target.value ? Number(e.target.value) : "")}>
                <option value="">Choose a deck…</option>
                {leafDecks.map((d) => (
                  <option key={d.id} value={d.id}>{d.full_name}</option>
                ))}
              </select>
              <button className="btn btn--ghost" onClick={() => setStage("input")}>← Back</button>
              <button
                className="btn btn--primary"
                disabled={busy || !deckId || drafts.length === 0}
                onClick={onProceed}
              >
                Proceed — add {drafts.length} to {selectedDeck?.name ?? "deck"}
              </button>
            </div>
          </div>

          <ul className="import__list">
            {drafts.map((d, i) => (
              <li key={i} className="import__item">
                <CardEditor value={d} onChange={(next) => updateDraft(i, next)} compact />
                <button className="cardrow__del" onClick={() => removeDraft(i)}>✕</button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
