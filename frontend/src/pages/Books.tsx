import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import {
  analyzeBook,
  deleteBook,
  fetchBookLesson,
  fetchBooks,
  processBookLesson,
  uploadBook,
  type Book,
  type BookLesson,
  type BookLessonDetail,
  type PageMapItem,
} from "../auth/api";
import { TRANSLATE_LANGS } from "../lib/translateLang";

export default function Books() {
  const [books, setBooks] = useState<Book[]>([]);
  const [loading, setLoading] = useState(true);
  const [title, setTitle] = useState("");
  const [sourceLang, setSourceLang] = useState<"de" | "en" | "">("de");
  const [transLang, setTransLang] = useState("English");
  const [file, setFile] = useState<File | null>(null);
  const [label, setLabel] = useState("Unit");
  const [fromLesson, setFromLesson] = useState("");
  const [toLesson, setToLesson] = useState("");
  const [pagesPerUnit, setPagesPerUnit] = useState("");
  const [startPage, setStartPage] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState<Set<number>>(new Set()); // lesson ids being processed
  // Preview step: editable unit->page map before the book is created.
  const [analyzing, setAnalyzing] = useState(false);
  const [creating, setCreating] = useState(false);
  const [preview, setPreview] = useState<{ page_count: number; detected_count: number } | null>(null);
  const [pageMap, setPageMap] = useState<PageMapItem[]>([]);
  // Lesson page-content viewer.
  const [viewing, setViewing] = useState<BookLessonDetail | null>(null);
  const [loadingView, setLoadingView] = useState<number | null>(null);

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

  async function onUpload(e: FormEvent) {
    e.preventDefault();
    if (!title.trim() || !file) {
      setError("Add a title and choose a file (.txt / .pdf).");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      await uploadBook({
        title: title.trim(),
        source_language: sourceLang,
        translation_language: transLang,
        file,
        lesson_label: label.trim() || undefined,
        from_lesson: fromLesson ? Number(fromLesson) : null,
        to_lesson: toLesson ? Number(toLesson) : null,
        pages_per_unit: pagesPerUnit ? Number(pagesPerUnit) : null,
        start_page: startPage ? Number(startPage) : null,
      });
      setTitle("");
      setFile(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  async function onPreview() {
    if (!file || !fromLesson || !toLesson) {
      setError("Choose a PDF and set the From/To unit numbers to preview pages.");
      return;
    }
    setAnalyzing(true);
    setError(null);
    try {
      const res = await analyzeBook({
        file,
        lesson_label: label.trim() || "Unit",
        from_lesson: Number(fromLesson),
        to_lesson: Number(toLesson),
        pages_per_unit: pagesPerUnit ? Number(pagesPerUnit) : null,
      });
      setPreview({ page_count: res.page_count, detected_count: res.detected_count });
      setPageMap(res.units);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not analyse the PDF.");
    } finally {
      setAnalyzing(false);
    }
  }

  function setRowPage(i: number, value: string) {
    setPageMap((m) => m.map((row, idx) => (idx === i ? { ...row, start_page: Number(value) || 0 } : row)));
  }

  async function onCreateFromMap() {
    if (!file) return;
    setCreating(true);
    setError(null);
    try {
      await uploadBook({
        title: title.trim() || "Book",
        source_language: sourceLang,
        translation_language: transLang,
        file,
        lesson_label: label.trim() || "Unit",
        page_map: pageMap,
      });
      setPreview(null);
      setPageMap([]);
      setTitle("");
      setFile(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the book.");
    } finally {
      setCreating(false);
    }
  }

  function patchLesson(bookId: number, updated: BookLesson) {
    setBooks((bs) =>
      bs.map((b) =>
        b.id !== bookId
          ? b
          : { ...b, lessons: b.lessons.map((l) => (l.id === updated.id ? updated : l)) },
      ),
    );
  }

  async function process(book: Book, lesson: BookLesson) {
    setWorking((w) => new Set(w).add(lesson.id));
    setError(null);
    try {
      patchLesson(book.id, await processBookLesson(book.id, lesson.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Processing failed.");
    } finally {
      setWorking((w) => {
        const n = new Set(w);
        n.delete(lesson.id);
        return n;
      });
    }
  }

  async function processAll(book: Book) {
    for (const l of book.lessons) {
      if (!l.processed) await process(book, l);
    }
  }

  async function viewLesson(b: Book, lessonId: number) {
    setLoadingView(lessonId);
    try {
      setViewing(await fetchBookLesson(b.id, lessonId));
    } finally {
      setLoadingView(null);
    }
  }

  async function onDelete(b: Book) {
    if (!window.confirm(`Delete the book "${b.title}"? (Decks you already imported stay.)`)) return;
    await deleteBook(b.id);
    load();
  }

  return (
    <div className="books">
      <h1>Books</h1>
      <p className="books__sub">
        Upload a coursebook — it's split into lessons instantly. Then process the
        lessons you want (vocabulary is extracted per lesson), and add them to
        your decks from the <Link to="/app/import">Import</Link> page.
      </p>

      <form className="books__upload panel" onSubmit={onUpload}>
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

        <div className="books__row books__row--file">
          <span className="books__or">Book file (.txt / .pdf)</span>
          <input type="file" accept=".txt,.pdf,text/plain,application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </div>

        <fieldset className="books__range">
          <legend>Lesson detection (recommended for big / PDF books)</legend>
          <div className="books__row">
            <label className="cardeditor__field">
              <span>Lesson label</span>
              <input
                className="input"
                list="lesson-labels"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="Unit"
              />
              <datalist id="lesson-labels">
                <option value="Unit" />
                <option value="Lesson" />
                <option value="Lektion" />
                <option value="Kapitel" />
                <option value="Chapter" />
                <option value="Modul" />
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
          <span className="books__hint">
            Tell me the heading word and the number range (e.g. Unit, 1–100). I'll
            look for each one in order. Leave blank to auto-detect.
          </span>

          <div className="books__row" style={{ marginTop: 4 }}>
            <label className="cardeditor__field">
              <span>Pages per unit</span>
              <input className="input" type="number" min={1} value={pagesPerUnit} onChange={(e) => setPagesPerUnit(e.target.value)} placeholder="e.g. 2" />
            </label>
            <label className="cardeditor__field">
              <span>First unit starts on page</span>
              <input className="input" type="number" min={1} value={startPage} onChange={(e) => setStartPage(e.target.value)} placeholder="e.g. 6" />
            </label>
          </div>
          <span className="books__hint">
            <strong>Most reliable for PDFs:</strong> if each unit is a fixed number of
            pages, set “pages per unit” + the page the first unit starts on, and I'll
            split the PDF by page (ignoring messy headings) — this always yields the
            full range.
          </span>
        </fieldset>

        {error && <p className="auth__error">{error}</p>}
        <div className="books__submit">
          <button className="btn btn--primary btn--lg" disabled={uploading}>
            {uploading
              ? "Splitting…"
              : file && fromLesson && toLesson
                ? `Upload & split into ${Math.max(0, Number(toLesson) - Number(fromLesson) + 1)} lessons`
                : "Upload & split into lessons"}
          </button>
          {file && fromLesson && toLesson && (
            <button type="button" className="btn btn--ghost btn--lg" disabled={analyzing} onClick={onPreview}>
              {analyzing ? "Analysing…" : "Preview & edit pages first"}
            </button>
          )}
        </div>
      </form>

      {preview && (
        <div className="panel pagemap">
          <div className="pagemap__head">
            <div>
              <strong>{pageMap.length}</strong> lessons · PDF has {preview.page_count} pages ·
              detected {preview.detected_count} unit headings
            </div>
            <div className="pagemap__actions">
              <button className="btn btn--ghost" onClick={() => { setPreview(null); setPageMap([]); }}>Cancel</button>
              <button className="btn btn--primary" disabled={creating} onClick={onCreateFromMap}>
                {creating ? "Creating…" : `Create book (${pageMap.length} lessons)`}
              </button>
            </div>
          </div>
          <p className="books__hint">
            Each unit's start page (detected per page; gaps interpolated). Edit any
            that look wrong — a unit runs from its page up to the next unit's page.
          </p>
          <ul className="pagemap__list">
            {pageMap.map((row, i) => (
              <li key={row.num} className="pagemap__row">
                <span className="pagemap__unit">{label.trim() || "Unit"} {row.num}</span>
                <label className="pagemap__page">
                  page
                  <input
                    className="input input--sm"
                    type="number"
                    min={1}
                    value={row.start_page}
                    onChange={(e) => setRowPage(i, e.target.value)}
                  />
                </label>
              </li>
            ))}
          </ul>
        </div>
      )}

      <h2 className="books__h2">Your books</h2>
      {loading ? (
        <div className="panel">Loading…</div>
      ) : books.length === 0 ? (
        <div className="panel">No books yet — upload one above.</div>
      ) : (
        books.map((b) => {
          const pending = b.lessons.filter((l) => !l.processed).length;
          return (
            <div key={b.id} className="bookblock">
              <div className="bookblock__banner" style={{ background: b.color }}>
                <div>
                  <span className="bookcard__title">{b.title}</span>
                  <span className="bookcard__langs">
                    {(b.source_language || "?").toUpperCase()} → {b.translation_language} · {b.lesson_count} lessons
                  </span>
                </div>
                <div className="bookblock__banneractions">
                  {pending > 0 && (
                    <button className="btn btn--ghost btn--sm" onClick={() => processAll(b)}>
                      Process all ({pending})
                    </button>
                  )}
                  <button className="btn btn--ghost btn--sm" onClick={() => onDelete(b)}>Delete</button>
                </div>
              </div>
              {b.note && <div className="bookblock__note">{b.note}</div>}
              <ul className="bookblock__lessons">
                {b.lessons.map((l) => (
                  <li key={l.id} className="bookblock__lesson">
                    <span className="bookblock__ltitle">{l.title}</span>
                    {l.page_start && (
                      <span className="bookblock__pages">
                        pp. {l.page_start}{l.page_end && l.page_end !== l.page_start ? `–${l.page_end}` : ""}
                      </span>
                    )}
                    {l.pdf_url ? (
                      <a
                        className="btn btn--ghost btn--sm"
                        href={l.pdf_url}
                        target="_blank"
                        rel="noreferrer"
                        title="Open this lesson's PDF"
                      >
                        View
                      </a>
                    ) : (
                      <button
                        className="btn btn--ghost btn--sm"
                        disabled={loadingView === l.id}
                        onClick={() => viewLesson(b, l.id)}
                        title="View this lesson's pages"
                      >
                        {loadingView === l.id ? "…" : "View"}
                      </button>
                    )}
                    {l.processed ? (
                      <>
                        <span className="bookblock__count">{l.card_count} vocab</span>
                        <button
                          className="btn btn--ghost btn--sm"
                          disabled={working.has(l.id)}
                          onClick={() => process(b, l)}
                          title="Re-extract vocabulary"
                        >
                          {working.has(l.id) ? "…" : "↻"}
                        </button>
                      </>
                    ) : (
                      <button
                        className="btn btn--primary btn--sm"
                        disabled={working.has(l.id)}
                        onClick={() => process(b, l)}
                      >
                        {working.has(l.id) ? "Processing…" : "Process"}
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          );
        })
      )}

      {viewing && (
        <div className="lessonview" onClick={() => setViewing(null)}>
          <div className="lessonview__card" onClick={(e) => e.stopPropagation()}>
            <div className="lessonview__head">
              <strong>{viewing.title}</strong>
              {viewing.page_start && (
                <span className="bookblock__pages">
                  pp. {viewing.page_start}{viewing.page_end && viewing.page_end !== viewing.page_start ? `–${viewing.page_end}` : ""}
                </span>
              )}
              <button className="btn btn--ghost btn--sm" onClick={() => setViewing(null)}>Close</button>
            </div>
            <pre className="lessonview__text">{viewing.raw_text || "(no text on these pages)"}</pre>
          </div>
        </div>
      )}
    </div>
  );
}
