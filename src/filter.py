from __future__ import annotations

import re
from difflib import SequenceMatcher

from .models import Paper


def normalize_title(title: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", title.lower())
    return re.sub(r"\s+", " ", normalized).strip()


def match_keywords(paper: Paper, keywords: list[str]) -> list[str]:
    haystack = f"{paper.title}\n{paper.abstract}".lower()
    matches = []
    for keyword in keywords:
        keyword_lower = keyword.lower().strip()
        if keyword_lower and keyword_lower in haystack:
            matches.append(keyword)
    return matches


def filter_by_keywords(papers: list[Paper], keywords: list[str]) -> list[Paper]:
    filtered = []
    for paper in papers:
        paper.matched_keywords = match_keywords(paper, keywords)
        if paper.matched_keywords:
            filtered.append(paper)
    return filtered


def deduplicate_papers(papers: list[Paper], title_similarity_threshold: float = 0.94) -> list[Paper]:
    seen_keys: set[str] = set()
    seen_titles: list[str] = []
    deduped: list[Paper] = []

    for paper in papers:
        keys = paper.identity_keys()
        if any(key in seen_keys for key in keys):
            continue

        normalized_title = normalize_title(paper.title)
        is_duplicate_title = any(
            SequenceMatcher(None, normalized_title, seen_title).ratio() >= title_similarity_threshold
            for seen_title in seen_titles
        )
        if is_duplicate_title:
            continue

        seen_keys.update(keys)
        if normalized_title:
            seen_titles.append(normalized_title)
        deduped.append(paper)

    return deduped
