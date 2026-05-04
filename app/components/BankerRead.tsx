import type { BankerRead as BankerReadShape } from "@/types/brief";
import { Hair } from "./Hair";
import { Mark } from "./Mark";

interface BankerReadProps {
  read: BankerReadShape;
  hero?: boolean;
}

export function BankerRead({ read, hero = false }: BankerReadProps) {
  const { verdict, watch = [], risk = [], runway } = read;
  return (
    <>
      <Hair style={{ marginTop: 36 }} />
      <div className={`tb-banker${hero ? " is-hero" : ""}`}>
        {runway ? (
          <div className="tb-banker-runway">
            <div className="num">
              {runway.value}
              <span className="dot">.</span>
            </div>
            <div className="label">{runway.unit}</div>
          </div>
        ) : (
          <div />
        )}
        <div className="tb-banker-body">
          <div>
            <div className="tb-banker-section-eyebrow">
              {hero && <span className="tb-banker-leadflag">LEAD</span>}
              VERDICT<div className="rule" />
            </div>
            <div className="tb-banker-verdict">{verdict}</div>
          </div>
          <div className="tb-banker-watchrisk">
            <div>
              <h4>WATCH</h4>
              <Hair tone="soft" style={{ marginBottom: 10 }} />
              <ul>
                {watch.map((t, i) => (
                  <li key={i}>
                    <Mark kind="warn" />
                    <span>{t}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h4>RISK</h4>
              <Hair tone="soft" style={{ marginBottom: 10 }} />
              <ul>
                {risk.map((t, i) => (
                  <li key={i}>
                    <Mark kind="bear" />
                    <span>{t}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
