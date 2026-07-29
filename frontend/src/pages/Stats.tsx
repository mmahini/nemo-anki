import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  fetchActivity,
  fetchStatsOverview,
  type ReviewActivity as Activity,
  type StatsOverview,
  type StatsRange,
} from "../auth/api";
import { ActivityHeatmap } from "../components/ReviewActivity";
import {
  BarRows,
  ChartCard,
  ColumnChart,
  Legend,
  ShareBar,
  fmtCount,
  fmtDuration,
  fmtPercent,
  niceMax,
  type Column,
} from "../components/charts";

const RANGES: StatsRange[] = [7, 30, 90, 365];

/** Maturity ramp — one hue, light→dark, so the progression reads as an order. */
const RAMP = ["var(--sr-1)", "var(--sr-2)", "var(--sr-3)", "var(--sr-4)"];
const ONE_HUE = "var(--sr-3)";

/**
 * Axis and tooltip dates. Persian gets the Jalali calendar — "۹ تیر" is the date
 * a Persian speaker recognises — but with `-u-nu-latn` so the digits stay Latin,
 * matching every count and percentage elsewhere in the app.
 */
function dateFmt(lang: string, opts: Intl.DateTimeFormatOptions) {
  return new Intl.DateTimeFormat(lang === "fa" ? "fa-IR-u-nu-latn" : "en-GB", opts);
}

/** A stat tile — the right form when the answer is a single number. */
function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="tile">
      <span className="tile__label">{label}</span>
      <span className="tile__value">{value}</span>
      {sub && <span className="tile__sub">{sub}</span>}
    </div>
  );
}

