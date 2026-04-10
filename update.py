import anthropic
import argparse
import html as html_mod
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# ── CLI flags ─────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="THE BRIEF daily update pipeline")
parser.add_argument('--dry-run', action='store_true', help='Skip API calls, use cached data')
args = parser.parse_args()

# ── Config (env vars with fallbacks) ──────────────────────────────────────────
BREVO_KEY        = os.environ.get("BREVO_API_KEY", "")
SUPABASE_URL     = os.environ.get("SUPABASE_URL", "https://ssbliukchgibjcjohibi.supabase.co")
SUPABASE_SVC_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
BRIEF_URL        = os.environ.get("BRIEF_URL", "https://clauding-lab.github.io/the-brief/")
FROM_EMAIL       = os.environ.get("FROM_EMAIL", "adnan.rshd@gmail.com")
FROM_NAME        = "THE BRIEF"

# ── Date constants (BDT = UTC+6) ─────────────────────────────────────────────
_BDT = timezone(timedelta(hours=6))
_now = datetime.now(_BDT)
today = _now.strftime("%A %d %B %Y").upper()
today_iso = _now.strftime("%Y-%m-%d")
today_search = f"{_now.day} {_now.strftime('%B')} {_now.year}"
today_short = f"{_now.day} {_now.strftime('%b')}"
chart_label = _now.strftime("%b ") + str(_now.day)

# ── Chart bounds for sanity checking ──────────────────────────────────────────
CHART_BOUNDS = {
    'dsex': (1000, 20000),
    'brent': (10, 300),
    'lng': (1, 100),
}

# ── Headline scraping config ─────────────────────────────────────────────────
_HEADLINE_SOURCES = [
    {
        "url": "https://www.thedailystar.net/business",
        "code": "DS",
        "name": "Daily Star",
        "pattern": r'<a\s+href="(/business/[^"]+)"[^>]*>\s*([^<]+?)\s*</a>',
        "base": "https://www.thedailystar.net",
    },
    {
        "url": "https://www.tbsnews.net/economy",
        "code": "TBS",
        "name": "TBS News",
        "pattern": r'<a\s+href="(/economy/[^"]+)"[^>]*>\s*([^<]{15,}?)\s*</a>',
        "base": "https://www.tbsnews.net",
    },
    {
        "url": "https://today.thefinancialexpress.com.bd/",
        "code": "FE",
        "name": "Financial Express BD",
        "pattern": r'<a\s+href="(https://today\.thefinancialexpress\.com\.bd/(?:first-page|last-page|economy|stock-corporate|trade-market|trade-commodities|public|national)/[^"]+)"[^>]*>.*?<h4>([^<]+)</h4>',
        "base": "",
        "dotall": True,
    },
]

# ── Slow sections (not updated daily — restored from original) ───────────────
_SLOW_SECTIONS = ['DSEXChart', 'LNGChart', 'SectionRMG', 'SectionFiscal', 'SectionNBR', 'SectionPower', 'SectionPeers', 'SectionIranWar']

# ── API config ────────────────────────────────────────────────────────────────
WEB_SEARCH_TOOL = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 25}]
MAX_RETRIES = 6


# ══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def _scrape_headlines(source, count=4):
    """Fetch a news page and extract the first `count` unique article headlines."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; TheBrief/1.0)"}
    req = urllib.request.Request(source["url"], headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            page = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  ⚠️  Failed to fetch {source['url']}: {e}")
        return []
    _flags = re.IGNORECASE | (re.DOTALL if source.get("dotall") else 0)
    matches = re.findall(source["pattern"], page, _flags)
    seen_titles = set()
    results = []
    for path, title in matches:
        title = re.sub(r'\s+', ' ', html_mod.unescape(title)).strip()
        if len(title) < 20 or title.lower() in ("read more", "see all", "more news"):
            continue
        _norm = re.sub(r'\s+', ' ', title.lower())
        if _norm in seen_titles:
            continue
        seen_titles.add(_norm)
        url = source["base"] + path if source["base"] else path
        results.append({
            "title": title,
            "url": url,
            "source": source["code"],
            "date": today_short,
        })
        if len(results) >= count:
            break
    return results


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
    for fname, key in (('TBillChart', 'TBILLCHART_RENDER_PLACEHOLDER'),):
        sc = _strip_return(sc, fname, key)

    sc = _strip_return(sc, 'SectionTariff', 'TARIFF_RENDER_PLACEHOLDER')
    sc = _strip_return(sc, 'SectionTrade', 'TRADE_RENDER_PLACEHOLDER')

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


def _stream_call(client, messages, tools, max_tokens, label):
    """Stream a Claude call with retry on rate limit. Returns final Message."""
    t0 = time.time()
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=max_tokens,
                tools=tools,
                messages=messages,
            ) as stream:
                resp = stream.get_final_message()
            print(f"{label} done in {time.time()-t0:.0f}s. Stop reason: {resp.stop_reason}")
            return resp
        except anthropic.RateLimitError as e:
            wait = 120 * attempt
            print(f"Rate limit (attempt {attempt}/{MAX_RETRIES}). Waiting {wait}s... ({e})")
            if attempt == MAX_RETRIES:
                print("ERROR: Max retries exceeded.")
                sys.exit(1)
            time.sleep(wait)
        except Exception as e:
            print(f"ERROR: {label} failed after {time.time()-t0:.0f}s — {type(e).__name__}: {e}")
            sys.exit(1)


def _extract_html(resp):
    """Extract HTML from a Claude response."""
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
    safe_name = html_mod.escape(name)
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
            Hi {safe_name},<br><br>
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
          <p style="margin:18px 0 0;font-size:10px;color:#64748b;letter-spacing:0.06em;font-style:italic;">
            Human-directed, AI-assisted intelligence.
          </p>
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
        return 0, 0

    sent, failed = 0, 0
    for n, sub in enumerate(subscribers, 1):
        payload = json.dumps({
            "sender":      {"name": FROM_NAME, "email": FROM_EMAIL},
            "to":          [{"email": sub["email"], "name": sub["name"]}],
            "subject":     f"THE BRIEF \u2014 {date_str}",
            "htmlContent": build_email_html(sub["name"], date_str),
            "headers": {
                "List-Unsubscribe": f"<mailto:{FROM_EMAIL}?subject=UNSUBSCRIBE>"
            },
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
            print(f"  \u2717 subscriber #{n}: {e.code} \u2014 {e.read().decode()}")
            failed += 1
        # Rate-limit courtesy delay between sends
        if n < len(subscribers):
            time.sleep(0.2)

    print(f"Emails: {sent} sent, {failed} failed out of {len(subscribers)} subscriber(s).")
    return sent, failed


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def load_and_strip_html(filepath):
    """Load the-brief.html, strip CSS/head/JS/props for Phase 2 prompt.
    Returns (current_html, prompt_html, saved_parts).
    saved_parts is a dict with keys: head_block, css_block, css_placeholder,
    js_parts, slow_saved, slow_originals.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        current_html = f.read()

    saved_parts = {}

    # ── Strip <head> block ────────────────────────────────────────────────
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
    saved_parts['head_block'] = _head_block

    # ── Strip <style> block (only if not already inside stripped head) ────
    # Note: <style> is typically nested inside <head>, so a successful head
    # strip already removes it. We only need this path when head stripping
    # failed or when <style> lives outside <head>.
    _css_block = None
    _placeholder = None
    if _head_block and re.search(r'<style>.*?</style>', _head_block, re.DOTALL):
        # CSS already captured inside the head block — no extra work.
        pass
    else:
        _css_match = re.search(r'(<style>)(.*?)(</style>)', prompt_html, re.DOTALL)
        if _css_match:
            _css_block   = _css_match.group(0)
            _css_content = _css_match.group(2)
            _placeholder = "<style>/* CSS_PLACEHOLDER — restored automatically */</style>"
            prompt_html  = prompt_html.replace(_css_block, _placeholder, 1)
            print(f"CSS stripped: {len(_css_content):,} chars saved from prompt "
                  f"(~{len(_css_content)//3:,} tokens).")
        else:
            print("Warning: no <style> block found (head strip may have missed it).")
    saved_parts['css_block'] = _css_block
    saved_parts['css_placeholder'] = _placeholder

    # ── Strip JS render sections ──────────────────────────────────────────
    prompt_html, _js_chars_saved, _js_parts = strip_js_render(prompt_html)
    saved_parts['js_parts'] = _js_parts

    # ── Strip long prop values ────────────────────────────────────────────
    _before_prop = len(prompt_html)
    prompt_html = re.sub(r'\btext="[^"]{30,}"', 'text=""', prompt_html)
    prompt_html = re.sub(r'\bheadline="[^"]{30,}"', 'headline=""', prompt_html)
    prompt_html = re.sub(r'\bdetail="[^"]{20,}"', 'detail=""', prompt_html)
    prompt_html = re.sub(r'\bsub="[^"]{20,}"', 'sub=""', prompt_html)
    prompt_html = re.sub(r'\bsource="[^"]*"', 'source=""', prompt_html)
    prompt_html = re.sub(r'\bsourceUrl="[^"]*"', 'sourceUrl=""', prompt_html)
    prompt_html = re.sub(r'\btime="[^"]*"', 'time=""', prompt_html)
    prompt_html = re.sub(r'\bchange="[^"]*"', 'change=""', prompt_html)
    prompt_html = re.sub(r'\binsight="[^"]*"', 'insight=""', prompt_html)
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

    # ── Strip old headline/oped arrays ────────────────────────────────────
    _hl_before = len(prompt_html)
    prompt_html = re.sub(
        r'(const headlines\s*=\s*)\[.*?\];',
        r'\1[];',
        prompt_html, count=1, flags=re.DOTALL)
    prompt_html = re.sub(
        r'(const opeds\s*=\s*)\[.*?\];',
        r'\1[];',
        prompt_html, count=1, flags=re.DOTALL)
    _hl_saved = _hl_before - len(prompt_html)
    if _hl_saved > 0:
        print(f"Old headlines/opeds stripped: {_hl_saved:,} chars saved (~{_hl_saved//3:,} tokens).")
    else:
        print("Warning: no headline/oped arrays found to strip in SectionHeadlines.")

    # ── Strip non-daily section functions ──────────────────────────────────
    _slow_originals = {}
    for _sname in _SLOW_SECTIONS:
        _om = re.search(r'function ' + re.escape(_sname) + r'\s*\(\s*\)', current_html)
        if _om:
            _ob = current_html.find('{', _om.end())
            if _ob != -1:
                _oe = _brace_end(current_html, _ob)
                _slow_originals[_sname] = current_html[_om.start():_oe + 1]
    saved_parts['slow_originals'] = _slow_originals

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
    saved_parts['slow_saved'] = _slow_saved

    if _slow_saved:
        print(f"Slow sections stripped: {_slow_chars_saved:,} chars saved from "
              f"{len(_slow_saved)} sections: {list(_slow_saved.keys())}")
    else:
        print("Warning: no slow sections found to strip — check function names.")

    return current_html, prompt_html, saved_parts


