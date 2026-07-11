import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { useAuth } from "../auth/AuthContext";
import {
  writingCheck,
  writingPrompt,
  writingToCard,
  type WritingIssue,
  type WritingPrompt,
} from "../auth/api";

const LANGS = [
  { code: "de", name: "German" },
  { code: "en", name: "English" },
  { code: "fr", name: "French" },
  { code: "es", name: "Spanish" },
  { code: "it", name: "Italian" },
];

const NATIVE_LANGS = [
  { code: "English", label: "English" },
  { code: "Persian", label: "Persian / فارسی" },
  { code: "French", label: "French / Français" },
  { code: "Spanish", label: "Spanish / Español" },
  { code: "Italian", label: "Italian / Italiano" },
  { code: "Arabic", label: "Arabic / العربية" },
  { code: "Russian", label: "Russian / Русский" },
  { code: "Chinese", label: "Chinese / 中文" },
  { code: "Turkish", label: "Turkish / Türkçe" },
];

export default function Writing() {
  const { t } = useTranslation();
  const { user } = useAuth();

  const [language, setLanguage] = useState("de");
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

  const didInitialFetch = useRef(false);

  async function doFetchPrompt(lang: string, native: string, src: "auto" | "books") {
    setPromptBusy(true);
    setError(null);
    try {
      setPrompt(await writingPrompt({ language: lang, translation_language: native, source: src }));
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.error"));
    } finally {
      setPromptBusy(false);
    }
  }

  // Auto-load on first user load and set native language from UI language
  useEffect(() => {
    if (!user) return;
    const detected = user.ui_language === "fa" ? "Persian" : "English";
    setNativeLang(detected);
    if (!didInitialFetch.current) {
      didInitialFetch.current = true;
      doFetchPrompt(language, detected, promptSource);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  // Clear prompt when settings change (user clicks different options)
  useEffect(() => {
    if (didInitialFetch.current) {
      setPrompt(null);
    }
  }, [language, nativeLang, promptSource]);

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
  const langName = LANGS.find((l) => l.code === language)?.name ?? language;

  return (
    <div className="writing">
      <h1>{t("writing.title")}</h1>
      <p className="import__sub">{t("writing.subtitle")}</p>

      <div className="writing__bar">
        <label className="cardeditor__field">
          <span>{t("writing.languageLabel")}</span>
          <select className="input" value={language} onChange={(e) => setLanguage(e.target.value)}>
            {LANGS.map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
          </select>
        </label>
        <label className="cardeditor__field">
          <span>{t("writing.promptNativeLang")}</span>
          <select className="input" value={nativeLang} onChange={(e) => setNativeLang(e.target.value)}>
            {NATIVE_LANGS.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
          </select>
        </label>
        <div className="writing__source-toggle">
          <button
            className={`btn btn--sm ${promptSource === "auto" ? "btn--primary" : "btn--ghost"}`}
            onClick={() => setPromptSource("auto")}
          >
            {t("writing.promptSourceAuto")}
          </button>
          <button
            className={`btn btn--sm ${promptSource === "books" ? "btn--primary" : "btn--ghost"}`}
            onClick={() => setPromptSource("books")}
          >
            {t("writing.promptSourceBooks")}
          </button>
        </div>
      </div>

      {/* Reference text panel */}
      <div className="panel writing__prompt">
        {promptBusy ? (
          <p className="writing__prompt-loading">{t("writing.promptLoading")}</p>
        ) : prompt ? (
          <>
            <p className="writing__prompt-text" dir="auto">{prompt.text}</p>
            <div className="writing__prompt-footer">
              {prompt.source === "books" && prompt.book_title && (
                <span className="writing__prompt-source">
                  📚 {[prompt.book_title, prompt.lesson_title].filter(Boolean).join(" — ")}
                </span>
              )}
              <button
                className="btn btn--ghost btn--sm writing__prompt-newbtn"
                onClick={() => doFetchPrompt(language, nativeLang, promptSource)}
              >
                {t("writing.newText")}
              </button>
            </div>
          </>
        ) : (
          <div className="writing__prompt-empty">
            <button
              className="btn btn--primary btn--sm"
              onClick={() => doFetchPrompt(language, nativeLang, promptSource)}
            >
              {t("writing.newText")}
            </button>
          </div>
        )}
      </div>

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

      {issues && (
        issues.length === 0 ? (
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
                    <button className="btn btn--ghost btn--sm" disabled={adding === i} onClick={() => addCard(it, i)}>
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
        )
      )}

      {Object.keys(added).length > 0 && (
        <p className="writing__hint">{t("writing.savedHint")}</p>
      )}
    </div>
  );
}
