type Props = {
  lens?: string;
  frame?: string;
  briefDate?: string;
};

const LENS_LABEL: Record<string, string> = {
  banking: "banking lens",
  fx: "FX lens",
  dse: "markets lens",
  tbond: "rates lens",
  macro: "macro lens",
  iran: "external lens",
  bb: "central bank lens",
  weekly_wrap: "weekly wrap",
};

const WEEKDAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function MastheadLensPill({ lens, frame, briefDate }: Props) {
  if (!lens) return null;
  const lensLabel = LENS_LABEL[lens] ?? `${lens} lens`;
  let dayLabel = "";
  if (briefDate) {
    const d = new Date(briefDate);
    if (!isNaN(d.getTime())) {
      const jsDay = d.getUTCDay();
      // JS getUTCDay: 0=Sun..6=Sat. Map to Mon=0..Sun=6 for the WEEKDAY array.
      const idx = jsDay === 0 ? 6 : jsDay - 1;
      dayLabel = WEEKDAY[idx];
    }
  }
  return (
    <div className="tb-masthead-lens-pill" aria-label={`Lens: ${lensLabel}`}>
      {dayLabel && (
        <>
          <span className="tb-mlp-day">{dayLabel}</span>
          <span className="tb-mlp-sep"> · </span>
        </>
      )}
      <span className="tb-mlp-lens">{lensLabel}</span>
      {frame && lens !== "weekly_wrap" && (
        <>
          <span className="tb-mlp-sep"> · </span>
          <span className="tb-mlp-frame">{frame.replace("-", " ")} frame</span>
        </>
      )}
    </div>
  );
}
