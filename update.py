import anthropic
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

# ── Email config ───────────────────────────────────────────────────────────────
BREVO_KEY        = os.environ.get("BREVO_API_KEY", "")
SUPABASE_URL     = "https://ssbliukchgibjcjohibi.supabase.co"
SUPABASE_SVC_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
BRIEF_URL        = "https://clauding-lab.github.io/the-brief/"
FROM_EMAIL       = "adnan.rshd@gmail.com"
FROM_NAME        = "THE BRIEF"

# ── Read current file ──────────────────────────────────────────────────────────
with open("the-brief.html", "r", encoding="utf-8") as f:
    current_html = f.read()

today = datetime.utcnow().strftime("%A %d %B %Y").upper()

# ── Strip CSS to stay under rate-limit (Claude is told not to touch CSS anyway) ─
# ── Strip <head> block (CDN scripts, PWA tags, meta) — Claude never touches these ─
# Saves ~600 chars and guarantees PWA manifest/SW/apple tags are never lost.
# The <title> is inside but Claude updates BRIEF_DATE via the JS constant, not <title>.
_head_match = re.search(r'(<head>)(.*?)(</head>)', current_html, re.DOTALL)
if _head_match:
    _head_block   = _head_match.group(0)
    _head_placeholder = "<head><!-- HEAD_PLACEHOLDER — restored automatically --></head>"
    prompt_html   = current_html.replace(_head_block, _head_placeholder, 1)
    print(f"Head stripped: {len(_head_block):,} chars saved (~{len(_head_block)//3:,} tokens).")
else:
    prompt_html   = current_html
    _head_block   = None
    print("Warning: no <head> block found.")

# Extract and stash the <style>...</style> block; replace with a tiny placeholder.
# We'll re-inject it into whatever HTML Claude returns.
_css_match = re.search(r'(<style>)(.*?)(</style>)', prompt_html, re.DOTALL)
if _css_match:
    _css_block   = _css_match.group(0)          # full <style>...</style>
    _css_content = _css_match.group(2)           # just the CSS text
    _placeholder = "<style>/* CSS_PLACEHOLDER — restored automatically */</style>"
    prompt_html  = prompt_html.replace(_css_block, _placeholder, 1)
    print(f"CSS stripped: {len(_css_content):,} chars saved from prompt "
          f"(~{len(_css_content)//3:,} tokens).")
else:
    _css_block   = None
    print("Warning: no <style> block found — sending full HTML.")

# ── Strip JS render sections to stay under the 30k input-token rate limit ──────
# Component helpers (Pill, MetricCard, etc.), chart return() JSX, and the App
# function are rendering-only — Claude never needs to update them.
# We strip each section, save it, and restore it into Claude's output afterwards.
# Claude is told to pass the placeholder comments through unchanged.

def _brace_end(text, start):
    """Return index of the } that closes the { at position `start`."""
    depth   = 0
    in_str  = None
    i       = start
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == '\\':
                i += 2
                continue
            if ch == in_str:
                in_str = None
        else:
            if ch in ('"', "'", '`'):
                in_str = ch
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return len(text) - 1

def strip_js_render(html):
    """Strip render-only JS; return (stripped_html, chars_saved, saved_parts)."""
    sm = re.search(r'(<script type="text/babel">)(.*?)(</script>)', html, re.DOTALL)
    if not sm:
        print("Warning: no <script type=\"text/babel\"> block found — JS not stripped.")
        return html, 0, {}
    before = html[:sm.start(2)]
    sc     = sm.group(2)
    after  = html[sm.end(2):]
    orig   = len(sc)
    saved  = {}

    def _strip_return(sc, fname, key):
        """Replace the `return (...);` of `fname` with a placeholder."""
        sig  = f'function {fname}()'
        fpos = sc.find(sig)
        if fpos == -1:
            return sc
        try:
            brace = sc.index('{', fpos)
        except ValueError:
            return sc
        fend = _brace_end(sc, brace)
        body = sc[brace+1:fend]
        ret  = body.rfind('\n  return (')
        if ret == -1:
            ret = body.rfind('  return (')
        if ret == -1:
            return sc
        saved[key] = body[ret+1:].rstrip()
        nb = body[:ret] + f'\n  // [{key} — restored automatically]\n'
        return sc[:brace+1] + nb + '}' + sc[fend+1:]

    # 1. Component helpers (Pill → TickerStrip)
    c0 = sc.find('// ── Components')
    s0 = sc.find('// ── Sections')
    if c0 != -1 and s0 != -1 and s0 > c0:
        eol = sc.index('\n', c0) + 1
        saved['COMPONENTS_PLACEHOLDER'] = sc[eol:s0].rstrip()
        sc  = (sc[:eol]
               + '// [COMPONENTS_PLACEHOLDER — restored automatically]\n\n'
               + sc[s0:])

    # 2-3. Chart return() statements
    for fname, key in (('DSEXChart',  'DSEXCHART_RENDER_PLACEHOLDER'),
                       ('TBillChart', 'TBILLCHART_RENDER_PLACEHOLDER')):
        sc = _strip_return(sc, fname, key)

    # 2d. SectionTariff — static US tariff explainer, never updated daily;
    #     stripping its return() saves ~10k chars from the Phase 2 prompt.
    sc = _strip_return(sc, 'SectionTariff', 'TARIFF_RENDER_PLACEHOLDER')

    # 2e. SectionTrade — static trade deep-dive, not in daily update instructions;
    #     stripping its return() saves ~5k chars from the Phase 2 prompt.
    sc = _strip_return(sc, 'SectionTrade', 'TRADE_RENDER_PLACEHOLDER')

    # 2b. (All 7 new sections are now live — no longer stripped/protected.
    #      Claude updates them directly with fresh data each day.)

    # 4. OilChart — keep STATIC_DATA array, strip everything else
    op = sc.find('function OilChart()')
    if op != -1:
        try:
            ob = sc.index('{', op)
        except ValueError:
            ob = -1
        if ob != -1:
            oe   = _brace_end(sc, ob)
            body = sc[ob+1:oe]
            s_s  = body.find('const STATIC_DATA')
            s_e  = body.find('];\n', s_s) + len('];\n') if s_s != -1 else -1
            if s_e > 0:
                key = 'OILCHART_RENDER_PLACEHOLDER'
                saved[key]  = body[s_e:].rstrip()
                nb = body[:s_e] + f'\n  // [{key} — restored automatically]\n'
                sc = sc[:ob+1] + nb + '}' + sc[oe+1:]

    # 5. App function + ReactDOM mount (everything after "// ── Main App")
    am = sc.find('// ── Main App')
    if am != -1:
        aeol = sc.index('\n', am) + 1
        saved['APP_PLACEHOLDER'] = sc[aeol:].rstrip()
        sc = sc[:aeol] + '// [APP_PLACEHOLDER — restored automatically]\n'

    chars_saved = orig - len(sc)
    print(f"JS render stripped: {chars_saved:,} chars saved "
          f"(~{chars_saved//3:,} tokens). Sections: {list(saved.keys())}")
    return before + sc + after, chars_saved, saved

