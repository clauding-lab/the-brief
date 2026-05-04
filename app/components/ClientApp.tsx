"use client";

import { useEffect, useState, useCallback } from "react";
import type { BriefPayload } from "@/types/brief";
import { getBrowserSupabase } from "@/lib/supabase";
import { Masthead } from "./Masthead";
import { StickyBar } from "./StickyBar";
import { SnapshotStrip } from "./SnapshotStrip";
import { SecNav } from "./SecNav";
import { Cover } from "./Cover";
import { Section } from "./Section";
import { SubscribeCTA } from "./SubscribeCTA";
import { StatusBar } from "./StatusBar";

const CACHE_KEY = "thebrief.lastBrief";

interface ClientAppProps {
  initialData: BriefPayload;
}

export function ClientApp({ initialData }: ClientAppProps) {
  const [data, setData] = useState<BriefPayload>(initialData);
  const [active, setActive] = useState<string>(() => {
    if (typeof window === "undefined") return "snapshot";
    return (window.location.hash || "#snapshot").slice(1);
  });
  const [stickyVisible, setStickyVisible] = useState(false);
  const [diffMode, setDiffMode] = useState<boolean>(false);
  const [printMode, setPrintMode] = useState<boolean>(false);

  // Read localStorage diff + URL print=1 after mount (avoid SSR hydration mismatch)
  useEffect(() => {
    try {
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
  useEffect(() => {
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
  }, []);

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
  const bodySections = data.sections.filter((s) => s.slug !== "snapshot");

  return (
    <div className="tb-shell">
      <a href="#cover" className="tb-skip">
        Skip to content
      </a>
      <StickyBar brief={data.brief} source={data._source} visible={stickyVisible} />
      <main id="content" className="tb-body">
        <Masthead brief={data.brief} source={data._source} sections={data.sections} />
        <SnapshotStrip section={snapshotSection} />
        <SecNav
          sections={data.sections}
          activeSlug={active}
          onJump={jump}
          diffMode={diffMode}
          onToggleDiff={() => setDiffMode((v) => !v)}
        />
        <Cover brief={data.brief} sections={data.sections} />
        {bodySections.map((s) => (
          <Section key={s.slug} section={s} diffMode={diffMode} />
        ))}
        <SubscribeCTA volume={data.brief?.volume} issueNo={data.brief?.issue_no} />
      </main>

      <footer className="tb-foot">
        <div>
          The Brief · Bangladesh business intelligence · Vol. {data.brief?.volume} · Issue{" "}
          {data.brief?.issue_no}
        </div>
        <div>Curated daily · Read time {data.brief?.read_minutes ?? 9} min</div>
      </footer>

      <StatusBar source={data._source} fetchedAt={data._fetchedAt} />
    </div>
  );
}
