import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  deleteBook,
  fetchBook,
  fetchBookLesson,
  importBookLesson,
  processBookLesson,
  regenerateBook,
  shareBook,
  unshareBook,
  updateBook,
  type Book,
  type BookLesson,
  type BookLessonDetail,
} from "../auth/api";
import { articleClass } from "../lib/article";
import { TRANSLATE_LANGS } from "../lib/translateLang";

function lessonNum(t: string): number {
  const m = /(\d+)/.exec(t || "");
  return m ? Number(m[1]) : 0;
}
function lessonLabel(t: string): string {
  const m = /^(.*?)\s*\d+/.exec(t || "");
  return (m && m[1].trim()) || "Unit";
}

type Tab = "lessons" | "share";

export default function BookPage() {
  const { bookId } = useParams();
  const id = Number(bookId);
  const navigate = useNavigate();

  const [book, setBook] = useState<Book | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("lessons");

  const [working, setWorking] = useState<Set<number>>(new Set());
  const [regenerating, setRegenerating] = useState(false);
  const [regenLessonId, setRegenLessonId] = useState<number | null>(null);
  const [regenL, setRegenL] = useState({ start: "", ppu: "" });

  // Whole-book split (separate from per-lesson "Re-split"). Re-runnable, so the
  // user can break the book into smaller chunks at any time.
  const [splitOpen, setSplitOpen] = useState(false);
  const [splitting, setSplitting] = useState(false);
  const [split, setSplit] = useState({ label: "Unit", from: "1", to: "", start: "", ppu: "" });

  const [lessonView, setLessonView] = useState<BookLessonDetail | null>(null);
  const [loadingLesson, setLoadingLesson] = useState<number | null>(null);
  const [reviewing, setReviewing] = useState(false);

  const [shareEmail, setShareEmail] = useState("");

  async function load() {
    setLoading(true);
    try {
      setBook(await fetchBook(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load the book.");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (loading) return <div className="panel">Loading…</div>;
  if (!book) return <div className="panel panel--error">{error ?? "Book not found."}</div>;
  const owner = book.is_owner;

  async function process(lesson: BookLesson) {
    setWorking((w) => new Set(w).add(lesson.id));
    setError(null);
    try {
      await processBookLesson(book!.id, lesson.id);
      await load();
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

  async function processAll() {
    for (const l of book!.lessons.filter((x) => !x.processed)) await process(l);
  }

  async function doSplit(e: FormEvent) {
    e.preventDefault();
    const from = Number(split.from) || 1;
    const to = Number(split.to);
    if (!to || to < from) {
      setError("Enter a valid range — e.g. From 1, To 20.");
      return;
    }
    const had = book!.lessons.length;
    if (had > 0 && !window.confirm(`Re-split replaces all ${had} current lessons (extracted vocab is cleared). Continue?`)) {
      return;
    }
    setSplitting(true);
    setError(null);
    try {
      const updated = await regenerateBook(book!.id, {
        from_lesson: from,
        to_lesson: to,
        start_page: split.start ? Number(split.start) : null,
        pages_per_unit: split.ppu ? Number(split.ppu) : null,
        lesson_label: split.label.trim() || "Unit",
        replace_all: true,
      });
      setBook(updated);
      setSplitOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Split failed.");
    } finally {
      setSplitting(false);
    }
  }

  function toggleLessonRegen(l: BookLesson) {
    if (regenLessonId === l.id) return setRegenLessonId(null);
    setRegenL({ start: l.page_start ? String(l.page_start) : "", ppu: "" });
    setRegenLessonId(l.id);
  }

  async function doLessonRegen(l: BookLesson, toEnd: boolean) {
    setRegenerating(true);
    setError(null);
    try {
      const num = lessonNum(l.title);
      const maxNum = Math.max(...book!.lessons.map((x) => lessonNum(x.title)));
      const updated = await regenerateBook(book!.id, {
        from_lesson: num,
        to_lesson: toEnd ? maxNum : num,
        pages_per_unit: regenL.ppu ? Number(regenL.ppu) : null,
        start_page: regenL.start ? Number(regenL.start) : null,
        lesson_label: lessonLabel(l.title),
      });
      setBook(updated);
      setRegenLessonId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Re-generate failed.");
    } finally {
      setRegenerating(false);
    }
  }

  async function openLesson(lesson: BookLesson) {
    setLoadingLesson(lesson.id);
    setError(null);
    try {
      setLessonView(await fetchBookLesson(book!.id, lesson.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't open the lesson.");
    } finally {
      setLoadingLesson(null);
    }
  }

  async function reviewLesson() {
    if (!lessonView) return;
    setReviewing(true);
    setError(null);
    try {
      const res = await importBookLesson(book!.id, lessonView.id, null);
      navigate(`/app/study/${res.lesson_deck}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't start review.");
      setReviewing(false);
    }
  }

  async function setLang(patch: Partial<{ source_language: "de" | "en" | ""; translation_language: string }>) {
    try {
      setBook(await updateBook(book!.id, patch as any));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't update the book.");
    }
  }

  async function onDelete() {
    if (!window.confirm(`Delete the book "${book!.title}"? (Decks you already imported stay.)`)) return;
    await deleteBook(book!.id);
    navigate("/app/books");
  }

  async function onShare(e: FormEvent) {
    e.preventDefault();
    const email = shareEmail.trim().toLowerCase();
    if (!email) return;
    setError(null);
    try {
      setBook(await shareBook(book!.id, email));
      setShareEmail("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't share.");
    }
  }

  async function onUnshare(email: string) {
    setBook(await unshareBook(book!.id, email));
  }

  return (
    <div className="bookpage">
      <div className="bookpage__top">
        <button className="btn btn--ghost btn--sm" onClick={() => navigate("/app/books")}>← Books</button>
      </div>

      <div className="bookblock__banner bookpage__banner" style={{ background: book.color }}>
        <div>
          <span className="bookcard__title">{book.title}</span>
          <span className="bookcard__langs bookblock__langedit">
            {owner ? (
              <>
                <select value={book.source_language} onChange={(e) => setLang({ source_language: e.target.value as any })} title="Book language">
                  <option value="en">English</option>
                  <option value="de">German</option>
                  <option value="">Other</option>
                </select>
                →
                <select value={book.translation_language} onChange={(e) => setLang({ translation_language: e.target.value })} title="Translate into">
                  {TRANSLATE_LANGS.map((l) => <option key={l} value={l}>{l}</option>)}
                </select>
              </>
            ) : (
              <>{(book.source_language || "?").toUpperCase()} → {book.translation_language} · shared by {book.owner_email}</>
            )}
            · {book.lesson_count} lessons
          </span>
        </div>
        {owner && (
          <div className="bookblock__banneractions">
            {book.lessons.some((l) => !l.processed) && (
              <button className="btn btn--ghost btn--sm" onClick={processAll}>
                Process all ({book.lessons.filter((l) => !l.processed).length})
              </button>
            )}
            <button className="btn btn--ghost btn--sm" onClick={onDelete}>Delete</button>
          </div>
        )}
      </div>
      {book.note && <div className="bookblock__note">{book.note}</div>}

      <div className="tabs bookpage__tabs">
        <button className={`tab ${tab === "lessons" ? "tab--on" : ""}`} onClick={() => setTab("lessons")}>Lessons</button>
        {owner && <button className={`tab ${tab === "share" ? "tab--on" : ""}`} onClick={() => setTab("share")}>Share</button>}
      </div>

      {error && <div className="panel panel--error">{error}</div>}

      {tab === "lessons" ? (
        <>
          {owner && book.has_pdf && (
            <div className="panel booksplit">
              <div className="booksplit__head">
                <strong>Split into lessons</strong>
                {book.lessons.length > 0 && (
                  <button className="btn btn--ghost btn--sm" onClick={() => setSplitOpen((o) => !o)}>
                    {splitOpen ? "Cancel" : "Re-split whole book"}
                  </button>
                )}
              </div>
              {(splitOpen || book.lessons.length === 0) && (
                <form className="booksplit__form" onSubmit={doSplit}>
                  <span className="books__hint">
                    {book.lessons.length === 0
                      ? "This book hasn't been split yet — slice the PDF into one sub-PDF per lesson."
                      : "Re-split the whole book (replaces all current lessons) — handy to break it into smaller chunks."}{" "}
                    Set where the first unit starts and how many pages each spans
                    (leave pages/unit blank to divide evenly across the range).
                  </span>
                  <div className="books__row">
                    <label className="cardeditor__field">
                      <span>Lesson label</span>
                      <input className="input" list="lesson-labels" value={split.label} onChange={(e) => setSplit({ ...split, label: e.target.value })} placeholder="Unit" />
                      <datalist id="lesson-labels">
                        <option value="Unit" /><option value="Lesson" /><option value="Lektion" /><option value="Kapitel" /><option value="Chapter" />
                      </datalist>
                    </label>
                    <label className="cardeditor__field">
                      <span>From</span>
                      <input className="input" type="number" min={1} value={split.from} onChange={(e) => setSplit({ ...split, from: e.target.value })} placeholder="1" />
                    </label>
                    <label className="cardeditor__field">
                      <span>To</span>
                      <input className="input" type="number" min={1} value={split.to} onChange={(e) => setSplit({ ...split, to: e.target.value })} placeholder="100" />
                    </label>
                    <label className="cardeditor__field">
                      <span>First unit page</span>
                      <input className="input" type="number" min={1} value={split.start} onChange={(e) => setSplit({ ...split, start: e.target.value })} placeholder="e.g. 6" />
                    </label>
                    <label className="cardeditor__field">
                      <span>Pages / unit</span>
                      <input className="input" type="number" min={1} value={split.ppu} onChange={(e) => setSplit({ ...split, ppu: e.target.value })} placeholder="e.g. 2" />
                    </label>
                  </div>
                  <button className="btn btn--primary" disabled={splitting}>
                    {splitting
                      ? "Splitting…"
                      : split.to && Number(split.to) >= (Number(split.from) || 1)
                        ? `Split into ${Number(split.to) - (Number(split.from) || 1) + 1} lessons`
                        : "Split into lessons"}
                  </button>
                </form>
              )}
            </div>
          )}
          <ul className="bookblock__lessons bookpage__lessons">
          {book.lessons.map((l) => (
            <li key={l.id} className="bookblock__lesson">
              <div className="bookblock__lessonrow">
                <span className="bookblock__ltitle">{l.title}</span>
                {l.page_start && (
                  <span className="bookblock__pages">
                    pp. {l.page_start}{l.page_end && l.page_end !== l.page_start ? `–${l.page_end}` : ""}
                  </span>
                )}
                {l.processed && (
                  <button className="bookblock__count bookblock__count--link" disabled={loadingLesson === l.id} onClick={() => openLesson(l)} title="Open PDF + vocab for review">
                    {loadingLesson === l.id ? "…" : `${l.card_count} vocab ›`}
                  </button>
                )}
                {owner && book.has_pdf && (
                  <button className="btn btn--ghost btn--sm" onClick={() => toggleLessonRegen(l)} title="Fix this lesson's pages (and optionally later ones)">Re-split</button>
                )}
                <button className="btn btn--ghost btn--sm" disabled={loadingLesson === l.id} onClick={() => openLesson(l)} title="Open PDF + vocab for review">
                  {loadingLesson === l.id ? "…" : "View"}
                </button>
                {owner && (
                  <button className="btn btn--primary btn--sm" disabled={working.has(l.id)} onClick={() => process(l)} title={l.processed ? "Re-extract vocabulary" : "Extract vocabulary"}>
                    {working.has(l.id) ? "…" : l.processed ? "↻" : "Process"}
                  </button>
                )}
              </div>
              {owner && regenLessonId === l.id && (
                <div className="bookblock__lessonregen">
                  <span className="books__hint">
                    Set where <strong>{l.title}</strong> really starts. “This lesson” fixes only it;
                    “From here → end” re-splits this and every later lesson with the same page size.
                  </span>
                  <div className="bookblock__regenrow">
                    <label>Start page<input className="input input--sm" type="number" min={1} value={regenL.start} onChange={(e) => setRegenL({ ...regenL, start: e.target.value })} /></label>
                    <label>Pages/unit<input className="input input--sm" type="number" min={1} value={regenL.ppu} onChange={(e) => setRegenL({ ...regenL, ppu: e.target.value })} placeholder="even" /></label>
                    <button className="btn btn--primary btn--sm" disabled={regenerating} onClick={() => doLessonRegen(l, false)}>{regenerating ? "…" : "This lesson"}</button>
                    <button className="btn btn--primary btn--sm" disabled={regenerating} onClick={() => doLessonRegen(l, true)}>{regenerating ? "…" : "From here → end"}</button>
                    <button className="btn btn--ghost btn--sm" onClick={() => setRegenLessonId(null)}>Cancel</button>
                  </div>
                </div>
              )}
            </li>
          ))}
          </ul>
        </>
      ) : (
        <div className="panel sharepanel">
          <h2>Share this book</h2>
          <p className="books__hint">Anyone you share with can view the lessons (PDF + vocab) and review them in their own decks. They can't edit or re-process.</p>
          <form className="sharepanel__add" onSubmit={onShare}>
            <input className="input" type="email" placeholder="person@example.com" value={shareEmail} onChange={(e) => setShareEmail(e.target.value)} />
            <button className="btn btn--primary">Share</button>
          </form>
          {book.shared_with.length === 0 ? (
            <p className="books__hint">Not shared with anyone yet.</p>
          ) : (
            <ul className="sharepanel__list">
              {book.shared_with.map((em) => (
                <li key={em}>
                  <span>{em}</span>
                  <button className="btn btn--ghost btn--sm" onClick={() => onUnshare(em)}>Remove</button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {lessonView && (
        <div className="lessonview" onClick={() => setLessonView(null)}>
          <div className="lessonview__card lessonview__card--split" onClick={(e) => e.stopPropagation()}>
            <div className="lessonview__head">
              <strong>{lessonView.title}</strong>
              {lessonView.page_start && (
                <span className="bookblock__pages">
                  pp. {lessonView.page_start}{lessonView.page_end && lessonView.page_end !== lessonView.page_start ? `–${lessonView.page_end}` : ""}
                </span>
              )}
              {lessonView.pdf_url && <a className="btn btn--ghost btn--sm" href={lessonView.pdf_url} target="_blank" rel="noreferrer">Open PDF in tab</a>}
              <button className="btn btn--primary btn--sm" disabled={reviewing || lessonView.cards.length === 0} onClick={reviewLesson}>
                {reviewing ? "Starting…" : "Review these cards →"}
              </button>
              <button className="btn btn--ghost btn--sm" onClick={() => setLessonView(null)}>Close</button>
            </div>
            <div className="lessonsplit">
              <div className="lessonsplit__pdf">
                {lessonView.pdf_url ? (
                  <iframe className="lessonview__pdf" src={lessonView.pdf_url} title={lessonView.title} />
                ) : (
                  <pre className="lessonview__text">{lessonView.raw_text || "(no text on these pages)"}</pre>
                )}
              </div>
              <div className="lessonsplit__vocab">
                {lessonView.cards.length === 0 ? (
                  <div className="lessonsplit__empty">No vocab yet — {owner ? "click Process on this lesson." : "the owner hasn't processed this lesson."}</div>
                ) : (
                  <ul className="vocablist">
                    {lessonView.cards.map((c, i) => (
                      <li key={i} className="vocablist__row">
                        <span className={`vocablist__front ${articleClass(c.article)}`}>
                          {c.article !== "none" ? `${c.article} ` : ""}{c.front}
                        </span>
                        {c.reading && <span className="vocablist__reading">/{c.reading}/</span>}
                        <span className="vocablist__back" dir="auto">{c.back}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
