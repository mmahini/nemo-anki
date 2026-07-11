import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

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

function lessonNum(title: string): number {
  const m = /(\d+)/.exec(title || "");
  return m ? Number(m[1]) : 0;
}
function lessonLabel(title: string): string {
  const m = /^(.*?)\s*\d+/.exec(title || "");
  return (m && m[1].trim()) || "Unit";
}

type Tab = "lessons" | "share";

export default function BookPage() {
  const { bookId } = useParams();
  const id = Number(bookId);
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [book, setBook] = useState<Book | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("lessons");

  const [working, setWorking] = useState<Set<number>>(new Set());
  const [regenerating, setRegenerating] = useState(false);
  const [regenLessonId, setRegenLessonId] = useState<number | null>(null);
  const [regenL, setRegenL] = useState({ start: "", ppu: "" });

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
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (loading) return <div className="panel">{t("common.loading")}</div>;
  if (!book) return <div className="panel panel--error">{error ?? t("common.error")}</div>;
  const owner = book.is_owner;

  async function process(lesson: BookLesson) {
    setWorking((w) => new Set(w).add(lesson.id));
    setError(null);
    try {
      await processBookLesson(book!.id, lesson.id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
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
    const overlap = book!.lessons.filter((l) => {
      const n = lessonNum(l.title);
      return n >= from && n <= to;
    }).length;
    if (overlap > 0 && !window.confirm(`Re-splitting replaces ${overlap} lesson${overlap === 1 ? "" : "s"} in units ${from}–${to} (their extracted vocab is cleared). Other lessons are kept. Continue?`)) {
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
      });
      setBook(updated);
      setSplitOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
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
      setError(err instanceof Error ? err.message : t("common.error"));
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
      setError(err instanceof Error ? err.message : t("common.error"));
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
      setError(err instanceof Error ? err.message : t("common.error"));
      setReviewing(false);
    }
  }

  async function setLang(patch: Partial<{ source_language: "de" | "en" | ""; translation_language: string }>) {
    try {
      setBook(await updateBook(book!.id, patch as any));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    }
  }

  async function onDelete() {
    if (!window.confirm(t("books.confirmDelete", { title: book!.title }))) return;
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
      setError(err instanceof Error ? err.message : t("common.error"));
    }
  }

  async function onUnshare(email: string) {
    setBook(await unshareBook(book!.id, email));
  }

  const splitCount = split.to && Number(split.to) >= (Number(split.from) || 1)
    ? Number(split.to) - (Number(split.from) || 1) + 1
    : 0;

  return (
    <div className="bookpage">
      <div className="bookpage__top">
        <button className="btn btn--ghost btn--sm" onClick={() => navigate("/app/books")}>{t("bookPage.backBtn")}</button>
      </div>

      <div className="bookblock__banner bookpage__banner" style={{ background: book.color }}>
        <div>
          <span className="bookcard__title">{book.title}</span>
          <span className="bookcard__langs bookblock__langedit">
            {owner ? (
              <>
                <select value={book.source_language} onChange={(e) => setLang({ source_language: e.target.value as any })} title={t("books.bookLanguage")}>
                  <option value="en">{t("common.english")}</option>
                  <option value="de">{t("common.german")}</option>
                  <option value="">{t("common.other")}</option>
                </select>
                →
                <select value={book.translation_language} onChange={(e) => setLang({ translation_language: e.target.value })} title={t("books.translateInto")}>
                  {TRANSLATE_LANGS.map((l) => <option key={l} value={l}>{l}</option>)}
                </select>
              </>
            ) : (
              <>{(book.source_language || "?").toUpperCase()} → {book.translation_language} · {t("bookPage.sharedBy", { email: book.owner_email })}</>
            )}
            · {book.lesson_count} {t("bookPage.lessons")}
          </span>
        </div>
        {owner && (
          <div className="bookblock__banneractions">
            {book.lessons.some((l) => !l.processed) && (
              <button className="btn btn--ghost btn--sm" onClick={processAll}>
                {t("bookPage.processAll", { count: book.lessons.filter((l) => !l.processed).length })}
              </button>
            )}
            <button className="btn btn--ghost btn--sm" onClick={onDelete}>{t("bookPage.deleteBtn")}</button>
          </div>
        )}
      </div>
      {book.note && <div className="bookblock__note">{book.note}</div>}

      <div className="tabs bookpage__tabs">
        <button className={`tab ${tab === "lessons" ? "tab--on" : ""}`} onClick={() => setTab("lessons")}>{t("bookPage.lessonsTab")}</button>
        {owner && <button className={`tab ${tab === "share" ? "tab--on" : ""}`} onClick={() => setTab("share")}>{t("bookPage.shareTab")}</button>}
      </div>

      {error && <div className="panel panel--error">{error}</div>}

      {tab === "lessons" ? (
        <>
          {owner && book.has_pdf && (
            <div className="panel booksplit">
              <div className="booksplit__head">
                <strong>{t("bookPage.splitTitle")}</strong>
                {book.lessons.length > 0 && (
                  <button className="btn btn--ghost btn--sm" onClick={() => setSplitOpen((o) => !o)}>
                    {splitOpen ? t("bookPage.cancelSplit") : t("bookPage.splitMore")}
                  </button>
                )}
              </div>
              {(splitOpen || book.lessons.length === 0) && (
                <form className="booksplit__form" onSubmit={doSplit}>
                  <span className="books__hint">
                    {book.lessons.length === 0
                      ? "This book hasn't been split yet — slice the PDF into one sub-PDF per lesson."
                      : "Split another range into lessons — only the units in From–To are (re)created; your other lessons stay."}{" "}
                    Set where the first unit starts and how many pages each spans
                    (leave pages/unit blank to divide evenly across the range).
                  </span>
                  <div className="books__row">
                    <label className="cardeditor__field">
                      <span>{t("bookPage.lessonLabel")}</span>
                      <input className="input" list="lesson-labels" value={split.label} onChange={(e) => setSplit({ ...split, label: e.target.value })} placeholder="Unit" />
                      <datalist id="lesson-labels">
                        <option value="Unit" /><option value="Lesson" /><option value="Lektion" /><option value="Kapitel" /><option value="Chapter" />
                      </datalist>
                    </label>
                    <label className="cardeditor__field">
                      <span>{t("bookPage.fromLabel")}</span>
                      <input className="input" type="number" min={1} value={split.from} onChange={(e) => setSplit({ ...split, from: e.target.value })} placeholder="1" />
                    </label>
                    <label className="cardeditor__field">
                      <span>{t("bookPage.toLabel")}</span>
                      <input className="input" type="number" min={1} value={split.to} onChange={(e) => setSplit({ ...split, to: e.target.value })} placeholder="100" />
                    </label>
                    <label className="cardeditor__field">
                      <span>{t("bookPage.firstPageLabel")}</span>
                      <input className="input" type="number" min={1} value={split.start} onChange={(e) => setSplit({ ...split, start: e.target.value })} placeholder="e.g. 6" />
                    </label>
                    <label className="cardeditor__field">
                      <span>{t("bookPage.pagesPerUnit")}</span>
                      <input className="input" type="number" min={1} value={split.ppu} onChange={(e) => setSplit({ ...split, ppu: e.target.value })} placeholder="e.g. 2" />
                    </label>
                  </div>
                  <button className="btn btn--primary" disabled={splitting}>
                    {splitting
                      ? t("bookPage.splitting")
                      : splitCount > 0
                        ? t("bookPage.splitBtn", { count: splitCount })
                        : t("bookPage.splitBtnGeneric")}
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
                  <button className="btn btn--ghost btn--sm" onClick={() => toggleLessonRegen(l)} title="Fix this lesson's pages">{t("bookPage.reSplit")}</button>
                )}
                <button className="btn btn--ghost btn--sm" disabled={loadingLesson === l.id} onClick={() => openLesson(l)}>
                  {loadingLesson === l.id ? "…" : t("bookPage.viewBtn")}
                </button>
                {owner && (
                  <button className="btn btn--primary btn--sm" disabled={working.has(l.id)} onClick={() => process(l)}>
                    {working.has(l.id) ? "…" : l.processed ? "↻" : t("import.process")}
                  </button>
                )}
              </div>
              {owner && regenLessonId === l.id && (
                <div className="bookblock__lessonregen">
                  <span className="books__hint">
                    Set where <strong>{l.title}</strong> really starts. "This lesson" fixes only it;
                    "From here → end" re-splits this and every later lesson with the same page size.
                  </span>
                  <div className="bookblock__regenrow">
                    <label>Start page<input className="input input--sm" type="number" min={1} value={regenL.start} onChange={(e) => setRegenL({ ...regenL, start: e.target.value })} /></label>
                    <label>Pages/unit<input className="input input--sm" type="number" min={1} value={regenL.ppu} onChange={(e) => setRegenL({ ...regenL, ppu: e.target.value })} placeholder="even" /></label>
                    <button className="btn btn--primary btn--sm" disabled={regenerating} onClick={() => doLessonRegen(l, false)}>{regenerating ? "…" : "This lesson"}</button>
                    <button className="btn btn--primary btn--sm" disabled={regenerating} onClick={() => doLessonRegen(l, true)}>{regenerating ? "…" : "From here → end"}</button>
                    <button className="btn btn--ghost btn--sm" onClick={() => setRegenLessonId(null)}>{t("bookPage.cancelSplit")}</button>
                  </div>
                </div>
              )}
            </li>
          ))}
          </ul>
        </>
      ) : (
        <div className="panel sharepanel">
          <h2>{t("bookPage.shareTitle")}</h2>
          <p className="books__hint">{t("bookPage.shareHint")}</p>
          <form className="sharepanel__add" onSubmit={onShare}>
            <input className="input" type="email" placeholder={t("bookPage.shareEmailPlaceholder")} value={shareEmail} onChange={(e) => setShareEmail(e.target.value)} />
            <button className="btn btn--primary">{t("bookPage.shareBtn")}</button>
          </form>
          {book.shared_with.length === 0 ? (
            <p className="books__hint">{t("bookPage.notShared")}</p>
          ) : (
            <ul className="sharepanel__list">
              {book.shared_with.map((em) => (
                <li key={em}>
                  <span>{em}</span>
                  <button className="btn btn--ghost btn--sm" onClick={() => onUnshare(em)}>{t("bookPage.removeBtn")}</button>
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
              {lessonView.pdf_url && <a className="btn btn--ghost btn--sm" href={lessonView.pdf_url} target="_blank" rel="noreferrer">{t("bookPage.openPDF")}</a>}
              <button className="btn btn--primary btn--sm" disabled={reviewing || lessonView.cards.length === 0} onClick={reviewLesson}>
                {reviewing ? t("bookPage.starting") : t("bookPage.reviewCards")}
              </button>
              <button className="btn btn--ghost btn--sm" onClick={() => setLessonView(null)}>{t("bookPage.closeBtn")}</button>
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
                  <div className="lessonsplit__empty">{t("bookPage.noVocab")}</div>
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
