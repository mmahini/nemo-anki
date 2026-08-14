import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  autotypeDeck,
  colourizeCard,
  colourizeDeck,
  deleteCard,
  findCardImage,
  fetchCards,
  fetchDecks,
  generateMnemonic,
  updateCard,
  type Card,
  type CardType,
  type Deck,
  type DraftCard,
} from "../auth/api";

import CardEditor from "../components/CardEditor";
import CardImages from "../components/CardImages";
import GermanText from "../components/GermanText";
import { articleClass } from "../lib/article";
import { CARD_TYPES } from "../lib/cardTypes";
import { CARD_IMAGE_SEARCH_ENABLED } from "../lib/features";

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
    conjugations: c.conjugations ?? [],
    tags: c.tags,
  };
}

const PAGE_SIZE = 25;

export default function DeckCards() {
  const { deckId } = useParams();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const id = Number(deckId);
  const [deck, setDeck] = useState<Deck | null>(null);
  const [cards, setCards] = useState<Card[]>([]);
  const [count, setCount] = useState(0);
  const [numPages, setNumPages] = useState(1);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState<DraftCard | null>(null);
  const [typePanel, setTypePanel] = useState(false);
  const [colourBusy, setColourBusy] = useState(false);
  const [colourMsg, setColourMsg] = useState<string | null>(null);
  const [autoBusy, setAutoBusy] = useState(false);
  const [colourCard, setColourCard] = useState<number | null>(null);
  const [findCard, setFindCard] = useState<number | null>(null);
  const [mnemonicCard, setMnemonicCard] = useState<number | null>(null);

  useEffect(() => {
    setPage(1);
    setQuery("");
    setSearch("");
  }, [id]);

  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(query.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [query]);

  const load = useCallback(async () => {
    setLoading(true);
    const [decks, res] = await Promise.all([
      fetchDecks(),
      fetchCards(id, { page, pageSize: PAGE_SIZE, q: search || undefined }),
    ]);
    setDeck(decks.find((d) => d.id === id) ?? null);
    if (res.results.length === 0 && res.count > 0 && page > 1) {
      setPage((p) => Math.max(1, Math.min(p - 1, res.num_pages)));
      return;
    }
    setCards(res.results);
    setCount(res.count);
    setNumPages(res.num_pages || 1);
    setLoading(false);
  }, [id, page, search]);

  useEffect(() => {
    load();
  }, [load]);

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
      await load();
    } catch {
      window.alert(t("common.error"));
    } finally {
      setFindCard(null);
    }
  }

  async function mnemonicOne(card: Card) {
    if (card.mnemonic) {
      window.alert(card.mnemonic);
      return;
    }
    setMnemonicCard(card.id);
    try {
      const updated = await generateMnemonic(card.id);
      setCards((cs) => cs.map((c) => (c.id === card.id ? updated : c)));
      window.alert(updated.mnemonic || t("common.error"));
    } catch (err) {
      window.alert(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setMnemonicCard(null);
    }
  }

  async function changeType(cardId: number, type: CardType) {
    setCards((cs) => cs.map((c) => (c.id === cardId ? { ...c, card_type: type } : c)));
    await updateCard(cardId, { card_type: type });
  }

  async function setAllTypes(type: CardType) {
    const targets = cards.filter((c) => c.card_type !== type);
    if (!targets.length || !window.confirm(`Set the ${targets.length} listed card(s) to "${type}"?`)) return;
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
    setColourMsg(t("deckCards.colouring"));
    try {
      let total = 0;
      for (let i = 0; i < 400; i++) {
        const res = await colourizeDeck(id);
        total += res.colourized;
        setColourMsg(`${t("deckCards.colouring")} ${total} done${res.remaining ? `, ~${res.remaining} left` : ""}`);
        if (res.remaining === 0 || res.colourized === 0) break;
      }
      setColourMsg(
        total
          ? `🎨 Coloured ${total} card(s) — articles for vocab, noun genders for sentences.`
          : t("deckCards.nothingToColour"),
      );
      await load();
    } catch (e) {
      setColourMsg(e instanceof Error ? e.message : t("common.error"));
    } finally {
      setColourBusy(false);
    }
  }

  if (loading && !deck) return <div className="panel">{t("deckCards.loading")}</div>;

  return (
    <div className="browse">
      <div className="browse__head">
        <div>
          <button className="btn btn--ghost btn--sm" onClick={() => navigate("/app/decks")}>{t("decks.backBtn")}</button>
          <h1>{deck?.full_name ?? "Deck"}</h1>
          <p className="browse__sub">{t("deckCards.cardCount", { count })}</p>
        </div>
        <div className="browse__actions">
          <Link to={`/app/decks/${id}/add`} className="btn btn--ghost">{t("deckCards.addCard")}</Link>
          <button className={`btn btn--ghost ${typePanel ? "btn--on" : ""}`} onClick={() => setTypePanel((v) => !v)}>
            {t("deckCards.cardTypes")}
          </button>
          <button className="btn btn--ghost" onClick={colourise} disabled={colourBusy} title="Run German gender colouring on every sentence/grammar card in this deck">
            {colourBusy ? t("deckCards.colouring") : t("deckCards.colouringBtn")}
          </button>
          <button
            className="btn btn--primary"
            disabled={!deck || deck.counts.new + deck.counts.learning + deck.counts.due === 0}
            onClick={() => navigate(`/app/study/${id}`)}
          >
            {t("deckCards.studyBtn")}
          </button>
        </div>
      </div>

      {(count > 0 || search) && (
        <div className="browse__search">
          <input
            className="input"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("deckCards.searchPlaceholder")}
            aria-label={t("deckCards.searchPlaceholder")}
          />
          {search && (
            <span className="browse__searchcount">
              {t("deckCards.searchResults_other", { count })}
            </span>
          )}
        </div>
      )}

      {colourMsg && <div className="panel browse__note">{colourMsg}</div>}

      {typePanel && cards.length > 0 && (
        <div className="panel typepanel">
          <div className="typepanel__bar">
            <strong>{t("deckCards.cardTypes")}</strong>
            <div className="typepanel__tools">
              <button className="btn btn--primary btn--sm" onClick={autoDetectTypes} disabled={autoBusy} title={t("deckCards.autotypeTitle")}>
                {autoBusy ? t("deckCards.detecting") : t("deckCards.autoDetect")}
              </button>
              <label className="typepanel__all">
                {t("deckCards.setAllTo")}
                <select className="input input--sm" defaultValue="" onChange={(e) => { if (e.target.value) { setAllTypes(e.target.value as CardType); e.target.value = ""; } }}>
                  <option value="">…</option>
                  {CARD_TYPES.map((tp) => <option key={tp} value={tp}>{tp}</option>)}
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
                  {CARD_TYPES.map((tp) => <option key={tp} value={tp}>{tp}</option>)}
                </select>
              </li>
            ))}
          </ul>
        </div>
      )}

      {cards.length === 0 ? (
        search ? (
          <div className="panel">{t("deckCards.noMatch", { search })}</div>
        ) : (
          <div className="panel">
            {t("deckCards.noCards")} <Link to={`/app/decks/${id}/add`}>{t("deckCards.addCard")}</Link> or use{" "}
            <Link to="/app/import">{t("import.title")}</Link>.
          </div>
        )
      ) : (
        <ul className="cardrows">
          {cards.map((c) => (
            <li key={c.id} className="cardrow">
              {editing === c.id && draft ? (
                <div className="cardrow__edit">
                  <CardEditor value={draft} onChange={setDraft} />
                  <CardImages card={c} onChange={load} />
                  <div className="cardrow__editactions">
                    <button className="btn btn--primary btn--sm" onClick={() => saveEdit(c.id)}>{t("deckCards.saveBtn")}</button>
                    <button className="btn btn--ghost btn--sm" onClick={() => setEditing(null)}>{t("deckCards.cancelBtn")}</button>
                  </div>
                </div>
              ) : (
                <div className="cardrow__view" onClick={() => startEdit(c)}>
                  <span className="badge">{c.card_type}</span>
                  {c.has_reverse && <span className="badge badge--rev" title={t("deckCards.bothWaysTitle")}>⇄</span>}
                  {(c.images?.length ?? 0) > 0 && (
                    <img className="cardrow__thumb" src={c.images![0].url} alt="" title={`${c.images!.length} photo(s)`} />
                  )}
                  <span className="cardrow__front"><FrontText card={c} /></span>
                  <span className="cardrow__back" dir="auto">{c.back}</span>
                  <span className={`state state--${c.state}`}>{c.state}</span>
                  <button
                    className="cardrow__review"
                    title={t("deckCards.reviewBtn")}
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(`/app/study/card/${c.id}`);
                    }}
                  >
                    {t("deckCards.reviewBtn")}
                  </button>
                  {CARD_IMAGE_SEARCH_ENABLED && c.card_type === "vocab" && (
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
                    title={t("deckCards.colouriseCardTitle")}
                    disabled={colourCard === c.id}
                    onClick={(e) => {
                      e.stopPropagation();
                      colouriseOne(c.id);
                    }}
                  >
                    {colourCard === c.id ? "…" : "🎨"}
                  </button>
                  <button
                    className="cardrow__colour"
                    title={c.mnemonic ? t("deckCards.mnemonicShowTitle") : t("deckCards.mnemonicCardTitle")}
                    disabled={mnemonicCard === c.id}
                    onClick={(e) => {
                      e.stopPropagation();
                      mnemonicOne(c);
                    }}
                  >
                    {mnemonicCard === c.id ? "…" : "🧠"}
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

      {numPages > 1 && (
        <div className="pager">
          <button
            className="btn btn--ghost btn--sm"
            disabled={page <= 1 || loading}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            {t("deckCards.prevBtn")}
          </button>
          <span className="pager__info">
            {t("deckCards.pageInfo", { page, total: numPages })}
          </span>
          <button
            className="btn btn--ghost btn--sm"
            disabled={page >= numPages || loading}
            onClick={() => setPage((p) => Math.min(numPages, p + 1))}
          >
            {t("deckCards.nextBtn")}
          </button>
        </div>
      )}
    </div>
  );
}
