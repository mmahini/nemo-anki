import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { deleteBook, fetchBooks, uploadBook, type Book } from "../auth/api";
import { TRANSLATE_LANGS } from "../lib/translateLang";

export default function Books() {
  const [books, setBooks] = useState<Book[]>([]);
  const [loading, setLoading] = useState(true);
  const [title, setTitle] = useState("");
  const [sourceLang, setSourceLang] = useState<"de" | "en" | "">("de");
  const [transLang, setTransLang] = useState("English");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      setBooks(await fetchBooks());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function onProcess(e: FormEvent) {
    e.preventDefault();
    if (!title.trim() || (!text.trim() && !file)) {
      setError("Add a title and either paste text or choose a file.");
      return;
    }
    setProcessing(true);
    setError(null);
    try {
      await uploadBook({
        title: title.trim(),
        source_language: sourceLang,
        translation_language: transLang,
        text,
        file,
      });
      setTitle("");
      setText("");
      setFile(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Processing failed.");
    } finally {
      setProcessing(false);
    }
  }

  async function onDelete(b: Book) {
    if (!window.confirm(`Delete the processed book "${b.title}"? (Decks you already imported stay.)`)) return;
    await deleteBook(b.id);
    load();
  }

  return (
    <div className="books">
      <h1>Books</h1>
      <p className="books__sub">
        Upload a coursebook — the whole book becomes one deck, each lesson a
        sub-deck, and every lesson's vocabulary is extracted for you. Then add
        the lessons you want from the <Link to="/app/import">Import</Link> page.
      </p>

      <form className="books__upload panel" onSubmit={onProcess}>
        <div className="books__row">
          <label className="cardeditor__field" style={{ flex: 2 }}>
            <span>Book title</span>
            <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Menschen A1.1" />
          </label>
          <label className="cardeditor__field">
            <span>Book language</span>
            <select className="input" value={sourceLang} onChange={(e) => setSourceLang(e.target.value as any)}>
              <option value="de">German</option>
              <option value="en">English</option>
              <option value="">Other</option>
            </select>
          </label>
          <label className="cardeditor__field">
            <span>Translate into</span>
            <select className="input" value={transLang} onChange={(e) => setTransLang(e.target.value)}>
              {TRANSLATE_LANGS.map((l) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
          </label>
        </div>

        <label className="cardeditor__field">
          <span>Paste the book text</span>
          <textarea
            className="import__textarea"
            rows={8}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={"Lektion 1 — …\nWortschatz: der Tisch, die Lampe …\n\nLektion 2 — …"}
          />
        </label>
        <div className="books__row books__row--file">
          <span className="books__or">or upload a file (.txt / .pdf)</span>
          <input type="file" accept=".txt,.pdf,text/plain,application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </div>

        {error && <p className="auth__error">{error}</p>}
        <button className="btn btn--primary btn--lg" disabled={processing}>
          {processing ? "Processing book… (this can take a moment)" : "Process book"}
        </button>
      </form>

      <h2 className="books__h2">Your processed books</h2>
      {loading ? (
        <div className="panel">Loading…</div>
      ) : books.length === 0 ? (
        <div className="panel">No books yet — process one above.</div>
      ) : (
        <ul className="books__list">
          {books.map((b) => (
            <li key={b.id} className="bookcard">
              <div className="bookcard__banner" style={{ background: b.color }}>
                <span className="bookcard__title">{b.title}</span>
                <span className="bookcard__langs">
                  {(b.source_language || "?").toUpperCase()} → {b.translation_language}
                </span>
              </div>
              <div className="bookcard__body">
                <span className="bookcard__meta">
                  {b.status === "ready" ? `${b.lesson_count} lessons · ${b.card_count} cards` : b.status}
                </span>
                {b.note && <span className="bookcard__note">{b.note}</span>}
                <div className="bookcard__actions">
                  <Link to="/app/import" className="btn btn--primary btn--sm">Add lessons →</Link>
                  <button className="btn btn--ghost btn--sm" onClick={() => onDelete(b)}>Delete</button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