def phase1_gather_data(client, prompt_html):
    """Phase 1: Web search to gather latest Bangladesh data. Returns gathered_json string."""
    # Scrape headlines first
    print("Scraping headlines from 3 mandatory sources...")
    _scraped_headlines = []
    for _src in _HEADLINE_SOURCES:
        _hl = _scrape_headlines(_src, count=4)
        print(f"  {_src['code']}: {len(_hl)} headlines from {_src['url']}")
        _scraped_headlines.extend(_hl)
    print(f"Total scraped: {len(_scraped_headlines)} headlines")

    GATHER_PROMPT = f"""Today is {today}. Search date: {today_search}.

Search for the latest Bangladesh economic and financial data, then return it as JSON.
Run searches for all categories below. Return ONLY a JSON object — no markdown, no explanation.

CRITICAL: For DAILY-CHANGING data (marked with ★), you MUST search for today's actual value.
Do NOT use any example values from this prompt — they are PLACEHOLDERS only.
If a value hasn't changed since yesterday, that's fine — but you must VERIFY by searching.

WHAT TO SEARCH:
1. Bangladesh CPI headline % YoY (BBS latest month), food inflation % YoY (BBS)
2. Bangladesh Bank (BB) policy rate %, SDF rate %, SLF rate %
3. Any recent BB MPC meeting decision or statement (include next MPC date if known)
4. Bangladesh GDP growth rate (BBS/World Bank latest), private sector credit growth % YoY (BB)
5. ★ DSEX closing value, DS30, CSCX, daily turnover crore BDT, change pts/%, 52-week high/low. Check amarstock.com AND tradingview.com/symbols/DSEBD-DSEX/ for the latest DSEX close — these are more reliable than dsebd.org. Use the MOST RECENT trading day close (DSE trades Sun-Thu, closed Fri-Sat and holidays). If DSE was closed today, use the last trading day's close and note the date. Also include "dsex_date" with the actual date of the close.
6. Latest DSE news (2-3 headlines)
7. BB T-bill primary auction cut-off yields: 91-day %, 182-day %, 364-day % (most recent auction)
8. 10-year and 5-year government bond yields (secondary market)
9. Any T-bill/bond market news
10. ★ BAJUS gold price 22K BDT per bhori (bajus.org or news) — search "BAJUS gold price today {today_search}"
11. ★ Brent crude spot USD/bbl, WTI crude USD/bbl, Henry Hub natural gas USD/MMBtu, Asian LNG spot price USD/MMBtu (JKM benchmark or equivalent). Search "Brent crude price today {today_search}". For LNG: provide 6-8 monthly/biweekly historical data points from Oct 2025 to today for Asian LNG spot (JKM or equivalent) to chart the trend.
12. Any commodity news (search for today's commodity news)
13. ★ USD/BDT BB reference rate, EUR/BDT, GBP/BDT — search "USD BDT exchange rate today {today_search}"
14. Bangladesh gross forex reserves USD billion (BPM6 basis, BB) — include "forex_reserves_date" with the date of the figure
15. Monthly exports USD million (EPB, latest month) — total and RMG portion; imports; trade deficit
16. Any forex/trade news
17. Monthly remittance inflow USD million (BB, latest month), which month, YoY % change. Also search for partial-month data if available (e.g. "Bangladesh remittance March 2026 first 10 days").
18. Any remittance news
19. NPL ratio % (BB), capital adequacy ratio %; any major banking news
20. ★ Brent crude current spot and latest US-Iran war developments affecting oil markets (search "Iran war oil {today_search}")
21. Bangladesh domestic food prices (DAM weekly survey, latest week): retail prices in Dhaka markets for rice coarse BDT/kg, rice fine/miniket BDT/kg, red lentil BDT/kg, soybean oil BDT/L, sugar BDT/kg, onion BDT/kg, egg BDT/dozen, broiler chicken BDT/kg, wheat flour BDT/kg; and the week-ending date of the survey. Search "DAM Bangladesh food prices" or "daily star DAM price" or "TBS Bangladesh market price".
22. Bangladesh RMG/garment export details (EPB, BGMEA latest release): most recent month's RMG exports USD million and YoY%; fiscal-year-to-date cumulative RMG exports USD billion and YoY%; buyer market shares (EU%, USA%, UK%, Canada%, Others%); BGMEA order pipeline assessment; 2-3 key RMG news headlines.
23. Bangladesh fiscal data (Ministry of Finance, NBR, IMED): NBR revenue collection Jul-to-latest cumulative BDT trillion and full-year target; ADP (Annual Development Programme) utilisation % and BDT crore spent vs target crore; government bank borrowing cumulative BDT trillion vs full-year ceiling; fiscal deficit FY26 target % of GDP; 2 fiscal news headlines.
24. Bangladesh power/electricity sector (BPDB, PGCB): current average daily generation MW, peak demand MW, daily shortage/loadshedding MW; rural and urban loadshedding hours per day; LNG spot import cost USD/MMBtu; 1-2 power sector news headlines.
25. Regional peer economic comparison (latest 2025-26 data): for India, Vietnam, Pakistan, Sri Lanka — GDP growth % (latest annual), CPI inflation % (latest month), gross forex reserves USD billion, current account balance % GDP, sovereign credit rating (S&P or Fitch).
26. Headlines are pre-scraped — DO NOT search for headlines. They will be injected into your JSON automatically.

Return ONLY this JSON structure. ALL values below are PLACEHOLDERS — replace with actual searched data. Use null for any value not found:
{{
  "gather_date": "{today_search}",
  "cpi_headline_pct": null,     "cpi_headline_month": null,
  "cpi_food_pct": null,         "cpi_food_month": null,
  "bb_policy_rate_pct": null,   "sdf_rate_pct": null,  "slf_rate_pct": null,
  "mpc_note": null,  "mpc_next_date": null,
  "gdp_growth_pct": null,  "gdp_year": null,
  "credit_growth_pct": null,
  "dsex": null,  "dsex_date": null,  "ds30": null,  "cscx": null,
  "dse_turnover_cr": null,
  "dse_change_pts": null,  "dse_change_pct": null,
  "dse_52wk_high": null,  "dse_52wk_low": null,
  "news_dse": [],
  "tbill_91d_pct": null,  "tbill_182d_pct": null,  "tbill_364d_pct": null,
  "tbill_auction_label": null,  "tbill_auction_date": null,
  "tbill_new_auction": false,
  "bond_10y_pct": null,  "bond_5y_pct": null,
  "news_tbill": [],
  "gold_22k_bdt": null,
  "brent_usd": null,  "wti_usd": null,  "natgas_usd": null,  "lng_spot_usd": null,
  "lng_history": [],
  "news_commodity": [],
  "usd_bdt": null,  "eur_bdt": null,  "gbp_bdt": null,
  "forex_reserves_bn": null,  "forex_reserves_date": null,
  "exports_mn": null,  "rmg_exports_mn": null,  "exports_month": null,
  "imports_mn": null,  "trade_deficit_mn": null,  "trade_deficit_yoy_pct": null,
  "news_forex": [],
  "remittance_mn": null,  "remittance_month": null,
  "remittance_yoy_pct": null,
  "remittance_partial_mn": null,  "remittance_partial_period": null,
  "news_remittance": [],
  "npl_ratio_pct": null,  "car_pct": null,
  "news_banking": [],
  "brent_spot": null,
  "news_iranwar": [],

  "dam_week_ending": null,
  "dam_rice_coarse": null,  "dam_rice_fine": null,
  "dam_lentil": null,       "dam_oil": null,
  "dam_sugar": null,        "dam_onion": null,
  "dam_egg": null,          "dam_chicken": null,  "dam_flour": null,

  "rmg_exports_latest_mn": null,  "rmg_exports_latest_yoy_pct": null,
  "rmg_exports_latest_month": null,
  "rmg_ytd_bn": null,  "rmg_ytd_yoy_pct": null,
  "rmg_eu_pct": null,  "rmg_us_pct": null,  "rmg_uk_pct": null,
  "rmg_canada_pct": null,  "rmg_others_pct": null,
  "rmg_pipeline": null,
  "news_rmg": [],

  "fiscal_period": null,
  "nbr_collected_trillion": null,  "nbr_target_trillion": null,
  "nbr_progress_pct": null,
  "adp_pct": null,  "adp_spent_crore": null,  "adp_target_crore": null,
  "govt_borrow_trillion": null,  "govt_borrow_pct": null,
  "govt_borrow_ceiling_trillion": null,
  "news_fiscal": [],

  "nbr_vat_bn": null,      "nbr_vat_share_pct": null,   "nbr_vat_yoy_pct": null,
  "nbr_it_bn": null,       "nbr_it_share_pct": null,    "nbr_it_yoy_pct": null,
  "nbr_customs_bn": null,  "nbr_customs_share_pct": null, "nbr_customs_yoy_pct": null,
  "nbr_shortfall_bn": null, "nbr_needed_5mo_trillion": null,

  "power_gen_mw": null,  "power_demand_mw": null,  "power_shortage_mw": null,
  "power_shedding_rural": null,  "power_shedding_urban": null,
  "power_lng_mmbtu": null,
  "news_power": [],

  "peers_in_gdp": null,   "peers_in_cpi": null,   "peers_in_fxr": null,  "peers_in_cab": null,  "peers_in_rating": null,
  "peers_vn_gdp": null,   "peers_vn_cpi": null,   "peers_vn_fxr": null,  "peers_vn_cab": null,  "peers_vn_rating": null,
  "peers_pk_gdp": null,   "peers_pk_cpi": null,   "peers_pk_fxr": null,  "peers_pk_cab": null,  "peers_pk_rating": null,
  "peers_lk_gdp": null,   "peers_lk_cpi": null,   "peers_lk_fxr": null,  "peers_lk_cab": null,  "peers_lk_rating": null,

  "headlines": "PRE_SCRAPED_PLACEHOLDER"
}}"""

    print("Phase 1: Gathering latest Bangladesh data via web search...")
    gather_resp = _stream_call(
        client,
        messages=[{"role": "user", "content": GATHER_PROMPT}],
        tools=WEB_SEARCH_TOOL,
        max_tokens=6000,
        label="Phase 1 (data gather)",
    )

    gathered_json = "{}"
    last_text = None
    for block in gather_resp.content:
        if block.type == "text" and block.text.strip():
            last_text = block.text
    if last_text:
        text = last_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        text = text.strip()
        _j_start = text.find('{')
        if _j_start > 0:
            text = text[_j_start:]
        gathered_json = text.strip()
        try:
            json.loads(gathered_json)
        except json.JSONDecodeError:
            _repaired = False
            _attempt = gathered_json
            for _ in range(200):
                _last_nl = _attempt.rfind('\n')
                if _last_nl <= 0:
                    break
                _attempt = _attempt[:_last_nl].rstrip().rstrip(',')
                for _suffix in ['}', ']}', '"]}', '"}]}', '"}', '"]}']:
                    try:
                        json.loads(_attempt + _suffix)
                        gathered_json = _attempt + _suffix
                        _repaired = True
                        print(f"  JSON repaired (trimmed {len(text) - len(gathered_json)} chars)")
                        break
                    except json.JSONDecodeError:
                        continue
                if _repaired:
                    break
            if not _repaired:
                print("  WARNING: Could not repair truncated JSON — Phase 2 may have incomplete data")

    # ── Trim gathered_json to fit Phase 2 token budget ────────────────────
    _MAX_JSON = 16500
    if len(gathered_json) > _MAX_JSON:
        print(f"Gathered JSON ({len(gathered_json):,} chars) exceeds budget ({_MAX_JSON:,}). Trimming...")
        try:
            _gd = json.loads(gathered_json)
            for _k, _v in list(_gd.items()):
                if _k.startswith('news_') and isinstance(_v, list):
                    _gd[_k] = [str(x)[:100] for x in _v[:2]]
                elif _k == 'headlines' and isinstance(_v, list):
                    _gd[_k] = _v[:12]
                elif _k == 'opeds' and isinstance(_v, list):
                    for _op in _v:
                        if isinstance(_op, dict) and 'summary' in _op:
                            _op['summary'] = _op['summary'][:80]
                elif isinstance(_v, str) and len(_v) > 100:
                    _gd[_k] = _v[:100]
            gathered_json = json.dumps(_gd, ensure_ascii=False)
            print(f"  Trimmed to {len(gathered_json):,} chars.")
        except Exception as _e:
            print(f"  Smart trim failed ({_e}). Hard-capping at {_MAX_JSON:,} chars.")
            gathered_json = gathered_json[:_MAX_JSON]

    # ── Inject scraped headlines into gathered JSON ───────────────────────
    try:
        _json_start = gathered_json.find('{')
        _json_end = gathered_json.rfind('}')
        _parseable = gathered_json[_json_start:_json_end+1] if _json_start >= 0 and _json_end > _json_start else gathered_json
        _gf = json.loads(_parseable)
        _gf['headlines'] = _scraped_headlines
        if 'opeds' in _gf:
            del _gf['opeds']
        gathered_json = json.dumps(_gf, ensure_ascii=False)
        print(f"  Injected {len(_scraped_headlines)} scraped headlines into gathered JSON")
    except Exception as _e:
        print(f"  Headline injection failed: {_e}")

    print(f"Gathered data: {len(gathered_json):,} chars")
    return gathered_json


