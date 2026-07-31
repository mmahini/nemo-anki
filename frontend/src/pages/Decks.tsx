import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { createDeck, deleteDeck, fetchDecks, updateDeck, type Deck } from "../auth/api";
import Modal from "../components/Modal";
import ReviewActivity from "../components/ReviewActivity";

/** Indentation depth from the `::` chain in full_name. */
function depth(d: Deck): number {
  return (d.full_name.match(/::/g) || []).length;
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
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
  const [movingDeck, setMovingDeck] = useState<number | null>(null);
  const [langDeck, setLangDeck] = useState<number | null>(null);
  const [renamingDeck, setRenamingDeck] = useState<number | null>(null);
  const [renameVal, setRenameVal] = useState("");
  const [openMenu, setOpenMenu] = useState<number | null>(null);
  const [menuPos, setMenuPos] = useState<{ top: number; right: number } | null>(null);

  async function load() {
    setLoading(true);
    try {
      setDecks(await fetchDecks());
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  /** Open the add-deck sheet, optionally pre-filling the parent (from a row's
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

  function toggle(id: number) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  const collapsedNames = new Set(
    decks.filter((d) => collapsed.has(d.id)).map((d) => d.full_name),
  );
  function hidden(d: Deck): boolean {
    for (const cn of collapsedNames) {
      if (d.full_name !== cn && d.full_name.startsWith(cn + "::")) return true;
    }
    return false;
  }

  if (loading) return <div className="panel">{t("decks.loading")}</div>;
  if (error) return <div className="panel panel--error">{error}</div>;

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
            <Link className="btn btn--ghost btn--sm" to="/app/import">
              {t("decks.importBtn")}
            </Link>
            <button className="btn btn--primary btn--sm" onClick={() => openAdd()}>
              {t("decks.addBtn")}
            </button>
          </div>
        </div>
      </div>

      {decks.length > 0 && <ReviewActivity />}

      <ul className="decklist">
        {decks.filter((d) => !hidden(d)).map((d) => {
          const hasChildren = decks.some((c) => c.parent === d.id);
          const isLeaf = !hasChildren;
          const studyable = d.counts.new + d.counts.learning + d.counts.due;
          return (
            <li
              key={d.id}
              className="decklist__row"
              style={{ paddingInlineStart: `${depth(d) * 18 + 12}px` }}
            >
              <div className="decklist__name">
                {hasChildren ? (
                  <button className="twisty" onClick={() => toggle(d.id)}>
                    {collapsed.has(d.id) ? "▸" : "▾"}
                  </button>
                ) : (
                  <span className="twisty twisty--leaf" />
                )}
                {d.language && <span className={`flag flag--${d.language}`}>{d.language}</span>}
                {renamingDeck === d.id ? (
                  <input
                    className="input input--sm decklist__rename"
                    autoFocus
                    value={renameVal}
                    onChange={(e) => setRenameVal(e.target.value)}
                    onBlur={() => onRename(d)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") onRename(d);
                      if (e.key === "Escape") setRenamingDeck(null);
                    }}
                  />
                ) : (
                  <Link to={`/app/decks/${d.id}`} className="decklist__link">
                    {d.name}
                  </Link>
                )}
              </div>
              <div className="decklist__counts">
                <span className="count count--new">{d.counts.new}</span>
                <span className="count count--learn">{d.counts.learning}</span>
                <span className="count count--due">{d.counts.due}</span>
              </div>
              <div className="decklist__actions">
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
                            {isLeaf && <button onClick={() => { setOpenMenu(null); navigate(`/app/decks/${d.id}/add`); }}>{t("decks.addCard")}</button>}
                            <button className="deckmenu__danger" onClick={() => { setOpenMenu(null); onDelete(d); }}>{t("decks.delete")}</button>
                          </div>
                        </>
                      )}
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
    </div>
  );
}
