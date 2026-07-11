import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

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
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("mine");
  const [mine, setMine] = useState<Book[]>([]);
  const [shared, setShared] = useState<Book[]>([]);
  const [loading, setLoading] = useState(true);

  const [title, setTitle] = useState("");
  const [sourceLang, setSourceLang] = useState<"de" | "en" | "">("en");
  const [transLang, setTransLang] = useState("English");
  const [file, setFile] = useState<File | null>(null);
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
      setError(t("books.errorUpload"));
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
      });
      setTitle("");
      setFile(null);
      navigate(`/app/books/${book.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setUploading(false);
    }
  }

  async function onDelete(b: Book) {
    if (!window.confirm(t("books.confirmDelete", { title: b.title }))) return;
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
            {(b.source_language || "?").toUpperCase()} → {b.translation_language} · {b.lesson_count} {t("books.lessons")}
            {!b.is_owner && ` ${t("books.sharedBy", { email: b.owner_email })}`}
          </span>
        </button>
        <div className="bookcard__body">
          <span className="bookcard__meta">{t("books.vocabCount", { count: b.card_count })}</span>
          <div className="bookcard__actions">
            <button className="btn btn--primary btn--sm" onClick={() => navigate(`/app/books/${b.id}`)}>{t("books.openBtn")}</button>
            {b.is_owner && <button className="btn btn--ghost btn--sm" onClick={() => onDelete(b)}>{t("books.deleteBtn")}</button>}
          </div>
        </div>
      </li>
    );
  }

  return (
    <div className="books">
      <h1>{t("books.title")}</h1>

      <form className="books__upload panel" onSubmit={onUpload}>
        <div className="books__row">
          <label className="cardeditor__field" style={{ flex: 2 }}>
            <span>{t("books.bookTitle")}</span>
            <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t("books.bookTitlePlaceholder")} />
          </label>
          <label className="cardeditor__field">
            <span>{t("books.bookLanguage")}</span>
            <select className="input" value={sourceLang} onChange={(e) => setSourceLang(e.target.value as any)}>
              <option value="en">{t("common.english")}</option>
              <option value="de">{t("common.german")}</option>
              <option value="">{t("common.other")}</option>
            </select>
          </label>
          <label className="cardeditor__field">
            <span>{t("books.translateInto")}</span>
            <select className="input" value={transLang} onChange={(e) => setTransLang(e.target.value)}>
              {TRANSLATE_LANGS.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </label>
        </div>
        <div className="books__row books__row--file">
          <span className="books__or">{t("books.bookFile")}</span>
          <input type="file" accept=".txt,.pdf,text/plain,application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </div>
        <span className="books__hint">
          {t("books.uploadHint")}
        </span>
        {error && <p className="auth__error">{error}</p>}
        <button className="btn btn--primary btn--lg" disabled={uploading}>
          {uploading ? t("books.uploading") : t("books.createBtn")}
        </button>
      </form>

      <div className="tabs books__tabs">
        <button className={`tab ${tab === "mine" ? "tab--on" : ""}`} onClick={() => setTab("mine")}>{t("books.myBooks", { count: mine.length })}</button>
        <button className={`tab ${tab === "shared" ? "tab--on" : ""}`} onClick={() => setTab("shared")}>{t("books.sharedWithMe", { count: shared.length })}</button>
      </div>

      {loading ? (
        <div className="panel">{t("books.loading")}</div>
      ) : list.length === 0 ? (
        <div className="panel">{tab === "mine" ? t("books.noBooks") : t("books.noShared")}</div>
      ) : (
        <ul className="books__list">{list.map(bookCard)}</ul>
      )}
    </div>
  );
}
