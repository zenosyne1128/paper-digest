"""
render_site.py
Builds the static "magazine" web app served by GitHub Pages.

  docs/papers.json  – accumulated history of every selected paper (source of truth)
  docs/index.html   – single self-contained page with the history inlined

No server, no build step, no extra dependencies.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from .models import Paper

TEMPLATE = Path(__file__).with_name("site_template.html")
SITE_DIR = Path("docs")


def paper_key(data: dict) -> str:
    key = data.get("doi") or data.get("arxiv_id") or data.get("link") or data.get("title") or ""
    return str(key).lower().strip()


def load_history(site_dir: Path = SITE_DIR) -> list[dict]:
    path = site_dir / "papers.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def seen_keys(site_dir: Path = SITE_DIR) -> set[str]:
    """Keys of papers already published, so a later run never repeats them."""
    return {item["key"] for item in load_history(site_dir)}


def _keywords_edit_url() -> str:
    """GitHub's web editor for keywords.txt. Only known inside GitHub Actions."""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    return f"https://github.com/{repo}/edit/{branch}/keywords.txt" if repo else ""


def update_site(
    papers: list[Paper],
    digest_date: date,
    site_dir: Path = SITE_DIR,
    keywords: list[str] | None = None,
) -> Path:
    history = load_history(site_dir)
    known = {item["key"] for item in history}
    for paper in papers:
        item = paper.to_dict()
        item["key"] = paper_key(item)
        item["issue"] = digest_date.isoformat()
        if item["key"] and item["key"] not in known:
            known.add(item["key"])
            history.append(item)

    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "papers.json").write_text(
        json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    payload = json.dumps(
        {
            "updated": digest_date.isoformat(),
            "papers": history,
            "keywords": keywords or [],
            "keywords_edit_url": _keywords_edit_url(),
        },
        ensure_ascii=False,
    ).replace("<", "\\u003c")  # keep paper text from closing the <script> tag
    html = TEMPLATE.read_text(encoding="utf-8").replace("__DATA__", payload)
    index_path = site_dir / "index.html"
    index_path.write_text(html, encoding="utf-8")
    return index_path
