import type { Brief, DataSource } from "@/types/brief";
import { formatBriefDate } from "@/lib/format";

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

  return (
    <header className={`tb-stickybar ${visible ? "is-visible" : ""}`} aria-hidden={!visible}>
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
        </div>
      </div>
    </header>
  );
}
