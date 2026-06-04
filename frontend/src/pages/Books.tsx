import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import {
  deleteBook,
  fetchBooks,
  fetchSharedBooks,
  uploadBook,
  type Book,
} from "../auth/api";
import { TRANSLATE_LANGS } from "../lib/translateLang";

type Tab = "mine" | "shared";

export default function Books() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("mine");
  const [mine, setMine] = useState<Book[]>([]);
  const [shared, setShared] = useState<Book[]>([]);
  const [loading, setLoading] = useState(true);

  const [title, setTitle] = useState("");
  const [sourceLang, setSourceLang] = useState<"de" | "en" | "">("en");
  const [transLang, setTransLang] = useState("English");
  const [file, setFile] = useState<File | null>(null);
  const [label, setLabel] = useState("Unit");
  const [fromLesson, setFromLesson] = useState("");
  const [toLesson, setToLesson] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [m, s] = await Promise.all([fetchBooks(), fetchSharedBooks().catch(() => [])]);
      setMine(m);
      setShared(s);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, []);

  async function onUpload(e: FormEvent) {
    e.preventDefault();
    if (!title.trim() || !file) {
      setError("Add a title and choose a file (.txt / .pdf).");
      return;
    }
    if (file && !(fromLesson && toLesson)) {
      setError("Enter From and To (e.g. 1 and 100) so the PDF can be split into lessons.");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const book = await uploadBook({
        title: title.trim(),
        source_language: sourceLang,
        translation_language: transLang,
        file,
        lesson_label: label.trim() || "Unit",
        from_lesson: fromLesson ? Number(fromLesson) : null,
        to_lesson: toLesson ? Number(toLesson) : null,
      });
      setTitle("");
      setFile(null);
      navigate(`/app/books/${book.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  async function onDelete(b: Book) {
    if (!window.confirm(`Delete the book "${b.title}"? (Decks you already imported stay.)`)) return;
    await deleteBook(b.id);
    load();
  }

  const list = tab === "mine" ? mine : shared;

  function bookCard(b: Book) {
    return (
      <li key={b.id} className="bookcard">
        <button
          className="bookcard__banner"
          style={{ background: b.color }}
          onClick={() => navigate(`/app/books/${b.id}`)}
        >
          <span className="bookcard__title">{b.title}</span>
          <span className="bookcard__langs">
            {(b.source_language || "?").toUpperCase()} → {b.translation_language} · {b.lesson_count} lessons
            {!b.is_owner && ` · by ${b.owner_email}`}
          </span>
        </button>
        <div className="bookcard__body">
          <span className="bookcard__meta">{b.card_count} vocab extracted</span>
          <div className="bookcard__actions">
            <button className="btn btn--primary btn--sm" onClick={() => navigate(`/app/books/${b.id}`)}>Open →</button>
            {b.is_owner && <button className="btn btn--ghost btn--sm" onClick={() => onDelete(b)}>Delete</button>}
          </div>
        </div>
      </li>
    );
  }

  return (
    <div className="books">
      <h1>Books</h1>

      <form className="books__upload panel" onSubmit={onUpload}>
        <div className="books__row">
          <label className="cardeditor__field" style={{ flex: 2 }}>
            <span>Book title</span>
            <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Oxford Word Skills Intermediate" />
          </label>
          <label className="cardeditor__field">
            <span>Book language</span>
            <select className="input" value={sourceLang} onChange={(e) => setSourceLang(e.target.value as any)}>
              <option value="en">English</option>
              <option value="de">German</option>
              <option value="">Other</option>
            </select>
          </label>
          <label className="cardeditor__field">
            <span>Translate into</span>
            <select className="input" value={transLang} onChange={(e) => setTransLang(e.target.value)}>
              {TRANSLATE_LANGS.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </label>
        </div>
        <div className="books__row books__row--file">
          <span className="books__or">Book file (.txt / .pdf)</span>
          <input type="file" accept=".txt,.pdf,text/plain,application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </div>
        <div className="books__row">
          <label className="cardeditor__field">
            <span>Lesson label</span>
            <input className="input" list="lesson-labels" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Unit" />
            <datalist id="lesson-labels">
              <option value="Unit" /><option value="Lesson" /><option value="Lektion" /><option value="Kapitel" /><option value="Chapter" />
            </datalist>
          </label>
          <label className="cardeditor__field">
            <span>From</span>
            <input className="input" type="number" min={1} value={fromLesson} onChange={(e) => setFromLesson(e.target.value)} placeholder="1" />
          </label>
          <label className="cardeditor__field">
            <span>To</span>
            <input className="input" type="number" min={1} value={toLesson} onChange={(e) => setToLesson(e.target.value)} placeholder="100" />
          </label>
        </div>
        <span className="books__hint">The PDF is split into one sub-PDF per lesson; open a book to process, review, re-split, and share its lessons.</span>
        {error && <p className="auth__error">{error}</p>}
        <button className="btn btn--primary btn--lg" disabled={uploading}>
          {uploading ? "Splitting…" : file && fromLesson && toLesson ? `Upload & split into ${Math.max(0, Number(toLesson) - Number(fromLesson) + 1)} lessons` : "Upload & split into lessons"}
        </button>
      </form>

      <div className="tabs books__tabs">
        <button className={`tab ${tab === "mine" ? "tab--on" : ""}`} onClick={() => setTab("mine")}>My books ({mine.length})</button>
        <button className={`tab ${tab === "shared" ? "tab--on" : ""}`} onClick={() => setTab("shared")}>Shared with me ({shared.length})</button>
      </div>

      {loading ? (
        <div className="panel">Loading…</div>
      ) : list.length === 0 ? (
        <div className="panel">{tab === "mine" ? "No books yet — upload one above." : "No books shared with you yet."}</div>
      ) : (
        <ul className="books__list">{list.map(bookCard)}</ul>
      )}
    </div>
  );
}
