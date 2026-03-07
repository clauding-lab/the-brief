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

# ── Update prompt ──────────────────────────────────────────────────────────────
PROMPT = f"""You are updating THE BRIEF, a Bangladesh business intelligence single-page app.
Today's date is {today}.

NOTE: To stay within API token limits, rendering-only sections have been stripped
and replaced with placeholder comments. Your output MUST include ALL of these
placeholders EXACTLY as shown (they are restored automatically after generation):
  <style>/* CSS_PLACEHOLDER — restored automatically */</style>
  // [COMPONENTS_PLACEHOLDER — restored automatically]
  // [DSEXCHART_RENDER_PLACEHOLDER — restored automatically]
  // [TBILLCHART_RENDER_PLACEHOLDER — restored automatically]
  // [OILCHART_RENDER_PLACEHOLDER — restored automatically]
  // [APP_PLACEHOLDER — restored automatically]
Do NOT write any CSS or any React rendering/component code — only update data values.

Here is the current HTML file (rendering sections stripped to save tokens):

<current_file>
{prompt_html}
</current_file>

Perform ALL of the following update steps using web search to find the latest data.
Return ONLY the complete updated HTML — placeholders intact, no explanation, no markdown fences.

────────────────────────────────────────────────────────────────

STEP 1 — HEADER
Update the day/date string (e.g. "FRIDAY 06 MARCH 2026") to today's date.
Update the publish time to the current UTC time converted to BDT (UTC+6).

STEP 2 — §01 MACRO OVERVIEW
Search for latest: Bangladesh GDP growth (BBS/World Bank), CPI headline & food inflation (BBS),
private sector credit growth (BB), remittance (latest monthly, BB),
gross forex reserves (BB BPM6 basis), trade deficit.
Update TickerStrip, MetricCard values/change/sub text, and NewsItem headlines + details.

STEP 3 — §02 INFLATION & MONETARY POLICY
Search for: latest CPI headline and food inflation (BBS), BB policy rate (any change?),
SDF/SLF corridor rates, any MPC meeting outcome or statement.
Update ticker, metric cards, and news items.

STEP 4 — §03 DHAKA STOCK EXCHANGE — DSEX Chart
The DSEXChart has 20 daily data points. Update as follows:
- Drop the oldest data point (index 0)
- Add today's DSEX closing value as the new last entry with {{ today: true }}
- Remove the {{ today: true }} flag from the previous last point
- Add/update event annotations for any new significant event (crash, rally, election)

ANNOTATION RULES (CRITICAL):
- BULL annotations (rallies/highs): box at y = pad.top - 40, dashed line goes DOWN to dot
- BEAR annotations (crashes/lows): box at y = cy(data[idx].value) + 19, INSIDE chart, NEVER below x-axis

Also update: FLASH banner (if major event), ticker strip values (DSEX pts, DS30, CSCX, TURNOVER, 52-WK RANGE).

STEP 5 — §04 TREASURY BILLS & BOND MARKET — T-Bill Chart
The TBillChart shows 5 auction data points for 3 tenors (91d, 182d, 364d).
Check bb.org.bd/monetaryactivity/treasury for the latest primary auction cut-off yields.
If a new auction has been held, drop the oldest point and add the new one to all three arrays and the labels array.
Update the PEAK annotation (pkI index, value, label) if a new peak has been set.
Update the BELOW POLICY RATE annotation text if the situation has changed.
Update TickerStrip and MetricCard values (10Y/5Y bond yields, last auction date).
Update NewsItems if there is new bond market news.

STEP 6 — §05 COMMODITY PRICING
Search for latest: BAJUS gold price 22K/bhori (bajus.org or local news),
Brent crude spot, WTI crude spot, natural gas (Henry Hub).
Update ticker, metric cards (value, change, sub), and news items.

STEP 7 — §06 TRADE & FOREX
Search for latest: USD/BDT BB reference rate, EUR/BDT, GBP/BDT,
monthly export figures (EPB) — RMG vs total, import figures / trade deficit.
Update ticker strip, metric cards, and news items.

STEP 8 — §07 REMITTANCE
Search for: latest monthly remittance inflow (BB), YoY % change,
top source countries / channels (banking vs hundi narrative).
Update MetricCards and NewsItems.

STEP 9 — §08 BANKING SECTOR
Search for: NPL ratio (BB), capital adequacy ratio,
any bank-specific news (scam, restructuring, merger), BB regulatory actions.
Update MetricCards and NewsItems.

STEP 10 — §09 US-IRAN WAR IMPACT — Oil Chart
The OilChart shows Brent crude for the last 6 months.
If significant price movement has occurred:
- Update the STATIC_DATA array: add a new daily data point with today's date,
  drop the oldest point if needed to keep the chart at ~8-12 data points
- Keep the {{ event: true }} flag on the Feb 28 Op. Epic Fury trigger point
- Keep {{ today: true }} only on the last point
Also update: ticker strip (Brent spot), MetricCard values, NewsItems with latest developments.

STEP 11 — FINAL CHECKS
- Ensure no change= text references a stale date
- Confirm pill= labels are still accurate (e.g. "RISING" vs "FALLING")
- Do not change any CSS, component structure, or layout — only data values and text content

════════════════════════════════════════════════════════════════
CRITICAL OUTPUT RULE — THIS OVERRIDES EVERYTHING ELSE:

After your final web search, your VERY NEXT output MUST be the
complete updated HTML file. Do NOT write:
  • "Now I have all the data I need..."
  • "Let me compile the updated HTML..."
  • "Key findings:" or ANY bullet-point summary of what you found
  • ANY words, sentences, or characters before <!DOCTYPE html>

Your response after the last search tool call must begin EXACTLY:
<!DOCTYPE html>
...and end with </html>. Nothing before it. Nothing after it.
The HTML IS your answer — there is no need to explain it first.
════════════════════════════════════════════════════════════════
"""

