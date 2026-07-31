import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { fetchActivity, type Deck, type ReviewActivity as Activity } from "../auth/api";

/**
 * Landing-page dashboard: what to study today, how much has been done today,
 * and what to study next. Replaces the old one-line `<ReviewActivity />` nudge
 * with the same underlying data (deck counts already loaded by the caller,
 * plus `fetchActivity()`), just answering three questions instead of one.
 */
export default function DailyDashboard({ decks }: { decks: Deck[] }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [activity, setActivity] = useState<Activity | null>(null);

  useEffect(() => {
    fetchActivity()
      .then(setActivity)
      .catch(() => {});
  }, []);

  // Deck.counts on a parent deck already rolls up its descendants (see
  // deck_counts() in the backend), so summing every deck would double-count —
  // only top-level decks give the true total.
  const topDecks = decks.filter((d) => d.parent === null);
  const totalNew = topDecks.reduce((sum, d) => sum + d.counts.new, 0);
  const totalLearning = topDecks.reduce((sum, d) => sum + d.counts.learning, 0);
  const totalDue = topDecks.reduce((sum, d) => sum + d.counts.due, 0);
  const totalStudyable = totalNew + totalLearning + totalDue;
  const nextDeck = topDecks.find(
    (d) => d.counts.new + d.counts.learning + d.counts.due > 0,
  );

  // "Goal" isn't a stored setting — it's how many cards were queued up for
  // today in total (done so far + still remaining), so the bar fills up
  // smoothly as the session progresses without needing new backend state.
  const doneToday = activity?.today.count ?? 0;
  const goal = doneToday + totalStudyable;
  const goalPct = goal > 0 ? Math.min(100, Math.round((doneToday / goal) * 100)) : 100;

  return (
    <section className="dashboard">
      <div className="dashboard__tiles">
        <div className="dashboard__tile">
          <span className="tile__label">{t("dashboard.studyTitle")}</span>
          {totalStudyable > 0 ? (
            <>
              <span className="tile__value">{totalStudyable}</span>
              <span className="tile__sub">
                {t("dashboard.studySub", { new: totalNew, learning: totalLearning, due: totalDue })}
              </span>
              <button
                className="btn btn--primary btn--sm dashboard__cta"
                onClick={() => nextDeck && navigate(`/app/study/${nextDeck.id}`)}
              >
                {t("dashboard.studyBtn")}
              </button>
            </>
          ) : (
            <span className="tile__sub">{t("dashboard.allDoneTitle")}</span>
          )}
        </div>

        <div className="dashboard__tile">
          <span className="tile__label">{t("dashboard.goalTitle")}</span>
          <span className="scorecard__meter">
            <span className="scorecard__fill" data-tone="good" style={{ width: `${goalPct}%` }} />
          </span>
          <span className="tile__sub">{t("dashboard.goalCount", { done: doneToday, goal })}</span>
          <span className="tile__sub">
            🔥 {activity?.streak ?? 0} {t("activity.dayStreak")}
          </span>
          {nextDeck ? (
            <button
              className="btn btn--primary btn--sm dashboard__cta"
              onClick={() => navigate(`/app/study/${nextDeck.id}`)}
            >
              {t("dashboard.continueBtn")}
            </button>
          ) : (
            <span className="tile__sub">{t("dashboard.allDoneTitle")}</span>
          )}
        </div>

        <div className="dashboard__tile">
          <span className="tile__label">{t("dashboard.nextTitle")}</span>
          {nextDeck ? (
            <>
              <span className="tile__value">{nextDeck.name}</span>
              <span className="tile__sub">
                {t("dashboard.nextDeckSub", {
                  count: nextDeck.counts.new + nextDeck.counts.learning + nextDeck.counts.due,
                })}
              </span>
            </>
          ) : (
            <span className="tile__sub">{t("dashboard.nextDone")}</span>
          )}
        </div>
      </div>

      <Link className="dashboard__more" to="/app/stats">
        {t("dashboard.viewStats")}
      </Link>
    </section>
  );
}
