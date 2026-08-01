import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { fetchDecks, type Deck } from "../auth/api";
import { useAuth } from "../auth/AuthContext";
import DailyDashboard from "../components/DailyDashboard";

/** Home: today's numbers and the study CTA (DailyDashboard), plus the
 * doorways that used to crowd the deck list — Books and Import. The deck
 * list itself is now purely about managing decks. */
export default function Home() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [decks, setDecks] = useState<Deck[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchDecks()
      .then(setDecks)
      .catch((err) => setError(err instanceof Error ? err.message : t("common.error")));
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

      <div className="home__grid">
        <Link className="homecard" to="/app/books">
          <span className="homecard__icon" aria-hidden>📖</span>
          <span>
            <span className="homecard__title">{t("home.booksTitle")}</span>
            <span className="homecard__body">{t("home.booksBody")}</span>
          </span>
        </Link>
        <Link className="homecard" to="/app/import">
          <span className="homecard__icon" aria-hidden>↓</span>
          <span>
            <span className="homecard__title">{t("home.importTitle")}</span>
            <span className="homecard__body">{t("home.importBody")}</span>
          </span>
        </Link>
      </div>
    </div>
  );
}
