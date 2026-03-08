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
# Extract and stash the <style>...</style> block; replace with a tiny placeholder.
# We'll re-inject it into whatever HTML Claude returns.
_css_match = re.search(r'(<style>)(.*?)(</style>)', current_html, re.DOTALL)
if _css_match:
    _css_block   = _css_match.group(0)          # full <style>...</style>
    _css_content = _css_match.group(2)           # just the CSS text
    _placeholder = "<style>/* CSS_PLACEHOLDER — restored automatically */</style>"
    prompt_html  = current_html.replace(_css_block, _placeholder, 1)
    print(f"CSS stripped: {len(_css_content):,} chars saved from prompt "
          f"(~{len(_css_content)//3:,} tokens).")
else:
    prompt_html  = current_html
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

WEB_SEARCH_TOOL = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 30}]
MAX_RETRIES = 3

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
            wait = 65 * attempt
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
    max_tokens=4000,
    label="Phase 1 (data gather)",
)

gathered_json = "{}"
for block in gather_resp.content:
    if block.type == "text":
        text = block.text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])
        gathered_json = text.strip()
        break
print(f"Gathered data: {len(gathered_json):,} chars")

# ── PHASE 2: Generate updated HTML (no web search, HTML is direct output) ───────
UPDATE_PROMPT = f"""You are updating THE BRIEF, a Bangladesh business intelligence single-page app.
Today's date is {today}. Current UTC time → add 6 hours for BDT.

LATEST DATA gathered from web searches (use this to update all values):
<data>
{gathered_json}
</data>

CURRENT HTML — rendering sections replaced by placeholders you MUST pass through unchanged:
<current_file>
{prompt_html}
</current_file>

REQUIRED PLACEHOLDERS — include these EXACTLY, do not alter them:
  <style>/* CSS_PLACEHOLDER — restored automatically */</style>
  // [COMPONENTS_PLACEHOLDER — restored automatically]
  // [DSEXCHART_RENDER_PLACEHOLDER — restored automatically]
  // [TBILLCHART_RENDER_PLACEHOLDER — restored automatically]
  // [OILCHART_RENDER_PLACEHOLDER — restored automatically]
  // [APP_PLACEHOLDER — restored automatically]


UPDATE INSTRUCTIONS:

1. HEADER: Set BRIEF_DATE = "{today} · HHMM BDT" using the current time.

2. SectionBB: Update with bb_policy_rate_pct, sdf_rate_pct, slf_rate_pct, gdp_growth_pct,
   credit_growth_pct, forex_reserves_bn, cpi_headline_pct, remittance_mn, news_banking.

3. SectionMacro: Update with cpi_headline_pct, cpi_headline_month, cpi_food_pct,
   cpi_food_month, bb_policy_rate_pct, sdf_rate_pct, slf_rate_pct, mpc_note.

4. DSEXChart data array (20 points): Drop index 0. Add new last entry:
   {{ label: "Mar 7", value: <dsex>, showLabel: true, today: true }}
   Remove today:true from the previous last entry.
   SectionDSE: Update ticker with dsex, ds30, cscx, dse_turnover_cr, dse_change_pts,
   dse_change_pct, dse_52wk_high, dse_52wk_low; update news_dse headlines.

5. TBillChart: If tbill_new_auction is true, drop labels[0]/d91[0]/d182[0]/d364[0] and
   append new values; update pkI/pkV if a new peak. Otherwise update last element if changed.
   SectionTBond: Update with tbill_91d_pct, tbill_182d_pct, tbill_364d_pct,
   bond_10y_pct, bond_5y_pct, tbill_auction_date; update news_tbill.

6. SectionComm: Update with gold_22k_bdt, brent_usd, wti_usd, natgas_usd, news_commodity.

7. SectionFX: Update with usd_bdt, eur_bdt, gbp_bdt, forex_reserves_bn, exports_mn,
   rmg_exports_mn, exports_month, imports_mn, trade_deficit_mn,
   trade_deficit_yoy_pct, news_forex.

8. SectionRemittance (§07): Update with remittance_mn, remittance_month,
   remittance_yoy_pct, news_remittance.

9. SectionBanking (§08): Update with npl_ratio_pct, car_pct, news_banking.

10. OilChart STATIC_DATA: Remove today:true from current last entry. Append:
    {{ label: "Mar 7", value: <brent_spot>, today: true }}
    Keep event:true on the Feb 28 entry. Drop oldest if array > 12 points.
    SectionIranWar: Update with brent_spot, news_iranwar.

11. SectionExec (Executive Summary — you WRITE this, do not copy old content):
    Synthesise 5 bullets from ALL gathered data. Use types: "bull" (positive), "bear" (negative),
    "warn" (risk/watch). Each bullet needs icon (📈 bull / 📉 bear / ⚠️ warn / 🔭 watch) and text.
    Cover: forex reserves + remittance, exports trend, oil/geopolitics risk, market/rates, forward look.
    Update the events array with accurate upcoming Bangladesh economic calendar dates.
    Set trafficStatus to "bull"/"bear"/"warn"/"neu" based on overall macro sentiment today.

12. SectionDAM (Domestic Food Prices):
    Update items array with all 9 commodity prices from dam_* fields.
    Derive MoM change type: price up → "bear", down → "bull", flat → "neu".
    Update ticker array to show 4 headline staples with current prices and MoM direction.
    Update hotspotLabel (names of rising items joined by " · "), hotspotStat ("N of 9 staples rising MoM"),
    hotspotDetail (specific % changes for rising items), easingLabel/easingStat/easingDetail (falling items).
    Set freshDate and sourceDate from dam_week_ending. Update news with fresh food-price headlines.
    Set trafficStatus: "warn" if 4+ rising, "neu" if mixed, "bull" if majority falling.

13. SectionRMG (RMG Deep Dive):
    Update markets array with rmg_eu_pct, rmg_us_pct, rmg_uk_pct, rmg_canada_pct, rmg_others_pct.
    Update all card and ticker values: rmg_exports_latest_mn, rmg_exports_latest_yoy_pct,
    rmg_ytd_bn, rmg_ytd_yoy_pct, rmg_pipeline. Update news with news_rmg headlines.
    Set trafficStatus: "bear" if YoY negative, "warn" if pipeline softening, "bull" if improving.

14. SectionFiscal (Fiscal & Budget):
    Update ticker and card values from fiscal_period, nbr_collected_trillion, nbr_target_trillion,
    nbr_progress_pct, adp_pct, adp_spent_crore, adp_target_crore,
    govt_borrow_trillion, govt_borrow_pct, govt_borrow_ceiling_trillion.
    Update all ProgressBar pct values to match the new percentages.
    Update news with news_fiscal headlines. Set trafficStatus based on fiscal health.

15. SectionNBR (NBR Tax Revenue):
    Update taxes array: VAT (nbr_vat_bn, nbr_vat_share_pct, nbr_vat_yoy_pct),
    Income Tax (nbr_it_bn, nbr_it_share_pct, nbr_it_yoy_pct),
    Customs (nbr_customs_bn, nbr_customs_share_pct, nbr_customs_yoy_pct).
    Update overall collection card: nbr_collected_trillion, nbr_target_trillion, nbr_progress_pct,
    nbr_shortfall_bn, nbr_needed_5mo_trillion. Update ticker. Set trafficStatus.

16. SectionPower (Power & Energy):
    Update ticker and cards from power_gen_mw, power_demand_mw, power_shortage_mw.
    Compute generation % of demand = round(power_gen_mw / power_demand_mw * 100).
    Update ProgressBar pct to this value. Update loadshedding hours from power_shedding_rural/urban.
    Update LNG cost from power_lng_mmbtu. Update news with news_power headlines.
    Set trafficStatus: "bear" if shortage > 2000 MW, "warn" if 1000-2000, "bull" if < 1000.

17. SectionPeers (Regional Peers):
    Update Bangladesh row: gdp = gdp_growth_pct, cpi = cpi_headline_pct, fxr = forex_reserves_bn,
    cab from trade/remittance data, rating unchanged unless new info.
    Update peers array for India, Vietnam, Pakistan, Sri Lanka from peers_* fields.
    Recalculate gdpC/cpiC/fxrC/cabC: "best" = top performer, "worst" = bottom, "mid" = others.
    Update ticker with current BD metrics. Set trafficStatus.

OUTPUT: Start your response IMMEDIATELY with <!DOCTYPE html> — the very first character
must be '<'. Do not write any introduction, summary, explanation, or reasoning before the HTML.
End with </html>. The complete file, nothing else."""

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