export default function Stats() {
  const { t, i18n } = useTranslation();
  const [range, setRange] = useState<StatsRange>(30);
  const [data, setData] = useState<StatsOverview | null>(null);
  const [activity, setActivity] = useState<Activity | null>(null);
  // `refreshing` keeps the previous render on screen at reduced opacity while a
  // new range loads — no skeleton, no layout jump.
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchActivity().then(setActivity).catch(() => {});
  }, []);

  useEffect(() => {
    let stale = false;
    setRefreshing(true);
    fetchStatsOverview(range)
      .then((res) => {
        if (stale) return;
        setData(res);
        setError(null);
      })
      .catch((err) => !stale && setError(err instanceof Error ? err.message : t("common.error")))
      .finally(() => !stale && setRefreshing(false));
    return () => {
      stale = true;
    };
  }, [range]);

  if (error && !data) return <div className="panel panel--error">{error}</div>;
  if (!data) return <div className="panel">{t("stats.loading")}</div>;

  const { range: r, collection: c, forecast, intervals, decks, leeches } = data;
  const dayLabel = dateFmt(i18n.language, { day: "numeric", month: "short" });
  const dayFull = dateFmt(i18n.language, { weekday: "short", day: "numeric", month: "short" });

  const maturitySeries = [
    { key: "new", label: t("stats.seriesNew"), color: RAMP[0] },
    { key: "learning", label: t("stats.seriesLearning"), color: RAMP[1] },
    { key: "review", label: t("stats.seriesReview"), color: RAMP[2] },
  ];

  // One tick per ~6 columns keeps the axis readable at every range length.
  const tickStep = Math.max(1, Math.ceil(r.days.length / 6));
  const dailyColumns: Column[] = r.days.map((d, i) => {
    const date = new Date(d.date + "T00:00:00");
    return {
      key: d.date,
      label: dayFull.format(date),
      tick: i % tickStep === 0 ? dayLabel.format(date) : undefined,
      values: [d.new, d.learning, d.review],
      note: d.seconds ? fmtDuration(d.seconds) : undefined,
    };
  });

  const forecastColumns: Column[] = forecast.map((d, i) => {
    const date = new Date(d.date + "T00:00:00");
    return {
      key: d.date,
      label: i === 0 ? t("stats.today") : dayFull.format(date),
      tick: i % 5 === 0 ? (i === 0 ? t("stats.today") : dayLabel.format(date)) : undefined,
      values: [d.count],
      note: t("stats.cumulative", { count: d.cumulative }),
    };
  });

  const intervalColumns: Column[] = intervals.map((b) => ({
    key: b.label,
    label: t("stats.intervalOf", { label: b.label }),
    tick: b.label,
    values: [b.count],
  }));

  const hourColumns: Column[] = r.hours.map((h) => ({
    key: String(h.hour),
    label: `${String(h.hour).padStart(2, "0")}:00`,
    tick: h.hour % 6 === 0 ? `${h.hour}` : undefined,
    values: [h.count],
    note:
      h.retention != null
        ? t("stats.retentionAt", { value: fmtPercent(h.retention) })
        : undefined,
  }));

  const ratingRows = [
    { key: "again", label: t("study.again"), value: r.ratings.again, color: "var(--again)" },
    { key: "hard", label: t("study.hard"), value: r.ratings.hard, color: "var(--hard)" },
    { key: "good", label: t("study.good"), value: r.ratings.good, color: "var(--good)" },
    { key: "easy", label: t("study.easy"), value: r.ratings.easy, color: "var(--easy)" },
  ];

  const composition = [
    { key: "new", label: t("stats.seriesNew"), value: c.new, color: RAMP[0] },
    { key: "learning", label: t("stats.seriesLearning"), value: c.learning, color: RAMP[1] },
    { key: "young", label: t("stats.young"), value: c.young, color: RAMP[2] },
    { key: "mature", label: t("stats.mature"), value: c.mature, color: RAMP[3] },
    { key: "suspended", label: t("stats.suspended"), value: c.suspended, color: "var(--sr-off)" },
  ];

  const rangeLabel = t(`stats.range${range}`);
  const hasReviews = r.reviews > 0;
  // Nothing studied ever: a wall of empty charts teaches nothing, so say what to
  // do instead. `activity` covers history older than the selected range.
  const isBlank = c.total === 0 && r.reviews === 0 && (activity?.total_reviews ?? 0) === 0;

  const head = (
    <div className="stats__head">
      <div>
        <h1>{t("stats.title")}</h1>
        <p className="stats__sub">{t("stats.subtitle")}</p>
      </div>
      <Link className="btn btn--ghost btn--sm" to="/app">
        {t("decks.backBtn")}
      </Link>
    </div>
  );

  if (isBlank) {
    return (
      <div className="stats">
        {head}
        <div className="panel decks__empty">
          <h2>{t("stats.blankTitle")}</h2>
          <p>{t("stats.blankHint")}</p>
          <Link className="btn btn--primary" to="/app">
            {t("stats.blankCta")}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className={`stats ${refreshing ? "stats--refreshing" : ""}`}>
      {head}

      {/* Filters: one row, above everything they scope. */}
      <div className="stats__filters" role="group" aria-label={t("stats.rangeLabel")}>
        <span className="stats__filterlabel">{t("stats.rangeLabel")}</span>
        {RANGES.map((d) => (
          <button
            key={d}
            className={`rangepill ${range === d ? "rangepill--on" : ""}`}
            aria-pressed={range === d}
            onClick={() => setRange(d)}
          >
            {t(`stats.range${d}`)}
          </button>
        ))}
      </div>

      {/* The headline number: retention is the one metric that says whether the
          scheduling is actually working. */}
      <section className="statshero">
        <div className="statshero__main">
          <span className="statshero__label">{t("stats.retention")}</span>
          <span className="statshero__value">{fmtPercent(r.retention, 1)}</span>
          <span className="statshero__sub">
            {r.mature_answers > 0
              ? t("stats.retentionSub", { count: r.mature_answers, range: rangeLabel })
              : t("stats.retentionNone")}
          </span>
        </div>
        <div className="statshero__tiles">
          <Tile label={t("stats.reviewsDone")} value={fmtCount(r.reviews)} sub={rangeLabel} />
          <Tile
            label={t("stats.timeStudied")}
            value={fmtDuration(r.seconds)}
            sub={r.reviews ? t("stats.perCard", { value: `${r.avg_seconds_per_card}s` }) : undefined}
          />
          <Tile
            label={t("stats.perDay")}
            value={fmtCount(r.avg_per_active_day)}
            sub={t("stats.activeDays", { count: r.active_days })}
          />
          <Tile
            label={t("stats.dueNow")}
            value={fmtCount(c.due_now)}
            sub={t("stats.ofCards", { count: c.total })}
          />
        </div>
      </section>

      <div className="stats__grid">
        <ChartCard
          wide
          title={t("stats.reviewsPerDay")}
          hint={t("stats.reviewsPerDayHint")}
          legend={<Legend items={maturitySeries} />}
          table={{
            columns: [t("stats.date"), t("stats.seriesNew"), t("stats.seriesLearning"), t("stats.seriesReview"), t("stats.total"), t("stats.time")],
            rows: r.days.map((d) => [
              d.date,
              d.new,
              d.learning,
              d.review,
              d.count,
              fmtDuration(d.seconds),
            ]),
          }}
        >
          <ColumnChart columns={dailyColumns} series={maturitySeries} />
        </ChartCard>

        <ChartCard
          title={t("stats.grades")}
          hint={t("stats.gradesHint")}
          table={{
            columns: [t("stats.grade"), t("stats.count"), t("stats.share")],
            rows: ratingRows.map((g) => [
              g.label,
              g.value,
              hasReviews ? fmtPercent(g.value / r.reviews, 1) : "—",
            ]),
          }}
        >
          <BarRows data={ratingRows} total={r.reviews} />
        </ChartCard>

        <ChartCard
          title={t("stats.bestHour")}
          hint={t("stats.bestHourHint")}
          table={{
            columns: [t("stats.hour"), t("stats.count"), t("stats.retention")],
            rows: r.hours
              .filter((h) => h.count > 0)
              .map((h) => [`${String(h.hour).padStart(2, "0")}:00`, h.count, fmtPercent(h.retention, 1)]),
          }}
        >
          <ColumnChart
            columns={hourColumns}
            series={[{ key: "count", label: t("stats.count"), color: ONE_HUE }]}
            height={104}
          />
        </ChartCard>

        <ChartCard
          wide
          title={t("stats.forecast")}
          hint={t("stats.forecastHint")}
          table={{
            columns: [t("stats.date"), t("stats.due"), t("stats.cumulativeCol")],
            rows: forecast.map((d) => [d.date, d.count, d.cumulative]),
          }}
        >
          <ColumnChart
            columns={forecastColumns}
            series={[{ key: "due", label: t("stats.due"), color: ONE_HUE }]}
          />
        </ChartCard>

        <ChartCard
          title={t("stats.composition")}
          hint={t("stats.compositionHint")}
          table={{
            columns: [t("stats.stage"), t("stats.count")],
            rows: composition.map((p) => [p.label, p.value]),
          }}
        >
          <ShareBar parts={composition} />
          {c.avg_interval != null && (
            <p className="chartcard__foot">
              {t("stats.avgInterval", { days: c.avg_interval })} ·{" "}
              {t("stats.avgEase", { value: ((c.avg_ease ?? 0) / 10).toFixed(0) })}
            </p>
          )}
        </ChartCard>

        <ChartCard
          title={t("stats.intervals")}
          hint={t("stats.intervalsHint")}
          table={{
            columns: [t("stats.interval"), t("stats.cards")],
            rows: intervals.map((b) => [b.label, b.count]),
          }}
        >
          <ColumnChart
            columns={intervalColumns}
            series={[{ key: "cards", label: t("stats.cards"), color: ONE_HUE }]}
            max={niceMax(Math.max(1, ...intervals.map((b) => b.count)))}
            height={104}
          />
        </ChartCard>

        {activity && (
          <ChartCard wide title={t("stats.consistency")} hint={t("stats.consistencyHint")}>
            <div className="stats__streaks">
              <Tile label={t("activity.dayStreak")} value={`🔥 ${activity.streak}`} />
              <Tile label={t("activity.bestStreak")} value={fmtCount(activity.longest_streak)} />
              <Tile
                label={t("stats.activeDaysLabel")}
                value={fmtCount(activity.active_days)}
                sub={t("stats.lastWeeks", { count: 17 })}
              />
              <Tile label={t("activity.allTime")} value={fmtCount(activity.total_reviews)} />
            </div>
            <ActivityHeatmap days={activity.days} />
          </ChartCard>
        )}

        <ChartCard wide title={t("stats.perDeck")} hint={t("stats.perDeckHint")}>
          {decks.length === 0 ? (
            <p className="chartcard__empty">{t("stats.noDecks")}</p>
          ) : (
            <div className="chartcard__tablewrap">
              <table className="datatable datatable--decks">
                <thead>
                  <tr>
                    <th>{t("stats.deck")}</th>
                    <th>{t("stats.cards")}</th>
                    <th>{t("stats.mature")}</th>
                    <th>{t("stats.due")}</th>
                    <th>{t("stats.reviewsCol")}</th>
                    <th>{t("stats.retention")}</th>
                  </tr>
                </thead>
                <tbody>
                  {decks.map((d) => (
                    <tr key={d.id}>
                      <td>
                        <Link to={`/app/decks/${d.id}`}>{d.full_name}</Link>
                      </td>
                      <td>{fmtCount(d.cards)}</td>
                      <td>{fmtCount(d.mature)}</td>
                      <td>{fmtCount(d.due)}</td>
                      <td>{fmtCount(d.reviews)}</td>
                      <td>{fmtPercent(d.retention, 1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </ChartCard>

        <ChartCard wide title={t("stats.toughest")} hint={t("stats.toughestHint")}>
          {leeches.length === 0 ? (
            <p className="chartcard__empty">{t("stats.noLeeches")}</p>
          ) : (
            <ul className="leechlist">
              {leeches.map((l) => (
                <li key={l.id} className="leechlist__row">
                  <div className="leechlist__text">
                    <Link to={`/app/study/card/${l.id}`} className="leechlist__front">
                      {l.front}
                    </Link>
                    {l.back && <span className="leechlist__back">{l.back}</span>}
                  </div>
                  <span className="leechlist__deck">{l.deck}</span>
                  <span className="leechlist__lapses" title={t("stats.lapsesTitle")}>
                    {t("stats.lapses", { count: l.lapses })}
                  </span>
                  {l.is_leech && <span className="leechlist__tag">{t("stats.leech")}</span>}
                </li>
              ))}
            </ul>
          )}
        </ChartCard>
      </div>
    </div>
  );
}
