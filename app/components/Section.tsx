import { Fragment } from "react";
import type { Section as SectionType, Mover } from "@/types/brief";
import { Hair } from "./Hair";
import { Mark } from "./Mark";
import { BankerRead } from "./BankerRead";
import { SignatureChart } from "./SignatureChart";
import { BriefChart } from "./BriefChart";
import { SECTION_TO_CHART, CHART_CARD_HEADS } from "@/lib/chartConfigs";
import { getChartLatestCaption, getChartStaleness, getChartAriaLabel } from "@/lib/chartMeta";
import { formatNewsMeta, cleanMetricValue, formatVintageDate } from "@/lib/format";

interface SectionProps {
  section: SectionType;
  diffMode: boolean;
  displayOrd?: number;
  /** Sequential FIG number (1, 2, 3, …) in reading order — only set for charted sections. */
  chartOrd?: number;
  /** The issue's brief_date (YYYY-MM-DD), used to judge chart staleness. */
  issueDate?: string;
}

export function Section({ section, diffMode, displayOrd, chartOrd, issueDate }: SectionProps) {
  const {
    slug,
    ord,
    title,
    verdict,
    verdict_tone,
    banker_read,
    metrics = [],
    news = [],
    series = [],
    notes = [],
    weight = 1,
    tldr,
    summary_pills,
    analysis,
    freshness,
    chart_read,
    movers,
  } = section;

  // SPA-side sequential numbering (1, 2, 3, …) — falls back to backend ord
  // when not provided by the parent (defensive; ClientApp always supplies it).
  const ordLabel = String(displayOrd ?? ord).padStart(2, "0");

  // Dead-section collapse only when there's truly nothing to show. If chart
  // data is present (e.g. comm has LNG history but a sibling metric like
  // BAJUS gold went None and dragged section_freshness to "unavailable"),
  // fall through to the normal render so the chart + remaining metrics
  // still appear.
  if (freshness === "unavailable" && series.length === 0) {
    return (
      <section
        id={slug}
        className={`tb-section is-unavailable${diffMode ? " is-diff" : ""}`}
        data-section-slug={slug}
        data-screen-label={`§${ordLabel} ${title}`}
      >
        <div className="tb-section-head">
          <div>
            <div className="eyebrow">§{ordLabel}</div>
            <h2 className="tb-section-title">{title}</h2>
          </div>
        </div>
        <p className="tb-unavailable-note">No fresh data this issue</p>
      </section>
    );
  }

  const hasChart = series && series.length > 1;
  const seriesKey = hasChart ? series[0].key : null;
  const filteredNotes = notes.filter((n) => n.series_key === seriesKey);
  const configKey = SECTION_TO_CHART[slug] ?? null;
  // Bound to the CHARTED series' own latest point — never metrics[0] (that
  // bug captioned the bb/"FX Reserves" chart with "Overnight Call Money
  // 9.31%", the section's first tile, which has no relation to the chart).
  const chartLatest = hasChart ? getChartLatestCaption(section, configKey) : null;
  const staleness = hasChart && configKey ? getChartStaleness(section, configKey, issueDate) : null;
  const isHero = (weight ?? 1) >= 2;
  const anySignal =
    metrics.some((m) => m.changed || m.held_from) ||
    news.some((n) => n.changed || n.held_from);

  return (
    <section
      id={slug}
      className={`tb-section${isHero ? " is-hero" : ""}${diffMode ? " is-diff" : ""}${diffMode && !anySignal ? " is-quiet" : ""}`}
      data-section-slug={slug}
      data-screen-label={`§${ordLabel} ${title}`}
    >
      <div className="tb-section-head">
        <div>
          <div className="eyebrow">
            §{ordLabel}
            {isHero && <span className="tb-hero-flag">Today&rsquo;s Lead</span>}
          </div>
          <h2 className="tb-section-title">{title}</h2>
        </div>
        {verdict && (
          <div>
            <span className="label">Verdict</span>
            <div className="tb-section-verdict">
              <Mark kind={verdict_tone || "neu"} /> {verdict}
            </div>
          </div>
        )}
      </div>

      {tldr && <p className="tb-tldr">{tldr}</p>}

      {summary_pills && summary_pills.length > 0 && (
        <div className="tb-summary-pills">
          {summary_pills.map((p, i) => (
            <div key={i} className={`tb-summary-pill tone-${p.tone || "neu"}`}>
              <span className="key">{p.key}</span>
              <span className="val">{p.value}</span>
            </div>
          ))}
        </div>
      )}

      <Hair style={{ marginTop: 18 }} />

      <div className={`tb-section-grid ${hasChart ? "" : "no-chart"}`}>
        {hasChart ? (
          <div className="tb-chart-card">
            {(() => {
              const head = CHART_CARD_HEADS[slug];
              if (head) {
                // Sequential FIG numbering in reading order (chartOrd, computed
                // in ClientApp from render order) — head.fig is a stable-but-
                // wrong "chart-addition-order" number kept only as a defensive
                // fallback for a charted section this table hasn't been told
                // the render position of.
                const figLabel = String(chartOrd ?? head.fig).padStart(2, "0");
                return (
                  <div className="tb-chart-card-head">
                    <span className="tb-chart-fig">FIG.{figLabel}</span>
                    <h3 className="tb-chart-title">{head.title}</h3>
                    {head.subtitle && (
                      <div className="tb-chart-sub">{head.subtitle}</div>
                    )}
                    {chartLatest && (
                      <div className="tb-chart-latest">
                        Latest: {chartLatest.label} {cleanMetricValue(chartLatest.value)}
                      </div>
                    )}
                  </div>
                );
              }
              return (
                <div className="eyebrow" style={{ marginBottom: 10 }}>
                  {title.toUpperCase()} — 12 months
                </div>
              );
            })()}
            {configKey ? (
              <BriefChart
                section={section}
                configKey={configKey}
                ariaLabel={getChartAriaLabel(section, configKey, CHART_CARD_HEADS[slug])}
                describedById={chart_read ? `${slug}-chart-read` : undefined}
                stale={staleness?.isStale ?? false}
                staleLabel={staleness?.label}
              />
            ) : (
              <SignatureChart series={series} notes={filteredNotes} label={`${title} chart`} />
            )}
            {chart_read && (
              <div className="tb-analysis tb-chart-read" id={`${slug}-chart-read`}>
                <span className="label">Chart read</span>
                <div className="body">
                  <p>{chart_read.signal}</p>
                  {chart_read.context && <p>{chart_read.context}</p>}
                  <p>{chart_read.implication}</p>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div
            className={`tb-news-rail${slug === "headlines" ? " is-headlines" : ""}`}
            style={{ paddingTop: 22 }}
          >
            {news.slice(0, slug === "headlines" ? 16 : 4).map((n, i) => (
              <a
                key={i}
                href={n.source_url || undefined}
                target={n.source_url ? "_blank" : undefined}
                rel={n.source_url ? "noopener noreferrer" : undefined}
                className={`tb-news-item${
                  n.changed ? " is-changed" : n.held_from ? " is-held-over" : ""
                }`}
              >
                <div>
                  <div className="tb-news-headline">{n.headline}</div>
                  {n.detail && <div className="tb-news-detail">{n.detail}</div>}
                  <div className="tb-news-meta">
                    {formatNewsMeta(n)}
                    {n.changed ? " · NEW" : ""}
                    {n.held_from && !n.changed ? ` · Held from ${n.held_from}` : ""}
                  </div>
                </div>
              </a>
            ))}
          </div>
        )}

        {metrics.length > 0 && (
          <div className="tb-kpi-rail">
            {/* Render every stored metric — the tile rail is a vertical
                flex column (.tb-kpi-rail, app/globals.css) with no fixed
                row count, so nothing here needs truncation. A prior
                slice(0, 5) silently dropped any section storing more than
                5 metrics (e.g. macro's 8-metric editor carve-out), which
                is a render-layer constraint leaking into the data layer —
                see AGENTS.md landmine 25. */}
            {metrics.map((m, i, arr) => (
              <Fragment key={i}>
                <div
                  className={`tb-kpi-row${
                    m.changed ? " is-changed" : m.held_from ? " is-held-over" : ""
                  }`}
                >
                  <div>
                    <div className="tb-kpi-label">
                      {m.label}
                      {m.changed && (
                        <span className="tb-changed-dot" title="Updated since yesterday" />
                      )}
                    </div>
                    {m.sub && <div className="tb-kpi-sub">{m.sub}</div>}
                    {/* Vintage footer. Shown even when `changed` is true: a
                        number can move and still be five months old — the
                        first issue after a source repoint is exactly that
                        case, and that is precisely when the reader needs the
                        date most. */}
                    {m.held_from && (
                      <div className="tb-held-footer">
                        As of {formatVintageDate(m.held_from)}
                        {m.next_print ? ` · next print ${m.next_print}` : ""}
                      </div>
                    )}
                  </div>
                  <div className="tb-kpi-value">{cleanMetricValue(m.value)}</div>
                </div>
                {i < arr.length - 1 && <Hair tone="faint" />}
              </Fragment>
            ))}
          </div>
        )}
      </div>

      {hasChart && news.length > 0 && (
        <>
          <Hair style={{ marginTop: 28 }} />
          <div className="tb-news-rail">
            {news.slice(0, 4).map((n, i) => (
              <a
                key={i}
                href={n.source_url || undefined}
                target={n.source_url ? "_blank" : undefined}
                rel={n.source_url ? "noopener noreferrer" : undefined}
                className={`tb-news-item${
                  n.changed ? " is-changed" : n.held_from ? " is-held-over" : ""
                }`}
              >
                <div>
                  <div className="tb-news-headline">{n.headline}</div>
                  {n.detail && <div className="tb-news-detail">{n.detail}</div>}
                  <div className="tb-news-meta">
                    {formatNewsMeta(n)}
                    {n.changed ? " · NEW" : ""}
                    {n.held_from && !n.changed ? ` · Held from ${n.held_from}` : ""}
                  </div>
                </div>
              </a>
            ))}
          </div>
        </>
      )}

      {movers && movers.length > 0 && (() => {
        const gainers = movers
          .filter((m) => m.return_pct > 0)
          .sort((a, b) => b.return_pct - a.return_pct);
        const losers = movers
          .filter((m) => m.return_pct < 0)
          .sort((a, b) => a.return_pct - b.return_pct);
        const fmtRet = (v: number) =>
          `${v > 0 ? "+" : "−"}${Math.abs(v).toFixed(1)}%`;
        const col = (heading: string, rows: Mover[], tone: string) => (
          <div className="tb-movers-col">
            <span className={`tb-movers-colhd ${tone}`}>{heading}</span>
            {rows.map((m) => (
              <div className="tb-mover-row" key={m.ticker}>
                <span className="tb-mover-tk">
                  {m.ticker}
                  <span className="tb-mover-px">{`Tk ${m.price}`}</span>
                </span>
                <span className={`tb-mover-rt ${tone}`}>{fmtRet(m.return_pct)}</span>
              </div>
            ))}
          </div>
        );
        return (
          <div className="tb-movers">
            <div className="tb-movers-head">
              <span>DS30 · Movers</span>
              <span>1-Month</span>
            </div>
            <div className="tb-movers-grid">
              {col("Gainers", gainers, "tone-bull")}
              {col("Losers", losers, "tone-bear")}
            </div>
          </div>
        );
      })()}

      {banker_read && <BankerRead read={banker_read} hero={isHero} />}

      {analysis && (
        <div className="tb-analysis">
          <span className="label">Analysis</span>
          <div className="body">
            {analysis.split(/\n{2,}/).map((para, i) => (
              <p key={i}>{para}</p>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
