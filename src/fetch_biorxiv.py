from __future__ import annotations

import logging
from datetime import date

import requests

from .models import Paper

LOGGER = logging.getLogger(__name__)
PREPRINT_API_URL = "https://api.biorxiv.org/details/{server}/{start}/{end}"


def fetch_preprint_server(server: str, start_date: date, end_date: date) -> list[Paper]:
    url = PREPRINT_API_URL.format(server=server, start=start_date.isoformat(), end=end_date.isoformat())
    LOGGER.info("Fetching %s papers", server)
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    payload = response.json()

    papers: list[Paper] = []
    for item in payload.get("collection", []):
        doi = item.get("doi") or None
        link = f"https://doi.org/{doi}" if doi else item.get("url", "")
        authors = [name.strip() for name in item.get("authors", "").split(";") if name.strip()]
        papers.append(
            Paper(
                title=item.get("title", "").strip(),
                authors=authors,
                source=server,
                date=(item.get("date") or item.get("published") or "")[:10],
                link=link,
                abstract=item.get("abstract", "").strip(),
                doi=doi,
            )
        )
    return papers


def fetch_biorxiv_medrxiv(config: dict, start_date: date, end_date: date) -> list[Paper]:
    servers = config.get("preprints", {}).get("servers", ["biorxiv", "medrxiv"])
    papers: list[Paper] = []
    for server in servers:
        papers.extend(fetch_preprint_server(server, start_date, end_date))
    return papers
