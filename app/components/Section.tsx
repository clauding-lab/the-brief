import { Fragment } from "react";
import type { Section as SectionType } from "@/types/brief";
import { Hair } from "./Hair";
import { Mark } from "./Mark";
import { BankerRead } from "./BankerRead";
import { SignatureChart } from "./SignatureChart";
import { BriefChart } from "./BriefChart";
import { SECTION_TO_CHART } from "@/lib/chartConfigs";
import { formatNewsMeta } from "@/lib/format";

interface SectionProps {
  section: SectionType;
  diffMode: boolean;
  displayOrd?: number;
}

export function Section({ section, diffMode, displayOrd }: SectionProps) {
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
          <div>
            <div className="eyebrow" style={{ marginBottom: 10 }}>
              {title.toUpperCase()} — 12 months
            </div>
            {SECTION_TO_CHART[slug] ? (
              <BriefChart section={section} configKey={SECTION_TO_CHART[slug]!} />
            ) : (
              <SignatureChart series={series} notes={filteredNotes} label={`${title} chart`} />
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
            {metrics.slice(0, 5).map((m, i, arr) => (
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
                    {m.held_from && !m.changed && (
                      <div className="tb-held-footer">
                        Held from {m.held_from}
                        {m.next_print ? ` · next print ${m.next_print}` : ""}
                      </div>
                    )}
                  </div>
                  <div className="tb-kpi-value">{m.value}</div>
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