def phase2_generate_html(client, gathered_json, prompt_html, current_html, saved_parts):
    """Phase 2: Generate updated HTML using gathered data. Returns updated_html."""
    _p2_est = len(prompt_html) + len(gathered_json) + 2500
    print(f"Phase 2 est: {_p2_est:,} chars (~{int(_p2_est/2.6):,} tok @2.6 ch/tok)")

    print("Cooling down 10s between phases...")
    time.sleep(10)

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
  // [TBILLCHART_RENDER_PLACEHOLDER — restored automatically]
  // [OILCHART_RENDER_PLACEHOLDER — restored automatically]
  // [DSEXCHART_PLACEHOLDER — restored automatically]
  // [TARIFF_RENDER_PLACEHOLDER — restored automatically]
  // [TRADE_RENDER_PLACEHOLDER — restored automatically]
  // [APP_PLACEHOLDER — restored automatically]
  // [SECTIONRMG_PLACEHOLDER — restored automatically]
  // [SECTIONFISCAL_PLACEHOLDER — restored automatically]
  // [SECTIONNBR_PLACEHOLDER — restored automatically]
  // [SECTIONPOWER_PLACEHOLDER — restored automatically]
  // [SECTIONPEERS_PLACEHOLDER — restored automatically]

UPDATE RULES (use gathered JSON keys by exact name):
HEADER: BRIEF_DATE = "{today}"
SectionBB: bb_policy_rate_pct sdf_rate_pct slf_rate_pct gdp_growth_pct credit_growth_pct forex_reserves_bn cpi_headline_pct remittance_mn news_banking
SectionMacro: cpi_headline_pct/_month cpi_food_pct/_month bb_policy_rate_pct sdf_rate_pct slf_rate_pct mpc_note
SectionDSE: all dse_* + news_dse (DSEXChart is PLACEHOLDER-restored — pass its placeholder through unchanged)
TBillChart: tbill_new_auction→drop[0]+append new yields; else update last entry. SectionTBond: tbill_91d/182d/364d bond_10y/5y tbill_auction_date news_tbill
SectionComm: gold_22k_bdt brent_usd wti_usd natgas_usd lng_spot_usd news_commodity. The OilChart in SectionComm has been REPLACED with LNGChart — do NOT add OilChart here (it lives in SectionIranWar only). Keep the existing LNGChart component as-is.
SectionFX: usd/eur/gbp_bdt forex_reserves_bn exports/rmg_exports_mn exports_month imports_mn trade_deficit_mn/_yoy_pct news_forex
SectionRemittance: remittance_mn/_month/_yoy_pct news_remittance
SectionBanking: npl_ratio_pct car_pct news_banking
OilChart: remove old today:true, append{{label:"{chart_label}",value:brent_spot,today:true}}, >12→drop oldest. SectionIranWar: brent_spot news_iranwar
SectionExec: WRITE 6-8 single-line headlines (max 15 words each). Each object: {{type, indicator, text, section}}. Types/indicators: bull="▲", bear="▼", warn="⚠", watch="→". `section` = anchor ID of the relevant section below (bb, macro, dse, tbond, comm, fx, remit, banking, iranwar, headlines, dam). Cover the day's most important signals: reserves, exports, oil/geopolitics, market/rates, policy, outlook. NO paragraphs — each `text` must be one punchy headline sentence, max 15 words. Update events calendar. trafficStatus(bull/bear/warn/neu).
SectionHeadlines: The template has an EMPTY headline array (const headlines = [];). You MUST populate it EXCLUSIVELY from the gathered data JSON "headlines" array. The OP-ED SECTION IS REMOVED — keep const opeds = [] and do NOT render any op-ed cards or op-ed section header. CRITICAL RULES: (1) ONLY use headlines from the gathered data JSON — do NOT invent, fabricate, or recall headlines from memory or prior knowledge. (2) If the gathered "headlines" array is EMPTY ([]), keep const headlines = [] and show a note "No headlines available for {today}" instead of cards. (3) Every headline `time` field MUST exactly match the `date` field from gathered data — do NOT change dates. (4) Every headline `url` MUST exactly match the `url` from gathered data — do NOT invent URLs. (5) NEVER carry over or preserve old headlines from any previous version — the template arrays are intentionally empty. Source tags: DS=Daily Star, FE=Financial Express BD, TBS=TBS News, NEWAGE=New Age, FT=Financial Times, BBC=BBC, REUTERS=Reuters, AJ=Al Jazeera, BSS=BSS News, NYT=NY Times, WAPO=Washington Post, PRINT=The Print, STATESMAN=The Statesman. Each headline object: {{title, url, source, time}}. Add sourceColors/sourceNames entries for any new source codes used. BankerRead: summarize what the headlines collectively signal for the bank's risk posture.
SectionDAM: all 9 dam_* prices; MoM bear=up/bull=down/neu=flat; hotspotLabel(rising items)·hotspotStat("N of 9 rising MoM")·hotspotDetail(pct changes); easingLabel/Stat/Detail(falling); freshDate/sourceDate=dam_week_ending; news; trafficStatus(warn≥4rising,bull=majority falling).
NOTE: DSEXChart/SectionRMG/SectionFiscal/SectionNBR/SectionPower/SectionPeers are PLACEHOLDER-restored — do NOT write them; pass their placeholders through EXACTLY as shown above.
BankerRead: Each section has <BankerRead insight="..." /> — the insight props are BLANK (stripped). Write a PLACEHOLDER insight (1 short sentence is fine) — a post-processing Phase 3 will regenerate all insights with fresh analysis. Do NOT spend tokens writing detailed insights here.

