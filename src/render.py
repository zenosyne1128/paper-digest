from __future__ import annotations

from datetime import date
from pathlib import Path

from .models import Paper


def render_digest(papers: list[Paper], digest_date: date, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Daily Literature Digest - {digest_date.isoformat()}",
        "",
        f"Selected papers: {len(papers)}",
        "",
    ]

    if not papers:
        lines.extend(["No matching papers found.", ""])
    for index, paper in enumerate(papers, start=1):
        lines.extend(
            [
                f"## {index}. {paper.title}",
                "",
                f"- **Authors:** {', '.join(paper.authors) or 'Unknown'}",
                f"- **Source:** {paper.source}",
                f"- **Date:** {paper.date or 'Unknown'}",
                f"- **Link / DOI:** {paper.link or paper.doi or 'Unavailable'}",
                f"- **Matched Keywords:** {', '.join(paper.matched_keywords) or 'None'}",
                f"- **LLM Relevance Score:** {paper.score if paper.score is not None else 'N/A'}",
                f"- **Score Reason:** {paper.score_reason or 'N/A'}",
                "",
                "### Why This May Be Interesting",
                "",
                paper.chinese_explanation or "暂无说明。",
                "",
                "### Original Abstract",
                "",
                paper.abstract or "No abstract available.",
                "",
            ]
        )

    output_path.write_text("\n".join(lines), encoding="utf-8")
