from __future__ import annotations

import logging
import re
from datetime import date
from urllib.parse import quote

import feedparser
import requests

from .models import Paper

LOGGER = logging.getLogger(__name__)
ARXIV_API_URL = "https://export.arxiv.org/api/query"


def _entry_date(entry: object) -> str:
    published = getattr(entry, "published", "") or getattr(entry, "updated", "")
    return published[:10]


def _extract_arxiv_id(entry_id: str) -> str | None:
    match = re.search(r"arxiv\.org/abs/([^v]+)(?:v\d+)?", entry_id)
    return match.group(1) if match else None


def _extract_doi(entry: object) -> str | None:
    doi = getattr(entry, "arxiv_doi", None)
    if doi:
        return str(doi)
    for link in getattr(entry, "links", []):
        if getattr(link, "title", "") == "doi":
            return getattr(link, "href", "").replace("https://doi.org/", "") or None
    return None


def fetch_arxiv(config: dict, start_date: date, end_date: date) -> list[Paper]:
    arxiv_config = config.get("arxiv", {})
    categories = arxiv_config.get("categories", [])
    max_results = int(arxiv_config.get("max_results", 100))
    if not categories:
        return []

    query = " OR ".join(f"cat:{category}" for category in categories)
    url = (
        f"{ARXIV_API_URL}?search_query={quote(query)}"
        f"&sortBy=submittedDate&sortOrder=descending&max_results={max_results}"
    )
    LOGGER.info("Fetching arXiv papers")
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    feed = feedparser.parse(response.text)
    papers: list[Paper] = []
    for entry in feed.entries:
        paper_date = _entry_date(entry)
        if not paper_date or not (start_date.isoformat() <= paper_date <= end_date.isoformat()):
            continue

        authors = [author.get("name", "") for author in getattr(entry, "authors", [])]
        papers.append(
            Paper(
                title=getattr(entry, "title", "").replace("\n", " ").strip(),
                authors=[author for author in authors if author],
                source="arXiv",
                date=paper_date,
                link=getattr(entry, "link", ""),
                abstract=getattr(entry, "summary", "").replace("\n", " ").strip(),
                doi=_extract_doi(entry),
                arxiv_id=_extract_arxiv_id(getattr(entry, "id", "")),
            )
        )
    return papers
