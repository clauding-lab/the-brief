"use client";

import { useEffect, useState, useCallback, Fragment } from "react";
import Link from "next/link";
import type { BriefPayload, SectionGroup } from "@/types/brief";
import { getBrowserSupabase } from "@/lib/supabase";
import { SECTION_TO_CHART } from "@/lib/chartConfigs";
import { useNavOffset } from "@/lib/useNavOffset";
import { useReducedMotion } from "@/lib/useReducedMotion";
import { Masthead } from "./Masthead";
import { StickyBar } from "./StickyBar";
import { SnapshotStrip } from "./SnapshotStrip";
import { SecNav } from "./SecNav";
import { Section } from "./Section";
import { SubscribeCTA } from "./SubscribeCTA";
import { StatusBar } from "./StatusBar";
import { LongView } from "./LongView";
import { longView } from "@/content/long-view";

const CACHE_KEY = "thebrief.lastBrief";

const GROUP_ORDER: SectionGroup[] = [
  "overview",
  "banking",
  "markets",
  "realeco",
  "policy",
];

const GROUP_LABELS: Record<SectionGroup, string> = {
  overview: "Overview",
  banking: "Banking",
  markets: "Markets",
  realeco: "Real Economy",
  policy: "Policy",
};

type ClientAppProps =
  | { initialData: BriefPayload; brief?: never; sections?: never; preview?: never; historical?: never }
  | {
      brief: BriefPayload["brief"];
      sections: BriefPayload["sections"];
      initialData?: never;
      preview?: boolean;
      /** A fixed past issue (e.g. /issue/[no]) — skip the live refetch-on-mount
       * so a permalink doesn't silently swap itself for today's latest brief. */
      historical?: boolean;
    };

