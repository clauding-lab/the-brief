"use client";

import { useEffect, useState, useCallback, Fragment } from "react";
import type { BriefPayload, SectionGroup } from "@/types/brief";
import { getBrowserSupabase } from "@/lib/supabase";
import { Masthead } from "./Masthead";
import { StickyBar } from "./StickyBar";
import { SnapshotStrip } from "./SnapshotStrip";
import { SecNav } from "./SecNav";
import { Cover } from "./Cover";
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
  | { initialData: BriefPayload; brief?: never; sections?: never; preview?: never }
  | { brief: BriefPayload["brief"]; sections: BriefPayload["sections"]; initialData?: never; preview?: boolean };

export function ClientApp(props: ClientAppProps) {
  const initialData: BriefPayload =
    "initialData" in props && props.initialData !== undefined
      ? props.initialData
      : { brief: props.brief!, sections: props.sections!, _source: "static" };
  const preview = ("preview" in props && props.preview) ?? false;

  const [data, setData] = useState<BriefPayload>(initialData);
  const [active, setActive] = useState<string>(() => {
    if (typeof window === "undefined") return "snapshot";
    return (window.location.hash || "#snapshot").slice(1);
  });
  const [stickyVisible, setStickyVisible] = useState(false);
  const [diffMode, setDiffMode] = useState<boolean>(false);
  const [printMode, setPrintMode] = useState<boolean>(false);

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

  // Apply body classes for diff/print modes
  useEffect(() => {
    document.body.classList.toggle("tb-print", printMode);
    document.body.classList.toggle("tb-diff", diffMode);
  }, [printMode, diffMode]);

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
    if (preview) return;
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
  }, [preview]);

  // Hash sync
  useEffect(() => {
    function onHash() {
      const slug = (window.location.hash || "").slice(1);
      if (slug) setActive(slug);
    }
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // Scroll-spy via IntersectionObserver
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
      { rootMargin: "-110px 0px -60% 0px", threshold: 0 }
    );
    ids.forEach((id) => {
      const el = document.getElementById(id);
      if (el) obs.observe(el);
    });
    return () => obs.disconnect();
  }, [data]);

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

  const jump = useCallback((slug: string) => {
    setActive(slug);
    if (typeof history !== "undefined" && history.replaceState) {
      history.replaceState(null, "", `#${slug}`);
    } else {
      window.location.hash = slug;
    }
    const el = document.getElementById(slug);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  const snapshotSection = data.sections.find((s) => s.slug === "snapshot");
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
      <a href="#cover" className="tb-skip">
        Skip to content
      </a>
      <StickyBar brief={data.brief} source={data._source} visible={stickyVisible} />
      <main id="content" className="tb-body">
        <Masthead
          brief={data.brief}
          source={data._source}
          sections={data.sections}
          displayOrdBySlug={displayOrdBySlug}
        />
        <SnapshotStrip section={snapshotSection} />
        <SecNav
          sections={data.sections}
          activeSlug={active}
          onJump={jump}
          diffMode={diffMode}
          onToggleDiff={() => setDiffMode((v) => !v)}
          displayOrdBySlug={displayOrdBySlug}
        />
        <Cover brief={data.brief} sections={data.sections} />
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
                />
              ))}
            </div>
            {/* The Long View sits between Overview and the next group (Banking).
                Renders nothing when `longView` is null. Fragment is used (vs. a
                wrapping div) so the existing `.tb-group + .tb-group` adjacent-
                sibling CSS rule still matches across groups. The new rule
                `.tb-longview + .tb-group` (added in Task 5) restores the 64px
                top margin on Banking, which is preceded by LongView instead of
                an adjacent .tb-group. */}
            {key === "overview" && <LongView data={longView} />}
          </Fragment>
        ))}
        <SubscribeCTA volume={data.brief?.volume} issueNo={data.brief?.issue_no} />
      </main>

      <footer className="tb-foot">
        <div>
          The Brief · Bangladesh business intelligence · Vol. {data.brief?.volume} · Issue{" "}
          {data.brief?.issue_no}
        </div>
        <div>Curated daily · Read time {data.brief?.read_minutes ?? 15} min</div>
      </footer>

      <StatusBar source={data._source} fetchedAt={data._fetchedAt} />
    </div>
  );
}
