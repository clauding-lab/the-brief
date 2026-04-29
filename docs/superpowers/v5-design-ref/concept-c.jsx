// Concept C — Index Card Stack
// Every section = a physical index card, stapled/clipped in loose columns.
// Typewriter labels, rubber stamps, cards of different sizes like a real desk.

function CardC({ section, metrics, pull, rot = 0, tint = "cream", stamp, pin = "clip", width = 320, children, extraStyle = {} }) {
  const tints = {
    cream:  { bg: "#f5efdd", rule: "#d8ceb1", edge: "#ebe0c2" },
    blue:   { bg: "#e4ecee", rule: "#bcc9cc", edge: "#d2dcdf" },
    pink:   { bg: "#f0dedb", rule: "#d5b9b5", edge: "#e5cfcb" },
    manila: { bg: "#e9ddbe", rule: "#c9b98e", edge: "#dcce9f" },
    white:  { bg: "#fafaf4", rule: "#d6d2c5", edge: "#ececde" },
  };
  const t = tints[tint] || tints.cream;
  const rules = Array.from({ length: 14 }, (_, i) => i);
  return (
    <div style={{
      position: "relative", width, background: t.bg,
      transform: `rotate(${rot}deg)`,
      boxShadow: "0 1px 2px rgba(0,0,0,.12), 0 8px 20px rgba(0,0,0,.06), inset 0 0 0 1px " + t.edge,
      padding: "22px 20px 18px",
      fontFamily: "'Special Elite','Courier Prime', ui-monospace, monospace",
      color: "#1a1612",
      ...extraStyle,
    }}>
      {/* red vertical margin line — index-card style */}
      <div style={{ position: "absolute", top: 0, bottom: 0, left: 36, width: 1, background: "rgba(150,40,40,.55)" }}/>
      {/* horizontal ruled lines */}
      {rules.map(i => (
        <div key={i} style={{ position:"absolute", left: 14, right: 14, top: 50 + i*22, height: 1, background: t.rule, opacity: .55 }}/>
      ))}
      {/* pin / clip */}
      {pin === "clip" && (
        <div style={{ position:"absolute", top: -14, left: "50%", transform:"translateX(-50%) rotate(-4deg)", width: 52, height: 26, zIndex: 3 }}>
          <svg width="52" height="26" viewBox="0 0 52 26">
            <rect x="2" y="2" width="48" height="22" rx="2" fill="#8b8a85" stroke="#4a4945" strokeWidth="1"/>
            <rect x="6" y="6" width="40" height="14" fill="none" stroke="#3a3936" strokeWidth=".6"/>
            <rect x="22" y="0" width="8" height="26" fill="#6a6965"/>
          </svg>
        </div>
      )}
      {pin === "staple" && (
        <div style={{ position:"absolute", top: 8, left: 16, width: 22, height: 3, background:"#6a6965", boxShadow:"0 1px 0 rgba(0,0,0,.3)", zIndex: 3 }}/>
      )}
      {pin === "pushpin" && (
        <div style={{ position:"absolute", top: -6, left: 24, zIndex: 3 }}>
          <svg width="20" height="20" viewBox="0 0 20 20">
            <circle cx="10" cy="9" r="8" fill="#c93a2e" stroke="#7a1e18" strokeWidth=".8"/>
            <circle cx="8" cy="6.5" r="2.2" fill="rgba(255,255,255,.5)"/>
          </svg>
        </div>
      )}
      {pin === "tape" && (
        <div style={{ position:"absolute", top: -8, left: "50%", transform:"translateX(-50%) rotate(-2deg)", width: 90, height: 22, background:"rgba(235,210,140,.7)", border:"1px solid rgba(160,130,60,.35)", boxShadow:"0 1px 2px rgba(0,0,0,.1)", zIndex: 3 }}/>
      )}

      {/* header — typewriter label */}
      <div style={{ position:"relative", zIndex: 2, display:"flex", alignItems:"baseline", gap: 6, letterSpacing:".02em", fontSize: 10, textTransform:"uppercase", color: "#5a4d3a" }}>
        <span style={{ padding:"1px 5px", background:"#1a1612", color:"#f5efdd", fontWeight: 700 }}>§{section.n}</span>
        <span>{section.kicker}</span>
        <span style={{ marginLeft: "auto", fontSize: 9 }}>{section.src}</span>
      </div>
      <div style={{ position:"relative", zIndex: 2, marginTop: 8, fontFamily:"'Special Elite',serif", fontSize: 22, lineHeight: 1.05, color:"#1a1612", textWrap:"balance" }}>
        {section.title}
      </div>

      <div style={{ position:"relative", zIndex: 2, marginTop: 12, fontSize: 12.5, lineHeight: 1.5, color:"#2a2420" }}>
        {children}
      </div>

      {/* rubber stamp */}
      {stamp && (
        <div style={{
          position:"absolute", bottom: 14, right: 14, zIndex: 3,
          transform: `rotate(${stamp.rot || -8}deg)`,
          border: `2.5px solid ${stamp.color || "#8a1f1f"}`,
          color: stamp.color || "#8a1f1f",
          padding: "4px 10px 3px",
          fontFamily:"'Special Elite',serif",
          fontSize: 13, fontWeight: 700, letterSpacing: ".14em",
          textTransform:"uppercase",
          opacity: .82,
          background: "transparent",
          borderRadius: 2,
        }}>
          {stamp.text}
        </div>
      )}
    </div>
  );
}

