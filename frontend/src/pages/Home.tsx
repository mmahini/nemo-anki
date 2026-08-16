import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  fetchBooks,
  fetchDecks,
  fetchReelsUnseenCount,
  fetchSharedBooks,
  type Deck,
} from "../auth/api";
import { useAuth } from "../auth/AuthContext";
import DailyDashboard from "../components/DailyDashboard";
import StudyBuddyCard from "../components/StudyBuddyCard";

/** Home: today's numbers and the study CTA (DailyDashboard), plus the
 * doorways that used to crowd the deck list — Books and Import. The deck
 * list itself is now purely about managing decks. */
export default function Home() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [decks, setDecks] = useState<Deck[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newReels, setNewReels] = useState(0);
  // Books is a doorway most users never need — it only earns a slot once they
  // actually have a book (their own or shared with them), and then at the
  // bottom, after the everyone-features.
  const [hasBooks, setHasBooks] = useState(false);

  useEffect(() => {
    fetchDecks()
      .then(setDecks)
      .catch((err) => setError(err instanceof Error ? err.message : t("common.error")));
    // Best-effort badge; the card is a doorway either way.
    fetchReelsUnseenCount()
      .then((r) => setNewReels(r.count))
      .catch(() => {});
    Promise.all([fetchBooks().catch(() => []), fetchSharedBooks().catch(() => [])])
      .then(([own, shared]) => setHasBooks(own.length > 0 || shared.length > 0))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const firstName = user?.display_name?.trim().split(/\s+/)[0] ?? "";

  return (
    <div className="home">
      <h1 className="home__greeting">
        {firstName ? t("home.greeting", { name: firstName }) : t("home.greetingNoName")}
      </h1>

      {error ? (
        <div className="panel panel--error">{error}</div>
      ) : decks === null ? (
        <div className="panel">{t("common.loading")}</div>
      ) : decks.length === 0 ? (
        <div className="panel decks__empty">
          <h2>{t("home.noDecksTitle")}</h2>
          <p>{t("home.noDecksHint")}</p>
          <Link className="btn btn--primary" to="/app/decks">
            {t("home.goDecksBtn")}
          </Link>
        </div>
      ) : (
        <DailyDashboard decks={decks} />
      )}

      <StudyBuddyCard />

      <div className="home__grid">
        <Link className="homecard" to="/app/reels">
          <span className="homecard__icon" aria-hidden>🎬</span>
          <span>
            <span className="homecard__title">
              {t("home.reelsTitle")}
              {newReels > 0 && (
                <span className="homecard__badge">
                  {t("home.reelsNew", { count: Math.min(newReels, 99) })}
                </span>
              )}
            </span>
            <span className="homecard__body">
              {newReels > 0 ? t("home.reelsBodyNew") : t("home.reelsBody")}
            </span>
          </span>
        </Link>
        <Link className="homecard" to="/app/import">
          <span className="homecard__icon" aria-hidden>↓</span>
          <span>
            <span className="homecard__title">{t("home.importTitle")}</span>
            <span className="homecard__body">{t("home.importBody")}</span>
          </span>
        </Link>
        {hasBooks && (
          <Link className="homecard" to="/app/books">
            <span className="homecard__icon" aria-hidden>📖</span>
            <span>
              <span className="homecard__title">{t("home.booksTitle")}</span>
              <span className="homecard__body">{t("home.booksBody")}</span>
            </span>
          </Link>
        )}
      </div>
    </div>
  );
}
