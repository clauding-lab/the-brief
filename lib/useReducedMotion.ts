"use client";

import { useEffect, useState } from "react";

// A CSS `@media (prefers-reduced-motion: reduce)` kill switch can't reach
// JS-driven motion: `Element.scrollIntoView({ behavior: "smooth" })` ignores
// the CSS `scroll-behavior` property once a call passes its own explicit
// `behavior`, and Chart.js's draw animation is a requestAnimationFrame loop,
// not a CSS transition. Every such call site needs to read the preference
// itself and choose "auto"/`false` instead.
//
// `useLayoutEffect` would give a slightly earlier read, but this value only
// gates whether FUTURE scroll/animation calls are instant — nothing renders
// differently on the first paint because of it, so the plain post-mount
// effect (matching this codebase's other client-only reads) is enough.
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    // Deliberate post-mount impure read (matchMedia) synced into state — the
    // server can't know the client's OS motion preference. Same pattern as
    // Masthead.tsx's Date.now() read and ClientApp's localStorage sync.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- see comment above
    setReduced(mq.matches);
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  return reduced;
}
