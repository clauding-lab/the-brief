// Concept A — Terminal Ledger
// Green-on-black Bloomberg-esque terminal, editorial voice.
// Fixed-pitch rows, ANSI box-drawing borders, status bar, keyboard hints.

function TBox({ title, right, children, accent = "#4ade80", style = {} }) {
  return (
    <div style={{
      border:"1px solid #2a3a2a",
      background:"#050807",
      position:"relative",
      ...style,
    }}>
      <div style={{
        padding:"4px 10px",
        borderBottom:"1px solid #2a3a2a",
        display:"flex", justifyContent:"space-between", alignItems:"center",
        background:"#0a1410",
        fontSize: 10, letterSpacing:".14em", textTransform:"uppercase",
        color: accent,
      }}>
        <span style={{ fontWeight: 700 }}>{title}</span>
        {right && <span style={{ color:"#6b7f6b" }}>{right}</span>}
      </div>
      <div style={{ padding:"10px 12px" }}>{children}</div>
    </div>
  );
}

function TRow({ k, v, unit, dlt, dir, bold }) {
  const col = dir === "up" ? "#4ade80" : dir === "down" ? "#f87171" : "#a3b3a3";
  return (
    <div style={{
      display:"grid",
      gridTemplateColumns:"1fr auto auto",
      gap: 10, alignItems:"baseline",
      fontSize: 12.5, lineHeight: 1.55,
      fontFamily:"'IBM Plex Mono', ui-monospace, monospace",
      color: bold ? "#e8f0e0" : "#c8d4c0",
      borderBottom:"1px dotted #1a2a1a",
      padding:"2px 0",
    }}>
      <span style={{ color:"#8aa08a", textTransform:"uppercase", letterSpacing:".08em", fontSize: 11 }}>{k}</span>
      <span style={{ fontWeight: bold ? 700 : 500, fontVariantNumeric:"tabular-nums", color: bold ? "#fde68a" : "#e8f0e0" }}>
        {v}{unit && <span style={{ color:"#6b7f6b", marginLeft: 3 }}>{unit}</span>}
      </span>
      <span style={{ color: col, fontVariantNumeric:"tabular-nums", fontSize: 11.5 }}>
        {dir === "up" ? "▲" : dir === "down" ? "▼" : "─"} {dlt}
      </span>
    </div>
  );
}

function Spark({ data, w = 160, h = 32, color = "#4ade80" }) {
  if (!data?.length) return null;
  const min = Math.min(...data), max = Math.max(...data);
  const range = (max - min) || 1;
  const step = (w - 4) / (data.length - 1);
  const pts = data.map((v,i) => [2 + i*step, 2 + (h-4) * (1 - (v-min)/range)]);
  const d = pts.map((p,i) => (i===0?"M":"L") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ");
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display:"block" }}>
      <path d={d} fill="none" stroke={color} strokeWidth="1.2"/>
      <circle cx={pts[pts.length-1][0]} cy={pts[pts.length-1][1]} r="2" fill={color}/>
    </svg>
  );
}

function AsciiRule({ ch = "═", color = "#2a3a2a" }) {
  return <div style={{ color, fontFamily:"'IBM Plex Mono',monospace", letterSpacing:"0", overflow:"hidden", whiteSpace:"nowrap", userSelect:"none", lineHeight: 1 }}>{ch.repeat(400)}</div>;
}

function SignalPill({ kind, children }) {
  const map = {
    bull:  { bg:"#0d2817", c:"#4ade80", sym:"▲" },
    bear:  { bg:"#2a0d0d", c:"#f87171", sym:"▼" },
    warn:  { bg:"#2a1f07", c:"#fbbf24", sym:"!" },
    watch: { bg:"#0d1a2a", c:"#60a5fa", sym:"→" },
  };
  const s = map[kind] || map.watch;
  return (
    <span style={{
      display:"inline-flex", alignItems:"center", gap: 6,
      padding:"1px 8px",
      background: s.bg,
      color: s.c,
      border: `1px solid ${s.c}`,
      fontFamily:"'IBM Plex Mono',monospace",
      fontSize: 10.5, fontWeight: 600,
      letterSpacing:".1em", textTransform:"uppercase",
    }}>
      {s.sym} {children}
    </span>
  );
}

