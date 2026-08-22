"use client";

import { useEffect, useState } from "react";

const FALLBACK_OFFSET = 110;

// SecNav (.tb-secnav) wraps to 2-3 rows at wide viewports once it has 10
// links (review round 1, H1) — its rendered height is no longer the fixed
// ~60px a single row used to be. `.tb-section`/`.tb-longview`'s
// scroll-margin-top and ClientApp's scroll-spy rootMargin both hardcoded
// 110px (= the old single-row height + the 50px reserved for the sticky
// bar above it), so a section could land 18-65px under the nav depending on
// how many rows it wrapped to at that width.
//
// Measures .tb-secnav's OWN sticky `top` (50px desktop / 48px ≤920px) plus
// its current rendered height, republishing the total as the `--nav-offset`
// CSS custom property so scroll-margin-top always matches — and returning
// the same number so the IntersectionObserver rootMargin in ClientApp.tsx
// can match it too, since rootMargin is a JS string, not something CSS
// custom properties can feed directly.
export function useNavOffset(): number {
  const [offset, setOffset] = useState(FALLBACK_OFFSET);

  useEffect(() => {
    const el = document.querySelector<HTMLElement>(".tb-secnav");
    if (!el) return;

    const measure = () => {
      const stickyTop = parseFloat(getComputedStyle(el).top) || 0;
      const height = el.getBoundingClientRect().height;
      if (height <= 0) return;
      const total = stickyTop + height;
      setOffset(total);
      document.documentElement.style.setProperty("--nav-offset", `${total}px`);
    };

    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    window.addEventListener("resize", measure);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, []);

  return offset;
}
