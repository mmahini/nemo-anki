import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { useAuth } from "../../auth/AuthContext";
import {
  writingCheck,
  writingPrompt,
  writingToCard,
  type WritingBook,
  type WritingIssue,
  type WritingPrompt,
} from "../../auth/api";
import { NATIVE_LANGS, findLang } from "./languages";

/**
 * Write a passage, get it corrected, turn each mistake into a card.
 *
 * The reference text is optional: with one you're translating, without one
 * you're writing freely. Either way the check + "add as card" flow is the same.
 */
export default function WritePanel({
  language,
  books,
  booksLoading,
}: {
  language: string;
  books: WritingBook[];
  booksLoading: boolean;
}) {
  const { t } = useTranslation();
  const { user } = useAuth();

  const [text, setText] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [issues, setIssues] = useState<WritingIssue[] | null>(null);
  const [busyCheck, setBusyCheck] = useState(false);
  const [added, setAdded] = useState<Record<number, string>>({});
  const [adding, setAdding] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [promptSource, setPromptSource] = useState<"auto" | "books">("auto");
  const [nativeLang, setNativeLang] = useState("English");
  const [prompt, setPrompt] = useState<WritingPrompt | null>(null);
  const [promptBusy, setPromptBusy] = useState(false);
  const [selectedBookId, setSelectedBookId] = useState<number | null>(null);

  const didInitialFetch = useRef(false);

  useEffect(() => {
    if (books.length > 0 && !selectedBookId) setSelectedBookId(books[0].id);
  }, [books, selectedBookId]);

  async function fetchPrompt() {
    setPromptBusy(true);
    setError(null);
    try {
      setPrompt(
        await writingPrompt({
          language,
          translation_language: nativeLang,
          source: promptSource,
          ...(promptSource === "books" && selectedBookId ? { book_id: selectedBookId } : {}),
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.error"));
    } finally {
      setPromptBusy(false);
    }
  }

  // Default the source language to the UI language, and fetch one text to start.
  useEffect(() => {
    if (!user || didInitialFetch.current) return;
    didInitialFetch.current = true;
    const detected = user.ui_language === "fa" ? "Persian" : "English";
    setNativeLang(detected);
    writingPrompt({ language, translation_language: detected, source: "auto" })
      .then(setPrompt)
      .catch(() => {});
  }, [user, language]);

  // A stale prompt is worse than none — drop it when its inputs change.
  useEffect(() => {
    if (didInitialFetch.current) setPrompt(null);
  }, [language, nativeLang, promptSource, selectedBookId]);

  async function check() {
    if (!text.trim()) return;
    setBusyCheck(true);
    setError(null);
    setIssues(null);
    setFeedback(null);
    setAdded({});
    try {
      const r = await writingCheck(text, language);
      setIssues(r.issues);
      setFeedback(r.feedback);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.error"));
    } finally {
      setBusyCheck(false);
    }
  }

  async function addCard(issue: WritingIssue, i: number) {
    setAdding(i);
    try {
      const res = await writingToCard({
        language,
        front: issue.correction || issue.original,
        back: issue.explanation,
        notes: issue.original ? `You wrote: ${issue.original}` : "",
      });
      setAdded((a) => ({ ...a, [i]: res.deck_name }));
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.error"));
    } finally {
      setAdding(null);
    }
  }

  const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0;
  const langName = findLang(language).name;
  const noBooks = promptSource === "books" && !booksLoading && books.length === 0;
  const canFetch = promptSource === "auto" || (books.length > 0 && !!selectedBookId);

  return (
    <div className="writepanel">
      <section className="promptcard">
        <header className="promptcard__head">
          <h2 className="promptcard__title">{t("practice.referenceTitle")}</h2>
          <div className="segmented segmented--sm" role="group" aria-label={t("practice.sourceLabel")}>
            <button
              className={`segmented__btn ${promptSource === "auto" ? "segmented__btn--on" : ""}`}
              aria-pressed={promptSource === "auto"}
              onClick={() => setPromptSource("auto")}
            >
              {t("writing.promptSourceAuto")}
            </button>
            <button
              className={`segmented__btn ${promptSource === "books" ? "segmented__btn--on" : ""}`}
              aria-pressed={promptSource === "books"}
              onClick={() => setPromptSource("books")}
            >
              {t("writing.promptSourceBooks")}
            </button>
          </div>
        </header>

        <div className="promptcard__body">
          {promptBusy ? (
            <p className="promptcard__muted">{t("writing.promptLoading")}</p>
          ) : noBooks ? (
            <p className="promptcard__muted">{t("writing.noBooksHint")}</p>
          ) : prompt ? (
            <p className="promptcard__text" dir="auto">{prompt.text}</p>
          ) : (
            <p className="promptcard__muted">{t("practice.referenceEmpty")}</p>
          )}
        </div>

        <footer className="promptcard__foot">
          <label className="inlinefield">
            <span>{t("writing.promptNativeLang")}</span>
            <select
              className="input input--sm"
              value={nativeLang}
              onChange={(e) => setNativeLang(e.target.value)}
            >
              {NATIVE_LANGS.map((l) => (
                <option key={l.code} value={l.code}>{l.label}</option>
              ))}
            </select>
          </label>

          {promptSource === "books" && books.length > 0 && (
            <label className="inlinefield">
              <span>{t("writing.selectBook")}</span>
              <select
                className="input input--sm"
                value={selectedBookId ?? ""}
                onChange={(e) => setSelectedBookId(Number(e.target.value))}
              >
                {books.map((b) => (
                  <option key={b.id} value={b.id}>{b.title}</option>
                ))}
              </select>
            </label>
          )}

          {prompt?.source === "books" && prompt.book_title && (
            <span className="promptcard__source">
              📚 {[prompt.book_title, prompt.lesson_title].filter(Boolean).join(" — ")}
            </span>
          )}

          <button
            className="btn btn--ghost btn--sm promptcard__new"
            disabled={!canFetch || promptBusy}
            onClick={fetchPrompt}
          >
            {t("writing.newText")}
          </button>
        </footer>
      </section>

      <textarea
        className="import__textarea writing__textarea"
        rows={10}
        placeholder={prompt ? t("writing.translatePlaceholder", { lang: langName }) : t("writing.placeholder")}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="writing__actions">
        <span className="writing__count">{t("writing.wordCount", { count: wordCount })}</span>
        <button className="btn btn--primary" disabled={busyCheck || !text.trim()} onClick={check}>
          {busyCheck ? t("writing.checking") : t("writing.checkBtn")}
        </button>
      </div>

      {error && <p className="auth__error">{error}</p>}
      {feedback && <div className="panel writing__feedback">💬 {feedback}</div>}

      {issues &&
        (issues.length === 0 ? (
          <div className="panel writing__clean">{t("writing.clean")}</div>
        ) : (
          <div className="writing__issues">
            <div className="writing__issueshead">
              <strong>{t("writing.issuesCount_other", { count: issues.length })}</strong>
              <span className="browse__sub">{t("writing.addHint", { lang: language })}</span>
            </div>
            {issues.map((it, i) => (
              <div key={i} className="issue">
                <div className="issue__top">
                  <span className="badge">{it.type}</span>
                  {added[i] ? (
                    <span className="issue__added">{t("writing.addedTo", { deck: added[i] })}</span>
                  ) : (
                    <button
                      className="btn btn--ghost btn--sm"
                      disabled={adding === i}
                      onClick={() => addCard(it, i)}
                    >
                      {adding === i ? t("writing.addingCard") : t("writing.addCard")}
                    </button>
                  )}
                </div>
                {it.original && <div className="issue__bad">✗ {it.original}</div>}
                {it.correction && <div className="issue__good">✓ {it.correction}</div>}
                {it.explanation && <div className="issue__why">{it.explanation}</div>}
              </div>
            ))}
          </div>
        ))}

      {Object.keys(added).length > 0 && <p className="writing__hint">{t("writing.savedHint")}</p>}
    </div>
  );
}
