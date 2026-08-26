"use client";

// Facelift PR A (docs/facelift-spec.md §3).
//
// Chart.js paints to canvas: buildPalette() resolves tokens via
// getComputedStyle at chart-build time and the strings are baked into the
// config — nothing re-renders charts when data-theme flips. Consumers put
// this hook's value in their rebuild dep array so a theme flip repaints.
//
// useSyncExternalStore uses getServerSnapshot for both the server and the
// hydration render, then re-reads getSnapshot post-commit — so no hydration
// mismatch on dark loads (verified against React 19 docs via Context7).

import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";

function subscribe(onChange: () => void) {
  const mo = new MutationObserver(onChange);
  mo.observe(document.documentElement, { attributeFilter: ["data-theme"] });
  return () => mo.disconnect();
}

const getSnapshot = (): Theme =>
  document.documentElement.dataset.theme === "dark" ? "dark" : "light";

const getServerSnapshot = (): Theme => "light";

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
