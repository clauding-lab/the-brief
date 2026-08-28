"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { useTheme } from "@/lib/useTheme";

// Browser-chrome color follows the ACTIVE theme on EVERY route (v2.4.0,
// spec §12). layout.tsx ships a prefers-color-scheme media pair as the
// no-JS baseline and its FOUC script stamps the metas pre-paint on hard
// loads — but Next re-creates the viewport <meta> nodes on every client
// navigation (the Viewport head element is keyed per request, so a route
// change unmounts and remounts them with the static media-pair content).
// This component therefore lives in the ROOT layout, not ClientApp: it
// re-applies on theme changes (useTheme's data-theme MutationObserver
// covers every writer — ThemeToggle, the OS listener, the FOUC stamp,
// ClientApp's print force/restore) and on pathname changes, and a head
// observer catches Next swapping the meta nodes mid-session. The
// only-write-when-different guard keeps our own setAttribute from
// re-triggering the observer in a loop. Hexes must match layout.tsx's
// viewport pair (--paper light / --band dark ink).
const INK = "#0B0F12";
const PAPER = "#E6E9EB";

export function ThemeColorSync() {
  const theme = useTheme();
  const pathname = usePathname();

  useEffect(() => {
    const color = theme === "dark" ? INK : PAPER;
    const apply = () => {
      document.querySelectorAll('meta[name="theme-color"]').forEach((m) => {
        if (m.getAttribute("content") !== color) m.setAttribute("content", color);
      });
    };
    apply();
    const mo = new MutationObserver(apply);
    mo.observe(document.head, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["content", "media"],
    });
    return () => mo.disconnect();
  }, [theme, pathname]);

  return null;
}
