"use client";

import { Fragment, useEffect, useRef } from "react";
import type { Section } from "@/types/brief";
import { useReducedMotion } from "@/lib/useReducedMotion";

interface SecNavProps {
  sections: Section[];
  activeSlug: string;
  onJump: (slug: string) => void;
  diffMode: boolean;
  onToggleDiff: () => void;
  displayOrdBySlug?: Map<string, number>;
  /** Slug of the lead section (weight >= 2) — its item gets is-lead accent (spec §7.7). */
  leadSlug?: string;
}

export function SecNav({
  sections,
  activeSlug,
  onJump,
  diffMode,
  onToggleDiff,
  displayOrdBySlug,
  leadSlug,
}: SecNavProps) {
  const ref = useRef<HTMLDivElement>(null);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    const el = ref.current?.querySelector<HTMLElement>(`[data-slug="${activeSlug}"]`);
    if (el) {
      // See ClientApp.tsx's `jump` for why this reads reducedMotion directly
      // instead of relying on the CSS scroll-behavior switch (H3).
      el.scrollIntoView({
        behavior: reducedMotion ? "auto" : "smooth",
        inline: "center",
        block: "nearest",
      });
    }
  }, [activeSlug, reducedMotion]);

  return (
    <nav className="tb-secnav" aria-label="Sections">
      <div className="tb-secnav-inner" ref={ref}>
        {sections.map((s, i) => {
          const tone = s.verdict_tone || "neu";
          const showDivider = i > 0 && sections[i - 1].group_key !== s.group_key;
          return (
            <Fragment key={s.slug}>
              {showDivider && <span className="tb-secnav-div" aria-hidden="true" />}
              <a
                href={`#${s.slug}`}
                data-slug={s.slug}
                className={`tb-secnav-item ${activeSlug === s.slug ? "active" : ""}${s.slug === leadSlug ? " is-lead" : ""}`}
                onClick={(e) => {
                  e.preventDefault();
                  onJump(s.slug);
                }}
              >
                <span className="num">§{String(displayOrdBySlug?.get(s.slug) ?? s.ord).padStart(2, "0")}</span>
                <span className={`tb-tl tb-tl-${tone}`} aria-hidden="true" />
                <span>{s.title}</span>
              </a>
            </Fragment>
          );
        })}
      </div>
      <button
        type="button"
        className={`tb-diff-toggle${diffMode ? " is-on" : ""}`}
        onClick={onToggleDiff}
        aria-pressed={diffMode}
        title="Highlight what changed since yesterday"
      >
        <span className="dot" /> Diff
      </button>
    </nav>
  );
}
