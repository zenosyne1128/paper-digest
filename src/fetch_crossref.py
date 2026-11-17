from __future__ import annotations

import logging
import os
import time
from datetime import date

import requests

from .models import Paper

LOGGER = logging.getLogger(__name__)
CROSSREF_WORKS_URL = "https://api.crossref.org/works"


def _flatten_abstract(raw: str | None) -> str:
    if not raw:
        return ""
    return raw.replace("<jats:p>", "").replace("</jats:p>", "").strip()


def _authors(item: dict) -> list[str]:
    authors = []
    for author in item.get("author", []):
        parts = [author.get("given", ""), author.get("family", "")]
        name = " ".join(part for part in parts if part).strip()
        if name:
            authors.append(name)
    return authors


def _published_date(item: dict) -> str:
    date_parts = (
        item.get("published-print", {}).get("date-parts")
        or item.get("published-online", {}).get("date-parts")
        or item.get("created", {}).get("date-parts")
        or []
    )
    if not date_parts:
        return ""
    parts = list(date_parts[0]) + [1, 1]
    year, month, day = parts[:3]
    return date(int(year), int(month), int(day)).isoformat()


def _get_with_retry(params: dict, attempts: int = 4) -> requests.Response:
    """Crossref rate-limits anonymous clients; wait and retry on HTTP 429."""
    for attempt in range(attempts):
        response = requests.get(CROSSREF_WORKS_URL, params=params, timeout=30)
        if response.status_code != 429 or attempt == attempts - 1:
            break
        retry_after = response.headers.get("Retry-After", "")
        time.sleep(min(int(retry_after) if retry_after.isdigit() else 5 * (attempt + 1), 60))
    response.raise_for_status()
    return response


def fetch_crossref(config: dict, start_date: date, end_date: date) -> list[Paper]:
    journals = config.get("journals", config.get("crossref_journals", []))
    rows = int(config.get("crossref", {}).get("rows_per_journal", 20))
    papers: list[Paper] = []
    # Optional: an email in CROSSREF_MAILTO moves requests to Crossref's faster "polite" pool.
    mailto = os.environ.get("CROSSREF_MAILTO", "")

    for journal in journals:
        LOGGER.info("Fetching Crossref metadata: %s", journal)
        params = {
            "filter": f"from-pub-date:{start_date.isoformat()},until-pub-date:{end_date.isoformat()}",
            "query.container-title": journal,
            "sort": "published",
            "order": "desc",
            "rows": rows,
        }
        if mailto:
            params["mailto"] = mailto
        try:
            response = _get_with_retry(params)
        except requests.RequestException as exc:
            # One journal failing must not throw away the others.
            LOGGER.warning("Crossref fetch failed for %s: %s", journal, exc)
            continue
        finally:
            time.sleep(1)  # stay well under Crossref's rate limit
        items = response.json().get("message", {}).get("items", [])
        for item in items:
            title = " ".join(item.get("title", [])).strip()
            if not title:
                continue
            papers.append(
                Paper(
                    title=title,
                    authors=_authors(item),
                    source="; ".join(item.get("container-title", [])) or journal,
                    date=_published_date(item),
                    link=item.get("URL", ""),
                    abstract=_flatten_abstract(item.get("abstract")),
                    doi=item.get("DOI"),
                )
            )

    return papers
