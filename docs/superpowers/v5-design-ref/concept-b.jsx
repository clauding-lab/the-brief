// Concept B — Broadsheet Vertical
// Turn-of-century financial weekly. One narrow column, drop caps,
// hairline rules, tiny tables, footnote sources. Reads like a story.

function BRule({ double }) {
  return <div style={{ borderTop: double ? "3px double #1a1410" : "1px solid #1a1410", margin: "14px 0" }}/>;
}

function BHair() { return <div style={{ borderTop:"1px solid #c9b98b", margin:"10px 0" }}/>; }

function BSmallCap({ children, style = {} }) {
  return <span style={{ fontVariant:"small-caps", letterSpacing:".08em", fontWeight: 600, ...style }}>{children}</span>;
}

function BMetricTable({ rows }) {
  return (
    <table style={{ width:"100%", borderCollapse:"collapse", fontFamily:"'IBM Plex Mono',monospace", fontSize: 11, margin: "4px 0 6px", color:"#1a1410" }}>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} style={{ borderBottom:"1px solid #d9ceaf" }}>
            <td style={{ padding:"3px 0", textTransform:"uppercase", letterSpacing:".08em", color:"#5c5240", width:"58%" }}>{r.k}</td>
            <td style={{ padding:"3px 0", textAlign:"right", fontWeight: 600, color:"#1a1410", fontVariantNumeric:"tabular-nums" }}>{r.v}</td>
            <td style={{ padding:"3px 0 3px 10px", textAlign:"right", color: r.dir==="up" ? "#2f6b3a" : r.dir==="down" ? "#8a1f1f" : "#5c5240", fontVariantNumeric:"tabular-nums", width: 80 }}>{r.d}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function BFootnote({ n, children }) {
  return (
    <div style={{ display:"grid", gridTemplateColumns:"18px 1fr", gap: 6, fontSize: 10.5, lineHeight: 1.4, color:"#5c5240", fontFamily:"'Source Serif 4',serif", marginTop: 4 }}>
      <sup style={{ fontFeatureSettings:"'sups'", fontSize: 10, color:"#8a1f1f", fontWeight: 700 }}>{n}</sup>
      <span>{children}</span>
    </div>
  );
}

function BArticle({ n, kicker, title, lead, body, rows, footnotes, pull, stamp }) {
  return (
    <article style={{ padding:"0 0 18px", position:"relative" }}>
      <div style={{ display:"flex", alignItems:"baseline", gap: 8, fontFamily:"'IBM Plex Mono',monospace", fontSize: 10, letterSpacing:".22em", textTransform:"uppercase", color:"#8a1f1f", marginBottom: 4 }}>
        <span style={{ fontWeight: 700 }}>§{n}</span>
        <span style={{ color:"#5c5240" }}>— {kicker}</span>
        {stamp && <span style={{ marginLeft:"auto", border:"1px solid #8a1f1f", padding:"0 5px", fontSize: 9, color:"#8a1f1f" }}>{stamp}</span>}
      </div>
      <h2 style={{ fontFamily:"'Playfair Display','Source Serif 4',serif", fontWeight: 900, fontSize: 30, lineHeight: 1.02, letterSpacing:"-.01em", margin: "0 0 6px", color:"#1a1410", textWrap:"balance" }}>
        {title}
      </h2>
      <div style={{ fontFamily:"'Source Serif 4',serif", fontStyle:"italic", fontSize: 13, lineHeight: 1.4, color:"#3a3126", marginBottom: 10 }}>
        {lead}
      </div>
      <div style={{ fontFamily:"'Source Serif 4',serif", fontSize: 14, lineHeight: 1.55, color:"#1a1410", textAlign:"justify", hyphens:"auto" }}>
        <span style={{ float:"left", fontFamily:"'Playfair Display',serif", fontWeight: 900, fontSize: 52, lineHeight: .82, marginRight: 6, marginTop: 4, color:"#8a1f1f" }}>{body[0]}</span>
        {body.slice(1)}
      </div>
      {rows && <>
        <BHair/>
        <BMetricTable rows={rows}/>
      </>}
      {pull && (
        <div style={{ margin:"12px 0", padding:"10px 0", borderTop:"1px solid #1a1410", borderBottom:"1px solid #1a1410", fontFamily:"'Playfair Display',serif", fontStyle:"italic", fontSize: 17, lineHeight: 1.3, color:"#1a1410", textAlign:"center", textWrap:"balance" }}>
          "{pull}"
          <div style={{ fontFamily:"'IBM Plex Mono',monospace", fontStyle:"normal", fontSize: 9, letterSpacing:".2em", textTransform:"uppercase", color:"#8a1f1f", marginTop: 6 }}>— BankerRead · §{n}</div>
        </div>
      )}
      {footnotes && footnotes.map((f, i) => <BFootnote key={i} n={i+1}>{f}</BFootnote>)}
    </article>
  );
}

function ConceptB() {
  return (
    <div style={{
      width: "100%", minHeight: "100%",
      background: "#f4ecd6",
      backgroundImage:[
        "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.045 0'/></filter><rect width='100%25' height='100%25' filter='url(%23n)'/></svg>\")",
      ].join(","),
      padding: "50px 60px 60px",
      color: "#1a1410",
      fontFamily: "'Source Serif 4', Georgia, serif",
    }}>
      {/* Masthead — ornate, centered, single column */}
      <div style={{ textAlign:"center", maxWidth: 520, margin: "0 auto 12px" }}>
        <div style={{ fontFamily:"'IBM Plex Mono',monospace", fontSize: 10, letterSpacing:".32em", textTransform:"uppercase", color:"#5c5240", marginBottom: 4 }}>
          ⎯⎯⎯⎯  Established in these pages, MMXXIV  ⎯⎯⎯⎯
        </div>
        <div style={{ fontFamily:"'Playfair Display','Source Serif 4',serif", fontWeight: 900, fontSize: 74, lineHeight: .9, letterSpacing:"-.02em", color:"#1a1410" }}>
          The <span style={{ fontStyle:"italic", fontWeight: 400 }}>Brief</span>.
        </div>
        <div style={{ fontFamily:"'Source Serif 4',serif", fontStyle:"italic", fontSize: 14, color:"#3a3126", marginTop: 6 }}>
          A morning weekly for the banks of Bangladesh<br/>
          — <span style={{ fontVariant:"small-caps", letterSpacing:".06em" }}>numbers first, commentary second, names on every source.</span>
        </div>
        <div style={{ borderTop:"3px double #1a1410", borderBottom:"3px double #1a1410", margin:"14px auto 0", padding:"6px 0", display:"flex", justifyContent:"space-between", fontFamily:"'IBM Plex Mono',monospace", fontSize: 10.5, letterSpacing:".18em", textTransform:"uppercase", color:"#1a1410" }}>
          <span>{VOL}</span>
          <span>{TODAY}</span>
          <span>{ISSUE}</span>
        </div>
      </div>

      {/* Single narrow column — the whole paper */}
      <div style={{ maxWidth: 520, margin: "32px auto 0" }}>

        {/* TODAY'S CALL — editorial sitting before the news */}
        <div style={{ textAlign:"center", marginBottom: 24 }}>
          <div style={{ fontFamily:"'IBM Plex Mono',monospace", fontSize: 10, letterSpacing:".3em", textTransform:"uppercase", color:"#8a1f1f", marginBottom: 6 }}>Today's Call · From the Desk</div>
          <div style={{ fontFamily:"'Playfair Display',serif", fontStyle:"italic", fontSize: 22, lineHeight: 1.3, color:"#1a1410", textWrap:"balance" }}>
            Hormuz is priced risk — <br/>
            <span style={{ color:"#8a1f1f" }}>not scarcity.</span>
          </div>
          <div style={{ fontFamily:"'Source Serif 4',serif", fontSize: 13, lineHeight: 1.55, color:"#3a3126", marginTop: 10, textAlign:"justify", hyphens:"auto" }}>
            With food inflation sticky at 10.4 per cent and reserves flat rather than rebuilding, the margin for a second incident is narrower than it looks. Hedge the oil book — not the headline.
          </div>
          <div style={{ fontFamily:"'IBM Plex Mono',monospace", fontSize: 10, letterSpacing:".2em", textTransform:"uppercase", color:"#5c5240", marginTop: 10 }}>
            ⎯⎯  The Brief · 06:15 BDT  ⎯⎯
          </div>
        </div>

        <BRule double/>

        {/* §08 OIL — the lead */}
        <BArticle n="08" kicker="Iran · Oil" stamp="LEAD · EVENT"
          title="A tanker in the Strait, and a premium on the book."
          lead="Brent jumps $3.40 to $95.10 on thin Asian trade; insurer war-risk premia firm 18 per cent overnight. No claim has emerged."
          body={["T","he incident reported at 03:05 BDT in the southern approach of the Strait of Hormuz has so far disrupted no crude flow, and that is precisely the reading: this morning's move is risk, re-priced. Not a scarcity call. The BSEC will review policy pricing at 10:00, at which time corporate hedge demand is likely to spike; bankers with aviation and bunker books above BDT 50 crore ought to stress at Brent $115 — not as a forecast, but as a housekeeping discipline. A confirmed closure, or a second incident within a fortnight, would put the food-CPI feed-through window at roughly six weeks."]}
          rows={[
            { k:"Brent spot",   v:"$95.10", d:"+3.40", dir:"up" },
            { k:"WTI spot",     v:"$91.00", d:"+2.95", dir:"up" },
            { k:"War-risk prem.", v:"+18%", d:"o'night", dir:"up" },
          ]}
          pull={PULLS.oil}
          footnotes={[
            "Yahoo Finance · Reuters wire · 05:00 GMT. Prices denominated USD/bbl, spot.",
            "Bangladesh Bank secondary communications to insurers, 05:42 BDT. Unconfirmed.",
          ]}
        />

        <BRule/>

        {/* §03 MACRO */}
        <BArticle n="03" kicker="Inflation · March print" stamp="AGING · 22d"
          title="Food will not let go."
          lead="Headline CPI flat at 9.2%; food inflation sticky above 10% for the fifth consecutive month."
          body={["T","he distance between headline and food is now the story. A household in the districts feels the food number, not the aggregate, and the aggregate has masked a sticky problem for the better part of a quarter. Rice at the wholesale level ran 2.1 per cent higher on the week into Boro pre-harvest; edible oil softened 0.6. Retail underwriting for unsecured personal loans to customers reporting monthly income under BDT 60,000 is the natural place to tighten; it is cheaper to build provisions ahead of the curve than to apologise to the audit committee in July."]}
          rows={[
            { k:"CPI food y/y",    v:"10.40%", d:"5th mo",  dir:"flat" },
            { k:"CPI head y/y",    v:"9.20%",  d:"flat MoM",dir:"flat" },
            { k:"Rice wholesale",  v:"+2.1%",  d:"WoW",     dir:"down" },
            { k:"Edible oil",      v:"-0.6%",  d:"WoW",     dir:"up" },
          ]}
          pull={PULLS.macro}
          footnotes={[
            "Bangladesh Bureau of Statistics; monthly CPI, March 2026. Next print May 8.",
            "Trading Corporation of Bangladesh; DAM weekly basket, Apr 19.",
          ]}
        />

        <BRule/>

        {/* §05 REMIT */}
        <BArticle n="05" kicker="Remittance · March" stamp="9-MO HIGH"
          title="The cushion the Bank cannot buy."
          lead="March remittance at $2.31bn — a nine-month high; third consecutive month of double-digit YoY growth."
          body={["T","hree months of double-digit year-on-year inflow, read alongside third-week reserves at $34.12bn, paints the cushion on the country's balance sheet in bankers' ink. The Middle East corridor led; the Eid-ul-Fitr window was no accident. The lesson, for those running NRB deposit desks, is not price but channel. Competitors chasing rate in a market where the customer is choosing which app to open on a Friday afternoon miss the architecture of the decision. Raise the 1-year USD FD ceiling by 25 bps where competitors are passive; compete on same-day crediting."]}
          rows={[
            { k:"Remit · Mar '26", v:"$2.31bn", d:"+11.6% YoY", dir:"up" },
            { k:"YTD FY26",        v:"$19.84bn",d:"+9.2%",      dir:"up" },
            { k:"Current acc.",    v:"-$0.48bn",d:"narrowing",  dir:"up" },
          ]}
          pull={PULLS.remit}
          footnotes={[
            "Bangladesh Bank; monthly remittance data, March 2026.",
          ]}
        />

        <BRule/>

        {/* §04 FX */}
        <BArticle n="04" kicker="External accounts" stamp="DAILY"
          title="The floor holds, but it does not rebuild."
          lead="Reserves up 0.4 per cent on the week to $34.12bn; trade deficit narrows on import compression, not export surge."
          body={["T","he distinction matters. An import-compression narrowing is defensive arithmetic; an export-surge narrowing would be an expansion in disguise. March's $4.64bn apparel-led export print is constructive, but the weekly reserves line is unmistakably flat. The USD-short book should be capped at 8 per cent of liquid assets as a matter of policy, with $33bn the line below which new NOSTRO drawdowns are halted and Q3 L/C obligations are pre-funded. Stretch tenor where you can."]}
          rows={[
            { k:"USD/BDT mid",    v:"122.70", d:"+0.04",    dir:"up" },
            { k:"Reserves",       v:"$34.12bn", d:"+0.12 WoW", dir:"up" },
            { k:"Trade def. Mar", v:"$1.34bn", d:"-11.4% YoY", dir:"up" },
            { k:"Exports Mar",    v:"$4.64bn", d:"+6.8% YoY",  dir:"up" },
          ]}
          pull={PULLS.fx}
          footnotes={[
            "Bangladesh Bank daily fix · 06:00 BDT. EPB monthly export data, March 2026.",
          ]}
        />

        <BRule/>

        {/* §07 BONDS */}
        <BArticle n="07" kicker="T-Bill & T-Bond" stamp="WEEKLY"
          title="The curve wants term premium."
          lead="91-day cut-off firms 9 bps to 11.85%; bear-steepen across the tenors. Next auction April 24."
          body={["T","he curve's geometry this week has nothing to do with the policy rate and everything to do with the term-premium investors are demanding for sitting longer. The 10-year at 12.92 is nine bps wider than a fortnight ago; the 5-year at 12.60 offers real carry for banks prepared to extend the HTM book selectively. A breach of 13.00 on the 10 forces a reopen of the barbell discussion versus a matched ladder. Use the auction calendar; do not sit the 364-day alone."]}
          rows={[
            { k:"91-day",   v:"11.85%", d:"+9 bps", dir:"up" },
            { k:"182-day",  v:"12.05%", d:"+7 bps", dir:"up" },
            { k:"BGTB 5Y",  v:"12.60%", d:"+4 bps", dir:"up" },
            { k:"BGTB 10Y", v:"12.92%", d:"+6 bps", dir:"up" },
          ]}
          pull={PULLS.tbond}
          footnotes={[
            "BB auction results · Apr 17. Next auction Apr 24; BDT 80bn across 91/182/364.",
          ]}
        />

        <BRule/>

        {/* §06 DSE */}
        <BArticle n="06" kicker="Equities · Dhaka Stock Exchange" stamp="DAILY"
          title="Thin tape, not broken book value."
          lead="DSEX down 0.78 per cent to 5,232 on broad financial weakness; turnover below the thirty-day average."
          body={["A","dvance/decline at 74 against 162 tells you the breadth of the move, but the turnover — BDT 428 crore against a thirty-day average of 462 — tells you its nature. This is a liquidity story and not, yet, a credit one. The margin book holds at current parameters; no book-value trigger has been breached. For the house account, it is the quarter, not the week, that matters: allocation rotation from banks toward consumer staples with pricing power remains the right move. Resist, however, the temptation to extend promotional leverage into a thin tape."]}
          rows={[
            { k:"DSEX",      v:"5,232", d:"-0.78%", dir:"down" },
            { k:"DS30",      v:"1,932", d:"-0.36%", dir:"down" },
            { k:"Turnover",  v:"428cr", d:"-6.1%",  dir:"down" },
            { k:"A/D",       v:"74/162",d:"decl 2.2×", dir:"down" },
          ]}
          pull={PULLS.dse}
          footnotes={[
            "Dhaka Stock Exchange · Apr 20 close.",
          ]}
        />

        <BRule/>

        {/* §02 POLICY */}
        <BArticle n="02" kicker="Policy & rates" stamp="EVENT"
          title="The Governor held, again."
          lead="Fourth consecutive hold at 9.00 per cent against credit growth undershooting for the fourth month."
          body={["T","he shape of this hold is not a pivot waiting in the wings; it is the Committee expressing comfort with the real-rate gap. A fifth month of credit growth below 9.5 would begin to change the odds on the Standing Lending ceiling, but not before. Meanwhile the working instruction is housekeeping: cap fixed-rate corporate lending above the 5-year tenor at 12 per cent of total, and rotate new origination toward floating-rate SME facilities that re-price with the T-bill."]}
          rows={[
            { k:"Policy rate",  v:"9.00%",  d:"hold 4×", dir:"flat" },
            { k:"SDF",          v:"7.50%",  d:"unch.",   dir:"flat" },
            { k:"SLF ceiling",  v:"10.50%", d:"unch.",   dir:"flat" },
            { k:"Credit g. y/y",v:"9.30%",  d:"4th <10%",dir:"down" },
          ]}
          pull={PULLS.policy}
          footnotes={[
            "BB Monetary Policy Committee statement, Apr 17. Feb '26 credit growth data.",
          ]}
        />

        <BRule double/>

        {/* WIRES — formatted as agate column */}
        <div>
          <div style={{ textAlign:"center", fontFamily:"'Playfair Display',serif", fontWeight: 900, fontSize: 22, lineHeight: 1, marginBottom: 4 }}>
            The Wires
          </div>
          <div style={{ textAlign:"center", fontFamily:"'Source Serif 4',serif", fontStyle:"italic", fontSize: 12, color:"#5c5240", marginBottom: 12 }}>
            Editor's cut from the feeds · dated, sourced, ordered.
          </div>
          <div style={{ columnCount: 2, columnGap: 24, columnRule:"1px solid #c9b98b", fontFamily:"'Source Serif 4',serif", fontSize: 12.5, lineHeight: 1.45, color:"#1a1410" }}>
            {[
              { src:"REU", time:"03:05", text:"Tanker struck in Strait of Hormuz; shipping lanes partially disrupted. No claim of responsibility; insurer war-risk premia up 18% overnight." },
              { src:"BBC", time:"22:30", text:"Bangladesh remittance inflow hits nine-month high in March at $2.31bn; Middle East corridor leads." },
              { src:"DS",  time:"04:52", text:"Export earnings rebound to $4.64bn in March, led by apparel." },
              { src:"TBS", time:"05:10", text:"BB eyes secondary bond liquidity as spreads widen into auction." },
              { src:"FE",  time:"05:40", text:"NBR revenue Tk 32,000cr short of nine-month target." },
              { src:"FT",  time:"04:20", text:"Dollar retreats as US soft data re-opens Fed cut debate." },
              { src:"AJZ", time:"20:45", text:"South Asia grapples with record pre-monsoon heat; BD rural districts report wheat crop damage up to 9%." },
              { src:"REU", time:"05:55", text:"Taka participation thin as EM Asia firms against dollar." },
            ].map((w, i) => (
              <div key={i} style={{ breakInside:"avoid", marginBottom: 10 }}>
                <span style={{ fontFamily:"'IBM Plex Mono',monospace", fontSize: 9.5, letterSpacing:".16em", color:"#8a1f1f", fontWeight: 700 }}>{w.src}</span>
                <span style={{ fontFamily:"'IBM Plex Mono',monospace", fontSize: 9.5, color:"#5c5240", marginLeft: 6 }}>{w.time}</span>
                <span> — {w.text}</span>
              </div>
            ))}
          </div>
        </div>

        <BRule double/>

        {/* Missing data notice — set like a correction column */}
        <div style={{ padding:"10px 14px", border:"1px dashed #5c5240", background:"rgba(90,80,60,.04)", fontFamily:"'Source Serif 4',serif" }}>
          <div style={{ fontFamily:"'IBM Plex Mono',monospace", fontSize: 9.5, letterSpacing:".2em", textTransform:"uppercase", color:"#8a1f1f", marginBottom: 4 }}>§ Correction · Unavailable</div>
          <div style={{ fontStyle:"italic", fontSize: 13, lineHeight: 1.45, color:"#1a1410" }}>
            Sector ROA detail is missing from today's file; BB quarterly supervisory bulletin is under review, with no fresh read for April. <BSmallCap>Last known</BSmallCap> — 1.02 per cent, September 2025. <BSmallCap>Next</BSmallCap> — April 30.
          </div>
        </div>

        {/* Colophon */}
        <div style={{ textAlign:"center", marginTop: 28, fontFamily:"'IBM Plex Mono',monospace", fontSize: 9.5, letterSpacing:".22em", textTransform:"uppercase", color:"#5c5240" }}>
          ⎯⎯⎯⎯&nbsp;&nbsp;The Brief · {ISSUE} · Broadsheet edition&nbsp;&nbsp;⎯⎯⎯⎯
          <div style={{ marginTop: 6, color:"#8a1f1f" }}>BB · BBS · DSE · EPB · TCB · Yahoo · Reuters · FT · BBC · AJZ</div>
          <div style={{ marginTop: 4 }}>Next edition · 22 April · 06:15 BDT</div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { ConceptB });
