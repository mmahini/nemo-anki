import { useId, useState, type CSSProperties, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

/**
 * Chart primitives for the performance page. Plain HTML + CSS on purpose — the
 * shapes here are bars and stacks, which flexbox draws exactly, so a charting
 * library would be pure bundle weight.
 *
 * Colour rules these follow (and why they aren't parameters):
 *  - Card maturity (new → learning → young → mature) is an *ordinal* progression,
 *    so it ramps one hue light→dark (--sr-1..4) rather than taking four identities.
 *    The reader sees the order in the colour.
 *  - Single-measure charts (forecast, intervals, hour-of-day) use one hue for
 *    every column. Shading a bar by its own height would re-encode length.
 *  - Grade colours (again/hard/good/easy) are reserved status tokens, already the
 *    app's language on the review buttons, so they carry over — always with the
 *    value written next to the bar, never colour alone.
 */

const nf = new Intl.NumberFormat();

export function fmtCount(n: number): string {
  return nf.format(n);
}

/** Compact duration for stat tiles: 45s / 12 min / 3h 20m. */
export function fmtDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.round(seconds / 60);
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

export function fmtPercent(ratio: number | null, digits = 0): string {
  if (ratio == null) return "—";
  return `${(ratio * 100).toFixed(digits)}%`;
}

/** Round an axis maximum up to a clean number so ticks read 0 / 20 / 40. */
export function niceMax(value: number): number {
  if (value <= 4) return 4;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  for (const step of [1, 2, 2.5, 5, 10]) {
    const candidate = step * magnitude;
    if (candidate >= value) return candidate;
  }
  return 10 * magnitude;
}

// ---------------------------------------------------------------- card shell

export type TableSpec = {
  columns: string[];
  rows: (string | number)[][];
};

/**
 * The frame every chart sits in: title, optional legend, the plot, and a table
 * disclosure. The table is not a nicety — it's how the numbers stay reachable
 * for keyboard and screen-reader users, who never get a hover tooltip.
 */
export function ChartCard({
  title,
  hint,
  legend,
  table,
  children,
  wide,
}: {
  title: string;
  hint?: string;
  legend?: ReactNode;
  table?: TableSpec;
  children: ReactNode;
  wide?: boolean;
}) {
  const { t } = useTranslation();
  const [showTable, setShowTable] = useState(false);
  const tableId = useId();

  return (
    <section className={`chartcard ${wide ? "chartcard--wide" : ""}`}>
      <header className="chartcard__head">
        <div className="chartcard__titles">
          <h2 className="chartcard__title">{title}</h2>
          {hint && <p className="chartcard__hint">{hint}</p>}
        </div>
        {table && (
          <button
            className="chartcard__tablebtn"
            aria-expanded={showTable}
            aria-controls={tableId}
            onClick={() => setShowTable((v) => !v)}
          >
            {showTable ? t("stats.hideTable") : t("stats.showTable")}
          </button>
        )}
      </header>

      {legend && <div className="chartlegend">{legend}</div>}

      {children}

      {table && showTable && (
        <div className="chartcard__tablewrap" id={tableId}>
          <table className="datatable">
            <thead>
              <tr>
                {table.columns.map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row, i) => (
                <tr key={i}>
                  {row.map((cell, j) => (
                    <td key={j}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <>
      {items.map((it) => (
        <span className="chartlegend__item" key={it.label}>
          <i className="chartlegend__swatch" style={{ background: it.color }} />
          {it.label}
        </span>
      ))}
    </>
  );
}

// -------------------------------------------------------------- column chart

export type Series = { key: string; label: string; color: string };

/** Where the tooltip sits: centred on the column, or pinned when that would
 * push it outside the plot. `transform: none` cancels the CSS centring. */
function tipPosition(index: number, total: number): CSSProperties {
  const pct = ((index + 0.5) / total) * 100;
  if (pct < 14) return { insetInlineStart: 0, transform: "none" };
  if (pct > 86) return { insetInlineEnd: 0, insetInlineStart: "auto", transform: "none" };
  return { insetInlineStart: `${pct}%` };
}

export type Column = {
  /** Stable identity for React and the tooltip. */
  key: string;
  /** Full name, used in the tooltip (e.g. "Wed 12 Aug"). */
  label: string;
  /** Sparse axis tick — only some columns get one, so labels never collide. */
  tick?: string;
  /** Per-series values, in the same order as `series`. */
  values: number[];
  /** Extra line in the tooltip (e.g. time spent). */
  note?: string;
};

/**
 * Stacked (or single-series) column chart. Segments are separated by a 2px gap
 * in the surface colour rather than a stroke, and only the topmost segment gets
 * the rounded data-end — the stack still reads as one bar off the baseline.
 */
export function ColumnChart({
  columns,
  series,
  max,
  height = 132,
}: {
  columns: Column[];
  series: Series[];
  max?: number;
  height?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const totals = columns.map((c) => c.values.reduce((a, b) => a + b, 0));
  const top = niceMax(max ?? Math.max(1, ...totals));
  const active = hover != null ? columns[hover] : null;

  return (
    <div className="colchart">
      <div className="colchart__yaxis" style={{ height }}>
        <span>{fmtCount(top)}</span>
        <span>{fmtCount(top / 2)}</span>
        <span>0</span>
      </div>

      <div className="colchart__plot">
        <div className="colchart__grid" style={{ height }} aria-hidden>
          <i />
          <i />
          <i />
        </div>

        <div className="colchart__cols" style={{ height }} onMouseLeave={() => setHover(null)}>
          {columns.map((col, i) => (
            <div
              className={`colchart__col ${hover === i ? "is-hover" : ""}`}
              key={col.key}
              onMouseEnter={() => setHover(i)}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
              tabIndex={0}
              role="img"
              aria-label={`${col.label}: ${fmtCount(totals[i])}`}
            >
              <div className="colchart__stack">
                {/* Bottom-up, so the last painted segment is the data-end. */}
                {series.map((s, si) => {
                  const value = col.values[si] ?? 0;
                  if (value <= 0) return null;
                  const isTop = !series.some((_, later) => later > si && (col.values[later] ?? 0) > 0);
                  return (
                    <span
                      key={s.key}
                      className={`colchart__seg ${isTop ? "colchart__seg--top" : ""}`}
                      style={{
                        height: `${(value / top) * 100}%`,
                        background: s.color,
                      }}
                    />
                  );
                })}
              </div>
              {col.tick && <span className="colchart__tick">{col.tick}</span>}
            </div>
          ))}
        </div>

        {active && (
          <div
            className="charttip"
            /* Near either edge the tooltip pins to the plot instead of centring
               on the column, so it never hangs outside the card. */
            style={tipPosition(hover!, columns.length)}
            role="status"
          >
            <strong className="charttip__value">{fmtCount(totals[hover!])}</strong>
            <span className="charttip__label">{active.label}</span>
            {series.length > 1 &&
              series.map((s, si) =>
                (active.values[si] ?? 0) > 0 ? (
                  <span className="charttip__row" key={s.key}>
                    <i className="charttip__key" style={{ background: s.color }} />
                    {s.label}
                    <b>{fmtCount(active.values[si])}</b>
                  </span>
                ) : null,
              )}
            {active.note && <span className="charttip__note">{active.note}</span>}
          </div>
        )}
      </div>
    </div>
  );
}

// ----------------------------------------------------------- horizontal bars

export type BarDatum = { key: string; label: string; value: number; color: string; note?: string };

/**
 * Horizontal bars with the value written at the tip. Used where the categories
 * are few and named (grade distribution) — the direct labels are also what makes
 * the reserved grade colours legal without relying on hue.
 */
export function BarRows({ data, total }: { data: BarDatum[]; total?: number }) {
  const sum = total ?? data.reduce((a, d) => a + d.value, 0);
  const top = Math.max(1, ...data.map((d) => d.value));
  return (
    <div className="barrows">
      {data.map((d) => (
        <div className="barrows__row" key={d.key}>
          <span className="barrows__label">{d.label}</span>
          <span className="barrows__track">
            {/* No mark at all for zero — a min-width stub would read as a value. */}
            {d.value > 0 && (
              <span
                className="barrows__fill"
                style={{ width: `${(d.value / top) * 100}%`, background: d.color }}
              />
            )}
          </span>
          <span className="barrows__value">
            {fmtCount(d.value)}
            {sum > 0 && <em>{fmtPercent(d.value / sum)}</em>}
          </span>
        </div>
      ))}
    </div>
  );
}

// --------------------------------------------------------- share (whole) bar

/**
 * One bar showing how a whole splits — the collection's composition. Segments
 * are labelled below rather than inside: an interior segment has no free end, so
 * an inline label would sooner or later be clipped.
 */
export function ShareBar({ parts }: { parts: { key: string; label: string; value: number; color: string }[] }) {
  const total = parts.reduce((a, p) => a + p.value, 0);
  const shown = parts.filter((p) => p.value > 0);
  return (
    <div className="sharebar">
      <div className="sharebar__track" role="img" aria-label={shown.map((p) => `${p.label} ${p.value}`).join(", ")}>
        {shown.map((p) => (
          <span
            key={p.key}
            className="sharebar__seg"
            style={{ flexGrow: p.value, background: p.color }}
            title={`${p.label}: ${fmtCount(p.value)} (${fmtPercent(p.value / total)})`}
          />
        ))}
        {total === 0 && <span className="sharebar__seg sharebar__seg--empty" />}
      </div>
      <dl className="sharebar__keys">
        {parts.map((p) => (
          <div className="sharebar__key" key={p.key}>
            <dt>
              <i className="chartlegend__swatch" style={{ background: p.color }} />
              {p.label}
            </dt>
            <dd>
              {fmtCount(p.value)}
              {total > 0 && <em>{fmtPercent(p.value / total)}</em>}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
