"use client";

import type { Brief, DataSource, Section } from "@/types/brief";
import { Hair } from "./Hair";
import { formatBriefDate } from "@/lib/format";
import { MastheadLensPill } from "./MastheadLensPill";

interface MastheadProps {
  brief?: Brief;
  source?: DataSource;
  sections: Section[];
  displayOrdBySlug?: Map<string, number>;
}

export function Masthead({ brief, source, sections, displayOrdBySlug }: MastheadProps) {
  const dateLabel = formatBriefDate(brief?.brief_date);
  const issueNo = brief?.issue_no ?? 87;
  const vol = brief?.volume ?? 1;
  const readMin = brief?.read_minutes ?? 9;
  const sourceLabel = source === "live" ? "Live" : source === "cache" ? "Cached" : "Static";

  // 4 most "newsworthy" — first 4 from headlines section
  const headlines = (sections.find((s) => s.slug === "headlines")?.news || []).slice(0, 12);

  return (
    <header className="tb-masthead-full" id="masthead">
      <div className="tb-masthead-meta">
        <div>
          No. {String(issueNo).padStart(2, "0")} / Vol. {String(vol).padStart(2, "0")}
        </div>
        <div className="tb-masthead-date-row">
          <span>{dateLabel}</span>
          <MastheadLensPill lens={brief?.lens} frame={brief?.frame} briefDate={brief?.brief_date} />
        </div>
        <div className="tb-live">
          <span className="pulse" />
          <span>{sourceLabel} · 14:02 BST</span>
        </div>
      </div>

      <Hair style={{ marginTop: 14 }} />

      <div className="tb-masthead-hero">
        <div>
          <div className="tb-wordmark-big">
            The Brief<span className="dot">.</span>
          </div>
          <div className="tb-tagline">
            Daily macro &amp; markets read for Bangladesh treasury desks. One brief.
            Numbers, news, and a banker&rsquo;s read on what matters.
          </div>
        </div>
        <div className="tb-issue-rail">
          <div className="eyebrow">In this issue</div>
          <ul>
            {headlines.map((h, i) => {
              const lower = h.headline.toLowerCase();
              const map: Array<[RegExp, string]> = [
                [/fx|taka|usd|reserve/, "fx"],
                [/npl|bank/, "banking"],
                [/remittance/, "remit"],
                [/brent|oil|hormuz/, "iran"],
                [/imf/, "bb"],
                [/dse/, "dse"],
                [/t-bill|t-bond/, "tbond"],
              ];
              let secOrd = "";
              let matchedSlug = "";
              for (const [pat, slug] of map) {
                if (pat.test(lower)) {
                  const sec = sections.find((s) => s.slug === slug);
                  if (sec) {
                    const display = displayOrdBySlug?.get(sec.slug) ?? sec.ord;
                    secOrd = `§${String(display).padStart(2, "0")}`;
                    matchedSlug = sec.slug;
                    break;
                  }
                }
              }
              const numText = secOrd || `§${String(i + 1).padStart(2, "0")}`;
              const inner = (
                <>
                  <span className="num">{numText}</span>
                  <span className="text">{h.headline}</span>
                </>
              );
              return (
                <li key={i}>
                  {matchedSlug ? (
                    <a
                      href={`#${matchedSlug}`}
                      onClick={(e) => {
                        e.preventDefault();
                        const el = document.getElementById(matchedSlug);
                        if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
                      }}
                    >
                      {inner}
                    </a>
                  ) : (
                    inner
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      </div>

      {brief?.todays_call && (
        <div className="tb-todays-call">
          <span className="label">Today&rsquo;s Call</span>
          <div>
            <div className="body">{brief.todays_call}</div>
            <div className="byline">— Desk Editor · The Brief</div>
          </div>
        </div>
      )}

      <Hair />

      <div className="tb-masthead-foot">
        <div className="tb-tag-row">
          <span className="tag">Macro</span>
          <span className="tag">Markets</span>
          <span className="tag">Banking</span>
          <span className="tag tag-soft">+15 sections</span>
        </div>
        <div className="tb-masthead-actions">
          <span className="tb-readtime">Read time · {readMin} min</span>
          <a
            href="#subscribe"
            className="tb-btn-cta"
            onClick={(e) => {
              e.preventDefault();
              const el = document.getElementById("subscribe");
              if (el) el.scrollIntoView({ behavior: "smooth" });
            }}
          >
            Subscribe →
          </a>
        </div>
      </div>
    </header>
  );
}
