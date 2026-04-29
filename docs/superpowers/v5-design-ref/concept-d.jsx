// Concept D — Risk Map
// Hero = 2D scatter of sections (volatility × significance today).
// Hover/tap a dot, an adjacent pane reveals the section. Below the map,
// sections flow in the importance order the map implies.

function TypeScale({ kind = "h1", children, style = {} }) {
  const base = {
    h1: { fontFamily:"'GT Alpina','Source Serif 4',Georgia,serif", fontWeight: 700, fontSize: 66, lineHeight: .96, letterSpacing:"-.02em" },
    h2: { fontFamily:"'Source Serif 4',Georgia,serif", fontWeight: 700, fontSize: 32, lineHeight: 1.08, letterSpacing:"-.01em" },
    lbl:{ fontFamily:"'IBM Plex Mono',JetBrains Mono,monospace", fontWeight: 500, fontSize: 10.5, letterSpacing:".2em", textTransform:"uppercase" },
    mono:{ fontFamily:"'IBM Plex Mono',JetBrains Mono,monospace", fontVariantNumeric:"tabular-nums" },
  };
  return <div style={{ ...base[kind], ...style }}>{children}</div>;
}

function RiskMap({ active, setActive }) {
  const W = 760, H = 420, padL = 64, padR = 30, padT = 36, padB = 56;
  const xScale = v => padL + (v / 10) * (W - padL - padR);
  const yScale = v => H - padB - (v / 10) * (H - padT - padB);

  // background quadrant tints + labels
  const midX = xScale(5), midY = yScale(5);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display:"block" }}>
      <defs>
        <radialGradient id="dotGlow">
          <stop offset="0%" stopColor="#6b1f27" stopOpacity=".18"/>
          <stop offset="100%" stopColor="#6b1f27" stopOpacity="0"/>
        </radialGradient>
      </defs>

      {/* quadrant fills */}
      <rect x={padL} y={padT} width={midX-padL} height={midY-padT} fill="#f3ede0"/>
      <rect x={midX} y={padT} width={W-padR-midX} height={midY-padT} fill="#f0e3df"/>
      <rect x={padL} y={midY} width={midX-padL} height={H-padB-midY} fill="#f5f0e4"/>
      <rect x={midX} y={midY} width={W-padR-midX} height={H-padB-midY} fill="#efe8d8"/>

      {/* grid */}
      {[1,2,3,4,5,6,7,8,9].map(v => (
        <g key={v}>
          <line x1={xScale(v)} x2={xScale(v)} y1={padT} y2={H-padB} stroke="#cfc4a4" strokeWidth=".5" strokeDasharray="2 3"/>
          <line x1={padL} x2={W-padR} y1={yScale(v)} y2={yScale(v)} stroke="#cfc4a4" strokeWidth=".5" strokeDasharray="2 3"/>
        </g>
      ))}

      {/* axes */}
      <line x1={padL} x2={W-padR} y1={H-padB} y2={H-padB} stroke="#171310" strokeWidth="1.2"/>
      <line x1={padL} x2={padL} y1={padT} y2={H-padB} stroke="#171310" strokeWidth="1.2"/>

      {/* axis ticks */}
      {[0,2.5,5,7.5,10].map(v => (
        <g key={"x"+v}>
          <line x1={xScale(v)} x2={xScale(v)} y1={H-padB} y2={H-padB+4} stroke="#171310" strokeWidth="1"/>
          <text x={xScale(v)} y={H-padB+16} textAnchor="middle" fontSize="9" fontFamily="IBM Plex Mono,monospace" fill="#6c6358">{v.toFixed(0)}</text>
        </g>
      ))}
      {[0,2.5,5,7.5,10].map(v => (
        <g key={"y"+v}>
          <line x1={padL-4} x2={padL} y1={yScale(v)} y2={yScale(v)} stroke="#171310" strokeWidth="1"/>
          <text x={padL-8} y={yScale(v)+3} textAnchor="end" fontSize="9" fontFamily="IBM Plex Mono,monospace" fill="#6c6358">{v.toFixed(0)}</text>
        </g>
      ))}

      {/* axis labels */}
      <text x={W-padR} y={H-padB+32} textAnchor="end" fontSize="10" letterSpacing="2" fontFamily="IBM Plex Mono,monospace" fill="#171310" fontWeight="600">
        MOVEMENT TODAY →
      </text>
      <g transform={`translate(${padL-44}, ${(padT+H-padB)/2}) rotate(-90)`}>
        <text fontSize="10" letterSpacing="2" textAnchor="middle" fontFamily="IBM Plex Mono,monospace" fill="#171310" fontWeight="600">
          SIGNIFICANCE FOR THE BOOK →
        </text>
      </g>

      {/* quadrant captions */}
      <text x={xScale(2.5)} y={yScale(8.8)} textAnchor="middle" fontSize="9.5" letterSpacing="3" fontFamily="IBM Plex Mono,monospace" fill="#a29785">SLOW · STRUCTURAL</text>
      <text x={xScale(7.5)} y={yScale(8.8)} textAnchor="middle" fontSize="9.5" letterSpacing="3" fontFamily="IBM Plex Mono,monospace" fill="#a29785">ACTIVE · MATERIAL</text>
      <text x={xScale(2.5)} y={yScale(1.4)} textAnchor="middle" fontSize="9.5" letterSpacing="3" fontFamily="IBM Plex Mono,monospace" fill="#a29785">DORMANT</text>
      <text x={xScale(7.5)} y={yScale(1.4)} textAnchor="middle" fontSize="9.5" letterSpacing="3" fontFamily="IBM Plex Mono,monospace" fill="#a29785">NOISE</text>

      {/* diagonal: "read first" line — upper-right */}
      <line x1={xScale(4)} y1={yScale(10)} x2={xScale(10)} y2={yScale(4)} stroke="#6b1f27" strokeWidth=".8" strokeDasharray="1 4" opacity=".6"/>
      <text x={xScale(9.3)} y={yScale(5.2)} fontSize="9" fontStyle="italic" fontFamily="Source Serif 4, serif" fill="#6b1f27">read first ↗</text>

      {/* dots */}
      {MAP.map(p => {
        const sec = SECTIONS.find(s => s.id === p.id);
        const isActive = active === p.id;
        const color = p.type === "event" ? "#6b1f27" : p.type === "anchor" ? "#171310" : p.type === "slow" ? "#b57a15" : "#2f6b3a";
        return (
          <g key={p.id} onMouseEnter={() => setActive(p.id)} onClick={() => setActive(p.id)} style={{ cursor:"pointer" }}>
            {isActive && <circle cx={xScale(p.x)} cy={yScale(p.y)} r={p.r+16} fill="url(#dotGlow)"/>}
            <circle cx={xScale(p.x)} cy={yScale(p.y)} r={p.r/2}
                    fill={color} opacity={isActive ? 1 : .88}
                    stroke={isActive ? "#171310" : "transparent"} strokeWidth="1.5"/>
            <text x={xScale(p.x)} y={yScale(p.y)+3.5} textAnchor="middle"
                  fontFamily="IBM Plex Mono,monospace" fontWeight="700" fontSize="10"
                  fill={p.type === "slow" ? "#171310" : "#f7f3e9"}>
              §{sec.n}
            </text>
            <text x={xScale(p.x)} y={yScale(p.y) - p.r/2 - 8} textAnchor="middle"
                  fontFamily="Source Serif 4, serif" fontWeight="600" fontSize="12"
                  fill="#171310">
              {sec.kicker.split(" · ")[0]}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function MapDetail({ id }) {
  if (!id) return (
    <div style={{ color:"#6c6358", padding:"24px 4px" }}>
      <TypeScale kind="lbl" style={{ color:"#a29785" }}>No selection</TypeScale>
      <TypeScale kind="h2" style={{ marginTop: 6, fontSize: 22, color:"#6c6358", fontStyle:"italic", fontWeight: 400 }}>
        Hover the map. Read clockwise from the event in the upper-right.
      </TypeScale>
    </div>
  );
  const sec = SECTIONS.find(s => s.id === id);
  const m = METRICS[id];
  const pull = PULLS[id];
  const br = BR[id];
  return (
    <div style={{ borderTop:"3px solid #6b1f27", padding:"20px 4px 0" }}>
      <div style={{ display:"flex", alignItems:"baseline", gap: 10, color:"#6c6358" }}>
        <TypeScale kind="lbl" style={{ color:"#6b1f27" }}>§{sec.n}</TypeScale>
        <TypeScale kind="lbl">{sec.kicker}</TypeScale>
        <span style={{ marginLeft:"auto", fontFamily:"IBM Plex Mono,monospace", fontSize: 10, letterSpacing:".14em", textTransform:"uppercase" }}>{sec.src}</span>
      </div>
      <TypeScale kind="h2" style={{ marginTop: 6, color:"#171310" }}>{sec.title}</TypeScale>
      <div style={{ marginTop: 10, padding:"10px 14px", background:"#14110e", color:"#e8dfc9", fontFamily:"Source Serif 4, serif", fontStyle:"italic", fontSize: 14, lineHeight: 1.4, borderLeft:"3px solid #6b1f27" }}>
        "{pull}"
      </div>
      <div style={{ marginTop: 14, display:"grid", gridTemplateColumns:"repeat(2,1fr)", gap: 8 }}>
        {m.slice(0,4).map((x,i) => {
          const col = x.dir === "up" ? "#2f6b3a" : x.dir === "down" ? "#a8322a" : "#6c6358";
          return (
            <div key={i} style={{ borderTop:"1px solid #c8bfa6", paddingTop: 6 }}>
              <div style={{ fontFamily:"IBM Plex Mono,monospace", fontSize: 9.5, letterSpacing:".14em", textTransform:"uppercase", color:"#6c6358" }}>{x.label}</div>
              <div style={{ fontFamily:"IBM Plex Mono,monospace", fontSize: 22, fontWeight: 500, fontVariantNumeric:"tabular-nums", color:"#171310", lineHeight: 1 }}>
                {x.value}<span style={{ fontSize: 11, color:"#6c6358", marginLeft: 3 }}>{x.unit}</span>
              </div>
              <div style={{ fontFamily:"IBM Plex Mono,monospace", fontSize: 10.5, color: col, marginTop: 2 }}>
                {x.dir === "up" ? "▲" : x.dir === "down" ? "▼" : "–"} {x.delta}
              </div>
            </div>
          );
        })}
      </div>
      <div style={{ marginTop: 14, fontFamily:"Source Serif 4, serif", fontSize: 13.5, lineHeight: 1.5, color:"#3b342c" }}>
        <b>Action.</b> {br.action} <b>Trigger.</b> {br.trigger}
      </div>
    </div>
  );
}

function FlowItem({ id, rank }) {
  const sec = SECTIONS.find(s => s.id === id);
  const m = METRICS[id];
  const pull = PULLS[id];
  const isLead = rank === 1;
  return (
    <div style={{ borderTop: isLead ? "3px solid #6b1f27" : "1px solid #c8bfa6", paddingTop: isLead ? 18 : 14, paddingBottom: isLead ? 22 : 14 }}>
      <div style={{ display:"flex", alignItems:"baseline", gap: 10, color:"#6c6358" }}>
        <span style={{ fontFamily:"'Source Serif 4',serif", fontWeight: 900, fontSize: 28, color: isLead ? "#6b1f27" : "#171310", lineHeight: 1, fontStyle:"italic" }}>{String(rank).padStart(2,"0")}</span>
        <TypeScale kind="lbl" style={{ color:"#6b1f27" }}>§{sec.n} · {sec.kicker}</TypeScale>
        <span style={{ marginLeft:"auto", fontFamily:"IBM Plex Mono,monospace", fontSize: 9.5, letterSpacing:".16em", textTransform:"uppercase", color:"#a29785" }}>{sec.src}</span>
      </div>
      <div style={{ marginTop: 6, fontFamily:"'Source Serif 4',serif", fontWeight: 700, fontSize: isLead ? 28 : 20, lineHeight: 1.1, letterSpacing:"-.005em", textWrap:"balance", color:"#171310" }}>
        {sec.title}
      </div>
      <div style={{ marginTop: 8, display:"grid", gridTemplateColumns: isLead ? "1.4fr 1fr" : "1fr", gap: 18 }}>
        <div>
          <div style={{ fontFamily:"'Source Serif 4',serif", fontStyle:"italic", fontSize: isLead ? 17 : 14.5, lineHeight: 1.45, color:"#3b342c" }}>
            "{pull}"
          </div>
          <div style={{ marginTop: 10, fontFamily:"IBM Plex Mono,monospace", fontSize: 11, color:"#3b342c", lineHeight: 1.6 }}>
            {m.slice(0,3).map((x,i) => {
              const col = x.dir === "up" ? "#2f6b3a" : x.dir === "down" ? "#a8322a" : "#6c6358";
              return (
                <span key={i} style={{ display:"inline-block", marginRight: 18 }}>
                  <span style={{ color:"#6c6358", textTransform:"uppercase", letterSpacing:".14em", fontSize: 9.5 }}>{x.label}</span>{" "}
                  <b style={{ color:"#171310" }}>{x.value}</b>
                  <span style={{ color:"#6c6358" }}>{x.unit ? " "+x.unit : ""}</span>
                  <span style={{ color: col, marginLeft: 6 }}>{x.dir === "up" ? "▲" : x.dir === "down" ? "▼" : "–"}{x.delta}</span>
                </span>
              );
            })}
          </div>
        </div>
        {isLead && (
          <div style={{ background:"#14110e", color:"#e8dfc9", padding:"14px 16px", borderLeft:"3px solid #6b1f27" }}>
            <div style={{ fontFamily:"IBM Plex Mono,monospace", fontSize: 10, letterSpacing:".18em", textTransform:"uppercase", color:"#f4c95d", marginBottom: 6 }}>BankerRead</div>
            <div style={{ fontFamily:"'Source Serif 4',serif", fontSize: 13.5, lineHeight: 1.45 }}>
              <b style={{ color:"#f4c95d" }}>A ·</b> {BR[id].meaning}<br/>
              <b style={{ color:"#f4c95d" }}>B ·</b> {BR[id].action}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ConceptD() {
  const [active, setActive] = React.useState("oil");

  return (
    <div style={{
      width: "100%", minHeight: "100%",
      background: "#f7f3e9",
      padding: "36px 44px 52px",
      fontFamily:"'Source Serif 4', Georgia, serif",
      color:"#171310",
    }}>
      {/* dateline strip */}
      <div style={{ background:"#6b1f27", color:"#f4e7d9", padding:"6px 14px", display:"flex", justifyContent:"space-between", fontFamily:"IBM Plex Mono, monospace", fontSize: 10, letterSpacing:".16em", textTransform:"uppercase" }}>
        <span>● LIVE · 06:15 BDT · Dhaka</span>
        <span>USD/BDT 122.70 · DSEX 5,232 · Brent $95.10 · Reserves $34.12bn</span>
        <span>Next update · 18:00 close</span>
      </div>

      {/* masthead */}
      <header style={{ padding:"28px 0 22px", borderBottom:"1px solid #171310", display:"grid", gridTemplateColumns:"1.6fr 1fr", gap: 40, alignItems:"end" }}>
        <div>
          <TypeScale kind="lbl" style={{ color:"#6c6358", marginBottom: 8 }}>{VOL} · {ISSUE} · {TODAY}</TypeScale>
          <TypeScale kind="h1">The <em style={{ fontStyle:"italic", fontWeight: 400, color:"#6b1f27" }}>Brief</em>, plotted.</TypeScale>
          <div style={{ marginTop: 10, fontFamily:"'Source Serif 4',serif", fontSize: 15, lineHeight: 1.5, color:"#3b342c", maxWidth: "60ch" }}>
            Seven sections arranged by <i>how much they moved</i> and <i>how much the book cares</i> — not by section number. The section order below follows the map.
          </div>
        </div>
        <div style={{ borderLeft:"1px solid #c8bfa6", paddingLeft: 24 }}>
          <TypeScale kind="lbl" style={{ color:"#6b1f27", marginBottom: 6 }}>Today's call</TypeScale>
          <div style={{ fontFamily:"'Source Serif 4',serif", fontSize: 17, lineHeight: 1.4, textWrap:"balance" }}>
            Hormuz is <b>priced risk, not scarcity.</b> Hedge the oil book — <span style={{ color:"#6b1f27", fontStyle:"italic" }}>not the headline.</span>
          </div>
        </div>
      </header>

      {/* hero: map + detail */}
      <section style={{ marginTop: 28, display:"grid", gridTemplateColumns: "1.6fr 1fr", gap: 32, alignItems:"start" }}>
        <div>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"baseline", marginBottom: 8 }}>
            <TypeScale kind="lbl">§ Risk map · 21 Apr 06:15</TypeScale>
            <TypeScale kind="lbl" style={{ color:"#a29785" }}>Area ∝ read-weight · color = kind</TypeScale>
          </div>
          <div style={{ border:"1px solid #171310", background:"#faf6ec", padding:"8px 10px 4px" }}>
            <RiskMap active={active} setActive={setActive}/>
          </div>
          {/* legend */}
          <div style={{ display:"flex", gap: 20, marginTop: 10, fontFamily:"IBM Plex Mono,monospace", fontSize: 10, letterSpacing:".12em", textTransform:"uppercase", color:"#6c6358" }}>
            <span><span style={{ display:"inline-block", width: 10, height: 10, borderRadius: 5, background:"#6b1f27", marginRight: 6, verticalAlign:"-1px" }}/>event</span>
            <span><span style={{ display:"inline-block", width: 10, height: 10, borderRadius: 5, background:"#2f6b3a", marginRight: 6, verticalAlign:"-1px" }}/>fresh print</span>
            <span><span style={{ display:"inline-block", width: 10, height: 10, borderRadius: 5, background:"#b57a15", marginRight: 6, verticalAlign:"-1px" }}/>slow / structural</span>
            <span><span style={{ display:"inline-block", width: 10, height: 10, borderRadius: 5, background:"#171310", marginRight: 6, verticalAlign:"-1px" }}/>anchor</span>
          </div>
        </div>
        <MapDetail id={active}/>
      </section>

      {/* The flow — sections in map-implied order */}
      <section style={{ marginTop: 40 }}>
        <div style={{ display:"flex", alignItems:"baseline", justifyContent:"space-between", borderTop:"3px double #171310", paddingTop: 14, marginBottom: 16 }}>
          <TypeScale kind="lbl">§ The flow · as plotted</TypeScale>
          <TypeScale kind="lbl" style={{ color:"#a29785" }}>Ordered by significance × movement · not by section number</TypeScale>
        </div>
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", columnGap: 40, rowGap: 4 }}>
          {READ_ORDER.map((id, i) => <FlowItem key={id} id={id} rank={i+1}/>)}
        </div>
      </section>

      {/* colophon */}
      <footer style={{ marginTop: 40, padding:"16px 0 0", borderTop:"3px double #171310", display:"flex", justifyContent:"space-between", fontFamily:"IBM Plex Mono,monospace", fontSize: 10, letterSpacing:".14em", textTransform:"uppercase", color:"#6c6358" }}>
        <span style={{ color:"#6b1f27", fontWeight: 700 }}>The Brief · {ISSUE} · Risk-map edition</span>
        <span>BB · BBS · DSE · EPB · TCB · Yahoo · Reuters · FT · BBC</span>
        <span>Next edition · 22 Apr · 06:15</span>
      </footer>
    </div>
  );
}

Object.assign(window, { ConceptD });
