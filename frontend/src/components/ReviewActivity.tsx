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
 * One-line nudge above the deck list: today's streak and effort, then out of the
 * way. Best-streak, all-time totals and the heatmap all live on /app/stats — the
 * deck list is where you come to *study*, so anything that pushes the decks
 * further down the page costs more than it gives.
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

  const nudge =
    data.today.count > 0
      ? t("activity.doneToday")
      : data.streak > 0
        ? t("activity.keepStreak")
        : t("activity.startToday");

  return (
    <section className="activity">
      <span className="activity__stat activity__stat--streak">
        <b>🔥 {data.streak}</b>
        <span className="activity__lbl">{t("activity.dayStreak")}</span>
      </span>
      <span className="activity__stat">
        <b>{data.today.count}</b>
        <span className="activity__lbl">
          {t("activity.today")}
          {data.today.count ? ` · ${fmtDuration(data.today.seconds)}` : ""}
        </span>
      </span>
      <span className="activity__nudge">{nudge}</span>
      <Link className="activity__more" to="/app/stats">
        {t("activity.viewStats")}
      </Link>
    </section>
  );
}