function ConceptA() {
  const sparkData = {
    oil:   [82,83,85,86,87,89,90,91,92,93,94,95.10],
    remit: [1.85,1.94,2.01,2.05,2.11,2.18,2.20,2.22,2.25,2.27,2.29,2.31],
    dsex:  [5380,5360,5345,5310,5290,5270,5260,5255,5248,5240,5238,5232],
    cpi:   [10.8,10.7,10.7,10.6,10.6,10.5,10.5,10.5,10.4,10.4,10.4,10.4],
    usd:   [121.8,122.0,122.2,122.3,122.5,122.6,122.65,122.7,122.7,122.7,122.7,122.7],
    t91:   [11.60,11.62,11.65,11.68,11.70,11.72,11.74,11.76,11.78,11.80,11.82,11.85],
    res:   [32.4,32.7,33.0,33.4,33.6,33.8,33.9,34.0,34.05,34.08,34.10,34.12],
  };

  const signals = [
    { k:"bear",  t:"OIL · HORMUZ TANKER, BRENT +$3.40",       n:"$95.10",  anc:"OIL" },
    { k:"bull",  t:"FX · RESERVES FIRM ABOVE $34BN",          n:"+0.4%",   anc:"FX " },
    { k:"bear",  t:"DSE · FINANCIALS LEAD BROAD DECLINE",     n:"-0.78%",  anc:"DSE" },
    { k:"warn",  t:"CPI FOOD STICKY · 5TH MONTH >10%",        n:"10.40%",  anc:"MAC" },
    { k:"bull",  t:"REMIT · 9-MO HIGH · +11.6% YOY",          n:"$2.31BN", anc:"RMT" },
    { k:"watch", t:"91-D T-BILL CUT-OFF +9 BPS",              n:"11.85%",  anc:"BND" },
    { k:"warn",  t:"BB HOLDS 9.00% · CREDIT UNDERSHOOT",      n:"HOLD",    anc:"POL" },
  ];

  return (
    <div style={{
      background:"#020504",
      color:"#c8d4c0",
      fontFamily:"'IBM Plex Mono', ui-monospace, monospace",
      padding:"18px 22px 22px",
      minHeight:"100%",
      backgroundImage:[
        "repeating-linear-gradient(0deg, rgba(74,222,128,0.018) 0 1px, transparent 1px 3px)",
        "radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,.5) 100%)",
      ].join(","),
    }}>
      {/* STATUS BAR */}
      <div style={{
        display:"flex", justifyContent:"space-between", alignItems:"center",
        padding:"4px 10px", marginBottom: 12,
        background:"#0a1410", border:"1px solid #2a3a2a",
        fontSize: 10.5, letterSpacing:".14em", textTransform:"uppercase",
        color:"#4ade80",
      }}>
        <span>■ THE BRIEF/TERMINAL · v2.4 · DHAKA</span>
        <span style={{ color:"#a3b3a3" }}>TUE 21 APR 2026 · 06:15:42 BDT · LIVE</span>
        <span><span style={{ color:"#fbbf24" }}>●</span> 1 WARN · <span style={{ color:"#f87171" }}>●</span> 1 EVT · AUTO-REFRESH 60s</span>
      </div>

      {/* MASTHEAD */}
      <div style={{ display:"grid", gridTemplateColumns:"1.2fr 1fr", gap: 14, marginBottom: 14 }}>
        <div style={{ padding:"14px 18px", border:"1px solid #2a3a2a", position:"relative", background:"linear-gradient(135deg,#030806 0%, #061008 100%)" }}>
          <div style={{ color:"#6b7f6b", fontSize: 10, letterSpacing:".3em" }}>╔═ BRIEF/TERMINAL ═ {"VOL.II · No.412".replace(/ /g,"·")} ═╗</div>
          <div style={{ fontFamily:"'IBM Plex Mono',monospace", fontSize: 46, fontWeight: 700, color:"#e8f0e0", lineHeight: 1, marginTop: 8, letterSpacing:"-.02em" }}>
            THE BRIEF<span style={{ color:"#4ade80" }}>/</span>TERMINAL
          </div>
          <div style={{ marginTop: 10, fontSize: 12, color:"#8aa08a", maxWidth:"58ch", lineHeight: 1.55 }}>
            &gt; The morning intelligence for Bangladesh banking. Keyboard-first.<br/>
            &gt; <span style={{ color:"#fbbf24" }}>[F1]</span> help &nbsp; <span style={{ color:"#fbbf24" }}>[F2]</span> jump &nbsp; <span style={{ color:"#fbbf24" }}>[F3]</span> banker-read &nbsp; <span style={{ color:"#fbbf24" }}>[/]</span> search &nbsp; <span style={{ color:"#fbbf24" }}>[G+G]</span> top
          </div>
        </div>
        <TBox title="TODAY'S CALL // DESK EDITOR" right="06:15 BDT" accent="#fbbf24">
          <div style={{ fontSize: 14, lineHeight: 1.5, color:"#fde68a", fontFamily:"'IBM Plex Mono',monospace" }}>
            &gt; Hormuz is <b style={{ color:"#f87171" }}>priced risk</b>, not scarcity.<br/>
            &gt; Food CPI sticky @ 10.4%, reserves flat-not-building.<br/>
            &gt; Margin for a second incident is <b style={{ color:"#fbbf24" }}>narrower than it looks.</b><br/>
            &gt; <span style={{ color:"#4ade80" }}>HEDGE THE OIL BOOK — NOT THE HEADLINE.</span>
          </div>
        </TBox>
      </div>

      {/* TICKER ROW */}
      <div style={{
        padding:"6px 10px", border:"1px solid #2a3a2a", background:"#050807",
        display:"grid", gridTemplateColumns:"repeat(7,1fr)", gap: 0,
        marginBottom: 14, fontSize: 11,
      }}>
        {[
          {k:"USD/BDT",v:"122.70",d:"+0.04",dir:"up"},
          {k:"DSEX",v:"5,232",d:"-41",dir:"down"},
          {k:"BRENT",v:"$95.10",d:"+3.40",dir:"up"},
          {k:"91-D",v:"11.85%",d:"+9bp",dir:"up"},
          {k:"RES",v:"$34.12B",d:"+0.12",dir:"up"},
          {k:"CPI",v:"9.20%",d:"flat",dir:"flat"},
          {k:"REMIT",v:"$2.31B",d:"+11.6%",dir:"up"},
        ].map((x,i) => {
          const col = x.dir==="up"?"#4ade80":x.dir==="down"?"#f87171":"#a3b3a3";
          return (
            <div key={i} style={{ padding:"0 10px", borderRight: i<6?"1px solid #1a2a1a":"none" }}>
              <div style={{ color:"#6b7f6b", fontSize: 9.5, letterSpacing:".14em" }}>{x.k}</div>
              <div style={{ color:"#e8f0e0", fontWeight: 600, fontVariantNumeric:"tabular-nums" }}>{x.v} <span style={{ color: col, fontSize: 10 }}>{x.dir==="up"?"▲":x.dir==="down"?"▼":"─"}{x.d}</span></div>
            </div>
          );
        })}
      </div>

      {/* EXEC SIGNALS */}
      <TBox title="[F1] EXEC/SIGNALS // 7 ITEMS" right="ORDER=SIG DESC" style={{ marginBottom: 14 }}>
        <div style={{ display:"grid", gridTemplateColumns:"repeat(2,1fr)", gap:"4px 24px" }}>
          {signals.map((s,i) => (
            <div key={i} style={{ display:"grid", gridTemplateColumns:"28px 90px 1fr auto", gap: 8, alignItems:"center", fontSize: 12, padding:"3px 0", borderBottom:"1px dotted #1a2a1a" }}>
              <span style={{ color:"#6b7f6b" }}>{String(i+1).padStart(2,"0")}</span>
              <SignalPill kind={s.k}>{s.anc}</SignalPill>
              <span style={{ color:"#c8d4c0" }}>{s.t}</span>
              <span style={{ color:"#fde68a", fontVariantNumeric:"tabular-nums" }}>{s.n}</span>
            </div>
          ))}
        </div>
      </TBox>

      {/* MAIN GRID */}
      <div style={{ display:"grid", gridTemplateColumns:"1.4fr 1fr", gap: 14, marginBottom: 14 }}>
        {/* LEFT: OIL */}
        <TBox title="[OIL] §08 · IRAN · HORMUZ TANKER" right="EVT · YAHOO" accent="#f87171">
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap: 12 }}>
            <div>
              <div style={{ color:"#6b7f6b", fontSize: 10, letterSpacing:".16em", textTransform:"uppercase" }}>BRENT SPOT</div>
              <div style={{ fontSize: 44, fontWeight: 700, color:"#f87171", lineHeight: 1, fontVariantNumeric:"tabular-nums" }}>95.10</div>
              <div style={{ color:"#f87171", fontSize: 12 }}>▲ +3.40 / +3.7% · 05:00 GMT</div>
              <Spark data={sparkData.oil} w={220} h={36} color="#f87171"/>
            </div>
            <div style={{ padding:"0 0 0 12px", borderLeft:"1px dashed #2a3a2a" }}>
              <TRow k="WTI" v="91.00" unit="usd" dlt="+2.95 / +3.4%" dir="up"/>
              <TRow k="WAR-RISK" v="+18" unit="%" dlt="overnight" dir="up"/>
              <TRow k="PREMIA" v="RISK" dlt="not scarcity" dir="flat" bold/>
            </div>
          </div>
          <AsciiRule ch="─"/>
          <div style={{ marginTop: 8, fontSize: 12, lineHeight: 1.55, color:"#c8d4c0" }}>
            <span style={{ color:"#fde68a" }}>BR&gt;</span> Risk premium, not scarcity — but price the next incident <b style={{ color:"#fde68a" }}>before it happens.</b><br/>
            <span style={{ color:"#fde68a" }}>TRG&gt;</span> Second incident / closure → CPI feed-through ~6 weeks.<br/>
            <span style={{ color:"#fde68a" }}>ACT&gt;</span> Scenario provisions on aviation + bunker &gt; BDT 50cr; stress @ $115.
          </div>
        </TBox>

        {/* RIGHT: MACRO */}
        <TBox title="[MAC] §03 · INFLATION" right="MON · BBS · AGING 22D" accent="#fbbf24">
          <div style={{ color:"#6b7f6b", fontSize: 10, letterSpacing:".16em", textTransform:"uppercase" }}>CPI FOOD Y/Y</div>
          <div style={{ fontSize: 44, fontWeight: 700, color:"#fbbf24", lineHeight: 1, fontVariantNumeric:"tabular-nums" }}>10.40<span style={{ fontSize: 16, color:"#6b7f6b" }}> %</span></div>
          <div style={{ color:"#fbbf24", fontSize: 12 }}>── sticky · 5th month</div>
          <Spark data={sparkData.cpi} w={260} h={32} color="#fbbf24"/>
          <AsciiRule ch="─"/>
          <TRow k="CPI HEAD" v="9.20" unit="% y/y" dlt="flat MoM" dir="flat"/>
          <TRow k="RICE WHS" v="+2.1" unit="% WoW" dlt="pre-harvest" dir="down"/>
          <TRow k="OIL EDBL" v="-0.6" unit="% WoW" dlt="soft" dir="up"/>
          <div style={{ marginTop: 8, fontSize: 11.5, lineHeight: 1.5, color:"#c8d4c0" }}>
            <span style={{ color:"#fde68a" }}>BR&gt;</span> Build provisions ahead of the curve — <b style={{ color:"#fde68a" }}>cheaper than apologising in July.</b>
          </div>
        </TBox>
      </div>

      {/* 4-WIDE SECTION */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap: 14, marginBottom: 14 }}>
        <TBox title="[FX] §04" right="DLY · BB">
          <div style={{ color:"#6b7f6b", fontSize: 10 }}>USD/BDT</div>
          <div style={{ fontSize: 30, fontWeight: 700, color:"#e8f0e0", lineHeight: 1, fontVariantNumeric:"tabular-nums" }}>122.70</div>
          <div style={{ color:"#4ade80", fontSize: 11 }}>▲ +0.04 DoD</div>
          <Spark data={sparkData.usd} w={200} h={28} color="#4ade80"/>
          <AsciiRule ch="─"/>
          <TRow k="RESERVES" v="34.12" unit="bn" dlt="+0.12 WoW" dir="up"/>
          <TRow k="TRADE DEF" v="1.34" unit="bn" dlt="-11.4% YoY" dir="up"/>
          <TRow k="EXPORTS" v="4.64" unit="bn" dlt="+6.8% YoY" dir="up"/>
        </TBox>
        <TBox title="[RMT] §05" right="MON · BB">
          <div style={{ color:"#6b7f6b", fontSize: 10 }}>REMIT · MAR '26</div>
          <div style={{ fontSize: 30, fontWeight: 700, color:"#4ade80", lineHeight: 1, fontVariantNumeric:"tabular-nums" }}>$2.31<span style={{ fontSize: 14, color:"#6b7f6b" }}>bn</span></div>
          <div style={{ color:"#4ade80", fontSize: 11 }}>▲ +11.6% YoY · 9-mo high</div>
          <Spark data={sparkData.remit} w={200} h={28} color="#4ade80"/>
          <AsciiRule ch="─"/>
          <TRow k="YTD FY26" v="19.84" unit="bn" dlt="+9.2%" dir="up"/>
          <TRow k="CURR ACC" v="-0.48" unit="bn" dlt="narrowing" dir="up"/>
        </TBox>
        <TBox title="[DSE] §06" right="DLY · CLOSE">
          <div style={{ color:"#6b7f6b", fontSize: 10 }}>DSEX</div>
          <div style={{ fontSize: 30, fontWeight: 700, color:"#f87171", lineHeight: 1, fontVariantNumeric:"tabular-nums" }}>5,232</div>
          <div style={{ color:"#f87171", fontSize: 11 }}>▼ -41 / -0.78%</div>
          <Spark data={sparkData.dsex} w={200} h={28} color="#f87171"/>
          <AsciiRule ch="─"/>
          <TRow k="TURNOVER" v="428" unit="cr" dlt="-6.1%" dir="down"/>
          <TRow k="A/D" v="74/162" dlt="decl 2.2×" dir="down"/>
        </TBox>
        <TBox title="[BND] §07" right="WKLY · AUC">
          <div style={{ color:"#6b7f6b", fontSize: 10 }}>91-DAY T-BILL</div>
          <div style={{ fontSize: 30, fontWeight: 700, color:"#fbbf24", lineHeight: 1, fontVariantNumeric:"tabular-nums" }}>11.85<span style={{ fontSize: 14, color:"#6b7f6b" }}>%</span></div>
          <div style={{ color:"#fbbf24", fontSize: 11 }}>▲ +9 bps WoW</div>
          <Spark data={sparkData.t91} w={200} h={28} color="#fbbf24"/>
          <AsciiRule ch="─"/>
          <TRow k="182-D" v="12.05" unit="%" dlt="+7 bps" dir="up"/>
          <TRow k="5Y BGTB" v="12.60" unit="%" dlt="+4 bps" dir="up"/>
          <TRow k="10Y BGTB" v="12.92" unit="%" dlt="+6 bps" dir="up"/>
        </TBox>
      </div>

      {/* YIELD CURVE */}
      <TBox title="[BND] YIELD CURVE · BDT GOVT" right="APR 17 vs APR 10" style={{ marginBottom: 14 }}>
        <svg viewBox="0 0 900 160" style={{ width:"100%", height:"auto", display:"block" }}>
          {[11.5,12.0,12.5,13.0].map((v,i) => {
            const y = 20 + (1 - (v-11.3)/1.8) * 120;
            return (
              <g key={v}>
                <line x1={40} x2={880} y1={y} y2={y} stroke="#1a2a1a" strokeDasharray="2 4"/>
                <text x={8} y={y+4} fill="#6b7f6b" fontSize="10" fontFamily="IBM Plex Mono,monospace">{v.toFixed(1)}</text>
              </g>
            );
          })}
          {(() => {
            const pts =  [[40,11.85],[208,12.05],[376,12.20],[544,12.40],[712,12.60],[880,12.92]];
            const prev = [[40,11.76],[208,11.96],[376,12.12],[544,12.32],[712,12.52],[880,12.84]];
            const sc = y => 20 + (1 - (y-11.3)/1.8) * 120;
            const d = pts.map(([x,y],i) => (i===0?"M":"L")+x+","+sc(y).toFixed(1)).join(" ");
            const dp = prev.map(([x,y],i) => (i===0?"M":"L")+x+","+sc(y).toFixed(1)).join(" ");
            return (<>
              <path d={dp} fill="none" stroke="#6b7f6b" strokeWidth="1.4" strokeDasharray="3 4"/>
              <path d={d} fill="none" stroke="#4ade80" strokeWidth="2.2"/>
              {pts.map(([x,y],i) => <circle key={i} cx={x} cy={sc(y)} r="3.5" fill="#4ade80"/>)}
              {["3M","6M","1Y","2Y","5Y","10Y"].map((t,i) => (
                <text key={t} x={pts[i][0]} y={154} textAnchor="middle" fill="#8aa08a" fontSize="10" fontFamily="IBM Plex Mono,monospace">{t}</text>
              ))}
            </>);
          })()}
        </svg>
        <div style={{ marginTop: 6, fontSize: 11.5, color:"#c8d4c0" }}>
          <span style={{ color:"#fde68a" }}>BR&gt;</span> Market wants <b style={{ color:"#fde68a" }}>term premium</b>, not a cut. Take the 5y @ 12.60% before the curve catches up.
        </div>
      </TBox>

      {/* THREE ACROSS */}
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap: 14, marginBottom: 14 }}>
        <TBox title="[POL] §02 · POLICY & RATES" right="EVT · BB">
          <TRow k="POLICY RATE" v="9.00" unit="%" dlt="HOLD · 4th" dir="flat" bold/>
          <TRow k="SDF" v="7.50" unit="%" dlt="unchanged" dir="flat"/>
          <TRow k="SLF CEIL" v="10.50" unit="%" dlt="unchanged" dir="flat"/>
          <TRow k="CREDIT G" v="9.30" unit="% y/y" dlt="-0.20pp · 4th &lt;10%" dir="down"/>
          <AsciiRule ch="─"/>
          <div style={{ fontSize: 11.5, color:"#c8d4c0", lineHeight: 1.5 }}>
            <span style={{ color:"#fde68a" }}>BR&gt;</span> Comfort with the real-rate gap. <b style={{ color:"#fde68a" }}>Not a pivot.</b>
          </div>
        </TBox>
        <TBox title="[WIRE] §09 · HEADLINES" right="FEEDS · LIVE">
          <div style={{ fontSize: 11.5, lineHeight: 1.55 }}>
            <div style={{ padding:"3px 0", borderBottom:"1px dotted #1a2a1a" }}>
              <span style={{ color:"#f87171", fontWeight: 700 }}>REU</span> <span style={{ color:"#6b7f6b" }}>03:05</span> &nbsp;<span style={{ color:"#e8f0e0" }}>Tanker struck in Strait of Hormuz; lanes partial.</span>
            </div>
            <div style={{ padding:"3px 0", borderBottom:"1px dotted #1a2a1a" }}>
              <span style={{ color:"#4ade80", fontWeight: 700 }}>BBC</span> <span style={{ color:"#6b7f6b" }}>22:30</span> &nbsp;BD remittance hits 9-mo high in March.
            </div>
            <div style={{ padding:"3px 0", borderBottom:"1px dotted #1a2a1a" }}>
              <span style={{ color:"#60a5fa", fontWeight: 700 }}>DS </span> <span style={{ color:"#6b7f6b" }}>04:52</span> &nbsp;Export earnings rebound to $4.64bn, apparel-led.
            </div>
            <div style={{ padding:"3px 0", borderBottom:"1px dotted #1a2a1a" }}>
              <span style={{ color:"#fbbf24", fontWeight: 700 }}>TBS</span> <span style={{ color:"#6b7f6b" }}>05:10</span> &nbsp;BB eyes secondary bond liquidity; spreads widen.
            </div>
            <div style={{ padding:"3px 0", borderBottom:"1px dotted #1a2a1a" }}>
              <span style={{ color:"#fbbf24", fontWeight: 700 }}>FE </span> <span style={{ color:"#6b7f6b" }}>05:40</span> &nbsp;NBR revenue Tk 32,000cr short of 9-mo target.
            </div>
            <div style={{ padding:"3px 0" }}>
              <span style={{ color:"#60a5fa", fontWeight: 700 }}>FT </span> <span style={{ color:"#6b7f6b" }}>04:20</span> &nbsp;Dollar retreats as US soft data re-opens cut debate.
            </div>
          </div>
        </TBox>
        <TBox title="[ALT] §11 · SECONDARY" right="MIXED">
          <TRow k="GOLD SPOT" v="2,384" unit="usd" dlt="+0.6%" dir="up"/>
          <TRow k="LNG JKM" v="11.40" unit="mmbtu" dlt="STALE 4d" dir="flat"/>
          <TRow k="NPL SYS" v="10.80" unit="%" dlt="+20 bp QoQ" dir="down"/>
          <TRow k="CAR SYS" v="11.60" unit="%" dlt="-10 bp QoQ" dir="down"/>
          <AsciiRule ch="─"/>
          <div style={{ padding:"8px 10px", marginTop: 6, border:"1px dashed #6b7f6b", color:"#6b7f6b", fontSize: 11 }}>
            <span style={{ color:"#fbbf24" }}>§UNAVAIL</span> · Sector ROA detail missing.<br/>
            Last · 1.02% · Sep '25. Next · Apr 30.
          </div>
        </TBox>
      </div>

      {/* FOOTER STATUS */}
      <div style={{
        padding:"5px 10px", border:"1px solid #2a3a2a", background:"#0a1410",
        display:"flex", justifyContent:"space-between",
        fontSize: 10, letterSpacing:".12em", textTransform:"uppercase",
        color:"#6b7f6b",
      }}>
        <span><span style={{ color:"#4ade80" }}>▪</span> THE BRIEF/TERMINAL · VOL.II · No.412</span>
        <span>SRC: BB · BBS · DSE · EPB · TCB · YHOO · REU · FT · BBC · AJZ</span>
        <span>NEXT · 22 APR 06:15 · <span style={{ color:"#4ade80" }}>Q</span>UIT <span style={{ color:"#4ade80" }}>?</span>HELP</span>
      </div>
    </div>
  );
}

Object.assign(window, { ConceptA });
