"""RSS/RDF news headlines for the kiosk idle board.

Handles RSS 2.0 (items under <channel>) and RDF/RSS 1.0 (items under <rdf:RDF>),
strips HTML from summaries, and interleaves multiple feeds (e.g. ZEIT + NDR
Hamburg) so the idle rotation alternates between sources.
"""
from __future__ import annotations

import asyncio
import html
import re
import xml.etree.ElementTree as ET

import httpx

from config import KioskNewsFeedConfig
from models import NewsHeadline

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(value: str | None) -> str:
    if not value:
        return ""
    text = html.unescape(_TAG_RE.sub(" ", value))
    return re.sub(r"\s+", " ", text).strip()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(node: ET.Element, *names: str) -> str:
    for child in node:
        if _local(child.tag) in names:
            return _clean(child.text)
    return ""


def _link(node: ET.Element) -> str | None:
    for child in node:
        if _local(child.tag) != "link":
            continue
        href = child.attrib.get("href") or (child.text or "").strip()
        if href:
            return href
    return None


def parse_news_feed(label: str, raw_xml: bytes, *, limit: int = 3) -> list[NewsHeadline]:
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError:
        return []
    # Works for both RSS 2.0 (item under channel) and RDF/RSS 1.0 (item under root).
    items = [node for node in root.iter() if _local(node.tag) in {"item", "entry"}]
    headlines: list[NewsHeadline] = []
    for item in items:
        title = _child_text(item, "title")
        if not title:
            continue
        summary = _child_text(item, "description", "summary")
        headlines.append(NewsHeadline(title=title, summary=summary, source=label, link=_link(item)))
        if len(headlines) >= limit:
            break
    return headlines


async def _fetch_one(
    http: httpx.AsyncClient, feed: KioskNewsFeedConfig, *, limit: int, timeout: float | None
) -> list[NewsHeadline]:
    try:
        response = await http.get(
            feed.url,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 VaultKiosk"},
            timeout=timeout if timeout is not None else httpx.USE_CLIENT_DEFAULT,
        )
    except httpx.HTTPError:
        return []
    if response.status_code >= 400:
        return []
    return parse_news_feed(feed.label, response.content, limit=limit)


def _interleave(groups: list[list[NewsHeadline]]) -> list[NewsHeadline]:
    result: list[NewsHeadline] = []
    for column in range(max((len(g) for g in groups), default=0)):
        for group in groups:
            if column < len(group):
                result.append(group[column])
    return result


async def fetch_headlines(
    http: httpx.AsyncClient,
    feeds: list[KioskNewsFeedConfig],
    *,
    per_feed: int = 3,
    timeout: float | None = 8.0,
) -> list[NewsHeadline]:
    """Top `per_feed` headlines per feed, interleaved across feeds (round-robin).

    A failing/slow feed simply contributes nothing — never raises.
    """
    if not feeds:
        return []
    groups = await asyncio.gather(
        *(_fetch_one(http, feed, limit=per_feed, timeout=timeout) for feed in feeds)
    )
    return _interleave(list(groups))
