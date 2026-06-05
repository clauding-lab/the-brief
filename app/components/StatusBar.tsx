import type { DataSource } from "@/types/brief";

interface StatusBarProps {
  source?: DataSource;
  fetchedAt?: number;
}

export function StatusBar({ source, fetchedAt }: StatusBarProps) {
  const map: Record<DataSource, string> = {
    live: "Live",
    cache: "Cached",
    static: "Static fallback",
  };
  const cls = source === "live" ? "" : source === "cache" ? "is-cache" : "is-static";
  const time = fetchedAt
    ? new Date(fetchedAt).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Dhaka" })
    : null;
  return (
    <div className={`tb-statusbar ${cls}`}>
      <span className="dot" />
      <span>
        {map[source ?? "static"]}
        {time ? ` · ${time}` : ""}
      </span>
    </div>
  );
}