prompt_html, _js_chars_saved, _js_parts = strip_js_render(prompt_html)

# ── Strip long data prop values to stay under 30k input-token rate limit ─────────
# BankerRead insight= — NOT stripped (prop renamed from text= to insight=).
#   Claude sees existing analytical commentary and can update it if today's data
#   changes materially; otherwise it persists unchanged.
# NewsItem detail=   — Claude writes fresh headlines; old detail values not needed.
# MetricCard sub=    — Claude updates sub-labels from gathered data in UPDATE instructions.
# Stripping old values saves tokens; Claude regenerates them from gathered_json + instructions.
_before_prop = len(prompt_html)
prompt_html = re.sub(r'\btext="[^"]{30,}"', 'text=""', prompt_html)
prompt_html = re.sub(r'\bheadline="[^"]{30,}"', 'headline=""', prompt_html)
prompt_html = re.sub(r'\bdetail="[^"]{20,}"', 'detail=""', prompt_html)
prompt_html = re.sub(r'\bsub="[^"]{20,}"', 'sub=""', prompt_html)
# Citation / metadata props — Claude regenerates from gathered_json each run
prompt_html = re.sub(r'\bsource="[^"]*"', 'source=""', prompt_html)
prompt_html = re.sub(r'\bsourceUrl="[^"]*"', 'sourceUrl=""', prompt_html)
prompt_html = re.sub(r'\btime="[^"]*"', 'time=""', prompt_html)
prompt_html = re.sub(r'\bchange="[^"]*"', 'change=""', prompt_html)
# DAM computed label props — Claude rewrites from dam_* data each run
prompt_html = re.sub(r'\bhotspotLabel="[^"]*"', 'hotspotLabel=""', prompt_html)
prompt_html = re.sub(r'\bhotspotStat="[^"]*"', 'hotspotStat=""', prompt_html)
prompt_html = re.sub(r'\bhotspotDetail="[^"]*"', 'hotspotDetail=""', prompt_html)
prompt_html = re.sub(r'\beasingLabel="[^"]*"', 'easingLabel=""', prompt_html)
prompt_html = re.sub(r'\beasingStat="[^"]*"', 'easingStat=""', prompt_html)
prompt_html = re.sub(r'\beasingDetail="[^"]*"', 'easingDetail=""', prompt_html)
prompt_html = re.sub(r'\bfreshDate="[^"]*"', 'freshDate=""', prompt_html)
prompt_html = re.sub(r'\bsourceDate="[^"]*"', 'sourceDate=""', prompt_html)
_prop_saved = _before_prop - len(prompt_html)
print(f"Prop values stripped: {_prop_saved:,} chars saved (~{_prop_saved//3:,} tokens).")

# ── Strip non-daily section functions to free Phase 2 token budget ─────────────
# SectionRMG, SectionFiscal, SectionNBR, SectionPower, SectionPeers contain
# monthly/quarterly data — they do NOT need daily updates. Stripping their JSX
# bodies saves ~15,000–20,000 chars from prompt_html, giving Phase 2 a comfortable
# margin under 30k tokens. Their original code is restored unchanged after Phase 2.
_SLOW_SECTIONS = ['SectionRMG', 'SectionFiscal', 'SectionNBR', 'SectionPower', 'SectionPeers']
# Save originals from current_html (before ANY stripping/prop-erasure) so restoration
# always uses the full, unmodified function body regardless of what Claude outputs.
_slow_originals = {}
for _sname in _SLOW_SECTIONS:
    _om = re.search(r'function ' + re.escape(_sname) + r'\s*\(\s*\)', current_html)
    if _om:
        _ob = current_html.find('{', _om.end())
        if _ob != -1:
            _oe = _brace_end(current_html, _ob)
            _slow_originals[_sname] = current_html[_om.start():_oe + 1]
