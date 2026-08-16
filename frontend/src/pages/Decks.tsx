import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  createDeck,
  deleteDeck,
  fetchDecks,
  fetchSharedDecks,
  importDeck,
  shareDeck,
  unshareDeck,
  updateDeck,
  type Deck,
} from "../auth/api";
import Modal from "../components/Modal";

/* Root cards get a stable accent colour: the deck's own colour when set,
 * otherwise picked from the palette by name so it survives reloads. */
const ACCENTS = ["#4c6ef5", "#12b886", "#e8590c", "#7048e8", "#1098ad", "#e64980", "#f59f00", "#37b24d"];
function accentFor(d: Deck): string {
  if (d.color) return d.color;
  let h = 0;
  for (const ch of d.name) h = (h * 31 + ch.charCodeAt(0)) % 997;
  return ACCENTS[h % ACCENTS.length];
}

export default function Decks() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [decks, setDecks] = useState<Deck[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [newLang, setNewLang] = useState<"de" | "en" | "">("");
  const [newParent, setNewParent] = useState<number | "">("");
  const [adding, setAdding] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [movingDeck, setMovingDeck] = useState<number | null>(null);
  const [langDeck, setLangDeck] = useState<number | null>(null);
  const [renamingDeck, setRenamingDeck] = useState<number | null>(null);
  const [renameVal, setRenameVal] = useState("");
  const [openMenu, setOpenMenu] = useState<number | null>(null);
  const [menuPos, setMenuPos] = useState<{ top: number; right: number } | null>(null);
  const [sharedDecks, setSharedDecks] = useState<Deck[]>([]);
  const [importingId, setImportingId] = useState<number | null>(null);
  const [sharingDeck, setSharingDeck] = useState<number | null>(null);
  const [shareEmail, setShareEmail] = useState("");
  const [sharing, setSharing] = useState(false);
  const [shareError, setShareError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [mine, shared] = await Promise.all([fetchDecks(), fetchSharedDecks()]);
      setDecks(mine);
      setSharedDecks(shared);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  /** Open the add-deck sheet, optionally pre-filling the parent (from a card's
   * "add sub-deck" action) so nesting doesn't need re-picking. */
  function openAdd(parent: number | "" = "") {
    setNewName("");
    setNewLang("");
    setNewParent(parent);
    setCreateError(null);
    setAdding(true);
  }

  async function onCreate() {
    if (!newName.trim() || creating) return;
    const parent = newParent === "" ? null : newParent;
    const parentLang = decks.find((d) => d.id === parent)?.language ?? "";
    setCreating(true);
    setCreateError(null);
    try {
      await createDeck({ name: newName.trim(), parent, language: newLang || parentLang });
      setAdding(false);
      setNewName("");
      load();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setCreating(false);
    }
  }

  async function onMove(d: Deck, parent: number | null) {
    setMovingDeck(null);
    try {
      await updateDeck(d.id, { parent });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    }
  }

  async function onRename(d: Deck) {
    const name = renameVal.trim();
    setRenamingDeck(null);
    if (!name || name === d.name) return;
    try {
      await updateDeck(d.id, { name });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    }
  }

  async function onSetLang(d: Deck, language: "de" | "en" | "") {
    setLangDeck(null);
    if (language === (d.language ?? "")) return;
    try {
      await updateDeck(d.id, { language });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    }
  }

  function parentOptions(d: Deck): Deck[] {
    const banned = new Set(
      decks.filter((x) => x.id === d.id || x.full_name.startsWith(d.full_name + "::")).map((x) => x.id),
    );
    return decks.filter((x) => !banned.has(x.id)).sort((a, b) => a.full_name.localeCompare(b.full_name));
  }

  async function onDelete(d: Deck) {
    const childCount = decks.filter((x) => x.full_name.startsWith(d.full_name + "::")).length;
    const msg = childCount
      ? t("decks.confirmDeleteWithChildren", { name: d.full_name, count: childCount })
      : t("decks.confirmDelete", { name: d.full_name });
    if (!window.confirm(msg)) return;
    await deleteDeck(d.id);
    load();
  }

  function openShare(id: number) {
    setShareEmail("");
    setShareError(null);
    setSharingDeck(id);
  }

  async function onShare() {
    if (sharingDeck == null || !shareEmail.trim() || sharing) return;
    setSharing(true);
    setShareError(null);
    try {
      const updated = await shareDeck(sharingDeck, shareEmail.trim());
      setDecks((ds) => ds.map((d) => (d.id === updated.id ? updated : d)));
      setShareEmail("");
    } catch (err) {
      setShareError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setSharing(false);
    }
  }

  async function onUnshare(email: string) {
    if (sharingDeck == null) return;
    const updated = await unshareDeck(sharingDeck, email);
    setDecks((ds) => ds.map((d) => (d.id === updated.id ? updated : d)));
  }

  async function onImport(d: Deck) {
    setImportingId(d.id);
    try {
      const res = await importDeck(d.id);
      navigate(`/app/decks/${res.deck}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setImportingId(null);
    }
  }

  if (loading) return <div className="panel">{t("decks.loading")}</div>;
  if (error) return <div className="panel panel--error">{error}</div>;

  const roots = decks.filter((d) => d.parent === null);

  return (
    <div className="decks">
      <div className="decks__head">
        <h1>{t("decks.title")}</h1>
        <div className="decks__headtools">
          <div className="legend">
            <span className="legend__item"><i className="dot dot--new" /> {t("decks.legend.new")}</span>
            <span className="legend__item"><i className="dot dot--learn" /> {t("decks.legend.learning")}</span>
            <span className="legend__item"><i className="dot dot--due" /> {t("decks.legend.due")}</span>
          </div>
          <div className="decks__actions">
            <button className="btn btn--primary btn--sm" onClick={() => openAdd()}>
              {t("decks.addBtn")}
            </button>
          </div>
        </div>
      </div>

      {sharedDecks.length > 0 && (
        <div className="panel decks__shared">
          <h2>{t("decks.sharedWithMe", { count: sharedDecks.length })}</h2>
          <ul className="decklist">
            {sharedDecks.map((d) => (
              <li key={d.id} className="decklist__row">
                <div className="decklist__name">
                  <span className="twisty twisty--leaf" />
                  {d.language && <span className={`flag flag--${d.language}`}>{d.language}</span>}
                  <span>
                    {d.name}
                    <span className="decklist__sharedby"> {t("decks.sharedBy", { email: d.owner_email })}</span>
                  </span>
                </div>
                <div className="decklist__actions">
                  <span className="decklist__cardcount">{t("decks.cardCount", { count: d.card_count })}</span>
                  <button
                    className="btn btn--primary btn--sm"
                    disabled={importingId === d.id}
                    onClick={() => onImport(d)}
                  >
                    {importingId === d.id ? t("decks.importing") : t("decks.importBtn")}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <ul className="deckgrid">
        {roots.map((d) => {
          const subCount = decks.filter((x) => x.full_name.startsWith(d.full_name + "::")).length;
          const studyable = d.counts.new + d.counts.learning + d.counts.due;
          return (
            <li key={d.id} className="deckcard" style={{ "--deck-accent": accentFor(d) } as React.CSSProperties}>
              <Link to={`/app/decks/${d.id}`} className="deckcard__main">
                <div className="deckcard__toprow">
                  {d.language ? (
                    <span className={`flag flag--${d.language}`}>{d.language}</span>
                  ) : (
                    <span className="deckcard__dot" />
                  )}
                  <span className="deckcard__meta">
                    {t("decks.cardCount", { count: d.card_count })}
                    {subCount > 0 && <> · {t("decks.subdeckCount", { count: subCount })}</>}
                  </span>
                </div>
                {renamingDeck === d.id ? (
                  <input
                    className="input input--sm decklist__rename"
                    autoFocus
                    value={renameVal}
                    onClick={(e) => e.preventDefault()}
                    onChange={(e) => setRenameVal(e.target.value)}
                    onBlur={() => onRename(d)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") onRename(d);
                      if (e.key === "Escape") setRenamingDeck(null);
                    }}
                  />
                ) : (
                  <h2 className="deckcard__name">{d.name}</h2>
                )}
              </Link>
              <div className="deckcard__foot">
                {langDeck === d.id ? (
                  <select
                    className="input input--sm"
                    autoFocus
                    defaultValue={d.language || ""}
                    onChange={(e) => onSetLang(d, e.target.value as "de" | "en" | "")}
                    onBlur={() => setLangDeck(null)}
                  >
                    <option value="">{t("decks.noLanguage")}</option>
                    <option value="de">{t("common.german")}</option>
                    <option value="en">{t("common.english")}</option>
                  </select>
                ) : movingDeck === d.id ? (
                  <select
                    className="input input--sm"
                    autoFocus
                    defaultValue={d.parent ?? ""}
                    onChange={(e) => onMove(d, e.target.value ? Number(e.target.value) : null)}
                    onBlur={() => setMovingDeck(null)}
                  >
                    <option value="">{t("decks.moveTop")}</option>
                    {parentOptions(d).map((p) => (
                      <option key={p.id} value={p.id}>{t("decks.under", { name: p.full_name })}</option>
                    ))}
                  </select>
                ) : (
                  <>
                    <div className="decklist__counts">
                      <span className="count count--new">{d.counts.new}</span>
                      <span className="count count--learn">{d.counts.learning}</span>
                      <span className="count count--due">{d.counts.due}</span>
                    </div>
                    <div className="decklist__actions">
                      <button
                        className="btn btn--primary btn--sm"
                        disabled={studyable === 0}
                        onClick={() => navigate(`/app/study/${d.id}`)}
                      >
                        {t("decks.studyBtn")}
                      </button>
                      <div className="deckmenu-wrap">
                        <button
                          className="btn btn--ghost btn--sm deckmenu-btn"
                          aria-label={t("decks.moreActions")}
                          onClick={(e) => {
                            if (openMenu === d.id) return setOpenMenu(null);
                            const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
                            setMenuPos({ top: r.bottom + 6, right: Math.max(8, window.innerWidth - r.right) });
                            setOpenMenu(d.id);
                          }}
                        >
                          ⋯
                        </button>
                        {openMenu === d.id && menuPos && (
                          <>
                            <div className="menu-overlay" onClick={() => setOpenMenu(null)} />
                            <div className="deckmenu" style={{ top: menuPos.top, right: menuPos.right }}>
                              <button onClick={() => { setOpenMenu(null); setRenameVal(d.name); setRenamingDeck(d.id); }}>{t("decks.rename")}</button>
                              <button onClick={() => { setOpenMenu(null); setLangDeck(d.id); }}>{t("decks.language")}{d.language ? ` (${d.language.toUpperCase()})` : ""}</button>
                              <button onClick={() => { setOpenMenu(null); setMovingDeck(d.id); }}>{t("decks.move")}</button>
                              <button onClick={() => { setOpenMenu(null); openAdd(d.id); }}>{t("decks.addSubdeck")}</button>
                              {subCount === 0 && <button onClick={() => { setOpenMenu(null); navigate(`/app/decks/${d.id}/add`); }}>{t("decks.addCard")}</button>}
                              <button onClick={() => { setOpenMenu(null); openShare(d.id); }}>{t("decks.shareBtn")}</button>
                              <button className="deckmenu__danger" onClick={() => { setOpenMenu(null); onDelete(d); }}>{t("decks.delete")}</button>
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  </>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      {decks.length === 0 && (
        <div className="panel decks__empty">
          <h2>{t("decks.noDecks")}</h2>
          <p>{t("decks.noDecksHint")}</p>
          <button className="btn btn--primary" onClick={() => openAdd()}>
            {t("decks.addBtn")}
          </button>
        </div>
      )}

      {adding && (
        <Modal
          title={t("decks.newTitle")}
          onClose={() => setAdding(false)}
          footer={
            <>
              <button className="btn btn--ghost" onClick={() => setAdding(false)}>
                {t("common.cancel")}
              </button>
              <button
                className="btn btn--primary"
                disabled={!newName.trim() || creating}
                onClick={onCreate}
              >
                {creating ? t("decks.creating") : t("decks.createBtn")}
              </button>
            </>
          }
        >
          <label className="field">
            <span className="field__label">{t("decks.nameLabel")}</span>
            <input
              className="input"
              autoFocus
              placeholder={t("decks.newPlaceholder")}
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && onCreate()}
            />
          </label>
          <label className="field">
            <span className="field__label">{t("decks.parentLabel")}</span>
            <select
              className="input"
              value={newParent}
              onChange={(e) => setNewParent(e.target.value ? Number(e.target.value) : "")}
            >
              <option value="">{t("decks.topLevel")}</option>
              {[...decks]
                .sort((a, b) => a.full_name.localeCompare(b.full_name))
                .map((d) => (
                  <option key={d.id} value={d.id}>{t("decks.under", { name: d.full_name })}</option>
                ))}
            </select>
          </label>
          <label className="field">
            <span className="field__label">{t("decks.languageField")}</span>
            <select className="input" value={newLang} onChange={(e) => setNewLang(e.target.value as any)}>
              <option value="">{t("decks.inheritLanguage")}</option>
              <option value="de">{t("common.german")}</option>
              <option value="en">{t("common.english")}</option>
            </select>
            <span className="field__hint">{t("decks.languageHint")}</span>
          </label>
          {createError && <p className="auth__error">{createError}</p>}
        </Modal>
      )}

      {sharingDeck != null && (() => {
        const d = decks.find((x) => x.id === sharingDeck);
        if (!d) return null;
        return (
          <Modal title={t("decks.shareTitle", { name: d.full_name })} onClose={() => setSharingDeck(null)}>
            <div className="sharepanel">
              <p className="field__hint">{t("decks.shareHint")}</p>
              <div className="sharepanel__add">
                <input
                  className="input"
                  type="email"
                  autoFocus
                  placeholder={t("decks.shareEmailPlaceholder")}
                  value={shareEmail}
                  onChange={(e) => setShareEmail(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && onShare()}
                />
                <button className="btn btn--primary" disabled={!shareEmail.trim() || sharing} onClick={onShare}>
                  {sharing ? t("decks.sharing") : t("decks.shareBtn")}
                </button>
              </div>
              {shareError && <p className="auth__error">{shareError}</p>}

              {d.shared_with.length === 0 ? (
                <p className="field__hint">{t("decks.notShared")}</p>
              ) : (
                <ul className="sharepanel__list">
                  {d.shared_with.map((email) => (
                    <li key={email}>
                      <span>{email}</span>
                      <button className="btn btn--ghost btn--sm" onClick={() => onUnshare(email)}>
                        {t("decks.removeBtn")}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Modal>
        );
      })()}
    </div>
  );
}
