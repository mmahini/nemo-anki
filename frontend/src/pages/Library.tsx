import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { fetchLibrary, type LibraryBook } from "../auth/api";

/** The public deck library: every book with published units, browsable by
 * anyone. Each book is a root deck; its published units are the decks a user
 * can copy into their own collection. */
export default function Library() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [books, setBooks] = useState<LibraryBook[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchLibrary()
      .then(setBooks)
      .catch((err) => setError(err instanceof Error ? err.message : t("common.error")))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="panel">{t("common.loading")}</div>;
  if (error) return <div className="panel panel--error">{error}</div>;

  return (
    <div className="library">
      <div className="bookpage__top">
        <button className="btn btn--ghost btn--sm" onClick={() => navigate("/app/decks")}>
          {t("decks.backBtn")}
        </button>
      </div>
      <h1>{t("library.title")}</h1>
      <p className="library__hint">{t("library.hint")}</p>

      {books.length === 0 ? (
        <div className="panel">{t("library.empty")}</div>
      ) : (
        <ul className="deckgrid">
          {books.map((b) => (
            <li key={b.id} className="deckcard" style={{ "--deck-accent": b.color } as React.CSSProperties}>
              <Link to={`/app/library/${b.id}`} className="deckcard__main">
                <div className="deckcard__toprow">
                  {b.source_language ? (
                    <span className={`flag flag--${b.source_language}`}>{b.source_language}</span>
                  ) : (
                    <span className="deckcard__dot" />
                  )}
                  <span className="deckcard__meta">
                    {t("decks.subdeckCount", { count: b.deck_count })} · {t("decks.cardCount", { count: b.card_count })}
                  </span>
                </div>
                <h2 className="deckcard__name">{b.title}</h2>
              </Link>
              <div className="deckcard__foot">
                <span className="deckcard__meta">→ {b.translation_language}</span>
                <Link to={`/app/library/${b.id}`} className="btn btn--primary btn--sm">
                  {t("library.openBtn")}
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