_slow_saved = {}
_slow_chars_saved = 0
for _sname in _SLOW_SECTIONS:
    _sm = re.search(r'function ' + re.escape(_sname) + r'\s*\(\s*\)', prompt_html)
    if _sm:
        _bs = prompt_html.find('{', _sm.end())
        if _bs != -1:
            _be = _brace_end(prompt_html, _bs)
            _full_fn = prompt_html[_sm.start():_be + 1]
            _sph = f'// [{_sname.upper()}_PLACEHOLDER — restored automatically]'
            _slow_saved[_sname] = _full_fn
            prompt_html = prompt_html[:_sm.start()] + _sph + prompt_html[_be + 1:]
            _slow_chars_saved += len(_full_fn) - len(_sph)
if _slow_saved:
    print(f"Slow sections stripped: {_slow_chars_saved:,} chars saved from "
          f"{len(_slow_saved)} sections: {list(_slow_saved.keys())}")
else:
    print("Warning: no slow sections found to strip — check function names.")

# ── Two-phase approach: gather data first, then generate HTML ───────────────────
# Phase 1 prompt: tiny (no HTML in prompt), Claude searches and returns JSON data.
# Phase 2 prompt: gathered JSON + stripped HTML (~22k tokens), Claude writes HTML.
# This guarantees Phase 2 has no tool use — Claude's first output IS the HTML.

GATHER_PROMPT = f"""Today is {today}.

Search for the latest Bangladesh economic and financial data, then return it as JSON.
Run searches for all categories below. Return ONLY a JSON object — no markdown, no explanation.

WHAT TO SEARCH:
1. Bangladesh CPI headline % YoY (BBS latest month), food inflation % YoY (BBS)
2. Bangladesh Bank (BB) policy rate %, SDF rate %, SLF rate %
3. Any recent BB MPC meeting decision or statement
4. Bangladesh GDP growth rate (BBS/World Bank latest), private sector credit growth % YoY (BB)
5. DSEX closing value, DS30, CSCX, daily turnover crore BDT, change pts/%, 52-week high/low
6. Latest DSE news (2-3 headlines)
7. BB T-bill primary auction cut-off yields: 91-day %, 182-day %, 364-day % (most recent auction)
8. 10-year and 5-year government bond yields (secondary market)
9. Any T-bill/bond market news
10. BAJUS gold price 22K BDT per bhori (bajus.org or news)
11. Brent crude spot USD/bbl, WTI crude USD/bbl, Henry Hub natural gas USD/MMBtu
12. Any commodity news
13. USD/BDT BB reference rate, EUR/BDT, GBP/BDT
14. Bangladesh gross forex reserves USD billion (BPM6 basis, BB)
15. Monthly exports USD million (EPB, latest month) — total and RMG portion; imports; trade deficit
16. Any forex/trade news
17. Monthly remittance inflow USD million (BB, latest month), which month, YoY % change
18. Any remittance news
19. NPL ratio % (BB), capital adequacy ratio %; any major banking news
20. Brent crude current spot and latest US-Iran war developments affecting oil markets
21. Bangladesh domestic food prices (DAM weekly survey, latest week): retail prices in Dhaka markets for rice coarse BDT/kg, rice fine/miniket BDT/kg, red lentil BDT/kg, soybean oil BDT/L, sugar BDT/kg, onion BDT/kg, egg BDT/dozen, broiler chicken BDT/kg, wheat flour BDT/kg; and the week-ending date of the survey. Search "DAM Bangladesh food prices" or "daily star DAM price" or "TBS Bangladesh market price".
22. Bangladesh RMG/garment export details (EPB, BGMEA latest release): most recent month's RMG exports USD million and YoY%; fiscal-year-to-date cumulative RMG exports USD billion and YoY%; buyer market shares (EU%, USA%, UK%, Canada%, Others%); BGMEA order pipeline assessment; 2-3 key RMG news headlines.
23. Bangladesh fiscal data (Ministry of Finance, NBR, IMED): NBR revenue collection Jul-to-latest cumulative BDT trillion and full-year target; ADP (Annual Development Programme) utilisation % and BDT crore spent vs target crore; government bank borrowing cumulative BDT trillion vs full-year ceiling; fiscal deficit FY26 target % of GDP; 2 fiscal news headlines.
24. Bangladesh power/electricity sector (BPDB, PGCB): current average daily generation MW, peak demand MW, daily shortage/loadshedding MW; rural and urban loadshedding hours per day; LNG spot import cost USD/MMBtu; 1-2 power sector news headlines.
25. Regional peer economic comparison (latest 2025-26 data): for India, Vietnam, Pakistan, Sri Lanka — GDP growth % (latest annual), CPI inflation % (latest month), gross forex reserves USD billion, current account balance % GDP, sovereign credit rating (S&P or Fitch).

Return ONLY this JSON (use null for any value not found):
{{
  "cpi_headline_pct": "9.94",     "cpi_headline_month": "Jan 2026",
  "cpi_food_pct": "11.35",        "cpi_food_month": "Jan 2026",
  "bb_policy_rate_pct": "10.00",  "sdf_rate_pct": "9.00",  "slf_rate_pct": "11.00",
  "mpc_note": null,
  "gdp_growth_pct": "5.17",  "gdp_year": "FY2024",
  "credit_growth_pct": "7.3",
  "dsex": 5323,  "ds30": 1890,  "cscx": 1100,
  "dse_turnover_cr": 445,
  "dse_change_pts": -2,  "dse_change_pct": "-0.03",
  "dse_52wk_high": 5684,  "dse_52wk_low": 4726,
  "news_dse": ["headline 1", "headline 2"],
  "tbill_91d_pct": "9.90",  "tbill_182d_pct": "9.98",  "tbill_364d_pct": "9.93",
  "tbill_auction_label": "Mar '26",  "tbill_auction_date": "05 Mar 2026",
  "tbill_new_auction": false,
  "bond_10y_pct": "12.50",  "bond_5y_pct": "11.90",
  "news_tbill": ["headline 1"],
  "gold_22k_bdt": 144956,
  "brent_usd": 84.0,  "wti_usd": 80.5,  "natgas_usd": 4.20,
  "news_commodity": ["headline 1", "headline 2"],
  "usd_bdt": 121.50,  "eur_bdt": 132.00,  "gbp_bdt": 154.00,
  "forex_reserves_bn": 20.5,
  "exports_mn": 4200,  "rmg_exports_mn": 3600,  "exports_month": "Jan 2026",
  "imports_mn": 5500,  "trade_deficit_mn": 1300,  "trade_deficit_yoy_pct": "-5.2",
  "news_forex": ["headline 1", "headline 2"],
  "remittance_mn": 2100,  "remittance_month": "February 2026",
  "remittance_yoy_pct": "+15.2",
  "news_remittance": ["headline 1", "headline 2"],
  "npl_ratio_pct": "9.93",  "car_pct": "12.5",
  "news_banking": ["headline 1", "headline 2", "headline 3"],
  "brent_spot": 84.0,
  "news_iranwar": ["headline 1", "headline 2", "headline 3"],

  "dam_week_ending": "Mar 6, 2026",
  "dam_rice_coarse": "42",  "dam_rice_fine": "72",
  "dam_lentil": "110",      "dam_oil": "155",
  "dam_sugar": "120",       "dam_onion": "45",
  "dam_egg": "140",         "dam_chicken": "185",  "dam_flour": "48",

  "rmg_exports_latest_mn": 2810,  "rmg_exports_latest_yoy_pct": "-13.21",
  "rmg_exports_latest_month": "February 2026",
  "rmg_ytd_bn": "24.1",  "rmg_ytd_yoy_pct": "-4.2",
  "rmg_eu_pct": 57,  "rmg_us_pct": 18,  "rmg_uk_pct": 9,
  "rmg_canada_pct": 4,  "rmg_others_pct": 12,
  "rmg_pipeline": "Softening",
  "news_rmg": ["headline 1", "headline 2"],

  "fiscal_period": "Jul–Jan FY26",
  "nbr_collected_trillion": "2.08",  "nbr_target_trillion": "7.97",
  "nbr_progress_pct": 26,
  "adp_pct": "22.5",  "adp_spent_crore": "64440",  "adp_target_crore": "285000",
  "govt_borrow_trillion": "1.03",  "govt_borrow_pct": 74,
  "govt_borrow_ceiling_trillion": "1.375",
  "news_fiscal": ["headline 1", "headline 2"],

  "nbr_vat_bn": "810",      "nbr_vat_share_pct": 39,   "nbr_vat_yoy_pct": "+12",
  "nbr_it_bn": "680",       "nbr_it_share_pct": 33,    "nbr_it_yoy_pct": "+8",
  "nbr_customs_bn": "590",  "nbr_customs_share_pct": 28, "nbr_customs_yoy_pct": "-3",
  "nbr_shortfall_bn": "380", "nbr_needed_5mo_trillion": "5.89",

  "power_gen_mw": 13200,  "power_demand_mw": 15800,  "power_shortage_mw": 2600,
  "power_shedding_rural": "3-4 hrs",  "power_shedding_urban": "1-2 hrs",
  "power_lng_mmbtu": "$12-14",
  "news_power": ["headline 1"],

  "peers_in_gdp": "6.4",   "peers_in_cpi": "4.3",   "peers_in_fxr": "638",  "peers_in_cab": "-1.0",  "peers_in_rating": "BBB-",
  "peers_vn_gdp": "6.8",   "peers_vn_cpi": "3.6",   "peers_vn_fxr": "103",  "peers_vn_cab": "+4.2",  "peers_vn_rating": "BB+",
  "peers_pk_gdp": "2.8",   "peers_pk_cpi": "23.0",  "peers_pk_fxr": "11.7", "peers_pk_cab": "-0.8",  "peers_pk_rating": "CCC+",
  "peers_lk_gdp": "4.5",   "peers_lk_cpi": "4.1",   "peers_lk_fxr": "6.1",  "peers_lk_cab": "-2.1",  "peers_lk_rating": "B-"
}}"""