JSX SYNTAX: Use EQUALS for JSX component props: <MetricCard value="10%" label="Rate" /> — NEVER use colons for JSX props. Colons are ONLY for JS object literals inside {{ }}.
OUTPUT: First character must be '<'. Start immediately with <!DOCTYPE html>. No preamble. End with </html>."""

    print("Phase 2: Generating updated HTML (no web search)...")
    response = _stream_call(
        client,
        messages=[{"role": "user", "content": UPDATE_PROMPT}],
        tools=[],
        max_tokens=64000,
        label="Phase 2 (HTML generation)",
    )

    updated_html = _extract_html(response)

    if not updated_html:
        print("ERROR: Phase 2 did not return valid HTML. Response blocks:")
        for i, block in enumerate(response.content):
            btype = getattr(block, "type", "?")
            btext = getattr(block, "text", "")[:300] if btype == "text" else ""
            print(f"  [{i}] type={btype} {btext!r}")
        sys.exit(1)

    # ── Restore <head> block ──────────────────────────────────────────────
    _head_block = saved_parts['head_block']
    if _head_block and "HEAD_PLACEHOLDER" in updated_html:
        updated_html = updated_html.replace(
            "<head><!-- HEAD_PLACEHOLDER — restored automatically --></head>",
            _head_block, 1)
        print("Head block restored.")
    elif _head_block:
        _hm = re.search(r'<head>.*?</head>', updated_html, re.DOTALL)
        if _hm:
            updated_html = updated_html[:_hm.start()] + _head_block + updated_html[_hm.end():]
            print("Head block fallback-restored (placeholder missing).")
        else:
            print("Warning: could not restore <head> block.")

    # ── Restore CSS block ─────────────────────────────────────────────────
    _css_block = saved_parts['css_block']
    _css_placeholder = saved_parts['css_placeholder']
    if _css_block and "CSS_PLACEHOLDER" in updated_html:
        updated_html = updated_html.replace(_css_placeholder, _css_block, 1)
        print("CSS block restored.")
    elif _css_block:
        print("Warning: CSS placeholder not found in Claude's output — CSS may be missing.")

    # ── Restore JS render sections ────────────────────────────────────────
    _js_parts = saved_parts['js_parts']
    for _js_key, _js_content in _js_parts.items():
        _js_ph = f'// [{_js_key} — restored automatically]'
        if _js_ph in updated_html:
            updated_html = updated_html.replace(_js_ph, _js_content, 1)
            print(f"  {_js_key} restored.")
        else:
            print(f"Warning: {_js_key} placeholder missing from Claude's output — "
                  f"restoring from original HTML as fallback.")
            anchor_map = {
                'COMPONENTS_PLACEHOLDER':       ('// ── Components',      '// ── Sections'),
                'TBILLCHART_RENDER_PLACEHOLDER': ('function TBillChart()', 'function SectionTBond()'),
                'OILCHART_RENDER_PLACEHOLDER':   ('function OilChart()',   'function SectionIranWar()'),
                'TARIFF_RENDER_PLACEHOLDER':     ('function SectionTariff()', 'function SectionTrade()'),
                'TRADE_RENDER_PLACEHOLDER':      ('function SectionTrade()', 'function SectionIranWar()'),
                'APP_PLACEHOLDER':               ('// ── Main App',          '</script>'),
            }
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

    # ── Restore non-daily section functions ────────────────────────────────
    _slow_saved = saved_parts['slow_saved']
    _slow_originals = saved_parts['slow_originals']
    for _sname, _fn_body in _slow_saved.items():
        _sph = f'// [{_sname.upper()}_PLACEHOLDER — restored automatically]'
        _restore_body = _slow_originals.get(_sname, _fn_body)
        if _sph in updated_html:
            updated_html = updated_html.replace(_sph, _restore_body, 1)
            print(f"  {_sname} restored.")
        else:
            print(f"Warning: {_sname} placeholder missing — restoring from original HTML.")
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

    # ── Hard-validate slow sections ───────────────────────────────────────
    for _sname in _SLOW_SECTIONS:
        _original = _slow_originals.get(_sname) or _slow_saved.get(_sname, '')
        if not _original:
            continue

        _dupes = list(re.finditer(r'function ' + re.escape(_sname) + r'\s*\(\s*\)', updated_html))
        for _dup in reversed(_dupes[:-1]):
            _db = updated_html.find('{', _dup.end())
            if _db != -1:
                _de = _brace_end(updated_html, _db)
                if 'return (' not in updated_html[_db:_de + 1]:
                    updated_html = updated_html[:_dup.start()] + updated_html[_de + 1:]
                    print(f"  {_sname}: removed Claude-generated stub.")

        _fm2 = re.search(r'function ' + re.escape(_sname) + r'\s*\(\s*\)', updated_html)
        if _fm2:
            _fb2 = updated_html.find('{', _fm2.end())
            if _fb2 != -1:
                _fe2 = _brace_end(updated_html, _fb2)
                if 'return (' not in updated_html[_fb2:_fe2 + 1]:
                    updated_html = updated_html[:_fm2.start()] + _original + updated_html[_fe2 + 1:]
                    print(f"  {_sname}: force-replaced (no return statement) from original.")
        else:
            _app_pos = updated_html.find('function App()')
            if _app_pos != -1:
                updated_html = updated_html[:_app_pos] + _original + '\n\n' + updated_html[_app_pos:]
                print(f"  {_sname}: injected from original (was missing entirely).")

        _sph2 = f'// [{_sname.upper()}_PLACEHOLDER — restored automatically]'
        if _sph2 in updated_html:
            updated_html = updated_html.replace(_sph2, '', 1)
            print(f"  {_sname}: removed orphaned placeholder comment.")

    # ── Final dedup ───────────────────────────────────────────────────────
    for _sname in _SLOW_SECTIONS:
        _dups = list(re.finditer(r'function ' + re.escape(_sname) + r'\s*\(\s*\)', updated_html))
        if len(_dups) > 1:
            for _dup in reversed(_dups[1:]):
                _db = updated_html.find('{', _dup.end())
                if _db != -1:
                    _de = _brace_end(updated_html, _db)
                    if _de != -1:
                        updated_html = updated_html[:_dup.start()] + updated_html[_de + 1:]
                        print(f"  {_sname}: removed duplicate definition (kept first).")

    # ── Hard enforce headlines ────────────────────────────────────────────
    try:
        _gf = json.loads(gathered_json)
        _today_headlines = _gf.get('headlines', [])

        def _js_headline_array(items):
            if not items:
                return '[]'
            parts = []
            for h in items:
                t = h.get('title', '').replace('"', '\\"').replace('\n', ' ')
                u = h.get('url', '').replace('"', '\\"')
                s = h.get('source', 'NEWS')
                d = h.get('date', today_short)
                parts.append(f'    {{ title: "{t}", url: "{u}", source: "{s}", time: "{d}" }}')
            return '[\n' + ',\n'.join(parts) + '\n  ]'

        _hl_re = re.sub(
            r'(const headlines\s*=\s*)\[.*?\];',
            lambda m: m.group(1) + _js_headline_array(_today_headlines) + ';',
            updated_html, count=1, flags=re.DOTALL)
        if _hl_re != updated_html:
            updated_html = _hl_re
            print(f"Headlines hard-enforced: {len(_today_headlines)} items from gathered data.")
        _op_re = re.sub(
            r'(const opeds\s*=\s*)\[.*?\];',
            r'\1[];',
            updated_html, count=1, flags=re.DOTALL)
        if _op_re != updated_html:
            updated_html = _op_re
            print("Op-eds cleared (section removed).")
    except Exception as _e:
        print(f"Warning: headline hard-enforcement failed: {_e}")

    return updated_html


def phase3_regenerate_insights(client, updated_html, gathered_json):
    """Phase 3: Regenerate all BankerRead insights. Returns final_html."""
    print("\nPhase 3: Regenerating all BankerRead insights...")

    _br_matches = list(re.finditer(
        r'(<BankerRead\s+insight=")([^"]*?)("\s*/>)',
        updated_html
    ))
    print(f"  Found {len(_br_matches)} BankerRead insights to regenerate.")

    if not _br_matches:
        return updated_html

    _br_sections = []
    for _brm in _br_matches:
        _pos = _brm.start()
        _fns = list(re.finditer(r'function (Section\w+|App)\s*\(', updated_html[:_pos]))
        _section_name = _fns[-1].group(1) if _fns else "Unknown"
        _br_sections.append(_section_name)

    _br_list = "\n".join(
        f"{i+1}. [{_br_sections[i]}] (old insight omitted — write fresh)"
        for i in range(len(_br_matches))
    )

    _P3_PROMPT = f"""Today is {today} (UTC+6 = BDT). Regenerate ALL {len(_br_matches)} BankerRead insights using ONLY the data below.

