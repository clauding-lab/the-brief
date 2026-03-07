import anthropic
import json
import os
import sys
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

# ── Update prompt ──────────────────────────────────────────────────────────────
PROMPT = f"""You are updating THE BRIEF, a Bangladesh business intelligence single-page app.
Today's date is {today}.

Here is the complete current HTML file:

<current_file>
{current_html}
</current_file>

Perform ALL of the following update steps using web search to find the latest data.
Return ONLY the complete updated HTML file — no explanation, no markdown fences, just the raw HTML.

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

Return the complete updated HTML file now.
"""

# ── Call Claude API ────────────────────────────────────────────────────────────
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

print("Calling Claude API with web search...")

response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=32000,
    tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 20}],
    messages=[{"role": "user", "content": PROMPT}],
)

# ── Extract the HTML from the response ────────────────────────────────────────
updated_html = None
for block in response.content:
    if block.type == "text":
        text = block.text.strip()
        # Strip markdown fences if Claude wrapped it anyway
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])
        if text.startswith("<!DOCTYPE") or text.startswith("<html"):
            updated_html = text
            break

if not updated_html:
    print("ERROR: Claude did not return valid HTML.")
    sys.exit(1)

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