export function ClientApp(props: ClientAppProps) {
  const initialData: BriefPayload =
    "initialData" in props && props.initialData !== undefined
      ? props.initialData
      : { brief: props.brief!, sections: props.sections!, _source: "static" };
  const preview = ("preview" in props && props.preview) ?? false;
  const historical = ("historical" in props && props.historical) ?? false;

  const [data, setData] = useState<BriefPayload>(initialData);
  const [active, setActive] = useState<string>(() => {
    if (typeof window === "undefined") return "snapshot";
    return (window.location.hash || "#snapshot").slice(1);
  });
  const [stickyVisible, setStickyVisible] = useState(false);
  const [diffMode, setDiffMode] = useState<boolean>(false);
  const [printMode, setPrintMode] = useState<boolean>(false);
  const navOffset = useNavOffset();
  const reducedMotion = useReducedMotion();

  // Read localStorage diff + URL print=1 after mount (avoid SSR hydration mismatch).
  // Reading client-only state (localStorage) post-mount and syncing it into React
  // state is the deliberate SSR-safe pattern here — server can't see localStorage,
  // so doing it in a lazy initializer would cause a hydration mismatch. The
  // react-hooks/set-state-in-effect rule is a false positive for this case.
  useEffect(() => {
    try {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- deliberate post-mount localStorage read; see comment above
      setDiffMode(localStorage.getItem("thebrief.diffMode") === "1");
    } catch {
      // ignore
    }
    try {
      const params = new URLSearchParams(window.location.search);
      setPrintMode(params.get("print") === "1");
    } catch {
      // ignore
    }
  }, []);

  // Apply body classes for diff/print modes. tb-print-root mirrors tb-print
  // onto <html> (spec §9.1b): html's own `background: var(--paper)` and any
  // getComputedStyle(documentElement) token read need the print tokens too —
  // body-level overrides can't reach either.
  useEffect(() => {
    document.body.classList.toggle("tb-print", printMode);
    document.documentElement.classList.toggle("tb-print-root", printMode);
    document.body.classList.toggle("tb-diff", diffMode);
    // Cleanup on unmount: body/html outlive this component, so a client-side
    // navigation away from a ?print=1 page (e.g. to /archive) must not carry
    // the print classes with it (review-caught).
    return () => {
      document.body.classList.remove("tb-print", "tb-diff");
      document.documentElement.classList.remove("tb-print-root");
    };
  }, [printMode, diffMode]);

  // Print renders light regardless of the visitor's theme (interim slice of
  // facelift spec §9.1c, pulled into PR A alongside dark mode): dark tokens
  // on white print paper measure 1.29:1 — invisible. Forcing the data-theme
  // ATTRIBUTE (not CSS overrides) also makes §3's useTheme consumers rebuild
  // every chart in light inks — canvases can't be recolored by print
  // stylesheets. The full §9 print token contract ships in PR C; this keeps
  // print output identical to pre-dark main. Native Cmd+P is best-effort:
  // the async chart rebuild may not beat the print snapshot (spec §11.12) —
  // ?print=1 is the documented path. The prior theme is parked in
  // data-theme-resume so both paths share one save/restore slot.
  useEffect(() => {
    const de = document.documentElement;
    const forceLight = () => {
      if (de.dataset.theme === "dark") {
        de.dataset.themeResume = "dark";
        de.dataset.theme = "light";
      }
    };
    const restore = () => {
      if (de.dataset.themeResume) {
        de.dataset.theme = de.dataset.themeResume;
        delete de.dataset.themeResume;
      }
    };
    // afterprint must NOT restore dark while ?print=1 is still active —
    // a Cmd+P from an already-forced ?print=1 page would otherwise flip
    // the visible page back to dark mid-print-mode.
    const onAfterPrint = () => {
      if (!printMode) restore();
    };
    if (printMode) forceLight();
    window.addEventListener("beforeprint", forceLight);
    window.addEventListener("afterprint", onAfterPrint);
    return () => {
      window.removeEventListener("beforeprint", forceLight);
      window.removeEventListener("afterprint", onAfterPrint);
      if (printMode) restore();
    };
  }, [printMode]);

  // Persist diff toggle
  useEffect(() => {
    try {
      localStorage.setItem("thebrief.diffMode", diffMode ? "1" : "0");
    } catch {
      // ignore
    }
  }, [diffMode]);

  // Hydrate from Supabase on mount — initialData was server-fetched but we re-fetch
  // to get the freshest state and to write the localStorage cache for next visit.
  // Skipped in preview mode: the fixture payload is the source of truth there.
  useEffect(() => {
    if (preview || historical) return;
    let cancelled = false;
    (async () => {
      try {
        const sb = getBrowserSupabase();
        const { data: rpc, error } = await sb.rpc("get_latest_brief");
        if (cancelled || error || !rpc?.brief) return;
        const fresh: BriefPayload = { ...rpc, _source: "live", _fetchedAt: Date.now() };
        setData(fresh);
        try {
          localStorage.setItem(
            CACHE_KEY,
            JSON.stringify({ payload: rpc, cachedAt: Date.now() })
          );
        } catch {
          // ignore
        }
      } catch {
        // network issue — keep server-rendered initialData
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [preview, historical]);

  // Hash sync
  useEffect(() => {
    function onHash() {
      const slug = (window.location.hash || "").slice(1);
      if (slug) setActive(slug);
    }
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // Scroll-spy via IntersectionObserver. rootMargin's top offset must match
  // .tb-section/.tb-longview's scroll-margin-top (both driven by
  // --nav-offset — review round 1, H1): SecNav can wrap to 2-3 rows at wide
  // viewports, so a hardcoded "-110px" landed sections under the nav by a
  // variable amount depending on how many rows it wrapped to.
  useEffect(() => {
    const ids = data.sections.map((s) => s.slug).concat(["snapshot"]);
    const obs = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) {
          const id = visible[0].target.id;
          if (id) setActive(id);
        }
      },
      { rootMargin: `-${Math.round(navOffset)}px 0px -60% 0px`, threshold: 0 }
    );
    ids.forEach((id) => {
      const el = document.getElementById(id);
      if (el) obs.observe(el);
    });
    return () => obs.disconnect();
  }, [data, navOffset]);

  // Sticky bar appears after the masthead scrolls out
  useEffect(() => {
    const masthead = document.getElementById("masthead");
    if (!masthead) return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        setStickyVisible(!entry.isIntersecting);
      },
      { rootMargin: "-40px 0px 0px 0px" }
    );
    obs.observe(masthead);
    return () => obs.disconnect();
  }, [data]);

  const jump = useCallback(
    (slug: string) => {
      setActive(slug);
      if (typeof history !== "undefined" && history.replaceState) {
        history.replaceState(null, "", `#${slug}`);
      } else {
        window.location.hash = slug;
      }
      const el = document.getElementById(slug);
      // A CSS prefers-reduced-motion switch can't stop this call — Element.
      // scrollIntoView({behavior:"smooth"}) animates regardless of the CSS
      // scroll-behavior property once a caller passes its own explicit
      // `behavior` (review round 1, H3; measured an 11,028px animated
      // scroll with reduced motion requested).
      if (el) el.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
    },
    [reducedMotion]
  );

  const bodySections = data.sections.filter(
    (s) => s.slug !== "snapshot" && s.slug !== "nbr"
  );
  const groupedSections = GROUP_ORDER.map((key) => ({
    key,
    sections: bodySections.filter((s) => s.group_key === key),
  })).filter((g) => g.sections.length > 0);

  // Sequential section numbers (1, 2, 3, …) based on rendered body order.
  // bodySections is ord-sorted but the body renders group-grouped, so build
  // the display map from the flattened render order — otherwise labels skip.
  const flatRenderOrder = groupedSections.flatMap((g) => g.sections);
  const displayOrdBySlug = new Map<string, number>(
    flatRenderOrder.map((s, i) => [s.slug, i + 1])
  );

  // Sequential FIG numbers (1, 2, …) for charted sections only, in the SAME
  // reading order as displayOrdBySlug — replaces CHART_CARD_HEADS' old
  // chart-addition-order numbering (fx=01…bb=08), which printed out of
  // order and skipped FIG.04 once the comm section was retired.
  const chartOrdBySlug = new Map<string, number>();
  let chartCounter = 0;
  for (const s of flatRenderOrder) {
    if (SECTION_TO_CHART[s.slug] && s.series && s.series.length > 1) {
      chartCounter += 1;
      chartOrdBySlug.set(s.slug, chartCounter);
    }
  }

  // The lead section (weight >= 2 — same flag that drives is-hero) gets an
  // accented SecNav item (spec §7.7). Production carries one lead per issue;
  // first-match is the tiebreak, and a collapsed dead section never leads.
  const leadSlug = flatRenderOrder.find(
    (s) => (s.weight ?? 1) >= 2 && s.freshness !== "unavailable"
  )?.slug;

  return (
    <div className="tb-shell">
      {preview && (
        <div
          role="status"
          aria-label="Preview mode — fixture data"
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            zIndex: 9999,
            backgroundColor: "var(--warn)",
            color: "var(--ink)",
            fontFamily: "var(--mono)",
            fontSize: "11px",
            fontWeight: 600,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            textAlign: "center",
            padding: "6px var(--gutter)",
            borderRadius: 0,
          }}
        >
          PREVIEW MODE · fixture-loaded · NOT live data
        </div>
      )}
      {/* #content: <main> always renders; the old #cover target was already
          dead on null-cover issues (spec §5.1) and Cover is retired (§7.5). */}
      <a href="#content" className="tb-skip">
        Skip to content
      </a>
      <StickyBar brief={data.brief} source={data._source} visible={stickyVisible} />
      {/* The ink band (spec §5.1): a true full-bleed wrapper — a <div>, not a
          <header> (Masthead's root already is one, and a second top-level
          header would add a spurious banner landmark next to StickyBar's).
          .tb-band-inner's gutters are owned by the §4.3 safe-area rules. */}
      <div className="tb-band">
        <div className="tb-band-inner">
          <Masthead
            brief={data.brief}
            source={data._source}
            fetchedAt={data._fetchedAt}
            sectionCount={flatRenderOrder.length}
            historical={historical}
          />
        </div>
      </div>
      <main id="content" className="tb-body">
        <SnapshotStrip sections={data.sections} />
        <SecNav
          sections={flatRenderOrder}
          activeSlug={active}
          onJump={jump}
          diffMode={diffMode}
          onToggleDiff={() => setDiffMode((v) => !v)}
          displayOrdBySlug={displayOrdBySlug}
          leadSlug={leadSlug}
        />
        {groupedSections.map(({ key, sections }) => (
          <Fragment key={key}>
            <div className="tb-group" data-group={key}>
              <div className="tb-group-header">
                <span className="tb-group-label">{GROUP_LABELS[key]}</span>
                <span className="tb-group-rule" aria-hidden="true" />
              </div>
              {sections.map((s) => (
                <Section
                  key={s.slug}
                  section={s}
                  diffMode={diffMode}
                  displayOrd={displayOrdBySlug.get(s.slug)}
                  chartOrd={chartOrdBySlug.get(s.slug)}
                  issueDate={data.brief?.brief_date}
                  groupLabel={GROUP_LABELS[key]}
                />
              ))}
            </div>
            {/* The Long View sits between Overview and the next group (Banking).
                Renders nothing when `longView` is null. Fragment is used (vs. a
                wrapping div) so the existing `.tb-group + .tb-group` adjacent-
                sibling CSS rule still matches across groups. The rule
                `.tb-longview + .tb-group` gives Banking — preceded by LongView
                instead of an adjacent .tb-group — the same group-gap tiers:
                26px desktop / 22px ≤920 / 20px print (facelift-spec §6). */}
            {key === "overview" && <LongView data={longView} />}
          </Fragment>
        ))}
        <SubscribeCTA volume={data.brief?.volume} issueNo={data.brief?.issue_no} />
      </main>

      <footer className="tb-foot">
        {/* Tagline's first sentence moved here from the masthead (spec §5.3,
            owner veto §11.2); the other two sentences are dropped. */}
        <div>
          The Brief · Daily macro &amp; markets read for Bangladesh banking professionals · Vol.{" "}
          {data.brief?.volume} · Issue {data.brief?.issue_no}
        </div>
        <div>Curated daily · Read time {data.brief?.read_minutes ?? 15} min</div>
        <div>
          <Link href="/archive">Archive →</Link>
        </div>
      </footer>

      <StatusBar source={data._source} fetchedAt={data._fetchedAt} />
    </div>
  );
}
