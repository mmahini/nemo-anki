import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { conversationText, type WritingBook } from "../../auth/api";
import { findLang, randomFallback } from "./languages";
import { useSpeech } from "./useSpeech";

type WordResult = { word: string; ok: boolean };

/** Compare what was read aloud against the passage, word by word. Punctuation and
 * case are ignored — the point is pronunciation, not typing. */
function diffWords(original: string, spoken: string): WordResult[] {
  const clean = (s: string) => s.toLowerCase().replace(/[.,!?;:'"„“«»]/g, "");
  const spokenSet = new Set(spoken.trim().split(/\s+/).map(clean));
  return original.trim().split(/\s+/).map((w) => ({ word: w, ok: spokenSet.has(clean(w)) }));
}

/** Read a passage aloud and see which words came through. */
export default function ReadPanel({
  language,
  books,
}: {
  language: string;
  books: WritingBook[];
}) {
  const { t } = useTranslation();
  const lang = findLang(language);
  const { supported, listening, speak, toggle, stop } = useSpeech(lang.speech);

  const [text, setText] = useState<string | null>(null);
  const [source, setSource] = useState<string | null>(null);
  const [bookTitle, setBookTitle] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<WordResult[] | null>(null);
  const [bookId, setBookId] = useState<number | "">("");

  // A passage in the old language is no use after switching.
  useEffect(() => {
    stop();
    setText(null);
    setResult(null);
  }, [language, stop]);

  async function fetchText() {
    setBusy(true);
    setResult(null);
    setText(null);
    setSource(null);
    setBookTitle(null);
    try {
      const res = await conversationText({
        language,
        ...(bookId ? { book_id: Number(bookId) } : {}),
      });
      setText(res.text);
      setSource(res.source);
      setBookTitle(res.book_title ?? null);
    } catch {
      // Better a canned passage than an empty tab.
      setText(randomFallback(language));
      setSource("fallback");
    } finally {
      setBusy(false);
    }
  }

  const correct = result ? result.filter((w) => w.ok).length : 0;
  const score = result && result.length ? correct / result.length : 0;

  return (
    <div className="readpanel">
      {!supported && (
        <div className="panel panel--error conv__nospeech">{t("conversation.noSpeechSupport")}</div>
      )}

      <div className="readpanel__bar">
        {books.length > 0 && (
          <label className="inlinefield">
            <span>{t("writing.selectBook")}</span>
            <select
              className="input input--sm"
              value={bookId}
              onChange={(e) => setBookId(e.target.value ? Number(e.target.value) : "")}
            >
              <option value="">{t("conversation.autoSource")}</option>
              {books.map((b) => (
                <option key={b.id} value={b.id}>{b.title}</option>
              ))}
            </select>
          </label>
        )}
        <button className="btn btn--primary btn--sm" disabled={busy} onClick={fetchText}>
          {busy ? t("conversation.fetchingText") : t("conversation.fetchText")}
        </button>
      </div>

      {!text && !busy && <p className="promptcard__muted">{t("practice.readEmpty")}</p>}

      {text && (
        <>
          <div className="panel conv__read-panel">
            <p className="conv__read-text" dir="auto">
              {result
                ? result.map((wr, i) => (
                    <span key={i} className={`conv__word conv__word--${wr.ok ? "ok" : "bad"}`}>
                      {wr.word}{" "}
                    </span>
                  ))
                : text}
            </p>
            <div className="conv__read-footer">
              <button className="btn btn--ghost btn--sm conv__play" onClick={() => speak(text)}>
                ▶ {t("conversation.listenBtn")}
              </button>
              {source === "books" && bookTitle && (
                <span className="promptcard__source">📚 {bookTitle}</span>
              )}
            </div>
          </div>

          {/* The score reads as a result, not a stray line of text. */}
          {result && (
            <div className="scorecard">
              <div className="scorecard__top">
                <strong className="scorecard__value">
                  {correct}/{result.length}
                </strong>
                <span className="scorecard__label">{t("conversation.correct")}</span>
                <button className="btn btn--ghost btn--sm scorecard__retry" onClick={() => setResult(null)}>
                  {t("conversation.tryAgain")}
                </button>
              </div>
              <span className="scorecard__meter">
                <span
                  className="scorecard__fill"
                  style={{ width: `${score * 100}%` }}
                  /* Green once most of it landed, amber while it hasn't. */
                  data-tone={score >= 0.8 ? "good" : score >= 0.5 ? "mid" : "low"}
                />
              </span>
            </div>
          )}

          {supported && (
            <div className="readpanel__controls">
              <button
                className={`btn conv__mic${listening ? " btn--ghost conv__mic--active" : " btn--primary"}`}
                onClick={() => toggle((spoken) => setResult(diffWords(text, spoken)))}
              >
                {listening
                  ? `⏹ ${t("conversation.stopReading")}`
                  : `🎙 ${t("conversation.startReading")}`}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