# ── API client (used by both phases) ───────────────────────────────────────────
client = anthropic.Anthropic(
    api_key=os.environ["ANTHROPIC_API_KEY"],
    timeout=anthropic.Timeout(connect=10.0, read=1800.0, write=600.0, pool=1800.0),
)

WEB_SEARCH_TOOL = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 12}]
MAX_RETRIES = 6   # allows 120+240+360+480+600 = 1,800s total wait across 5 retries

def _stream_call(messages, tools, max_tokens, label):
    """Stream a Claude call with retry on rate limit. Returns final Message."""
    t0 = time.time()
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=max_tokens,
                tools=tools,
                messages=messages,
            ) as stream:
                resp = stream.get_final_message()
            print(f"{label} done in {time.time()-t0:.0f}s. Stop reason: {resp.stop_reason}")
            return resp
        except anthropic.RateLimitError as e:
            wait = 120 * attempt   # 120s, 240s, 360s, 480s, 600s — clears any ≤10-min window
            print(f"Rate limit (attempt {attempt}/{MAX_RETRIES}). Waiting {wait}s... ({e})")
            if attempt == MAX_RETRIES:
                print("ERROR: Max retries exceeded.")
                sys.exit(1)
            time.sleep(wait)
        except Exception as e:
            print(f"ERROR: {label} failed after {time.time()-t0:.0f}s — {type(e).__name__}: {e}")
            sys.exit(1)