function TypedMetric({ m }) {
  const arrow = m.dir === "up" ? "▲" : m.dir === "down" ? "▼" : "—";
  const col = m.dir === "up" ? "#2d6638" : m.dir === "down" ? "#9c2a22" : "#5a4d3a";
  return (
    <div style={{ display:"grid", gridTemplateColumns:"1fr auto", gap: 4, alignItems:"baseline", padding:"2px 0", borderBottom: "1px dashed rgba(0,0,0,.12)", fontSize: 12 }}>
      <span style={{ textTransform:"uppercase", letterSpacing:".04em", color:"#5a4d3a", fontSize: 10.5 }}>{m.label}</span>
      <span style={{ fontWeight: 700, fontVariantNumeric:"tabular-nums" }}>{m.value}<span style={{ fontWeight:400, fontSize: 9.5, marginLeft: 3, color:"#5a4d3a" }}>{m.unit}</span></span>
      <span style={{ gridColumn:"1 / -1", fontSize: 10.5, color: col, fontStyle:"italic" }}>{arrow} {m.delta}</span>
    </div>
  );
}

function ConceptC() {
  const stack = (id) => ({ sec: SECTIONS.find(s => s.id === id), m: METRICS[id], pull: PULLS[id], br: BR[id] });

  return (
    <div style={{
      width: "100%", minHeight: "100%",
      background: "#1e1a14",
      backgroundImage: [
        "repeating-linear-gradient(90deg, rgba(255,255,255,.015) 0 1px, transparent 1px 8px)",
        "radial-gradient(circle at 30% 20%, rgba(255,220,140,.05), transparent 50%)",
        "radial-gradient(circle at 80% 80%, rgba(255,180,120,.04), transparent 55%)",
      ].join(","),
      padding: "40px 36px 60px",
      fontFamily: "'Special Elite','Courier Prime', ui-monospace, monospace",
      color: "#f5efdd",
      position: "relative",
    }}>
      {/* Masthead — typed slip on the desk */}
      <div style={{ display:"flex", alignItems:"flex-end", justifyContent:"space-between", gap: 24, marginBottom: 28, color:"#f5efdd" }}>
        <div>
          <div style={{ fontSize: 11, letterSpacing:".3em", textTransform:"uppercase", color:"#d9c48a", marginBottom: 6 }}>THE BRIEF · Desk edition</div>
          <div style={{ fontFamily:"'Special Elite',serif", fontSize: 54, lineHeight: .95, letterSpacing:"-.01em" }}>
            TUESDAY FILE<span style={{ color:"#d9c48a" }}>.</span>
          </div>
          <div style={{ marginTop: 10, fontSize: 12, color:"#c9bfa3", maxWidth: "58ch" }}>
            Seven cards on the desk this morning. Ordered by the hand that filed them — not by alphabet, not by score. Read clockwise from the upper-left.
          </div>
        </div>
        <div style={{ border:"1px dashed rgba(245,239,221,.35)", padding:"10px 14px", fontSize: 11, letterSpacing:".14em", textTransform:"uppercase", textAlign:"right", color:"#d9c48a" }}>
          <div>{TODAY}</div>
          <div style={{ marginTop: 3 }}>{VOL} · {ISSUE}</div>
          <div style={{ marginTop: 3, color:"#8a7e5f" }}>06:15 BDT · Dhaka</div>
        </div>
      </div>

      {/* TODAY'S CALL — a taped receipt */}
      <div style={{
        background:"#f5efdd", color:"#1a1612",
        padding:"20px 28px 22px", margin:"0 auto 36px",
        maxWidth: 760, position:"relative",
        transform:"rotate(-.6deg)",
        boxShadow: "0 2px 4px rgba(0,0,0,.2), 0 14px 40px rgba(0,0,0,.35)",
        fontFamily:"'Special Elite',serif",
      }}>
        <div style={{ position:"absolute", top: -10, left: "50%", transform:"translateX(-50%) rotate(-1deg)", width: 140, height: 24, background:"rgba(235,210,140,.6)", border:"1px solid rgba(160,130,60,.25)" }}/>
        <div style={{ fontSize: 10, letterSpacing:".3em", textTransform:"uppercase", color:"#8a1f1f" }}>TODAY'S CALL · Desk editor</div>
        <div style={{ marginTop: 8, fontSize: 19, lineHeight: 1.35, textWrap:"balance" }}>
          Hormuz is priced risk — <span style={{ color:"#8a1f1f" }}>not scarcity</span>. With food CPI sticky at 10.4% and reserves flat-not-building, the margin for a second incident is narrower than it looks. Hedge the oil book, not the headline.
        </div>
        <div style={{ marginTop: 10, fontSize: 10.5, letterSpacing:".2em", textTransform:"uppercase", color:"#5a4d3a", textAlign:"right" }}>— THE BRIEF · 06:15</div>
      </div>

      {/* three columns of cards, loosely stacked */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap: 28, alignItems:"start" }}>

        {/* COL 1 */}
        <div style={{ display:"flex", flexDirection:"column", gap: 32 }}>
          {(() => { const {sec, m, pull} = stack("oil"); return (
            <CardC section={sec} metrics={m} pull={pull} rot={-1.4} tint="pink" pin="pushpin"
                   stamp={{ text:"URGENT", color:"#8a1f1f", rot:-6 }} width={360}>
              {m.map((x,i) => <TypedMetric key={i} m={x}/>)}
              <div style={{ marginTop: 10, padding:"8px 10px", borderLeft:"3px solid #8a1f1f", background:"rgba(138,31,31,.06)", fontStyle:"italic", fontSize: 12.5, lineHeight: 1.45 }}>
                "{pull}"
              </div>
              <div style={{ marginTop: 10, fontSize: 10.5, letterSpacing:".12em", textTransform:"uppercase", color:"#5a4d3a" }}>
                FILED 05:08 · YAHOO · REUTERS
              </div>
            </CardC>
          );})()}

          {(() => { const {sec, m, pull} = stack("fx"); return (
            <CardC section={sec} metrics={m} pull={pull} rot={1.2} tint="blue" pin="clip" width={340}
                   stamp={{ text:"HOLD", color:"#4a5f6a", rot:3 }}>
              {m.map((x,i) => <TypedMetric key={i} m={x}/>)}
              <div style={{ marginTop: 8, fontSize: 11.5, fontStyle:"italic", color:"#3a4248" }}>"{pull}"</div>
            </CardC>
          );})()}

          {(() => { const {sec, m} = stack("tbond"); return (
            <CardC section={sec} metrics={m} rot={-.8} tint="manila" pin="staple" width={320}>
              {m.map((x,i) => <TypedMetric key={i} m={x}/>)}
              {/* tiny curve sparkline */}
              <svg width="100%" height="44" viewBox="0 0 260 44" style={{ marginTop: 8 }}>
                <path d="M8 30 L54 26 L100 22 L146 18 L192 14 L246 8" fill="none" stroke="#1a1612" strokeWidth="1.6"/>
                <path d="M8 34 L54 30 L100 26 L146 22 L192 18 L246 12" fill="none" stroke="#8a7e5f" strokeWidth="1.2" strokeDasharray="3 3"/>
                {["3M","6M","1Y","2Y","5Y","10Y"].map((t,i) => (
                  <text key={t} x={8 + i*47.6} y="42" fontSize="9" fill="#5a4d3a" fontFamily="Special Elite">{t}</text>
                ))}
              </svg>
            </CardC>
          );})()}
        </div>

        {/* COL 2 */}
        <div style={{ display:"flex", flexDirection:"column", gap: 32, paddingTop: 28 }}>
          {(() => { const {sec, m, pull} = stack("macro"); return (
            <CardC section={sec} metrics={m} pull={pull} rot={.8} tint="cream" pin="clip" width={350}
                   stamp={{ text:"AGING · 22d", color:"#b87025", rot:-4 }}>
              {m.map((x,i) => <TypedMetric key={i} m={x}/>)}
              <div style={{ marginTop: 10, padding:"8px 10px", borderLeft:"3px solid #b87025", background:"rgba(184,112,37,.08)", fontStyle:"italic", fontSize: 12.5, lineHeight: 1.45 }}>
                "{pull}"
              </div>
              <div style={{ marginTop: 8, fontSize: 10.5, letterSpacing:".1em", textTransform:"uppercase", color:"#8a1f1f" }}>
                Next release · May 8
              </div>
            </CardC>
          );})()}

          {(() => { const {sec, m, pull} = stack("remit"); return (
            <CardC section={sec} metrics={m} pull={pull} rot={-1.1} tint="white" pin="tape" width={340}
                   stamp={{ text:"CONFIRMED", color:"#2d6638", rot:-7 }}>
              {m.map((x,i) => <TypedMetric key={i} m={x}/>)}
              <div style={{ marginTop: 8, fontSize: 11.5, fontStyle:"italic", color:"#3a3226" }}>"{pull}"</div>
              {/* rising bars */}
              <div style={{ marginTop: 10, display:"flex", alignItems:"flex-end", gap: 3, height: 36 }}>
                {[1.85,1.94,2.01,2.05,2.11,2.18,2.20,2.22,2.25,2.27,2.29,2.31].map((v,i) => (
                  <div key={i} style={{ flex:1, height: `${(v-1.8)*60}px`, background: i === 11 ? "#2d6638" : "#8a7e5f", opacity: i === 11 ? 1 : .6 }}/>
                ))}
              </div>
              <div style={{ fontSize: 9.5, color:"#5a4d3a", marginTop: 3 }}>remit · 12 mo · Apr'25 → Mar'26</div>
            </CardC>
          );})()}
        </div>

        {/* COL 3 */}
        <div style={{ display:"flex", flexDirection:"column", gap: 32, paddingTop: 64 }}>
          {(() => { const {sec, m, pull} = stack("policy"); return (
            <CardC section={sec} metrics={m} pull={pull} rot={1.6} tint="manila" pin="pushpin" width={340}
                   stamp={{ text:"HELD · 4th", color:"#1a1612", rot:5 }}>
              {m.map((x,i) => <TypedMetric key={i} m={x}/>)}
              <div style={{ marginTop: 10, padding:"8px 10px", borderLeft:"3px solid #1a1612", fontStyle:"italic", fontSize: 12.5, lineHeight: 1.45 }}>
                "{pull}"
              </div>
            </CardC>
          );})()}

          {(() => { const {sec, m, pull} = stack("dse"); return (
            <CardC section={sec} metrics={m} pull={pull} rot={-.6} tint="cream" pin="clip" width={340}>
              {m.map((x,i) => <TypedMetric key={i} m={x}/>)}
              <div style={{ marginTop: 8, fontSize: 11.5, fontStyle:"italic", color:"#3a3226" }}>"{pull}"</div>
              {/* sector heat mini */}
              <div style={{ marginTop: 10, display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap: 3, fontSize: 9.5 }}>
                {[{n:"Bk",p:-1.4},{n:"NBFI",p:-1.1},{n:"Txt",p:-.3},{n:"Ph",p:.4},{n:"Fuel",p:.8},{n:"Tel",p:-.6},{n:"Fd",p:.2},{n:"IT",p:.1}].map(s => {
                  const col = s.p>=0 ? `rgba(45,102,56,${.2+Math.abs(s.p)/3})` : `rgba(156,42,34,${.2+Math.abs(s.p)/3})`;
                  return <div key={s.n} style={{ background: col, padding:"4px 3px", textAlign:"center" }}>
                    <div style={{ fontSize: 8.5, color:"#5a4d3a", textTransform:"uppercase", letterSpacing:".06em" }}>{s.n}</div>
                    <div style={{ fontWeight: 700, color: s.p>=0?"#2d6638":"#9c2a22" }}>{s.p>0?"+":""}{s.p.toFixed(1)}</div>
                  </div>;
                })}
              </div>
            </CardC>
          );})()}

          {/* Missing-data card */}
          <div style={{
            width: 300, padding: "22px 20px",
            background: "repeating-linear-gradient(-45deg, #c9bfa3 0 8px, #b8ae92 8px 16px)",
            color:"#1a1612", fontFamily:"'Special Elite',serif",
            transform:"rotate(2.4deg)",
            boxShadow:"0 1px 2px rgba(0,0,0,.12), 0 8px 20px rgba(0,0,0,.06)",
            position:"relative",
          }}>
            <div style={{ position:"absolute", top: -10, right: 24, transform:"rotate(8deg)" }}>
              <svg width="20" height="20" viewBox="0 0 20 20">
                <circle cx="10" cy="9" r="8" fill="#1a1612" stroke="#000" strokeWidth=".8"/>
              </svg>
            </div>
            <div style={{ fontSize: 10, letterSpacing:".3em", textTransform:"uppercase", color:"#8a1f1f" }}>§ UNAVAILABLE</div>
            <div style={{ marginTop: 8, fontSize: 16, lineHeight: 1.2 }}>Sector ROA detail missing today.</div>
            <div style={{ marginTop: 8, fontSize: 11.5 }}>BB quarterly supervisory bulletin under review. Last known · 1.02% · Sep '25.</div>
          </div>
        </div>

      </div>

      {/* colophon — typewriter footer */}
      <div style={{ marginTop: 48, padding:"14px 0 0", borderTop:"1px dashed rgba(245,239,221,.25)", display:"flex", justifyContent:"space-between", fontSize: 10, letterSpacing:".14em", textTransform:"uppercase", color:"#8a7e5f" }}>
        <span style={{ color:"#d9c48a" }}>THE BRIEF · {ISSUE} · Desk edition</span>
        <span>BB · BBS · DSE · EPB · TCB · Yahoo · Reuters · FT · BBC</span>
        <span>Next file · 22 Apr · 06:15</span>
      </div>
    </div>
  );
}

Object.assign(window, { ConceptC });
