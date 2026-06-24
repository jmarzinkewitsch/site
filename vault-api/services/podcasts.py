from __future__ import annotations

import hashlib
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from config import KioskPodcastFeedConfig
from models import PodcastEpisode, PodcastFeed


class PodcastError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class ParsedPodcastFeed:
    feed: PodcastFeed
    episodes: list[PodcastEpisode]


_TAG_RE = re.compile(r"<[^>]+>")


def _clean_text(value: str | None) -> str | None:
    if not value:
        return None
    text = html.unescape(_TAG_RE.sub(" ", value))
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _child(node: ET.Element, local_name: str) -> ET.Element | None:
    for child in node:
        if child.tag.rsplit("}", 1)[-1] == local_name:
            return child
    return None


def _text(node: ET.Element, local_name: str) -> str | None:
    child = _child(node, local_name)
    if child is None:
        return None
    return _clean_text(child.text)


def _image_url(node: ET.Element) -> str | None:
    image = _child(node, "image")
    if image is not None:
        href = image.attrib.get("href")
        if href:
            return href
        url = _text(image, "url")
        if url:
            return url
    for child in node:
        if child.tag.rsplit("}", 1)[-1] == "image" and child.attrib.get("href"):
            return child.attrib["href"]
    return None


def _published(item: ET.Element) -> str | None:
    value = _text(item, "pubDate") or _text(item, "published") or _text(item, "updated")
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError, IndexError):
        return value


def _audio_url(item: ET.Element) -> str | None:
    enclosure = _child(item, "enclosure")
    if enclosure is not None and enclosure.attrib.get("url"):
        return enclosure.attrib["url"]
    for child in item:
        if child.tag.rsplit("}", 1)[-1] != "link":
            continue
        href = child.attrib.get("href") or (child.text or "").strip()
        link_type = child.attrib.get("type", "")
        if href and (link_type.startswith("audio/") or href.lower().endswith((".mp3", ".m4a", ".aac", ".ogg"))):
            return href
    return None


def _episode_id(feed_id: str, audio_url: str) -> str:
    digest = hashlib.sha1(f"{feed_id}:{audio_url}".encode("utf-8")).hexdigest()[:16]
    return f"{feed_id}-{digest}"


def parse_podcast_feed(config: KioskPodcastFeedConfig, raw_xml: bytes) -> ParsedPodcastFeed:
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as exc:
        raise PodcastError(f"Podcast-Feed {config.id} ist kein gültiges XML") from exc

    rss_channel = _child(root, "channel")
    channel = rss_channel if rss_channel is not None else root
    feed_title = config.title or _text(channel, "title") or config.id
    feed_image = _image_url(channel)
    feed_description = _text(channel, "description") or _text(channel, "subtitle")

    item_nodes = [node for node in channel if node.tag.rsplit("}", 1)[-1] in {"item", "entry"}]
    episodes: list[PodcastEpisode] = []
    for item in item_nodes:
        audio_url = _audio_url(item)
        if not audio_url:
            continue
        title = _text(item, "title") or "Unbenannte Episode"
        description = _text(item, "description") or _text(item, "summary")
        episode_image = _image_url(item) or feed_image
        episodes.append(
            PodcastEpisode(
                id=_episode_id(config.id, audio_url),
                feed_id=config.id,
                feed_title=feed_title,
                title=title,
                subtitle=description,
                description=description,
                published=_published(item),
                duration=_text(item, "duration"),
                audio_url=audio_url,
                image_url=episode_image,
            )
        )

    return ParsedPodcastFeed(
        feed=PodcastFeed(
            id=config.id,
            title=feed_title,
            description=feed_description,
            image_url=feed_image,
            episode_count=len(episodes),
        ),
        episodes=episodes,
    )


async def fetch_podcast_feed(
    http: httpx.AsyncClient, feed: KioskPodcastFeedConfig, *, timeout: float | None = None
) -> ParsedPodcastFeed:
    try:
        response = await http.get(
            feed.url,
            follow_redirects=True,
            timeout=timeout if timeout is not None else httpx.USE_CLIENT_DEFAULT,
        )
    except httpx.HTTPError as exc:
        raise PodcastError(f"Podcast-Feed {feed.id} ist nicht erreichbar") from exc
    if response.status_code >= 400:
        raise PodcastError(f"Podcast-Feed {feed.id} antwortet mit {response.status_code}")
    return parse_podcast_feed(feed, response.content)


def dump_parsed(parsed: ParsedPodcastFeed) -> dict[str, Any]:
    return {
        "feed": parsed.feed.model_dump(),
        "episodes": [episode.model_dump() for episode in parsed.episodes],
    }


def load_parsed(raw: dict[str, Any]) -> ParsedPodcastFeed:
    return ParsedPodcastFeed(
        feed=PodcastFeed.model_validate(raw["feed"]),
        episodes=[PodcastEpisode.model_validate(item) for item in raw.get("episodes", [])],
    )
