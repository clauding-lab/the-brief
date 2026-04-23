"""Headline scraping — ported verbatim from update.py:_scrape_headlines."""
from __future__ import annotations

import html as _html
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

HEADLINE_SOURCES: list[dict] = [
    {
        "url":     "https://www.thedailystar.net/business",
        "code":    "DS",
        "name":    "Daily Star",
        "pattern": r'<a\s+href="(/business/[^"]+)"[^>]*>\s*([^<]+?)\s*</a>',
        "base":    "https://www.thedailystar.net",
    },
    {
        "url":     "https://www.tbsnews.net/economy",
        "code":    "TBS",
        "name":    "TBS News",
        "pattern": r'<a\s+href="(/economy/[^"]+)"[^>]*>\s*([^<]{15,}?)\s*</a>',
        "base":    "https://www.tbsnews.net",
    },
    {
        "url":     "https://today.thefinancialexpress.com.bd/",
        "code":    "FE",
        "name":    "Financial Express BD",
        "pattern": (
            r'<a\s+href="(https://today\.thefinancialexpress\.com\.bd/'
            r'(?:first-page|last-page|economy|stock-corporate|'
            r'trade-market|trade-commodities|public|national)/[^"]+)"'
            r'[^>]*>.*?<h4>([^<]+)</h4>'
        ),
        "base":    "",
        "dotall":  True,
    },
]


@dataclass(frozen=True)
class Headline:
    title: str
    url: str
    source: str
    published: datetime


def _fetch_page(url: str, timeout: int = 15) -> str:  # pragma: no cover
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; TheBrief/1.0)"
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError):
        return ""


def scrape_source(src: dict, *, count: int = 4,
                  now: datetime | None = None) -> list[Headline]:
    now = now or datetime.now(timezone.utc)
    page = _fetch_page(src["url"])
    if not page:
        return []
    flags = re.IGNORECASE | (re.DOTALL if src.get("dotall") else 0)
    matches = re.findall(src["pattern"], page, flags)
    seen: set[str] = set()
    out: list[Headline] = []
    for path, raw_title in matches:
        title = re.sub(r'\s+', ' ', _html.unescape(raw_title)).strip()
        if len(title) < 20 or title.lower() in ("read more", "see all", "more news"):
            continue
        norm = re.sub(r'\s+', ' ', title.lower())
        if norm in seen:
            continue
        seen.add(norm)
        url = src["base"] + path if src["base"] else path
        out.append(Headline(title=title, url=url, source=src["code"], published=now))
        if len(out) >= count:
            break
    return out


def scrape_all(*, count_per_source: int = 4) -> list[Headline]:
    out: list[Headline] = []
    for src in HEADLINE_SOURCES:
        out.extend(scrape_source(src, count=count_per_source))
    return out
