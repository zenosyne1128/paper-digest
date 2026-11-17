from __future__ import annotations

import logging
from datetime import date

import feedparser
import requests
from dateutil import parser as date_parser

from .models import Paper

LOGGER = logging.getLogger(__name__)


def _parse_entry_date(entry: object) -> str:
    for attr in ("published", "updated", "created"):
        value = getattr(entry, attr, None)
        if value:
            return date_parser.parse(value).date().isoformat()
    return ""


def _entry_authors(entry: object) -> list[str]:
    authors = getattr(entry, "authors", None)
    if authors:
        return [author.get("name", "") for author in authors if author.get("name")]
    author = getattr(entry, "author", "")
    return [author] if author else []


def _entry_doi(entry: object) -> str | None:
    for key in ("dc_identifier", "prism_doi", "doi"):
        value = getattr(entry, key, None)
        if value:
            value = str(value).replace("doi:", "").strip()
            if "/" in value:
                return value
    return None


def fetch_rss(config: dict, start_date: date, end_date: date) -> list[Paper]:
    feeds = config.get("rss_feeds", [])
    papers: list[Paper] = []
    for feed_config in feeds:
        name = feed_config.get("name", "RSS")
        url = feed_config.get("url")
        if not url:
            continue

        LOGGER.info("Fetching RSS feed: %s", name)
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        feed = feedparser.parse(response.text)
        for entry in feed.entries:
            paper_date = _parse_entry_date(entry)
            if paper_date and not (start_date.isoformat() <= paper_date <= end_date.isoformat()):
                continue
            abstract = getattr(entry, "summary", "") or getattr(entry, "description", "")
            papers.append(
                Paper(
                    title=getattr(entry, "title", "").replace("\n", " ").strip(),
                    authors=_entry_authors(entry),
                    source=name,
                    date=paper_date,
                    link=getattr(entry, "link", ""),
                    abstract=abstract.replace("\n", " ").strip(),
                    doi=_entry_doi(entry),
                )
            )
    return papers
