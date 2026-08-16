import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { addLibraryDeck, fetchLibraryBook, type LibraryBookDetail } from "../auth/api";

/** One library book: its published unit decks, each addable to the user's own
 * decks with one tap (a plain copy — no AI, no quota). */
export default function LibraryBook() {
  const { bookId } = useParams();
  const id = Number(bookId);
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [book, setBook] = useState<LibraryBookDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState<Set<number>>(new Set());
  const [addingAll, setAddingAll] = useState(false);
  // lesson id -> the user's own deck id, once added this visit.
  const [added, setAdded] = useState<Map<number, number | null>>(new Map());

  useEffect(() => {
    fetchLibraryBook(id)
      .then(setBook)
      .catch((err) => setError(err instanceof Error ? err.message : t("common.error")))
      .finally(() => setLoading(false));
  }, [id]);

  async function addOne(lessonId: number) {
    setAdding((s) => new Set(s).add(lessonId));
    setError(null);
    try {
      const res = await addLibraryDeck(id, lessonId);
      setAdded((m) => new Map(m).set(lessonId, res.lesson_deck));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setAdding((s) => {
        const n = new Set(s);
        n.delete(lessonId);
        return n;
      });
    }
  }

  async function addAll() {
    setAddingAll(true);
    setError(null);
    try {
      const res = await addLibraryDeck(id);
      setAdded((m) => {
        const n = new Map(m);
        for (const l of book?.lessons ?? []) if (!n.has(l.id)) n.set(l.id, null);
        return n;
      });
      navigate(`/app/decks/${res.book_deck}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
      setAddingAll(false);
    }
  }

  if (loading) return <div className="panel">{t("common.loading")}</div>;
  if (!book) return <div className="panel panel--error">{error ?? t("common.error")}</div>;

  return (
    <div className="library">
      <div className="bookpage__top">
        <button className="btn btn--ghost btn--sm" onClick={() => navigate("/app/library")}>
          {t("library.backBtn")}
        </button>
      </div>

      <div className="bookblock__banner bookpage__banner" style={{ background: book.color }}>
        <div>
          <span className="bookcard__title">{book.title}</span>
          <span className="bookcard__langs">
            {(book.source_language || "?").toUpperCase()} → {book.translation_language}
            {" · "}
            {t("decks.subdeckCount", { count: book.deck_count })}
            {" · "}
            {t("decks.cardCount", { count: book.card_count })}
          </span>
        </div>
        <div className="bookblock__banneractions">
          <button className="btn btn--ghost btn--sm" disabled={addingAll} onClick={addAll}>
            {addingAll ? t("library.adding") : t("library.addAllBtn")}
          </button>
        </div>
      </div>

      {error && <div className="panel panel--error">{error}</div>}

      <ul className="bookblock__lessons bookpage__lessons">
        {book.lessons.map((l) => {
          const deckId = added.get(l.id);
          const isAdded = added.has(l.id);
          return (
            <li key={l.id} className="bookblock__lesson">
              <div className="bookblock__lessonrow">
                <span className="bookblock__ltitle">{l.title}</span>
                <span className="bookblock__count">{t("decks.cardCount", { count: l.card_count })}</span>
                {isAdded ? (
                  deckId != null ? (
                    <Link to={`/app/decks/${deckId}`} className="btn btn--ghost btn--sm">
                      {t("library.addedBtn")}
                    </Link>
                  ) : (
                    <span className="bookblock__added">{t("library.addedBtn")}</span>
                  )
                ) : (
                  <button
                    className="btn btn--primary btn--sm"
                    disabled={adding.has(l.id)}
                    onClick={() => addOne(l.id)}
                  >
                    {adding.has(l.id) ? "…" : t("library.addBtn")}
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