GATHERED DATA:
<data>
{gathered_json}
</data>

SECTIONS (in order):
{_br_list}

RULES:
- Each insight: exactly 4 sentences.
  (1) What today's data means for the bank's book
  (2) A specific actionable step with a named exposure type or threshold
  (3) One forward trigger to watch with a specific metric and threshold
  (4) What business strategy to pursue or focus
- Tone: direct, specific, no hedging. Style of Ray Dalio / Gita Gopinath / Raghuram Rajan.
- Cite actual numbers from the gathered data. Never use generic phrases like "monitor closely" without specifying what metric and what threshold.
- Target reader: CFO, CRO, SME Banking head, corporate banking head, retail banking head, or treasury head reading at early morning.
- CRITICAL: Each insight MUST reference today's date context ({today}) — what makes TODAY different from yesterday. Even if the raw numbers are the same, the countdown to key events (MPC meeting, Eid, CPI release, IMF review) changes daily. Frame urgency relative to today.
- Use different angles for each section — do NOT repeat the same Brent/CPI/remittance framing across sections. Each section's insight should focus on that section's specific domain.
- Do NOT use double quotes inside the insight text (it breaks JSX). Use single quotes or no quotes.

OUTPUT: Return ONLY a JSON array of {len(_br_matches)} strings, one per BankerRead in order. No markdown, no explanation.
Example: ["insight 1 text...", "insight 2 text...", ...]"""

    print("  Cooling down 10s before Phase 3...")
    time.sleep(10)

    _p3_resp = _stream_call(
        client,
        messages=[{"role": "user", "content": _P3_PROMPT}],
        tools=[],
        max_tokens=16000,
        label="Phase 3 (BankerRead regeneration)",
    )

    _p3_text = ""
    for block in _p3_resp.content:
        if block.type == "text" and block.text.strip():
            _p3_text = block.text.strip()

    if _p3_text.startswith("```"):
        _p3_lines = _p3_text.split("\n")
        _p3_text = "\n".join(_p3_lines[1:-1]) if _p3_lines[-1].strip() == "```" else "\n".join(_p3_lines[1:])
        _p3_text = _p3_text.strip()

    _j_start = _p3_text.find('[')
    if _j_start >= 0:
        _p3_text = _p3_text[_j_start:]

    try:
        _new_insights = json.loads(_p3_text)
        if isinstance(_new_insights, list) and len(_new_insights) == len(_br_matches):
            for i in reversed(range(len(_br_matches))):
                _brm = _br_matches[i]
                _new_insight = str(_new_insights[i]).replace('"', "'")
                updated_html = (
                    updated_html[:_brm.start(2)] +
                    _new_insight +
                    updated_html[_brm.end(2):]
                )
            print(f"  All {len(_new_insights)} BankerRead insights regenerated successfully.")
        else:
            _got = len(_new_insights) if isinstance(_new_insights, list) else "not a list"
            print(f"  WARNING: Phase 3 returned {_got} insights (expected {len(_br_matches)}) — keeping old insights.")
    except json.JSONDecodeError as _e:
        print(f"  WARNING: Phase 3 JSON parse failed ({_e}) — keeping old insights.")
        _repaired_p3 = False
        _attempt_p3 = _p3_text
        for _ in range(100):
            _last_nl = _attempt_p3.rfind('\n')
            if _last_nl <= 0:
                break
            _attempt_p3 = _attempt_p3[:_last_nl].rstrip().rstrip(',')
            for _suffix in [']', '"]', '"]']:
                try:
                    _new_insights = json.loads(_attempt_p3 + _suffix)
                    if isinstance(_new_insights, list) and len(_new_insights) == len(_br_matches):
                        for i in reversed(range(len(_br_matches))):
                            _brm = _br_matches[i]
                            _new_insight = str(_new_insights[i]).replace('"', "'")
                            updated_html = (
                                updated_html[:_brm.start(2)] +
                                _new_insight +
                                updated_html[_brm.end(2):]
                            )
                        print(f"  JSON repaired — {len(_new_insights)} BankerRead insights regenerated.")
                        _repaired_p3 = True
                        break
                except json.JSONDecodeError:
                    continue
            if _repaired_p3:
                break
        if not _repaired_p3:
            print("  Could not repair Phase 3 JSON — old insights preserved.")

    return updated_html


def run_sanity_checks(updated_html, current_html, saved_parts):
    """Run post-restoration sanity checks. Returns validated html (may roll back)."""
    _js_parts = saved_parts['js_parts']
    _sanity_ok = True

    # 1. ReactDOM call must be present
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

    # 2. No orphaned placeholder comments
    _orphaned = [k for k in _js_parts if f'// [{k} — restored automatically]' in updated_html]
    for _k in _orphaned:
        print(f"⚠️  Sanity: orphaned placeholder {_k} still in output — removing stale comment.")
        updated_html = updated_html.replace(f'  // [{_k} — restored automatically]', '', 1)
        updated_html = updated_html.replace(f'// [{_k} — restored automatically]', '', 1)
        _sanity_ok = False

    # 3. Fix stray "} />" in JSX self-closing tags
    _stray_count = updated_html.count('" } />')
    if _stray_count:
        updated_html = updated_html.replace('" } />', '" />')
        print(f"⚠️  Sanity: fixed {_stray_count} stray '}}' in JSX self-closing tags.")
        _sanity_ok = False

    # 4. Truncate after first </html>
    _first_html_close = updated_html.find('</html>')
    if _first_html_close != -1:
        _after = updated_html[_first_html_close + len('</html>'):].strip()
        if _after:
            print(f"⚠️  Sanity: {len(_after)} chars of orphaned content after first </html> — truncating.")
            updated_html = updated_html[:_first_html_close + len('</html>')] + '\n'
            _sanity_ok = False

    # 4b. File must end with </html>
    if not updated_html.rstrip().endswith('</html>'):
        print("⚠️  Sanity: file does not end with </html> — aborting write, keeping original.")
        updated_html = current_html
        _sanity_ok = False

    # 5. JSX syntax validation
    _script_m = re.search(r'<script[^>]*type="text/babel"[^>]*>(.*?)</script>', updated_html, re.DOTALL)
    _jsx_errors = []
    if _script_m:
        _jsx_src = _script_m.group(1)
        _between_fns = re.findall(r'\)\s*;\s*\n\s*(</(?:svg|div|span|section)>)', _jsx_src)
        if _between_fns:
            _jsx_errors.append(f"{len(_between_fns)} orphaned closing tag(s) between functions")
        _colon_props_re = r'\b(value|label|change|sub|insight|detail|num|title|icon):\s*"'
        _colon_fix_count = 0
        _fixed_lines = []
        for _line in _jsx_src.split('\n'):
            _stripped = _line.lstrip()
            _is_jsx_tag = ((_stripped.startswith('<') and not _stripped.startswith('</') and not _stripped.startswith('<!--'))
                           or _stripped.endswith('/>')
                           or _stripped.endswith('>')) \
                          and not _stripped.startswith('{') and not _stripped.startswith('//')
            _is_obj_literal = '{ name:' in _line or '{ id:' in _line or _stripped.startswith('{') \
                              or 'const ' in _line or re.match(r'^\s*\{', _line)
            if _is_jsx_tag and not _is_obj_literal:
                _new_line, _n = re.subn(_colon_props_re, lambda m: m.group(1) + '="', _line)
                if _n:
                    _colon_fix_count += _n
                    _line = _new_line
            _fixed_lines.append(_line)
        if _colon_fix_count:
            _jsx_src = '\n'.join(_fixed_lines)
            _script_start = _script_m.start(1)
            _script_end = _script_m.end(1)
            updated_html = updated_html[:_script_start] + _jsx_src + updated_html[_script_end:]
            print(f"⚠️  Sanity: auto-fixed {_colon_fix_count} colon-instead-of-equals in JSX props.")
            _sanity_ok = False
        _frags_open = len(re.findall(r'(?<!\w)<>(?!\s*$)', _jsx_src))
        _frags_close = len(re.findall(r'</>', _jsx_src))
        if _frags_open != _frags_close:
            _jsx_errors.append(f"mismatched JSX fragments: {_frags_open} opens vs {_frags_close} closes")
    if _jsx_errors:
        print(f"⚠️  Sanity: JSX validation failed — falling back to original HTML:")
        for _je in _jsx_errors:
            print(f"    • {_je}")
        updated_html = current_html
        _sanity_ok = False

    # 6. File size sanity check
    input_size = len(current_html)
    output_size = len(updated_html)
    if input_size > 0:
        ratio = output_size / input_size
        if ratio < 0.5:
            print(f"⚠️  Sanity: output HTML is {ratio:.0%} of input size — too small, rolling back.")
            updated_html = current_html
            _sanity_ok = False
        elif ratio > 1.5:
            print(f"⚠️  Sanity: output HTML is {ratio:.0%} of input size — too large, rolling back.")
            updated_html = current_html
            _sanity_ok = False

    if _sanity_ok:
        print("Sanity check passed ✅")
    else:
        print("Sanity check applied fixes — review warnings above.")

    return updated_html


def update_chart_data(html, pattern, chart_label_str, new_value, max_entries, value_fmt='.2f', chart_name='chart', bounds_key=None, warnings=None):
    """Generic chart data updater. Returns updated html.

    Args:
        html: the full HTML string
        pattern: regex pattern with 3 groups: (prefix)(data_body)(suffix like '];')
        chart_label_str: label for today's entry (e.g. "Apr 10")
        new_value: numeric value for today
        max_entries: max data points to keep
        value_fmt: format spec for value (e.g. '.2f', 'd')
        chart_name: display name for logging
        bounds_key: key into CHART_BOUNDS for range check, or None
        warnings: list to append warning strings to
    """
    if warnings is None:
        warnings = []

    # Bounds check
    if bounds_key and bounds_key in CHART_BOUNDS:
        lo, hi = CHART_BOUNDS[bounds_key]
        if not (lo <= new_value <= hi):
            msg = f"Warning: {chart_name} value {new_value} out of bounds ({lo}-{hi}) — skipping update."
            print(msg)
            warnings.append(msg)
            return html

    _dm = re.search(pattern, html, re.DOTALL)
    if not _dm:
        print(f"Warning: {chart_name} data array pattern not found in output.")
        return html

    _data_body = _dm.group(2)
    _entries_raw = re.findall(r'\{([^}]+)\}', _data_body)
    _parsed_entries = []
    for _er in _entries_raw:
        _entry = {}
        _lm = re.search(r'label:\s*"([^"]+)"', _er)
        if _lm: _entry['label'] = _lm.group(1)
        _vm = re.search(r'value:\s*([\d.]+)', _er)
        if _vm:
            raw_val = _vm.group(1)
            _entry['value'] = int(raw_val) if '.' not in raw_val and value_fmt == 'd' else float(raw_val)
        if re.search(r'showLabel:\s*true', _er): _entry['showLabel'] = True
        if re.search(r'today:\s*true', _er): _entry['today'] = True
        _em = re.search(r'event:\s*"([^"]+)"', _er)
        if _em: _entry['event'] = _em.group(1)
        if 'label' in _entry and 'value' in _entry:
            _parsed_entries.append(_entry)

    if not _parsed_entries:
        print(f"Warning: could not parse {chart_name} data entries.")
        return html

    # Remove old today markers
    for _pe in _parsed_entries:
        _pe.pop('today', None)

    # Update or append today's value
    _today_found = False
    for _pe in _parsed_entries:
        if _pe.get('label') == chart_label_str:
            if value_fmt == 'd':
                _pe['value'] = int(round(new_value))
            else:
                _pe['value'] = new_value
            _pe['showLabel'] = True
            _pe['today'] = True
            _today_found = True
            break

    if not _today_found:
        entry = {
            'label': chart_label_str,
            'value': int(round(new_value)) if value_fmt == 'd' else new_value,
            'showLabel': True,
            'today': True,
        }
        _parsed_entries.append(entry)

    while len(_parsed_entries) > max_entries:
        _parsed_entries.pop(0)

    # Rebuild data string
    _lines = []
    for _pe in _parsed_entries:
        if value_fmt == 'd':
            _parts = [f'label: "{_pe["label"]}"', f'value: {int(_pe["value"])}']
        else:
            _parts = [f'label: "{_pe["label"]}"', f'value: {_pe["value"]}']
        if _pe.get('showLabel'): _parts.append('showLabel: true')
        if _pe.get('event'): _parts.append(f'event: "{_pe["event"]}"')
        if _pe.get('today'): _parts.append('today: true')
        _lines.append('    { ' + ', '.join(_parts) + ' }')
    _new_data = '\n' + ',\n'.join(_lines) + ',\n  '

    html = (
        html[:_dm.start(2)] +
        _new_data +
        html[_dm.end(2):]
    )
    if value_fmt == 'd':
        print(f"{chart_name} data updated: {len(_parsed_entries)} points, "
              f"today={chart_label_str} value={int(round(new_value))}")
    else:
        print(f"{chart_name} data updated: {len(_parsed_entries)} points, "
              f"today={chart_label_str} value={new_value}")

    return html


def _supabase_upsert(table, rows, on_conflict):
    """POST an array of rows to PostgREST as an upsert.
    Uses SUPABASE_SERVICE_ROLE_KEY (preferred) or falls back to SUPABASE_SERVICE_KEY.
    Returns True on success, False on failure (logged, non-fatal).
    """
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or SUPABASE_SVC_KEY
    if not key or not rows:
        return False
    import urllib.error, urllib.request as _ur
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table}?on_conflict={on_conflict}"
    data = json.dumps(rows).encode("utf-8")
    req = _ur.Request(
        url,
        data=data,
        method="POST",
        headers={
            "apikey":        key,
            "Authorization": f"Bearer {key}",
            "Content-Type":  "application/json",
            "Prefer":        "resolution=merge-duplicates,return=minimal",
        },
    )
    try:
        with _ur.urlopen(req, timeout=20) as resp:
            return resp.status in (200, 201, 204)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        print(f"Warning: Supabase upsert {table} HTTP {e.code}: {body}")
        return False
    except Exception as e:
        print(f"Warning: Supabase upsert {table} failed: {e}")
        return False


def update_charts_deterministic(html, gathered_json, warnings=None):
    """Deterministic post-processing: BRIEF_DATE + Supabase chart upserts.

    Chart data now lives in Supabase (tb_* tables), not inline HTML arrays.
    This function:
      - Updates BRIEF_DATE in the HTML (still inline text)
      - Writes today's DSEX / LNG values (from Claude's gathered_json) to
        Supabase, so the Supabase-backed chart components pick them up
        on the next page load.
      - Skips Brent entirely — ingest.py pulls real Brent futures from
        Yahoo Finance before this runs, which is authoritative.
    Returns updated html and list of charts updated.
    """
    if warnings is None:
        warnings = []
    charts_updated = []

    # ── 1. BRIEF_DATE — always set to today ───────────────────────────────
    _date_m = re.search(r'const BRIEF_DATE\s*=\s*"[^"]*"', html)
    if _date_m:
        html = html[:_date_m.start()] + f'const BRIEF_DATE = "{today}"' + html[_date_m.end():]
        print(f"BRIEF_DATE set to \"{today}\"")

    try:
        _gd = json.loads(gathered_json)
    except Exception:
        print("Warning: could not parse gathered_json for chart updates.")
        return html, charts_updated

    # ── 2. Write DSEX close to Supabase ───────────────────────────────────
    _dsex_val = _gd.get("dsex")
    if _dsex_val is not None:
        try:
            _dsex_val = int(round(float(str(_dsex_val).replace(",", ""))))
            lo, hi = CHART_BOUNDS.get("dsex", (1000, 10000))
            if lo <= _dsex_val <= hi:
                if _supabase_upsert(
                    "tb_dsex_daily",
                    [{"date": today_iso, "close": _dsex_val, "source": "claude-daily"}],
                    on_conflict="date",
                ):
                    print(f"DSEX upserted to Supabase: {today_iso}={_dsex_val}")
                    charts_updated.append("dsex")
            else:
                msg = f"Warning: DSEX {_dsex_val} out of bounds ({lo}-{hi}) — skipped."
                print(msg)
                warnings.append(msg)
        except Exception as _e:
            print(f"Warning: DSEX upsert failed ({_e}).")

    # ── 3. Write LNG JKM spot to Supabase ─────────────────────────────────
    _lng_val = _gd.get("lng_spot_usd")
    if _lng_val is not None:
        try:
            _lng_val = round(float(str(_lng_val).replace(",", "")), 2)
            lo, hi = CHART_BOUNDS.get("lng", (1, 100))
            if lo <= _lng_val <= hi:
                # Use the Monday of the current week as week_start
                from datetime import datetime as _dt, timedelta as _td
                _d = _dt.fromisoformat(today_iso)
                _monday = (_d - _td(days=_d.weekday())).date().isoformat()
                _label = _d.strftime("%b %-d")
                if _supabase_upsert(
                    "tb_lng_jkm_weekly",
                    [{
                        "week_start": _monday,
                        "label": _label,
                        "price_usd_mmbtu": _lng_val,
                        "source": "claude-daily",
                    }],
                    on_conflict="week_start",
                ):
                    print(f"LNG upserted to Supabase: {_monday}={_lng_val}")
                    charts_updated.append("lng")
            else:
                msg = f"Warning: LNG {_lng_val} out of bounds ({lo}-{hi}) — skipped."
                print(msg)
                warnings.append(msg)
        except Exception as _e:
            print(f"Warning: LNG upsert failed ({_e}).")

    return html, charts_updated


def compile_and_write(html):
    """Write final HTML to the-brief.html and index.html.

    Chart data lives in Supabase (tb_* tables) so there's nothing to
    inject here — chart components fetch their data on page load.
    """
    with open("the-brief.html", "w", encoding="utf-8") as f:
        f.write(html)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Done. Updated the-brief.html and index.html for {today}.")


def main():
    """Orchestrate the full update pipeline."""
    summary = {
        "date": today,
        "phase1": "skipped",
        "phase2": "skipped",
        "phase3": "skipped",
        "charts_updated": [],
        "emails_sent": 0,
        "emails_failed": 0,
        "warnings": [],
        "stale": False,
    }

    # ── Load and strip HTML ───────────────────────────────────────────────
    current_html, prompt_html, saved_parts = load_and_strip_html("the-brief.html")

    # ── API client ────────────────────────────────────────────────────────
    client = None
    if not args.dry_run:
        client = anthropic.Anthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            timeout=anthropic.Timeout(connect=10.0, read=1800.0, write=600.0, pool=1800.0),
        )

    # ── Phase 1: Gather data ──────────────────────────────────────────────
    gathered_json = "{}"
    _cache_file = "gathered_data.json"
    _cache_fresh = False

    if os.path.exists(_cache_file):
        _cache_age = time.time() - os.path.getmtime(_cache_file)
        if _cache_age < 3600:  # less than 1 hour old
            _cache_fresh = True
            print(f"Phase 1 cache found ({_cache_age:.0f}s old, <1hr).")

    if args.dry_run:
        if os.path.exists(_cache_file):
            with open(_cache_file, "r") as f:
                gathered_json = f.read()
            print(f"[DRY-RUN] Phase 1 skipped — loaded cached data from {_cache_file}")
            summary["phase1"] = "skipped"
        else:
            print("[DRY-RUN] Phase 1 skipped — no cached data available, using empty JSON.")
            summary["phase1"] = "skipped"
    elif _cache_fresh:
        with open(_cache_file, "r") as f:
            gathered_json = f.read()
        print(f"Phase 1 skipped — using fresh cache ({_cache_age:.0f}s old).")
        summary["phase1"] = "skipped"
    else:
        try:
            gathered_json = phase1_gather_data(client, prompt_html)
            summary["phase1"] = "ok"
            # Checkpoint: save gathered data
            with open(_cache_file, "w") as f:
                f.write(gathered_json)
            print(f"Phase 1 checkpoint saved to {_cache_file}")
        except Exception as e:
            print(f"ERROR: Phase 1 failed — {e}")
            summary["phase1"] = "failed"
            summary["warnings"].append(f"Phase 1 failed: {e}")
            print(json.dumps(summary, indent=2))
            sys.exit(1)

    # ── Phase 2: Generate updated HTML ────────────────────────────────────
    if args.dry_run:
        updated_html = current_html
        print("[DRY-RUN] Phase 2 skipped — using current HTML as-is.")
        summary["phase2"] = "skipped"
    else:
        try:
            updated_html = phase2_generate_html(client, gathered_json, prompt_html, current_html, saved_parts)
            summary["phase2"] = "ok"
        except Exception as e:
            print(f"ERROR: Phase 2 failed — {e}")
            summary["phase2"] = "failed"
            summary["warnings"].append(f"Phase 2 failed: {e}")
            print(json.dumps(summary, indent=2))
            sys.exit(1)

    # ── Sanity checks ─────────────────────────────────────────────────────
    updated_html = run_sanity_checks(updated_html, current_html, saved_parts)

    # ── Deterministic chart updates ───────────────────────────────────────
    updated_html, charts_updated = update_charts_deterministic(updated_html, gathered_json, summary["warnings"])
    summary["charts_updated"] = charts_updated

    # ── Stale data detection ──────────────────────────────────────────────
    is_stale = (updated_html == current_html)
    summary["stale"] = is_stale
    if is_stale:
        print("[STALE] No changes detected")

    # ── Phase 3: Regenerate insights ──────────────────────────────────────
    if args.dry_run:
        print("[DRY-RUN] Phase 3 skipped.")
        summary["phase3"] = "skipped"
    elif is_stale:
        print("Phase 3 skipped — content is stale/unchanged.")
        summary["phase3"] = "skipped"
    else:
        try:
            updated_html = phase3_regenerate_insights(client, updated_html, gathered_json)
            summary["phase3"] = "ok"
        except Exception as e:
            print(f"ERROR: Phase 3 failed — {e}")
            summary["phase3"] = "failed"
            summary["warnings"].append(f"Phase 3 failed: {e}")

    # ── Write output files ────────────────────────────────────────────────
    compile_and_write(updated_html)

    # ── Email subscribers ─────────────────────────────────────────────────
    if args.dry_run:
        print("[DRY-RUN] Email sending skipped.")
    elif is_stale:
        print("Email sending skipped — content is stale/unchanged.")
    else:
        print("Fetching subscribers...")
        subscribers = fetch_subscribers()
        if subscribers:
            print(f"Sending to {len(subscribers)} subscriber(s)...")
            sent, failed = send_emails(subscribers, today)
            summary["emails_sent"] = sent
            summary["emails_failed"] = failed
        else:
            print("No subscribers found — email step skipped.")

    # ── Execution summary ─────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("EXECUTION SUMMARY")
    print("=" * 60)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
