from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import yaml

from src.fetch_arxiv import fetch_arxiv
from src.fetch_biorxiv import fetch_biorxiv_medrxiv
from src.fetch_crossref import fetch_crossref
from src.fetch_rss import fetch_rss
from src.filter import deduplicate_papers, filter_by_keywords
from src.models import Paper
from src.notify_email import build_html, send_email_digest
from src.rank_llm import rank_papers
from src.render import render_digest
from src.render_site import SITE_DIR, paper_key, seen_keys, update_site

LOGGER = logging.getLogger(__name__)


Fetcher = Callable[[dict, date, date], list[Paper]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a daily academic literature digest.")
    parser.add_argument("--config", default="config.yaml", help="Path to YAML config file.")
    parser.add_argument("--date", help="Single date to fetch, or 'today'.")
    parser.add_argument("--from", dest="from_date", help="Start date, YYYY-MM-DD.")
    parser.add_argument("--to", dest="to_date", help="End date, YYYY-MM-DD.")
    parser.add_argument("--dry-run", action="store_true", help="No LLM, no email: placeholder ranking, output to data/preview/.")
    parser.add_argument("--preview", action="store_true", help="Real LLM ranking, but no email; output to data/preview/.")
    parser.add_argument("--verbose", action="store_true", help="Print detailed fetch logs.")
    return parser.parse_args()


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_dotenv(path: Path = Path(".env")) -> None:
    """Local convenience: copy KEY=value lines from .env into os.environ (never overrides)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        value = value.strip().strip("'\"")
        # Untouched placeholders count as "not set" so the next provider is tried.
        if sep and key and not key.startswith("#") and value and value != "REPLACE_ME":
            os.environ.setdefault(key.strip(), value)


def load_keywords(config: dict, path: Path = Path("keywords.txt")) -> list[str]:
    """keywords.txt (one per line) is the source of truth; config.yaml is the fallback."""
    if not path.exists():
        return list(config.get("keywords", []))
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return list(dict.fromkeys(line for line in lines if line and not line.startswith("#")))


def _parse_date(value: str) -> date:
    if value == "today":
        return date.today()
    return date.fromisoformat(value)


def resolve_date_range(args: argparse.Namespace, config: dict) -> tuple[date, date, date]:
    if args.date and (args.from_date or args.to_date):
        raise ValueError("Use either --date or --from/--to, not both.")

    if args.date:
        selected = _parse_date(args.date)
        return selected, selected, selected

    if args.from_date or args.to_date:
        if not args.from_date or not args.to_date:
            raise ValueError("Both --from and --to are required for a date range.")
        start_date = _parse_date(args.from_date)
        end_date = _parse_date(args.to_date)
        return start_date, end_date, end_date

    config_range = config.get("date_range", {})
    if config_range.get("from") and config_range.get("to"):
        start_date = _parse_date(str(config_range["from"]))
        end_date = _parse_date(str(config_range["to"]))
        return start_date, end_date, end_date

    days_back = int(config_range.get("days_back", 1))
    end_date = date.today()
    start_date = end_date - timedelta(days=max(days_back - 1, 0))
    return start_date, end_date, end_date


def run_fetchers(config: dict, start_date: date, end_date: date) -> list[Paper]:
    fetchers: list[tuple[str, Fetcher]] = [
        ("arXiv", fetch_arxiv),
        ("bioRxiv/medRxiv", fetch_biorxiv_medrxiv),
        ("RSS", fetch_rss),
        ("Crossref", fetch_crossref),
    ]
    papers: list[Paper] = []
    for name, fetcher in fetchers:
        try:
            papers.extend(fetcher(config, start_date, end_date))
        except Exception as exc:
            LOGGER.warning("%s fetch failed: %s", name, exc)
    return papers


def save_candidates(papers: list[Paper], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [paper.to_dict() for paper in papers]
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )
    load_dotenv()
    config = load_config(Path(args.config))
    config["keywords"] = load_keywords(config)
    local_only = args.dry_run or args.preview
    start_date, end_date, output_date = resolve_date_range(args, config)

    raw_papers = run_fetchers(config, start_date, end_date)
    deduped = deduplicate_papers(raw_papers)
    candidates = filter_by_keywords(deduped, config.get("keywords", []))
    # Local test runs build a throwaway preview so they never touch the published site.
    site_dir = Path("data") / "preview" if local_only else SITE_DIR
    published = seen_keys(site_dir)
    candidates = [p for p in candidates if paper_key(p.to_dict()) not in published]
    try:
        selected = rank_papers(candidates, config, dry_run=args.dry_run)
    except RuntimeError as exc:
        # Stop here: never publish or email a digest without real LLM summaries.
        raise SystemExit(f"ERROR: {exc}")

    candidate_path = Path("data") / f"candidates_{output_date.isoformat()}.json"
    digest_path = Path("digest") / f"{output_date.isoformat()}.md"
    save_candidates(candidates, candidate_path)
    render_digest(selected, output_date, digest_path)

    print(f"Fetched {len(raw_papers)} papers; {len(candidates)} matched keywords.")
    print(f"Saved candidates to {candidate_path}")
    print(f"Saved digest to {digest_path}")

    # ── Publish: web app (docs/ → GitHub Pages) + email ───────────────────────
    index_path = update_site(selected, output_date, site_dir, config["keywords"])
    print(f"Saved web app to {index_path}")
    if local_only:
        email_path = site_dir / "email.html"
        email_path.write_text(build_html(selected, output_date, "index.html"), encoding="utf-8")
        print(f"[notify] 本地预览模式：未发送邮件，邮件样例保存在 {email_path}")
    elif selected:
        send_email_digest(selected, output_date)


if __name__ == "__main__":
    main()