# ── PHASE 1: Web search → gathered JSON (tiny prompt, no HTML) ─────────────────
print("Phase 1: Gathering latest Bangladesh data via web search...")
gather_resp = _stream_call(
    messages=[{"role": "user", "content": GATHER_PROMPT}],
    tools=WEB_SEARCH_TOOL,
    max_tokens=6000,
    label="Phase 1 (data gather)",
)

gathered_json = "{}"
last_text = None
for block in gather_resp.content:
    if block.type == "text" and block.text.strip():
        last_text = block.text          # keep overwriting — we want the LAST text block
if last_text:
    text = last_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    gathered_json = text.strip()

# ── Trim gathered_json to fit Phase 2 token budget ───────────────────────────
# gathered_json size is variable (7k–15k chars depending on Phase 1 verbosity).
# Cap at 8,500 chars to guarantee Phase 2 stays under 30k input tokens @2.6 ch/tok.
# Budget: ~76,000 total chars - ~65,500 prompt_html - ~2,500 framing = ~8,000 for JSON.
_MAX_JSON = 8500
if len(gathered_json) > _MAX_JSON:
    print(f"Gathered JSON ({len(gathered_json):,} chars) exceeds budget ({_MAX_JSON:,}). Trimming...")
    try:
        import json as _json
        _gd = _json.loads(gathered_json)
        for _k, _v in list(_gd.items()):
            if _k.startswith('news_') and isinstance(_v, list):
                _gd[_k] = [str(x)[:100] for x in _v[:2]]  # max 2 headlines, 100 chars each
            elif isinstance(_v, str) and len(_v) > 100:
                _gd[_k] = _v[:100]                         # cap other string fields at 100 chars
        gathered_json = _json.dumps(_gd, ensure_ascii=False)
        print(f"  Trimmed to {len(gathered_json):,} chars.")
    except Exception as _e:
        print(f"  Smart trim failed ({_e}). Hard-capping at {_MAX_JSON:,} chars.")
        gathered_json = gathered_json[:_MAX_JSON]

print(f"Gathered data: {len(gathered_json):,} chars")
_p2_est = len(prompt_html) + len(gathered_json) + 2500
print(f"Phase 2 est: {_p2_est:,} chars (~{int(_p2_est/2.6):,} tok @2.6 ch/tok)")

# ── Rate-limit cooldown between Phase 1 and Phase 2 ────────────────────────────
# Phase 1's web_search tool makes 15-20 successive internal API calls, each
# accumulating prior search results. The last internal calls can send 20,000-40,000
# input tokens — much of the 30k/min budget. Waiting 70s ensures those tokens
# have rolled off Anthropic's 60-second sliding window before Phase 2 fires.
print("Cooling down 70s to clear Phase 1 token usage from rate-limit window...")
time.sleep(70)

# ── PHASE 2: Generate updated HTML (no web search, HTML is direct output) ───────
UPDATE_PROMPT = f"""THE BRIEF update. Today: {today} (UTC; +6 hrs = BDT).

GATHERED DATA:
<data>
{gathered_json}
</data>

CURRENT HTML (pass all placeholder comments through UNCHANGED):
<current_file>
{prompt_html}
</current_file>

REQUIRED PLACEHOLDERS — copy EXACTLY:
  <head><!-- HEAD_PLACEHOLDER — restored automatically --></head>
  <style>/* CSS_PLACEHOLDER — restored automatically */</style>
  // [COMPONENTS_PLACEHOLDER — restored automatically]
  // [DSEXCHART_RENDER_PLACEHOLDER — restored automatically]
  // [TBILLCHART_RENDER_PLACEHOLDER — restored automatically]
  // [OILCHART_RENDER_PLACEHOLDER — restored automatically]
  // [TARIFF_RENDER_PLACEHOLDER — restored automatically]
  // [TRADE_RENDER_PLACEHOLDER — restored automatically]
  // [APP_PLACEHOLDER — restored automatically]
  // [SECTIONRMG_PLACEHOLDER — restored automatically]
  // [SECTIONFISCAL_PLACEHOLDER — restored automatically]
  // [SECTIONNBR_PLACEHOLDER — restored automatically]
  // [SECTIONPOWER_PLACEHOLDER — restored automatically]
  // [SECTIONPEERS_PLACEHOLDER — restored automatically]

UPDATE RULES (use gathered JSON keys by exact name):
HEADER: BRIEF_DATE = "{today} · HHMM BDT"
SectionBB: bb_policy_rate_pct sdf_rate_pct slf_rate_pct gdp_growth_pct credit_growth_pct forex_reserves_bn cpi_headline_pct remittance_mn news_banking
SectionMacro: cpi_headline_pct/_month cpi_food_pct/_month bb_policy_rate_pct sdf_rate_pct slf_rate_pct mpc_note
DSEXChart: drop[0], append{{label:"Mar 7",value:dsex,showLabel:true,today:true}}, remove today:true from prior last. SectionDSE: all dse_* + news_dse
TBillChart: tbill_new_auction→drop[0]+append new yields; else update last entry. SectionTBond: tbill_91d/182d/364d bond_10y/5y tbill_auction_date news_tbill
SectionComm: gold_22k_bdt brent_usd wti_usd natgas_usd news_commodity
SectionFX: usd/eur/gbp_bdt forex_reserves_bn exports/rmg_exports_mn exports_month imports_mn trade_deficit_mn/_yoy_pct news_forex
SectionRemittance: remittance_mn/_month/_yoy_pct news_remittance
SectionBanking: npl_ratio_pct car_pct news_banking
OilChart: remove old today:true, append{{label:"Mar 7",value:brent_spot,today:true}}, keep Feb28 event:true, >12→drop oldest. SectionIranWar: brent_spot news_iranwar
SectionExec: WRITE 5 fresh bullets (bull📈/bear📉/warn⚠️/watch🔭). Cover: reserves+remittance, exports, oil/geopolitics, market/rates, outlook. Update events calendar. trafficStatus(bull/bear/warn/neu).
SectionDAM: all 9 dam_* prices; MoM bear=up/bull=down/neu=flat; hotspotLabel(rising items)·hotspotStat("N of 9 rising MoM")·hotspotDetail(pct changes); easingLabel/Stat/Detail(falling); freshDate/sourceDate=dam_week_ending; news; trafficStatus(warn≥4rising,bull=majority falling).
NOTE: SectionRMG/SectionFiscal/SectionNBR/SectionPower/SectionPeers are PLACEHOLDER-restored — do NOT write them; pass their placeholders through EXACTLY as shown above.
BankerRead: Each section has <BankerRead insight="..." /> — the insight= prop is NOT stripped, so the previous text is visible. Update it only if today's gathered data represents a material change for that section; otherwise leave it EXACTLY as-is.

OUTPUT: First character must be '<'. Start immediately with <!DOCTYPE html>. No preamble. End with </html>."""

