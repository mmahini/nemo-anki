import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  addCardImage,
  deleteCard,
  deleteCardImage,
  fetchCards,
  fetchDecks,
  updateCard,
  type Card,
  type Deck,
  type DraftCard,
} from "../auth/api";
import CardEditor from "../components/CardEditor";
import GermanText from "../components/GermanText";
import { articleClass } from "../lib/article";

/** The card's front, coloured by gender where it makes sense, on one line. */
function FrontText({ card }: { card: Card }) {
  if (card.card_type === "vocab") {
    return <span className={articleClass(card.article)}>{card.front}</span>;
  }
  if (card.card_type === "sentence") {
    return <GermanText text={card.front} lang={card.language} genders={card.genders} />;
  }
  return <>{card.front}</>;
}

/** Manage a card's photos (shown on the answer side during review). */
function CardImages({ card, onChange }: { card: Card; onChange: () => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const images = card.images ?? [];

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (!files.length) return;
    setBusy(true);
    setErr(null);
    try {
      for (const f of files) await addCardImage(card.id, f);
      onChange();
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(imageId: number) {
    setBusy(true);
    try {
      await deleteCardImage(card.id, imageId);
      onChange();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="cardimages">
      <span className="cardimages__label">Photos (shown on the answer)</span>
      <div className="cardimages__grid">
        {images.map((im) => (
          <div key={im.id} className="cardimages__item">
            <img src={im.url} alt="" />
            <button type="button" className="cardimages__del" disabled={busy} onClick={() => remove(im.id)}>✕</button>
          </div>
        ))}
        <label className={`cardimages__add ${busy ? "is-busy" : ""}`}>
          {busy ? "…" : "+ Photo"}
          <input type="file" accept="image/*" multiple hidden onChange={onPick} disabled={busy} />
        </label>
      </div>
      {err && <p className="auth__error">{err}</p>}
    </div>
  );
}

function toDraft(c: Card): DraftCard {
  return {
    card_type: c.card_type,
    language: c.language as any,
    front: c.front,
    back: c.back,
    reading: c.reading,
    article: c.article,
    plural: c.plural,
    example: c.example,
    notes: c.notes,
    table: c.table,
    genders: c.genders,
    tags: c.tags,
  };
}

export default function DeckCards() {
  const { deckId } = useParams();
  const navigate = useNavigate();
  const id = Number(deckId);
  const [deck, setDeck] = useState<Deck | null>(null);
  const [cards, setCards] = useState<Card[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState<DraftCard | null>(null);

  async function load() {
    setLoading(true);
    const [decks, cs] = await Promise.all([fetchDecks(), fetchCards(id)]);
    setDeck(decks.find((d) => d.id === id) ?? null);
    setCards(cs);
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, [id]);

  function startEdit(c: Card) {
    setEditing(c.id);
    setDraft(toDraft(c));
  }

  async function saveEdit(cardId: number) {
    if (!draft) return;
    await updateCard(cardId, draft);
    setEditing(null);
    setDraft(null);
    load();
  }

  async function remove(cardId: number) {
    await deleteCard(cardId);
    load();
  }

  if (loading) return <div className="panel">Loading…</div>;

  return (
    <div className="browse">
      <div className="browse__head">
        <div>
          <button className="btn btn--ghost btn--sm" onClick={() => navigate("/app")}>← Decks</button>
          <h1>{deck?.full_name ?? "Deck"}</h1>
          <p className="browse__sub">{cards.length} cards</p>
        </div>
        <div className="browse__actions">
          <Link to={`/app/decks/${id}/add`} className="btn btn--ghost">+ Add card</Link>
          <button
            className="btn btn--primary"
            disabled={!deck || deck.counts.new + deck.counts.learning + deck.counts.due === 0}
            onClick={() => navigate(`/app/study/${id}`)}
          >
            Study
          </button>
        </div>
      </div>

      {cards.length === 0 ? (
        <div className="panel">
          No cards yet. <Link to={`/app/decks/${id}/add`}>Add one</Link> or use{" "}
          <Link to="/app/import">Import</Link>.
        </div>
      ) : (
        <ul className="cardrows">
          {cards.map((c) => (
            <li key={c.id} className="cardrow">
              {editing === c.id && draft ? (
                <div className="cardrow__edit">
                  <CardEditor value={draft} onChange={setDraft} />
                  <CardImages card={c} onChange={load} />
                  <div className="cardrow__editactions">
                    <button className="btn btn--primary btn--sm" onClick={() => saveEdit(c.id)}>Save</button>
                    <button className="btn btn--ghost btn--sm" onClick={() => setEditing(null)}>Cancel</button>
                  </div>
                </div>
              ) : (
                <div className="cardrow__view" onClick={() => startEdit(c)}>
                  <span className="badge">{c.card_type}</span>
                  {c.has_reverse && <span className="badge badge--rev" title="Reviewed both ways (term ⇄ meaning), tracked separately">⇄</span>}
                  {(c.images?.length ?? 0) > 0 && (
                    <img className="cardrow__thumb" src={c.images![0].url} alt="" title={`${c.images!.length} photo(s)`} />
                  )}
                  <span className="cardrow__front"><FrontText card={c} /></span>
                  <span className="cardrow__back" dir="auto">{c.back}</span>
                  <span className={`state state--${c.state}`}>{c.state}</span>
                  <button
                    className="cardrow__del"
                    onClick={(e) => {
                      e.stopPropagation();
                      remove(c.id);
                    }}
                  >
                    ✕
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
