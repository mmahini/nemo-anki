import { useEffect, useState } from "react";

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

function message(a: Activity): string {
  if (a.today.count > 0) {
    const s = a.streak > 1 ? ` ${a.streak}-day streak 🔥` : "";
    return `Great work today!${s} Keep the momentum going.`;
  }
  if (a.streak > 0) return `Don't break your ${a.streak}-day streak 🔥 — review a few cards today!`;
  if (a.total_reviews > 0) return "Welcome back — a few reviews today restarts your streak.";
  return "Study a deck to start your streak. A little every day goes a long way!";
}

/** Motivational activity panel: streak, today's effort, and a contribution-style
 * heatmap of reviews over the last ~17 weeks. */
export default function ReviewActivity() {
  const [data, setData] = useState<Activity | null>(null);

  useEffect(() => {
    fetchActivity()
      .then(setData)
      .catch(() => {});
  }, []);

  if (!data) return null;

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
          <span className="activity__lbl">day streak</span>
        </div>
        <div className="activity__stat">
          <span className="activity__num">{data.today.count}</span>
          <span className="activity__lbl">today{data.today.count ? ` · ${fmtTime(data.today.seconds)}` : ""}</span>
        </div>
        <div className="activity__stat">
          <span className="activity__num">{data.longest_streak}</span>
          <span className="activity__lbl">best streak</span>
        </div>
        <div className="activity__stat">
          <span className="activity__num">{data.total_reviews.toLocaleString()}</span>
          <span className="activity__lbl">reviews all-time</span>
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
        <span>Less</span>
        <span className="heatcell heat--0" />
        <span className="heatcell heat--1" />
        <span className="heatcell heat--2" />
        <span className="heatcell heat--3" />
        <span className="heatcell heat--4" />
        <span>More</span>
      </div>
    </section>
  );
}
