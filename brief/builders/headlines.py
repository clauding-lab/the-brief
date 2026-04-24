"""Builder: Headlines — takes raw scraped list + optional curation from Claude Call 1.

Fresh path: use curation from `ctx.claude_outputs['headlines_curation']['selected']`
to keep only selected URLs (in order). Fail-closed: show all scraped headlines.
"""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.schema import Metric, NewsItem, SectionData
from . import BuilderContext


def _news_items(ctx: BuilderContext) -> list[NewsItem]:
    items = [
        NewsItem(title=h.title, url=h.url, source=h.source, published=h.published)
        for h in ctx.headlines
    ]
    curation = ctx.claude_outputs.get("headlines_curation") if ctx.claude_outputs else None
    if not curation or not isinstance(curation, dict):
        return items
    selected_urls = [s.get("url") for s in curation.get("selected", []) if s.get("url")]
    if not selected_urls:
        return items
    by_url = {n.url: n for n in items}
    return [by_url[u] for u in selected_urls if u in by_url]


def build(ctx: BuilderContext) -> SectionData:
    news = _news_items(ctx)
    count_metric = Metric(
        id="headlines_count", label="Headlines count",
        value=len(news), unit="items", as_of=ctx.today,
        source="scraper", cadence="daily",
    )
    return SectionData(
        id="headlines", title="Headlines",
        metrics=[count_metric], news=news,
        freshness=section_freshness([count_metric], today=ctx.today),
    )
