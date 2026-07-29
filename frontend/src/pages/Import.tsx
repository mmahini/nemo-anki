import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  bulkCreateCards,
  fetchBooks,
  fetchSharedBooks,
  fetchDecks,
  importAnki,
  type AnkiImportResult,
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
type Tab = "paste" | "books" | "anki";

export default function ImportPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("paste");
  const [decks, setDecks] = useState<Deck[]>([]);

  const [stage, setStage] = useState<Stage>("input");
  const [deckId, setDeckId] = useState<number | "">("");
  const [text, setText] = useState("");
  const [language, setLanguage] = useState<"de" | "en" | "">("");
  const [defaultType, setDefaultType] = useState<CardType>("vocab");
  const [drafts, setDrafts] = useState<DraftCard[]>([]);
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [books, setBooks] = useState<Book[]>([]);
  const [bookParent, setBookParent] = useState<number | "">("");
  const [added, setAdded] = useState<Record<number, string>>({}); // lessonId -> message
  const [importingLesson, setImportingLesson] = useState<number | null>(null);
  const [processingLesson, setProcessingLesson] = useState<number | null>(null);

  const [ankiFile, setAnkiFile] = useState<File | null>(null);
  const [ankiParent, setAnkiParent] = useState<number | "">("");
  const [ankiBusy, setAnkiBusy] = useState(false);
  const [ankiResult, setAnkiResult] = useState<AnkiImportResult | null>(null);

  useEffect(() => {
    fetchDecks().then(setDecks);
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
      setError(err instanceof Error ? err.message : t("common.error"));
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
      setError(err instanceof Error ? err.message : t("common.error"));
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
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setProcessingLesson(null);
    }
  }

  async function addLesson(book: Book, lessonId: number) {
    setImportingLesson(lessonId);
    setError(null);
    try {
      const res = await importBookLesson(book.id, lessonId, bookParent === "" ? null : Number(bookParent));
      setAdded((a) => ({ ...a, [lessonId]: t("import.addedCards", { count: res.cards }) }));
      fetchDecks().then(setDecks);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setImportingLesson(null);
    }
  }

  async function onImportAnki() {
    if (!ankiFile || ankiBusy) return;
    setAnkiBusy(true);
    setError(null);
    setAnkiResult(null);
    try {
      const res = await importAnki(ankiFile, ankiParent === "" ? null : Number(ankiParent));
      setAnkiResult(res);
      setAnkiFile(null);
      fetchDecks().then(setDecks);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setAnkiBusy(false);
    }
  }

  return (
    <div className="import">
      <div className="import__head">
        <div className="import__titlerow">
          <h1>{t("import.title")}</h1>
          {/* Reached from the deck list rather than the nav, so it needs its own
              way back — otherwise this page is a dead end on mobile. */}
          <Link className="btn btn--ghost btn--sm" to="/app">
            {t("decks.backBtn")}
          </Link>
        </div>
        <div className="segmented" role="group" aria-label={t("import.title")}>
          {(["paste", "books", "anki"] as const).map((key) => (
            <button
              key={key}
              className={`segmented__btn ${tab === key ? "segmented__btn--on" : ""}`}
              aria-pressed={tab === key}
              onClick={() => setTab(key)}
            >
              {t(`import.tabs.${key}`)}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="panel panel--error">{error}</div>}

      {tab === "paste" ? (
        stage === "input" ? (
          <div className="import__input">
            <div className="import__controls">
              <label>
                {t("import.languageLabel")}
                <select className="input" value={language} onChange={(e) => setLanguage(e.target.value as any)}>
                  <option value="">{t("import.languageAuto")}</option>
                  <option value="de">{t("common.german")}</option>
                  <option value="en">{t("common.english")}</option>
                </select>
              </label>
              <label>
                {t("import.defaultType")}
                <select className="input" value={defaultType} onChange={(e) => setDefaultType(e.target.value as CardType)}>
                  <option value="vocab">vocab</option>
                  <option value="sentence">sentence</option>
                  <option value="grammar">grammar</option>
                  <option value="verb">verb</option>
                </select>
              </label>
            </div>
            <textarea
              className="import__textarea"
              placeholder={t("import.textPlaceholder")}
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={14}
            />
            <button className="btn btn--primary btn--lg" disabled={busy || !text.trim()} onClick={onParse}>
              {busy ? t("import.generating") : t("import.generateBtn")}
            </button>
          </div>
        ) : (
          <div className="import__review">
            <div className="import__reviewbar">
              <div>
                <strong>{drafts.length}</strong> {t("import.draftCards", { count: drafts.length })}
                <span className="import__source"> {t("import.via", { source })}</span>
              </div>
              <div className="import__commit">
                <select className="input" value={deckId} onChange={(e) => setDeckId(e.target.value ? Number(e.target.value) : "")}>
                  <option value="">{t("import.chooseDeck")}</option>
                  {leafDecks.map((d) => (
                    <option key={d.id} value={d.id}>{d.full_name}</option>
                  ))}
                </select>
                <button className="btn btn--ghost" onClick={() => setStage("input")}>{t("import.backBtn")}</button>
                <button className="btn btn--primary" disabled={busy || !deckId || drafts.length === 0} onClick={onProceed}>
                  {t("import.proceedBtn", { count: drafts.length, deck: selectedDeck?.name ?? "deck" })}
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
      ) : tab === "books" ? (
        <div className="import__books">
          <div className="import__parentbar">
            <label>
              {t("import.addBookDecksUnder")}
              <select className="input" value={bookParent} onChange={(e) => setBookParent(e.target.value ? Number(e.target.value) : "")}>
                <option value="">{t("decks.topLevel")}</option>
                {[...decks].sort((a, b) => a.full_name.localeCompare(b.full_name)).map((d) => (
                  <option key={d.id} value={d.id}>{d.full_name}</option>
                ))}
              </select>
            </label>
          </div>

          {books.length === 0 ? (
            <div className="panel">
              {t("import.noBooks")} <Link to="/app/books">{t("nav.books")}</Link>.
            </div>
          ) : (
            books.map((b) => (
              <div key={b.id} className="bookblock">
                <div className="bookblock__banner" style={{ background: b.color }}>
                  <span className="bookcard__title">{b.title}</span>
                  <span className="bookcard__langs">
                    {(b.source_language || "?").toUpperCase()} → {b.translation_language} · {b.lesson_count} {t("books.lessons")}
                    {!b.is_owner && ` · ${t("books.sharedBy", { email: b.owner_email })}`}
                  </span>
                </div>
                <ul className="bookblock__lessons">
                  {b.lessons.map((l) => (
                    <li key={l.id} className="bookblock__lesson">
                      <span className="bookblock__ltitle">{l.title}</span>
                      {l.processed ? (
                        <span className="bookblock__count">{l.card_count} {t("import.vocab")}</span>
                      ) : (
                        <span className="bookblock__count bookblock__count--todo">{t("import.notProcessed")}</span>
                      )}
                      {added[l.id] ? (
                        <span className="bookblock__added">{added[l.id]}</span>
                      ) : l.processed ? (
                        <button
                          className="btn btn--primary btn--sm"
                          disabled={importingLesson === l.id || l.card_count === 0}
                          onClick={() => addLesson(b, l.id)}
                        >
                          {importingLesson === l.id ? t("import.adding") : t("import.add")}
                        </button>
                      ) : (
                        <button
                          className="btn btn--ghost btn--sm"
                          disabled={processingLesson === l.id}
                          onClick={() => processLesson(b, l.id)}
                        >
                          {processingLesson === l.id ? t("import.processing") : t("import.process")}
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))
          )}
        </div>
      ) : (
        <div className="import__anki">
          <div className="panel import__ankiform">
            <p className="import__ankihelp">
              {t("import.ankiHelp")}
            </p>
            <label className="import__parentbar">
              {t("import.ankiParentLabel")}
              <select
                className="input"
                value={ankiParent}
                onChange={(e) => setAnkiParent(e.target.value ? Number(e.target.value) : "")}
              >
                <option value="">{t("decks.topLevel")}</option>
                {[...decks].sort((a, b) => a.full_name.localeCompare(b.full_name)).map((d) => (
                  <option key={d.id} value={d.id}>{d.full_name}</option>
                ))}
              </select>
            </label>
            <div className="books__row books__row--file">
              <span className="books__or">{t("import.ankiPackageLabel")}</span>
              <input
                type="file"
                accept=".apkg,.colpkg"
                onChange={(e) => {
                  setAnkiFile(e.target.files?.[0] ?? null);
                  setAnkiResult(null);
                }}
              />
            </div>
            <button className="btn btn--primary btn--lg" disabled={ankiBusy || !ankiFile} onClick={onImportAnki}>
              {ankiBusy
                ? t("import.ankiImporting")
                : ankiFile
                ? t("import.ankiImportBtn", { name: ankiFile.name })
                : t("import.ankiChooseBtn")}
            </button>
            {ankiResult && (
              <div className="panel import__ankiresult">
                {t("import.ankiSuccess", {
                  cards: ankiResult.cards,
                  notes: ankiResult.notes,
                  reversed: ankiResult.reversed,
                  decks: ankiResult.decks,
                })}{" "}
                <Link to="/app">{t("import.goStudy")}</Link>
                {ankiResult.truncated && (
                  <div className="import__ankiwarn">
                    {t("import.ankiTruncated", { max: ankiResult.max_notes.toLocaleString() })}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