print("Phase 2: Generating updated HTML (no web search)...")
response = _stream_call(
    messages=[{"role": "user", "content": UPDATE_PROMPT}],
    tools=[],
    max_tokens=64000,
    label="Phase 2 (HTML generation)",
)

# ── Extract the HTML from Phase 2 response ─────────────────────────────────────
# Phase 2 has no tool use — Claude's output should begin with <!DOCTYPE html>.
def _extract_html(resp):
    for block in resp.content:
        if block.type == "text":
            text = block.text
            stripped = text.strip()
            if stripped.startswith("```"):
                lines = stripped.split("\n")
                stripped = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])
                text = stripped
            for marker in ("<!DOCTYPE", "<!doctype", "<html", "<HTML"):
                idx = text.find(marker)
                if idx != -1:
                    return text[idx:]
    return None

updated_html = _extract_html(response)

if not updated_html:
    print("ERROR: Phase 2 did not return valid HTML. Response blocks:")
    for i, block in enumerate(response.content):
        btype = getattr(block, "type", "?")
        btext = getattr(block, "text", "")[:300] if btype == "text" else ""
        print(f"  [{i}] type={btype} {btext!r}")
    sys.exit(1)

# ── Restore <head> block (PWA tags, CDN scripts, meta) ─────────────────────────
if _head_block and "HEAD_PLACEHOLDER" in updated_html:
    updated_html = updated_html.replace(
        "<head><!-- HEAD_PLACEHOLDER — restored automatically --></head>",
        _head_block, 1)
    print("Head block restored.")
elif _head_block:
    # Fallback: splice original head into Claude's output
    _hm = re.search(r'<head>.*?</head>', updated_html, re.DOTALL)
    if _hm:
        updated_html = updated_html[:_hm.start()] + _head_block + updated_html[_hm.end():]
        print("Head block fallback-restored (placeholder missing).")
    else:
        print("Warning: could not restore <head> block.")

# ── Restore CSS block ──────────────────────────────────────────────────────────
if _css_block and "CSS_PLACEHOLDER" in updated_html:
    updated_html = updated_html.replace(_placeholder, _css_block, 1)
    print("CSS block restored.")
elif _css_block:
    print("Warning: CSS placeholder not found in Claude's output — CSS may be missing.")

# ── Restore JS render sections ──────────────────────────────────────────────────
for _js_key, _js_content in _js_parts.items():
    _js_ph = f'// [{_js_key} — restored automatically]'
    if _js_ph in updated_html:
        updated_html = updated_html.replace(_js_ph, _js_content, 1)
        print(f"  {_js_key} restored.")
    else:
        print(f"Warning: {_js_key} placeholder missing from Claude's output — "
              f"restoring from original HTML as fallback.")
        # Fallback: inject the original rendering back at the known anchor point
        anchor_map = {
            'COMPONENTS_PLACEHOLDER':       ('// ── Components',      '// ── Sections'),
            'DSEXCHART_RENDER_PLACEHOLDER':  ('function DSEXChart()',  'function SectionDSE()'),
            'TBILLCHART_RENDER_PLACEHOLDER': ('function TBillChart()', 'function SectionTBond()'),
            'OILCHART_RENDER_PLACEHOLDER':   ('function OilChart()',   'function SectionIranWar()'),
            'TARIFF_RENDER_PLACEHOLDER':     ('function SectionTariff()', 'function SectionTrade()'),
            'TRADE_RENDER_PLACEHOLDER':      ('function SectionTrade()', 'function SectionIranWar()'),
            'APP_PLACEHOLDER':               ('// ── Main App',          '</script>'),
        }
        # Simple fallback: copy the corresponding block from the original HTML
        if _js_key in anchor_map:
            a_start, a_end = anchor_map[_js_key]
            orig_s = current_html.find(a_start)
            orig_e = current_html.find(a_end, orig_s + len(a_start)) if orig_s != -1 else -1
            if orig_s != -1 and orig_e != -1:
                orig_block = current_html[orig_s:orig_e]
                upd_s = updated_html.find(a_start)
                upd_e = updated_html.find(a_end, upd_s + len(a_start)) if upd_s != -1 else -1
                if upd_s != -1 and upd_e != -1:
                    updated_html = updated_html[:upd_s] + orig_block + updated_html[upd_e:]
                    print(f"  {_js_key} fallback-restored from original HTML.")

