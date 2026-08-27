import type { Brief, DataSource } from "@/types/brief";
import { formatBriefDate } from "@/lib/format";
import { ThemeToggle } from "./ThemeToggle";

interface StickyBarProps {
  brief?: Brief;
  source?: DataSource;
  visible: boolean;
}

export function StickyBar({ brief, source, visible }: StickyBarProps) {
  const dateLabel = formatBriefDate(brief?.brief_date);
  const issueNo = brief?.issue_no ?? 87;
  const vol = brief?.volume ?? 1;
  const sourceLabel = source === "live" ? "Live" : source === "cache" ? "Cached" : "Static";

  // inert while hidden (facelift spec §2): the bar's hidden state is
  // aria-hidden + pointer-events:none but its children stayed in tab
  // order — inert removes the hidden ThemeToggle (and everything else)
  // from keyboard focus. React 19 takes it as a plain boolean prop.
  return (
    <header
      className={`tb-stickybar ${visible ? "is-visible" : ""}`}
      aria-hidden={!visible}
      inert={!visible}
    >
      <div className="tb-stickybar-inner">
        <div className="meta">
          No. {String(issueNo).padStart(2, "0")} / Vol. {String(vol).padStart(2, "0")}
        </div>
        <div className="wordmark">
          The Brief<span className="dot">.</span>
        </div>
        <div className="meta meta-right">
          <span style={{ marginRight: 14 }}>{dateLabel}</span>
          <span className="tb-live">
            <span className="pulse" />
            <span>{sourceLabel}</span>
          </span>
          {/* On the band since PR C (spec §2/§5.4). */}
          <ThemeToggle onBand />
        </div>
      </div>
    </header>
  );
}
