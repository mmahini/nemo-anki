import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { fetchActivity, type Deck, type ReviewActivity as Activity } from "../auth/api";

/**
 * Home hero card: Nemo presents today's queue, the goal bar and the streak in
 * one friendly card, with the study CTA. Same data as before (deck counts from
 * the caller + fetchActivity()), just fewer boxes and more personality.
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
  const streak = activity?.streak ?? 0;

  return (
    <section className="dashboard">
      <div className="nemocard">
        <div className="nemocard__body">
          {totalStudyable > 0 ? (
            <>
              <h2 className="nemocard__title">
                {t("dashboard.heroTitle", { count: totalStudyable })}
              </h2>
              <p className="nemocard__sub">
                {t("dashboard.studySub", { new: totalNew, learning: totalLearning, due: totalDue })}
              </p>
            </>
          ) : (
            <>
              <h2 className="nemocard__title">{t("dashboard.heroDoneTitle")}</h2>
              <p className="nemocard__sub">{t("dashboard.heroDoneSub")}</p>
            </>
          )}

          <div className="nemocard__goal">
            <span className="scorecard__meter">
              <span
                className="scorecard__fill"
                data-tone="good"
                style={{ width: `${goalPct}%` }}
              />
            </span>
            <span className="nemocard__goaltext">
              {t("dashboard.goalCount", { done: doneToday, goal })}
              {streak > 0 && <> · 🔥 {streak} {t("activity.dayStreak")}</>}
            </span>
          </div>

          {nextDeck && (
            <>
              <button
                className="btn btn--primary btn--lg nemocard__cta"
                onClick={() => navigate(`/app/study/${nextDeck.id}`)}
              >
                {t("dashboard.heroCta")}
              </button>
              <span className="nemocard__next">
                {t("dashboard.nextUp", { name: nextDeck.name })}
              </span>
            </>
          )}
        </div>

        {/* Decorative — the text carries everything. Mirrored in RTL so the
            fish keeps facing the words. */}
        <img className="nemocard__img" src="/nemo-side.webp" alt="" aria-hidden />
      </div>

      <Link className="dashboard__more" to="/app/stats">
        {t("dashboard.viewStats")}
      </Link>
    </section>
  );
}
