"use client";

import { useEffect, useRef } from "react";
import type { Section } from "@/types/brief";

interface SecNavProps {
  sections: Section[];
  activeSlug: string;
  onJump: (slug: string) => void;
  diffMode: boolean;
  onToggleDiff: () => void;
}

export function SecNav({ sections, activeSlug, onJump, diffMode, onToggleDiff }: SecNavProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current?.querySelector<HTMLElement>(`[data-slug="${activeSlug}"]`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
    }
  }, [activeSlug]);

  return (
    <nav className="tb-secnav" aria-label="Sections">
      <div className="tb-secnav-inner" ref={ref}>
        {sections.map((s) => {
          const tone = s.verdict_tone || "neu";
          return (
            <a
              key={s.slug}
              href={`#${s.slug}`}
              data-slug={s.slug}
              className={`tb-secnav-item ${activeSlug === s.slug ? "active" : ""}`}
              onClick={(e) => {
                e.preventDefault();
                onJump(s.slug);
              }}
            >
              <span className="num">§{String(s.ord).padStart(2, "0")}</span>
              <span className={`tb-tl tb-tl-${tone}`} aria-hidden="true" />
              <span>{s.title}</span>
            </a>
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
