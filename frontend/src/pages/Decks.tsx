import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { createDeck, fetchDecks, type Deck } from "../auth/api";

/** Indentation depth from the `::` chain in full_name. */
function depth(d: Deck): number {
  return (d.full_name.match(/::/g) || []).length;
}

export default function Decks() {
  const navigate = useNavigate();
  const [decks, setDecks] = useState<Deck[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [newLang, setNewLang] = useState<"de" | "en" | "">("");
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());

  async function load() {
    setLoading(true);
    try {
      setDecks(await fetchDecks());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load decks.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function onCreate() {
    if (!newName.trim()) return;
    await createDeck({ name: newName.trim(), language: newLang });
    setNewName("");
    load();
  }

  function toggle(id: number) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  // Hide a deck if any ancestor is collapsed.
  const collapsedNames = new Set(
    decks.filter((d) => collapsed.has(d.id)).map((d) => d.full_name),
  );
  function hidden(d: Deck): boolean {
    for (const cn of collapsedNames) {
      if (d.full_name !== cn && d.full_name.startsWith(cn + "::")) return true;
    }
    return false;
  }

  if (loading) return <div className="panel">Loading decks…</div>;
  if (error) return <div className="panel panel--error">{error}</div>;

  return (
    <div className="decks">
      <div className="decks__head">
        <h1>Your decks</h1>
        <div className="legend">
          <span className="legend__item"><i className="dot dot--new" /> new</span>
          <span className="legend__item"><i className="dot dot--learn" /> learning</span>
          <span className="legend__item"><i className="dot dot--due" /> due</span>
        </div>
      </div>

      <ul className="decklist">
        {decks.filter((d) => !hidden(d)).map((d) => {
          const hasChildren = decks.some((c) => c.parent === d.id);
          const isLeaf = !hasChildren;
          const studyable = d.counts.new + d.counts.learning + d.counts.due;
          return (
            <li
              key={d.id}
              className="decklist__row"
              style={{ paddingLeft: `${depth(d) * 18 + 12}px` }}
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
                <Link to={`/app/decks/${d.id}`} className="decklist__link">
                  {d.name}
                </Link>
              </div>
              <div className="decklist__counts">
                <span className="count count--new">{d.counts.new}</span>
                <span className="count count--learn">{d.counts.learning}</span>
                <span className="count count--due">{d.counts.due}</span>
              </div>
              <div className="decklist__actions">
                {isLeaf && (
                  <Link to={`/app/decks/${d.id}/add`} className="btn btn--ghost btn--sm">
                    + Card
                  </Link>
                )}
                <button
                  className="btn btn--primary btn--sm"
                  disabled={studyable === 0}
                  onClick={() => navigate(`/app/study/${d.id}`)}
                >
                  Study
                </button>
              </div>
            </li>
          );
        })}
      </ul>

      <div className="decks__new">
        <input
          className="input"
          placeholder="New top-level deck name"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onCreate()}
        />
        <select className="input" value={newLang} onChange={(e) => setNewLang(e.target.value as any)}>
          <option value="">No language</option>
          <option value="de">German</option>
          <option value="en">English</option>
        </select>
        <button className="btn btn--primary" onClick={onCreate}>Add deck</button>
      </div>
    </div>
  );
}
