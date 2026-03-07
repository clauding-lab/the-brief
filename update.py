import anthropic
import os
import sys
from datetime import datetime

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
The OilChart shows Brent crude from Oct 2024 to present.
If significant price movement has occurred:
- Add a new data point (drop oldest if needed to keep chart readable)
- Update the red post-conflict segment start index if the conflict phase has evolved
- Update the annotation label/value if a new high/low has been set
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
    model="claude-opus-4-5",
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

# ── Write updated file ─────────────────────────────────────────────────────────
with open("the-brief.html", "w", encoding="utf-8") as f:
    f.write(updated_html)

with open("index.html", "w", encoding="utf-8") as f:
    f.write(updated_html)

print(f"Done. Updated the-brief.html and index.html for {today}.")