# ── Restore non-daily section functions ─────────────────────────────────────────
for _sname, _fn_body in _slow_saved.items():
    _sph = f'// [{_sname.upper()}_PLACEHOLDER — restored automatically]'
    if _sph in updated_html:
        updated_html = updated_html.replace(_sph, _fn_body, 1)
        print(f"  {_sname} restored.")
    else:
        print(f"Warning: {_sname} placeholder missing — restoring from original HTML.")
        # Fallback: locate the function in current_html and splice it into updated_html
        _fm = re.search(r'function ' + re.escape(_sname) + r'\s*\(\s*\)', current_html)
        if _fm:
            _fb = current_html.find('{', _fm.end())
            if _fb != -1:
                _fbe = _brace_end(current_html, _fb)
                _orig_fn = current_html[_fm.start():_fbe + 1]
                _um = re.search(r'function ' + re.escape(_sname) + r'\s*\(\s*\)', updated_html)
                if _um:
                    _ub = updated_html.find('{', _um.end())
                    if _ub != -1:
                        _ube = _brace_end(updated_html, _ub)
                        updated_html = updated_html[:_um.start()] + _orig_fn + updated_html[_ube + 1:]
                        print(f"  {_sname} fallback-restored from original HTML.")

# ── Hard-validate slow sections ─────────────────────────────────────────────────
# Claude may (a) generate a stub without a return, (b) generate a stub AND pass
# through the placeholder (causing two defs), or (c) omit the section entirely.
# This pass handles all three cases using the unstripped originals from current_html.
for _sname in _SLOW_SECTIONS:
    _original = _slow_originals.get(_sname) or _slow_saved.get(_sname, '')
    if not _original:
        continue

    # (a/b) Remove any stubs Claude generated that lack a return statement
    _dupes = list(re.finditer(r'function ' + re.escape(_sname) + r'\s*\(\s*\)', updated_html))
    for _dup in reversed(_dupes[:-1]):           # all occurrences except the last
        _db = updated_html.find('{', _dup.end())
        if _db != -1:
            _de = _brace_end(updated_html, _db)
            if 'return (' not in updated_html[_db:_de + 1]:
                updated_html = updated_html[:_dup.start()] + updated_html[_de + 1:]
                print(f"  {_sname}: removed Claude-generated stub.")

    # Force-replace from original if the remaining definition has no return
    _fm2 = re.search(r'function ' + re.escape(_sname) + r'\s*\(\s*\)', updated_html)
    if _fm2:
        _fb2 = updated_html.find('{', _fm2.end())
        if _fb2 != -1:
            _fe2 = _brace_end(updated_html, _fb2)
            if 'return (' not in updated_html[_fb2:_fe2 + 1]:
                updated_html = updated_html[:_fm2.start()] + _original + updated_html[_fe2 + 1:]
                print(f"  {_sname}: force-replaced (no return statement) from original.")
    else:
        # (c) Section missing entirely — inject before function App()
        _app_pos = updated_html.find('function App()')
        if _app_pos != -1:
            updated_html = updated_html[:_app_pos] + _original + '\n\n' + updated_html[_app_pos:]
            print(f"  {_sname}: injected from original (was missing entirely).")

    # Clean up any orphaned placeholder comment left in the output
    _sph2 = f'// [{_sname.upper()}_PLACEHOLDER — restored automatically]'
    if _sph2 in updated_html:
        updated_html = updated_html.replace(_sph2, '', 1)
        print(f"  {_sname}: removed orphaned placeholder comment.")

# ── Post-restoration sanity check ──────────────────────────────────────────────
# Verify the output is a complete, renderable file before writing.
# If critical pieces are missing or orphaned placeholders remain, fall back to
# the original for those blocks so the page never goes blank.

_sanity_ok = True

# 1. ReactDOM call must be present (App function wasn't truncated)
if 'ReactDOM' not in updated_html:
    print("⚠️  Sanity: ReactDOM missing — App function truncated. Restoring from original.")
    orig_s = current_html.find('// ── Main App')
    upd_s  = updated_html.find('// ── Main App')
    script_end = '</script>'
    orig_e = current_html.find(script_end, orig_s)
    upd_e  = updated_html.find(script_end, upd_s) if upd_s != -1 else -1
    if orig_s != -1 and orig_e != -1 and upd_s != -1 and upd_e != -1:
        updated_html = updated_html[:upd_s] + current_html[orig_s:orig_e] + updated_html[upd_e:]
        print("  App block restored from original.")
    _sanity_ok = False

# 2. No orphaned placeholder comments should remain after restoration
_orphaned = [k for k in _js_parts if f'// [{k} — restored automatically]' in updated_html]
for _k in _orphaned:
    print(f"⚠️  Sanity: orphaned placeholder {_k} still in output — removing stale comment.")
    updated_html = updated_html.replace(f'  // [{_k} — restored automatically]', '', 1)
    updated_html = updated_html.replace(f'// [{_k} — restored automatically]', '', 1)
    _sanity_ok = False

# 3. File must end with </html>
if not updated_html.rstrip().endswith('</html>'):
    print("⚠️  Sanity: file does not end with </html> — aborting write, keeping original.")
    updated_html = current_html   # full rollback
    _sanity_ok = False

