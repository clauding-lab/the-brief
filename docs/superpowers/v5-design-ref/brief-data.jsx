// Shared data for The Brief concept artboards
// Lifted from The Brief v3 — same numbers, same voice.

const TODAY = "Tue 21 Apr 2026";
const ISSUE = "No. 412";
const VOL = "Vol. II";

const SECTIONS = [
  { id: "policy",  n: "02", kicker: "Policy & rates",    title: "Governor held. Again.",                 tldr: "4th consecutive hold; credit growth undershooting.",             src: "BB",         cadence: "Event",   freshness: "fresh"   },
  { id: "macro",   n: "03", kicker: "Inflation",         title: "Food won't let go.",                    tldr: "Headline CPI 9.2%; food sticky above 10%, 5th month.",           src: "BBS",        cadence: "Monthly", freshness: "warn"    },
  { id: "fx",      n: "04", kicker: "FX & external",     title: "Floor holds, doesn't rebuild.",         tldr: "Reserves +0.4% WoW; trade gap narrows on import compression.",   src: "BB · EPB",   cadence: "Daily",   freshness: "fresh"   },
  { id: "remit",   n: "05", kicker: "Remittance",        title: "The cushion BB cannot buy.",            tldr: "March $2.31bn, 9-mo high; 3rd double-digit YoY in a row.",       src: "BB",         cadence: "Monthly", freshness: "fresh"   },
  { id: "dse",     n: "06", kicker: "Equities · DSE",    title: "Thin tape, not broken book.",           tldr: "DSEX -0.78% to 5,232 on financials; turnover below 30-d avg.",   src: "DSE",        cadence: "Daily",   freshness: "fresh"   },
  { id: "tbond",   n: "07", kicker: "T-Bill & T-Bond",   title: "The curve wants term premium.",         tldr: "91-d cut-off +9 bps to 11.85%; bear-steepen across.",            src: "BB auction", cadence: "Weekly",  freshness: "fresh"   },
  { id: "oil",     n: "08", kicker: "Iran · Oil",        title: "Risk premium, not scarcity.",           tldr: "Hormuz tanker; Brent +$3.40 to $95.10; war-risk premia +18%.",   src: "Yahoo · Reuters", cadence: "Event", freshness: "fresh" },
];

const METRICS = {
  policy: [
    { label: "Policy rate",    value: "9.00",  unit: "%",         delta: "Unchanged · 4th hold", dir: "flat" },
    { label: "SLF ceiling",    value: "10.50", unit: "%",         delta: "Unchanged",            dir: "flat" },
    { label: "SDF",            value: "7.50",  unit: "%",         delta: "Unchanged",            dir: "flat" },
    { label: "Credit growth",  value: "9.30",  unit: "% y/y",     delta: "-0.20pp · 4th mo < 10%", dir: "down" },
  ],
  macro: [
    { label: "CPI food",       value: "10.40", unit: "% y/y",     delta: "Sticky · 5th month",    dir: "flat", state: "warn" },
    { label: "CPI headline",   value: "9.20",  unit: "% y/y",     delta: "Flat MoM",              dir: "flat" },
    { label: "Rice wholesale", value: "+2.1",  unit: "% WoW",     delta: "Boro pre-harvest",      dir: "down" },
    { label: "Edible oil",     value: "-0.6",  unit: "% WoW",     delta: "Soft",                  dir: "up" },
  ],
  fx: [
    { label: "USD/BDT",        value: "122.70",                   delta: "+0.04 DoD",             dir: "up" },
    { label: "Reserves",       value: "34.12", unit: "bn USD",    delta: "+0.12 WoW",             dir: "up" },
    { label: "Exports Mar",    value: "4.64",  unit: "bn USD",    delta: "+6.8% YoY",             dir: "up" },
    { label: "Trade deficit",  value: "1.34",  unit: "bn USD",    delta: "-11.4% YoY · narrow",   dir: "up" },
  ],
  remit: [
    { label: "Remit · Mar",    value: "2.31",  unit: "bn USD",    delta: "+11.6% YoY · 9-mo high", dir: "up" },
    { label: "YTD FY26",       value: "19.84", unit: "bn USD",    delta: "+9.2% vs FY25",          dir: "up" },
    { label: "Current account",value: "-0.48", unit: "bn USD",    delta: "Narrowing trend",        dir: "up" },
  ],
  dse: [
    { label: "DSEX",           value: "5,232",                    delta: "-41 / -0.78%",           dir: "down" },
    { label: "DS30",           value: "1,932",                    delta: "-7 / -0.36%",            dir: "down" },
    { label: "Turnover",       value: "428",   unit: "cr BDT",    delta: "-6.1% DoD · below avg",  dir: "down" },
    { label: "Breadth A/D",    value: "74/162",                   delta: "Decliners 2.2×",         dir: "down" },
  ],
  tbond: [
    { label: "91-day",         value: "11.85", unit: "%",         delta: "+9 bps WoW",             dir: "up" },
    { label: "182-day",        value: "12.05", unit: "%",         delta: "+7 bps",                 dir: "up" },
    { label: "BGTB 5Y",        value: "12.60", unit: "%",         delta: "+4 bps",                 dir: "up" },
    { label: "BGTB 10Y",       value: "12.92", unit: "%",         delta: "+6 bps",                 dir: "up" },
  ],
  oil: [
    { label: "Brent spot",     value: "95.10", unit: "USD/bbl",   delta: "+3.40 / +3.7%",          dir: "up" },
    { label: "WTI spot",       value: "91.00", unit: "USD/bbl",   delta: "+2.95 / +3.4%",          dir: "up" },
    { label: "War-risk premia",value: "+18",   unit: "%",         delta: "Overnight",              dir: "up" },
  ],
};

