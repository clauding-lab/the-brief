"use client";

// Facelift PR A (docs/facelift-spec.md §2).
//
// Single source of truth is document.documentElement.dataset.theme — written
// pre-hydration by the FOUC script in layout.tsx and mutated only here (and
// by the OS listener below). The visible label is CSS-keyed on [data-theme]
// (.when-light/.when-dark in globals.css), so the component renders
// identically on server and client: no hydration dependency, no first-frame
// flicker, no suppressHydrationWarning needed anywhere in this component.

import { useEffect } from "react";

const KEY = "thebrief.theme";

export function ThemeToggle({ onBand = false }: { onBand?: boolean }) {
  // Follow OS changes only while the visitor has never chosen explicitly.
  // localStorage is re-checked INSIDE the handler — a click that stores a
  // choice immediately stops the OS listener from overriding it.
  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      try {
        const s = localStorage.getItem(KEY);
        if (s === "light" || s === "dark") return;
      } catch {
        /* ignore */
      }
      document.documentElement.dataset.theme = mq.matches ? "dark" : "light";
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const flip = () => {
    const cur = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* ignore */
    }
  };

  return (
    <button
      type="button"
      className={`tb-theme-toggle${onBand ? " on-band" : ""}`}
      // State-independent accessible name: a state-dependent one would be
      // stale for the first client pass on dark loads.
      aria-label="Toggle dark mode"
      onClick={flip}
    >
      <span aria-hidden="true">◐ </span>
      <span className="when-light">Dark</span>
      <span className="when-dark">Light</span>
    </button>
  );
}