# ── Call Claude API ────────────────────────────────────────────────────────────
# Timeout: 30 min read/pool to cover 20 web searches + large token generation
client = anthropic.Anthropic(
    api_key=os.environ["ANTHROPIC_API_KEY"],
    timeout=anthropic.Timeout(connect=10.0, read=1800.0, write=600.0, pool=1800.0),
)

print("Calling Claude API with web search...")
t0 = time.time()

MAX_RETRIES = 3
for attempt in range(1, MAX_RETRIES + 1):
    try:
        # Use streaming to avoid SDK's 10-minute non-streaming limit with large max_tokens
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=64000,           # Raised from 32k: search results + full HTML easily exceed 32k
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 20}],
            messages=[{"role": "user", "content": PROMPT}],
        ) as stream:
            response = stream.get_final_message()
        break   # success — exit retry loop
    except anthropic.RateLimitError as e:
        wait = 65 * attempt      # 65s, 130s, 195s
        print(f"Rate limit hit (attempt {attempt}/{MAX_RETRIES}). Waiting {wait}s... ({e})")
        if attempt == MAX_RETRIES:
            print("ERROR: Max retries exceeded.")
            sys.exit(1)
        time.sleep(wait)
    except Exception as e:
        print(f"ERROR: Claude API call failed after {time.time()-t0:.0f}s — {type(e).__name__}: {e}")
        sys.exit(1)

print(f"Claude API call completed in {time.time()-t0:.0f}s. Stop reason: {response.stop_reason}")

# ── Extract the HTML from the response ────────────────────────────────────────
# Claude sometimes prefixes the HTML with a short reasoning sentence.
# Search for <!DOCTYPE or <html anywhere inside each text block (not just at start).
updated_html = None
for block in response.content:
    if block.type == "text":
        text = block.text
        # Strip markdown fences if Claude wrapped it anyway
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.split("\n")
            stripped = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])
            text = stripped
        # Find the HTML start marker anywhere in the block
        for marker in ("<!DOCTYPE", "<!doctype", "<html", "<HTML"):
            idx = text.find(marker)
            if idx != -1:
                updated_html = text[idx:]
                break
        if updated_html:
            break

if not updated_html:
    print("ERROR: Claude did not return valid HTML. Response blocks:")
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
            'COMPONENTS_PLACEHOLDER':       ('// ── Components',   '// ── Sections'),
            'DSEXCHART_RENDER_PLACEHOLDER':  ('function DSEXChart()',  'function SectionDSE()'),
            'TBILLCHART_RENDER_PLACEHOLDER': ('function TBillChart()', 'function SectionTBond()'),
            'OILCHART_RENDER_PLACEHOLDER':   ('function OilChart()',   'function SectionIranWar()'),
            'APP_PLACEHOLDER':               ('// ── Main App',        '</script>'),
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
