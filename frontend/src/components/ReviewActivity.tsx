import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { fetchActivity, type ReviewActivity as Activity } from "../auth/api";
import { fmtDuration } from "./charts";

function level(count: number): number {
  if (!count) return 0;
  if (count < 5) return 1;
  if (count < 15) return 2;
  if (count < 30) return 3;
  return 4;
}

/**
 * Contribution-style heatmap of reviews over the last ~17 weeks. Forced LTR so
 * the calendar reads oldest→newest even in the Persian UI, where flipping it
 * would put "today" on the left and break the mental model people bring from
 * every other heatmap they've seen.
 */
export function ActivityHeatmap({ days }: { days: Activity["days"] }) {
  const { t } = useTranslation();
  // Pad so the first column starts on the right weekday (0 = Sunday).
  const firstDow = new Date(days[0].date + "T00:00:00").getDay();
  const cells: (Activity["days"][number] | null)[] = [...Array(firstDow).fill(null), ...days];

  return (
    <>
      <div className="activity__heatwrap" dir="ltr">
        <div className="activity__heat" role="img" aria-label={t("activity.heatmapAria")}>
          {cells.map((d, i) =>
            d ? (
              <span
                key={d.date}
                className={`heatcell heat--${level(d.count)}`}
                title={`${d.date}: ${d.count} review${d.count === 1 ? "" : "s"}${d.count ? ` · ${fmtDuration(d.seconds)}` : ""}`}
              />
            ) : (
              <span key={`pad-${i}`} className="heatcell heatcell--pad" />
            ),
          )}
        </div>
      </div>
      <div className="activity__legend">
        <span>{t("activity.less")}</span>
        <span className="heatcell heat--0" />
        <span className="heatcell heat--1" />
        <span className="heatcell heat--2" />
        <span className="heatcell heat--3" />
        <span className="heatcell heat--4" />
        <span>{t("activity.more")}</span>
      </div>
    </>
  );
}

/**
 * Motivational strip above the deck list: streak, today's effort, and a way
 * through to the full performance page. Deliberately *not* the whole analysis —
 * the deck list is where you go to study, so this stays a nudge and the charts
 * live on /app/stats.
 */
export default function ReviewActivity() {
  const { t } = useTranslation();
  const [data, setData] = useState<Activity | null>(null);

  useEffect(() => {
    fetchActivity()
      .then(setData)
      .catch(() => {});
  }, []);

  if (!data) return null;

  function message(a: Activity): string {
    if (a.today.count > 0) {
      const s = a.streak > 1 ? ` ${a.streak}-day streak 🔥` : "";
      return t("activity.msgGreat", { streak: s });
    }
    if (a.streak > 0) return t("activity.msgStreak", { count: a.streak });
    if (a.total_reviews > 0) return t("activity.msgWelcomeBack");
    return t("activity.msgStart");
  }

  return (
    <section className="activity panel">
      <div className="activity__stats">
        <div className="activity__stat activity__stat--streak">
          <span className="activity__num">🔥 {data.streak}</span>
          <span className="activity__lbl">{t("activity.dayStreak")}</span>
        </div>
        <div className="activity__stat">
          <span className="activity__num">{data.today.count}</span>
          <span className="activity__lbl">
            {t("activity.today")}
            {data.today.count ? ` · ${fmtDuration(data.today.seconds)}` : ""}
          </span>
        </div>
        <div className="activity__stat">
          <span className="activity__num">{data.longest_streak}</span>
          <span className="activity__lbl">{t("activity.bestStreak")}</span>
        </div>
        <div className="activity__stat">
          <span className="activity__num">{data.total_reviews.toLocaleString()}</span>
          <span className="activity__lbl">{t("activity.allTime")}</span>
        </div>
      </div>

      <div className="activity__foot">
        <p className="activity__msg">{message(data)}</p>
        <Link className="activity__more" to="/app/stats">
          {t("activity.viewStats")}
        </Link>
      </div>
    </section>
  );
}