// BankerRead pull quotes — for the "single-line call" on the map
const PULLS = {
  policy: "Comfort with the real-rate gap, not the prelude to a pivot.",
  macro:  "Build provisions ahead of the curve — cheaper than apologising in July.",
  fx:     "The floor is holding; it is not rebuilding. Price the difference.",
  remit:  "The FX cushion the central bank cannot buy. Compete on channel.",
  dse:    "A liquidity story, not yet a credit one. Don't confuse thin tape with broken book.",
  tbond:  "The market wants term premium, not a cut. Take the 5y carry.",
  oil:    "Risk premium, not scarcity — but price the next incident before it happens.",
};

// BankerRead — full 4 sentences for card backs / detail panes
const BR = {
  policy: { meaning: "Fourth consecutive hold against undershooting credit growth signals comfort with the real-rate gap, not a pivot.", action: "Cap fixed-rate corporate book above 5y at 12% of total.", trigger: "A fifth month below 9.5% credit growth raises odds of SLF easing.", focus: "Rotate new origination toward floating-rate SME facilities." },
  macro:  { meaning: "Headline 9.2% masks food above 10%; household real-income pressure persists.", action: "Tighten retail underwriting on unsecured personal loans under BDT 60k income.", trigger: "Food CPI breach of 10.8% next print likely triggers supervisory letter.", focus: "Build provisions ahead of the curve." },
  fx:     { meaning: "Third week of flat reserves: floor holding, not rebuilding.", action: "Cap USD-short book at 8% of liquid assets.", trigger: "Below $33bn with BDT past 123.0 — halt new NOSTRO drawdowns.", focus: "Stretch USD deposit tenor; pre-fund Q3 L/C obligations." },
  remit:  { meaning: "Third month of double-digit YoY builds the FX cushion BB cannot buy.", action: "Raise NRB 1y USD FD ceiling by 25bps where competitors are passive.", trigger: "Single month below $1.85bn marks reversal — prep FX contingency.", focus: "Compete on channel reliability; Eid-cycle rewards same-day crediting." },
  dse:    { meaning: "Broad-based financial weakness on thin turnover — liquidity, not credit.", action: "No book-value trigger breached — hold margin book steady.", trigger: "DSEX < 5,150 with turnover < 350cr forces MTM review.", focus: "Shift prop allocation from banks toward consumer staples with pricing power." },
  tbond:  { meaning: "Bear-steepen signals market wants term premium, not a policy cut.", action: "Extend HTM book in the 5y bucket at 12.60% for real carry.", trigger: "10y through 13.00% — reopen barbell vs matching the ladder.", focus: "Use next auction calendar to smooth rollover — don't sit on 364 alone." },
  oil:    { meaning: "Hormuz re-prices risk, not supply; move is premium, not scarcity — for now.", action: "Add scenario provisions on aviation and bunker > BDT 50cr; stress at $115.", trigger: "Second incident or confirmed closure puts CPI feed-through in 6 weeks.", focus: "Revisit oil hedge pricing to corporates — structured caps beat swaps." },
};

// Risk Map coordinates — plotted by (volatility, significance-today)
// x: 0-10 (volatility / movement today), y: 0-10 (significance for banker's book today)
const MAP = [
  { id: "oil",    x: 9.4, y: 9.1, r: 38, type: "event"   },  // big move, very significant
  { id: "macro",  x: 2.2, y: 7.8, r: 32, type: "slow"    },  // no move but sticky
  { id: "remit",  x: 6.0, y: 7.0, r: 30, type: "fresh"   },
  { id: "fx",     x: 3.4, y: 6.3, r: 28, type: "slow"    },
  { id: "dse",    x: 6.5, y: 4.8, r: 26, type: "fresh"   },
  { id: "tbond",  x: 5.0, y: 5.4, r: 24, type: "fresh"   },
  { id: "policy", x: 1.2, y: 6.0, r: 24, type: "anchor"  },  // no move, always matters
];

// Read-order implied by the map (descending significance + event weight)
const READ_ORDER = ["oil", "macro", "remit", "fx", "tbond", "dse", "policy"];

Object.assign(window, { TODAY, ISSUE, VOL, SECTIONS, METRICS, PULLS, BR, MAP, READ_ORDER });
