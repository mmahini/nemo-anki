import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  createDeck,
  deleteDeck,
  shareDeck,
  unshareDeck,
  updateDeck,
  type Deck,
} from "../auth/api";
import Modal from "./Modal";

/** Indentation depth from the `::` chain in full_name. */
function depth(d: Deck): number {
  return (d.full_name.match(/::/g) || []).length;
}

/** The nested deck rows under one root deck — the tree UI that used to live on
 * the Decks page, now scoped to a subtree and shown inside the deck's own page.
 * Rows keep the full action set (rename / language / move / add sub-deck /
 * add card / share / delete) since sub-decks appear nowhere else. */
export default function DeckTree({
  decks,
  rootId,
  onChanged,
}: {
  /** The user's full flat deck list (needed for move targets + nesting). */
  decks: Deck[];
  /** Only decks strictly below this one are rendered. */
  rootId: number;
  onChanged: () => void;
}) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [error, setError] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
  const [movingDeck, setMovingDeck] = useState<number | null>(null);
  const [langDeck, setLangDeck] = useState<number | null>(null);
  const [renamingDeck, setRenamingDeck] = useState<number | null>(null);
  const [renameVal, setRenameVal] = useState("");
  const [openMenu, setOpenMenu] = useState<number | null>(null);
  const [menuPos, setMenuPos] = useState<{ top: number; right: number } | null>(null);
  const [sharingDeck, setSharingDeck] = useState<number | null>(null);
  const [shareEmail, setShareEmail] = useState("");
  const [sharing, setSharing] = useState(false);
  const [shareError, setShareError] = useState<string | null>(null);
  const [addParent, setAddParent] = useState<number | null>(null);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  // Shared decks come back from the share/unshare endpoints — mirror them into
  // the parent's list via onChanged, but keep the modal's view fresh locally.
  const [shareView, setShareView] = useState<Deck | null>(null);

  const root = decks.find((d) => d.id === rootId);
  if (!root) return null;
  const rootDepth = depth(root);
  const subtree = decks
    .filter((d) => d.full_name.startsWith(root.full_name + "::"))
    .sort((a, b) => a.full_name.toLowerCase().localeCompare(b.full_name.toLowerCase()));
  if (subtree.length === 0) return null;

  const collapsedNames = new Set(
    subtree.filter((d) => collapsed.has(d.id)).map((d) => d.full_name),
  );
  function hidden(d: Deck): boolean {
    for (const cn of collapsedNames) {
      if (d.full_name !== cn && d.full_name.startsWith(cn + "::")) return true;
    }
    return false;
  }

  function toggle(id: number) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function parentOptions(d: Deck): Deck[] {
    const banned = new Set(
      decks.filter((x) => x.id === d.id || x.full_name.startsWith(d.full_name + "::")).map((x) => x.id),
    );
    return decks.filter((x) => !banned.has(x.id)).sort((a, b) => a.full_name.localeCompare(b.full_name));
  }

  async function onMove(d: Deck, parent: number | null) {
    setMovingDeck(null);
    try {
      await updateDeck(d.id, { parent });
      onChanged();
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
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    }
  }

  async function onSetLang(d: Deck, language: "de" | "en" | "") {
    setLangDeck(null);
    if (language === (d.language ?? "")) return;
    try {
      await updateDeck(d.id, { language });
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    }
  }

  async function onDelete(d: Deck) {
    const childCount = decks.filter((x) => x.full_name.startsWith(d.full_name + "::")).length;
    const msg = childCount
      ? t("decks.confirmDeleteWithChildren", { name: d.full_name, count: childCount })
      : t("decks.confirmDelete", { name: d.full_name });
    if (!window.confirm(msg)) return;
    await deleteDeck(d.id);
    onChanged();
  }

  function openAdd(parent: number) {
    setNewName("");
    setCreateError(null);
    setAddParent(parent);
  }

  async function onCreate() {
    if (!newName.trim() || creating || addParent == null) return;
    const parentLang = decks.find((d) => d.id === addParent)?.language ?? "";
    setCreating(true);
    setCreateError(null);
    try {
      await createDeck({ name: newName.trim(), parent: addParent, language: parentLang });
      setAddParent(null);
      onChanged();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setCreating(false);
    }
  }

  function openShare(d: Deck) {
    setShareEmail("");
    setShareError(null);
    setShareView(d);
    setSharingDeck(d.id);
  }

  async function onShare() {
    if (sharingDeck == null || !shareEmail.trim() || sharing) return;
    setSharing(true);
    setShareError(null);
    try {
      const updated = await shareDeck(sharingDeck, shareEmail.trim());
      setShareView(updated);
      setShareEmail("");
      onChanged();
    } catch (err) {
      setShareError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setSharing(false);
    }
  }

  async function onUnshare(email: string) {
    if (sharingDeck == null) return;
    const updated = await unshareDeck(sharingDeck, email);
    setShareView(updated);
    onChanged();
  }

  return (
    <>
      {error && <div className="panel panel--error">{error}</div>}
      <ul className="decklist">
        {subtree.filter((d) => !hidden(d)).map((d) => {
          const hasChildren = decks.some((c) => c.parent === d.id);
          const isLeaf = !hasChildren;
          const studyable = d.counts.new + d.counts.learning + d.counts.due;
          return (
            <li
              key={d.id}
              className="decklist__row"
              style={{ paddingInlineStart: `${(depth(d) - rootDepth - 1) * 18 + 12}px` }}
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
                            <button onClick={() => { setOpenMenu(null); openShare(d); }}>{t("decks.shareBtn")}</button>
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

      {addParent != null && (
        <Modal
          title={t("decks.newTitle")}
          onClose={() => setAddParent(null)}
          footer={
            <>
              <button className="btn btn--ghost" onClick={() => setAddParent(null)}>
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
          <p className="field__hint">
            {t("decks.under", { name: decks.find((d) => d.id === addParent)?.full_name ?? "" })}
          </p>
          {createError && <p className="auth__error">{createError}</p>}
        </Modal>
      )}

      {sharingDeck != null && shareView && (
        <Modal title={t("decks.shareTitle", { name: shareView.full_name })} onClose={() => setSharingDeck(null)}>
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

            {shareView.shared_with.length === 0 ? (
              <p className="field__hint">{t("decks.notShared")}</p>
            ) : (
              <ul className="sharepanel__list">
                {shareView.shared_with.map((email) => (
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
      )}
    </>
  );
}
