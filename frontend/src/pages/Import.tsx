import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import {
  bulkCreateCards,
  fetchBooks,
  fetchSharedBooks,
  fetchDecks,
  importBookLesson,
  parseImport,
  processBookLesson,
  type Book,
  type BookLesson,
  type CardType,
  type Deck,
  type DraftCard,
} from "../auth/api";
import CardEditor from "../components/CardEditor";

type Stage = "input" | "review";
type Tab = "paste" | "books";

export default function ImportPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("paste");
  const [decks, setDecks] = useState<Deck[]>([]);

  // --- Paste-text flow ---
  const [stage, setStage] = useState<Stage>("input");
  const [deckId, setDeckId] = useState<number | "">("");
  const [text, setText] = useState("");
  const [language, setLanguage] = useState<"de" | "en" | "">("");
  const [defaultType, setDefaultType] = useState<CardType>("vocab");
  const [drafts, setDrafts] = useState<DraftCard[]>([]);
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // --- Books flow ---
  const [books, setBooks] = useState<Book[]>([]);
  const [bookParent, setBookParent] = useState<number | "">("");
  const [added, setAdded] = useState<Record<number, string>>({}); // lessonId -> message
  const [importingLesson, setImportingLesson] = useState<number | null>(null);
  const [processingLesson, setProcessingLesson] = useState<number | null>(null);

  useEffect(() => {
    fetchDecks().then(setDecks);
    // Owner's books + books shared with the user — same as the Books page,
    // so a shared book is usable in Import just like one you own.
    Promise.all([fetchBooks(), fetchSharedBooks().catch(() => [] as Book[])])
      .then(([mine, shared]) => {
        const seen = new Set(mine.map((b) => b.id));
        setBooks([...mine, ...shared.filter((b) => !seen.has(b.id))]);
      })
      .catch(() => {});
  }, []);

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

  function patchLesson(bookId: number, updated: BookLesson) {
    setBooks((bs) =>
      bs.map((b) =>
        b.id !== bookId ? b : { ...b, lessons: b.lessons.map((l) => (l.id === updated.id ? updated : l)) },
      ),
    );
  }

  async function processLesson(book: Book, lessonId: number) {
    setProcessingLesson(lessonId);
    setError(null);
    try {
      patchLesson(book.id, await processBookLesson(book.id, lessonId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not process the lesson.");
    } finally {
      setProcessingLesson(null);
    }
  }

  async function addLesson(book: Book, lessonId: number) {
    setImportingLesson(lessonId);
    setError(null);
    try {
      const res = await importBookLesson(book.id, lessonId, bookParent === "" ? null : Number(bookParent));
      setAdded((a) => ({ ...a, [lessonId]: `✓ Added ${res.cards} cards` }));
      fetchDecks().then(setDecks); // refresh so the new deck shows as a parent option
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add the lesson.");
    } finally {
      setImportingLesson(null);
    }
  }

  return (
    <div className="import">
      <div className="import__head">
        <h1>Import</h1>
        <div className="tabs">
          <button className={`tab ${tab === "paste" ? "tab--on" : ""}`} onClick={() => setTab("paste")}>
            Paste text
          </button>
          <button className={`tab ${tab === "books" ? "tab--on" : ""}`} onClick={() => setTab("books")}>
            From books
          </button>
        </div>
      </div>

      {error && <div className="panel panel--error">{error}</div>}

      {tab === "paste" ? (
        stage === "input" ? (
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
              placeholder={"Paste a word list or passage, e.g.\nder Tisch — table\ndie Lampe — lamp"}
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
                <button className="btn btn--primary" disabled={busy || !deckId || drafts.length === 0} onClick={onProceed}>
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
        )
      ) : (
        <div className="import__books">
          <div className="import__parentbar">
            <label>
              Add book decks under
              <select className="input" value={bookParent} onChange={(e) => setBookParent(e.target.value ? Number(e.target.value) : "")}>
                <option value="">Top level (no parent)</option>
                {[...decks].sort((a, b) => a.full_name.localeCompare(b.full_name)).map((d) => (
                  <option key={d.id} value={d.id}>{d.full_name}</option>
                ))}
              </select>
            </label>
          </div>

          {books.length === 0 ? (
            <div className="panel">
              No processed books yet. Upload one on the <Link to="/app/books">Books</Link> page.
            </div>
          ) : (
            books.map((b) => (
              <div key={b.id} className="bookblock">
                <div className="bookblock__banner" style={{ background: b.color }}>
                  <span className="bookcard__title">{b.title}</span>
                  <span className="bookcard__langs">
                    {(b.source_language || "?").toUpperCase()} → {b.translation_language} · {b.lesson_count} lessons
                    {!b.is_owner && ` · shared by ${b.owner_email}`}
                  </span>
                </div>
                <ul className="bookblock__lessons">
                  {b.lessons.map((l) => (
                    <li key={l.id} className="bookblock__lesson">
                      <span className="bookblock__ltitle">{l.title}</span>
                      {l.processed ? (
                        <span className="bookblock__count">{l.card_count} vocab</span>
                      ) : (
                        <span className="bookblock__count bookblock__count--todo">not processed</span>
                      )}
                      {added[l.id] ? (
                        <span className="bookblock__added">{added[l.id]}</span>
                      ) : l.processed ? (
                        <button
                          className="btn btn--primary btn--sm"
                          disabled={importingLesson === l.id || l.card_count === 0}
                          onClick={() => addLesson(b, l.id)}
                        >
                          {importingLesson === l.id ? "Adding…" : "+ Add"}
                        </button>
                      ) : (
                        <button
                          className="btn btn--ghost btn--sm"
                          disabled={processingLesson === l.id}
                          onClick={() => processLesson(b, l.id)}
                        >
                          {processingLesson === l.id ? "Processing…" : "Process"}
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
