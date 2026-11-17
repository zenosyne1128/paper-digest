from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Paper:
    title: str
    authors: list[str]
    source: str
    date: str
    link: str
    abstract: str
    doi: str | None = None
    arxiv_id: str | None = None
    matched_keywords: list[str] = field(default_factory=list)
    score: float | None = None
    score_reason: str | None = None
    chinese_explanation: str | None = None

    def identity_keys(self) -> list[str]:
        keys = []
        if self.doi:
            keys.append(f"doi:{self.doi.lower().strip()}")
        if self.arxiv_id:
            keys.append(f"arxiv:{self.arxiv_id.lower().strip()}")
        if self.link:
            keys.append(f"url:{self.link.lower().strip()}")
        return keys

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "authors": self.authors,
            "source": self.source,
            "date": self.date,
            "link": self.link,
            "abstract": self.abstract,
            "doi": self.doi,
            "arxiv_id": self.arxiv_id,
            "matched_keywords": self.matched_keywords,
            "score": self.score,
            "score_reason": self.score_reason,
            "chinese_explanation": self.chinese_explanation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Paper":
        return cls(
            title=data.get("title", ""),
            authors=list(data.get("authors", [])),
            source=data.get("source", ""),
            date=data.get("date", ""),
            link=data.get("link", ""),
            abstract=data.get("abstract", ""),
            doi=data.get("doi"),
            arxiv_id=data.get("arxiv_id"),
            matched_keywords=list(data.get("matched_keywords", [])),
            score=data.get("score"),
            score_reason=data.get("score_reason"),
            chinese_explanation=data.get("chinese_explanation"),
        )
