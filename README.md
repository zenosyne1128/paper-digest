# Daily Literature Digest

A small Python tool that fetches recent papers from arXiv, bioRxiv/medRxiv, journal RSS feeds, and Crossref, filters them by configurable research keywords, ranks them, and writes a daily markdown digest.

The default ranking is a deterministic placeholder, so the project works without an LLM API key. You can enable OpenAI later through `config.yaml`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Edit `config.yaml` to change keywords, arXiv categories, journal names, RSS feeds, date range, selected paper count, and LLM settings.

## Run

Fetch today's papers and write a digest:

```bash
python main.py --date today
```

Fetch a date range:

```bash
python main.py --from 2026-05-01 --to 2026-05-07
```

Use placeholder ranking and avoid any LLM call:

```bash
python main.py --date today --dry-run
```

Outputs:

- `data/candidates_YYYY-MM-DD.json`: keyword-matched candidate papers after deduplication.
- `digest/YYYY-MM-DD.md`: top selected papers with abstracts, matched keywords, scores, reasons, and Chinese explanations.

## LLM Ranking

By default, `config.yaml` is set up for OpenAI ranking:

```yaml
llm:
  provider: openai
  model: gpt-4o-mini
  api_key_env: OPENAI_API_KEY
```

Then set your API key:

```bash
export OPENAI_API_KEY="..."
python main.py --date today
```

The `export OPENAI_API_KEY=...` command can be run from any directory. It sets an environment variable for the current terminal session; the important part is that `python main.py ...` is launched from that same terminal session. The `python main.py ...` command itself should be run from this project directory unless you pass absolute paths.

If the API key is missing, `--dry-run` is used, or the LLM call fails, the tool falls back to placeholder ranking so scheduled runs can still complete.

## Scheduling With Cron

Open your crontab:

```bash
crontab -e
```

Run every day at 8 AM:

```cron
0 8 * * * cd /path/to/daily-lit-digest && . .venv/bin/activate && python main.py --date today >> digest/cron.log 2>&1
```

Replace `/path/to/daily-lit-digest` with this project directory.

## Scheduling With GitHub Actions

Create `.github/workflows/daily-digest.yml`:

```yaml
name: Daily literature digest

on:
  schedule:
    - cron: "0 13 * * *"
  workflow_dispatch:

jobs:
  digest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: python main.py --date today
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
      - uses: actions/upload-artifact@v4
        with:
          name: literature-digest
          path: |
            data/
            digest/
```

## Notes

- arXiv is fetched through the official API and filtered by publication date locally.
- bioRxiv and medRxiv are fetched through the public `api.biorxiv.org` details API.
- Journal RSS feeds are used when listed in `config.yaml`.
- Crossref is used as a fallback for journal metadata by querying configured journal names.
- Deduplication uses DOI, arXiv ID, URL, and title similarity.
