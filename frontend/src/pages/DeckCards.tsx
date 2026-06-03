import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  deleteCard,
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
                  <div className="cardrow__editactions">
                    <button className="btn btn--primary btn--sm" onClick={() => saveEdit(c.id)}>Save</button>
                    <button className="btn btn--ghost btn--sm" onClick={() => setEditing(null)}>Cancel</button>
                  </div>
                </div>
              ) : (
                <div className="cardrow__view" onClick={() => startEdit(c)}>
                  <span className="badge">{c.card_type}</span>
                  <span className="cardrow__front"><FrontText card={c} /></span>
                  <span className="cardrow__back">{c.back}</span>
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
