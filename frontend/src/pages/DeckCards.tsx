import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  autotypeDeck,
  colourizeCard,
  colourizeDeck,
  deleteCard,
  findCardImage,
  fetchCards,
  fetchDecks,
  updateCard,
  type Card,
  type CardType,
  type Deck,
  type DraftCard,
} from "../auth/api";

const CARD_TYPES: CardType[] = ["vocab", "sentence", "grammar"];
import CardEditor from "../components/CardEditor";
import CardImages from "../components/CardImages";
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
  const [typePanel, setTypePanel] = useState(false);
  const [colourBusy, setColourBusy] = useState(false);
  const [colourMsg, setColourMsg] = useState<string | null>(null);
  const [autoBusy, setAutoBusy] = useState(false);
  const [colourCard, setColourCard] = useState<number | null>(null);
  const [findCard, setFindCard] = useState<number | null>(null);

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

  async function colouriseOne(cardId: number) {
    setColourCard(cardId);
    try {
      const updated = await colourizeCard(cardId);
      setCards((cs) => cs.map((c) => (c.id === cardId ? updated : c)));
    } finally {
      setColourCard(null);
    }
  }

  async function findImageOne(cardId: number) {
    setFindCard(cardId);
    try {
      await findCardImage(cardId);
      await load(); // refresh — regenerate replaces the previous auto image
    } catch {
      window.alert("Couldn't find an image for this card.");
    } finally {
      setFindCard(null);
    }
  }

  async function changeType(cardId: number, type: CardType) {
    setCards((cs) => cs.map((c) => (c.id === cardId ? { ...c, card_type: type } : c)));
    await updateCard(cardId, { card_type: type });
  }

  async function setAllTypes(type: CardType) {
    const targets = cards.filter((c) => c.card_type !== type);
    if (!targets.length || !window.confirm(`Set all ${targets.length} card(s) to "${type}"?`)) return;
    setCards((cs) => cs.map((c) => ({ ...c, card_type: type })));
    for (const c of targets) await updateCard(c.id, { card_type: type });
  }

  async function autoDetectTypes() {
    setAutoBusy(true);
    try {
      const res = await autotypeDeck(id);
      await load();
      window.alert(
        `Auto-detected types: ${res.changed} changed.\n` +
          `vocab ${res.counts.vocab ?? 0} · sentence ${res.counts.sentence ?? 0} · grammar ${res.counts.grammar ?? 0}`,
      );
    } finally {
      setAutoBusy(false);
    }
  }

  async function colourise() {
    setColourBusy(true);
    setColourMsg("Colourising…");
    try {
      let total = 0;
      // Process batch after batch until nothing colourable remains.
      for (let i = 0; i < 400; i++) {
        const res = await colourizeDeck(id);
        total += res.colourized;
        setColourMsg(`Colourising… ${total} done${res.remaining ? `, ~${res.remaining} left` : ""}`);
        if (res.remaining === 0 || res.colourized === 0) break;
      }
      setColourMsg(
        total
          ? `🎨 Coloured ${total} card(s) — articles for vocab, noun genders for sentences.`
          : "Nothing to colour — cards already coloured, or no German nouns detected.",
      );
      await load();
    } catch (e) {
      setColourMsg(e instanceof Error ? e.message : "Colourise failed.");
    } finally {
      setColourBusy(false);
    }
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
          <button className={`btn btn--ghost ${typePanel ? "btn--on" : ""}`} onClick={() => setTypePanel((v) => !v)}>
            Card types
          </button>
          <button className="btn btn--ghost" onClick={colourise} disabled={colourBusy} title="Run German gender colouring on every sentence/grammar card in this deck">
            {colourBusy ? "🎨 Colourising…" : "🎨 Colourise German"}
          </button>
          <button
            className="btn btn--primary"
            disabled={!deck || deck.counts.new + deck.counts.learning + deck.counts.due === 0}
            onClick={() => navigate(`/app/study/${id}`)}
          >
            Study
          </button>
        </div>
      </div>

      {colourMsg && <div className="panel browse__note">{colourMsg}</div>}

      {typePanel && cards.length > 0 && (
        <div className="panel typepanel">
          <div className="typepanel__bar">
            <strong>Card types</strong>
            <div className="typepanel__tools">
              <button className="btn btn--primary btn--sm" onClick={autoDetectTypes} disabled={autoBusy} title="Check every card and set its type automatically from its content">
                {autoBusy ? "Detecting…" : "✨ Auto-detect types"}
              </button>
              <label className="typepanel__all">
                Set all to
                <select className="input input--sm" defaultValue="" onChange={(e) => { if (e.target.value) { setAllTypes(e.target.value as CardType); e.target.value = ""; } }}>
                  <option value="">…</option>
                  {CARD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </label>
            </div>
          </div>
          <ul className="typepanel__list">
            {cards.map((c) => (
              <li key={c.id} className="typepanel__row">
                <span className="typepanel__front"><FrontText card={c} /></span>
                <select
                  className={`input input--sm cardtype cardtype--${c.card_type}`}
                  value={c.card_type}
                  onChange={(e) => changeType(c.id, e.target.value as CardType)}
                >
                  {CARD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </li>
            ))}
          </ul>
        </div>
      )}

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
                    className="cardrow__review"
                    title="Review just this card"
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(`/app/study/card/${c.id}`);
                    }}
                  >
                    ▶ Review
                  </button>
                  {c.card_type === "vocab" && (
                    <button
                      className="cardrow__colour"
                      title={(c.images?.length ?? 0) > 0 ? "Find a different image (regenerate)" : "Auto-find an image for this card"}
                      disabled={findCard === c.id}
                      onClick={(e) => {
                        e.stopPropagation();
                        findImageOne(c.id);
                      }}
                    >
                      {findCard === c.id ? "…" : "🖼️"}
                    </button>
                  )}
                  <button
                    className="cardrow__colour"
                    title="Colourise this card (German article / noun genders)"
                    disabled={colourCard === c.id}
                    onClick={(e) => {
                      e.stopPropagation();
                      colouriseOne(c.id);
                    }}
                  >
                    {colourCard === c.id ? "…" : "🎨"}
                  </button>
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
