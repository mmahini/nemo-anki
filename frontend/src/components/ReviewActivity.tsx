import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { fetchActivity, type ReviewActivity as Activity } from "../auth/api";

function level(count: number): number {
  if (!count) return 0;
  if (count < 5) return 1;
  if (count < 15) return 2;
  if (count < 30) return 3;
  return 4;
}

function fmtTime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.round(seconds / 60);
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

/** Motivational activity panel: streak, today's effort, and a contribution-style
 * heatmap of reviews over the last ~17 weeks. */
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

  // Pad so the first column starts on the right weekday (0 = Sunday).
  const firstDow = new Date(data.days[0].date + "T00:00:00").getDay();
  const cells: (Activity["days"][number] | null)[] = [
    ...Array(firstDow).fill(null),
    ...data.days,
  ];

  return (
    <section className="activity panel">
      <div className="activity__stats">
        <div className="activity__stat activity__stat--streak">
          <span className="activity__num">🔥 {data.streak}</span>
          <span className="activity__lbl">{t("activity.dayStreak")}</span>
        </div>
        <div className="activity__stat">
          <span className="activity__num">{data.today.count}</span>
          <span className="activity__lbl">{t("activity.today")}{data.today.count ? ` · ${fmtTime(data.today.seconds)}` : ""}</span>
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

      <p className="activity__msg">{message(data)}</p>

      <div className="activity__heatwrap">
        <div className="activity__heat" role="img" aria-label="Review activity over the last weeks">
          {cells.map((d, i) =>
            d ? (
              <span
                key={d.date}
                className={`heatcell heat--${level(d.count)}`}
                title={`${d.date}: ${d.count} review${d.count === 1 ? "" : "s"}${d.count ? ` · ${fmtTime(d.seconds)}` : ""}`}
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
    </section>
  );
}