if _sanity_ok:
    print("Sanity check passed ✅")
else:
    print("Sanity check applied fixes — review warnings above.")

# ── Write updated files ────────────────────────────────────────────────────────
with open("the-brief.html", "w", encoding="utf-8") as f:
    f.write(updated_html)

with open("index.html", "w", encoding="utf-8") as f:
    f.write(updated_html)

print(f"Done. Updated the-brief.html and index.html for {today}.")

# ══════════════════════════════════════════════════════════════════════════════
# SUBSCRIBER EMAIL
# ══════════════════════════════════════════════════════════════════════════════

def fetch_subscribers():
    """Return list of {name, email} dicts from Supabase using the service key."""
    if not SUPABASE_SVC_KEY:
        print("SUPABASE_SERVICE_KEY not set — skipping email send.")
        return []
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/subscribers?select=name,email&order=created_at.asc",
        headers={
            "apikey":        SUPABASE_SVC_KEY,
            "Authorization": f"Bearer {SUPABASE_SVC_KEY}",
        }
    )
    try:
        with urllib.request.urlopen(req) as r:
            subs = json.loads(r.read())
            print(f"Fetched {len(subs)} subscriber(s) from Supabase.")
            return subs
    except Exception as e:
        print(f"Failed to fetch subscribers: {e}")
        return []


def build_email_html(name, date_str):
    """Return a personalised HTML email string for one subscriber."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>THE BRIEF \u2014 {date_str}</title>
</head>
<body style="margin:0;padding:0;background-color:#0a0c0f;font-family:'Courier New',Courier,monospace;">
  <table width="100%" cellpadding="0" cellspacing="0" bgcolor="#0a0c0f">
    <tr><td align="center" style="padding:40px 20px;">
      <table width="540" cellpadding="0" cellspacing="0" style="max-width:540px;width:100%;">

        <!-- Header -->
        <tr><td bgcolor="#111418" style="background-color:#111418;border:1px solid #1e2329;border-radius:4px 4px 0 0;padding:24px 28px 18px;">
          <p style="margin:0;font-size:20px;font-weight:700;letter-spacing:0.25em;color:#ffffff;text-transform:uppercase;">
            THE <span style="color:#3b82f6;">BRIEF</span>
          </p>
          <p style="margin:4px 0 0;font-size:9px;letter-spacing:0.2em;color:#64748b;text-transform:uppercase;">
            Bangladesh Business Intelligence
          </p>
        </td></tr>

        <!-- Body -->
        <tr><td bgcolor="#111418" style="background-color:#111418;border:1px solid #1e2329;border-top:none;padding:22px 28px 28px;">
          <p style="margin:0 0 16px;font-size:10px;letter-spacing:0.12em;color:#64748b;text-transform:uppercase;">
            {date_str}
          </p>
          <p style="margin:0 0 22px;font-size:13px;color:#e2e8f0;line-height:1.75;">
            Hi {name},<br><br>
            Today&#39;s edition of THE BRIEF is ready &mdash; your daily snapshot of
            Bangladesh&#39;s macro economy, capital markets, monetary policy, and trade flows.
          </p>
          <table cellpadding="0" cellspacing="0">
            <tr><td bgcolor="#3b82f6" style="background-color:#3b82f6;border-radius:2px;">
              <a href="{BRIEF_URL}"
                 style="display:inline-block;padding:10px 24px;color:#ffffff;text-decoration:none;font-size:10px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;">
                Read Today&#39;s Brief &rarr;
              </a>
            </td></tr>
          </table>
        </td></tr>

        <!-- Footer -->
        <tr><td bgcolor="#0f1419" style="background-color:#0f1419;border:1px solid #1e2329;border-top:none;border-radius:0 0 4px 4px;padding:14px 28px;">
          <p style="margin:0;font-size:9px;color:#475569;letter-spacing:0.08em;text-transform:uppercase;text-align:center;">
            THE BRIEF &middot; Bangladesh &middot;
            <a href="mailto:{FROM_EMAIL}?subject=UNSUBSCRIBE"
               style="color:#475569;text-decoration:underline;">Unsubscribe</a>
          </p>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def send_emails(subscribers, date_str):
    """Send THE BRIEF to all subscribers via Brevo transactional email API."""
    if not BREVO_KEY:
        print("BREVO_API_KEY not set — skipping email send.")
        return

    sent, failed = 0, 0
    for sub in subscribers:
        payload = json.dumps({
            "sender":      {"name": FROM_NAME, "email": FROM_EMAIL},
            "to":          [{"email": sub["email"], "name": sub["name"]}],
            "subject":     f"THE BRIEF \u2014 {date_str}",
            "htmlContent": build_email_html(sub["name"], date_str),
        }).encode()
        req = urllib.request.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=payload,
            headers={
                "api-key":      BREVO_KEY,
                "Content-Type": "application/json",
                "Accept":       "application/json",
            }
        )
        try:
            with urllib.request.urlopen(req) as r:
                sent += 1
        except urllib.error.HTTPError as e:
            print(f"  \u2717 {sub['email']}: {e.code} \u2014 {e.read().decode()}")
            failed += 1

    print(f"Emails: {sent} sent, {failed} failed out of {len(subscribers)} subscriber(s).")


# ── Run email step ─────────────────────────────────────────────────────────────
print("Fetching subscribers...")
subscribers = fetch_subscribers()
if subscribers:
    print(f"Sending to {len(subscribers)} subscriber(s)...")
    send_emails(subscribers, today)
else:
    print("No subscribers found — email step skipped.")
