"""
notify_email.py
Sends a styled HTML digest email via the Resend API (plain HTTPS, no SDK).

Required env vars:
  RESEND_API_KEY   – your Resend API key
  EMAIL_FROM       – sender address verified in Resend (e.g. digest@yourdomain.com)
  EMAIL_TO         – recipient address
Optional:
  SITE_URL         – GitHub Pages URL; adds an "open the web edition" button
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import date
from html import escape

from .models import Paper

COLORS = ["#e4572e", "#1f7a8c", "#5b5f97", "#c2185b", "#2e7d32", "#b7791f"]
SERIF = "Georgia,'Songti SC','Noto Serif SC',serif"
SANS = "-apple-system,BlinkMacSystemFont,'PingFang SC','Segoe UI',sans-serif"


def _score_colour(score: float | None) -> str:
    if score is None:
        return "#888888"
    if score >= 8.0:
        return "#15803d"
    if score >= 6.0:
        return "#b7791f"
    if score >= 4.0:
        return "#d9580d"
    return "#c81e1e"


def _card(index: int, paper: Paper) -> str:
    colour = COLORS[index % len(COLORS)]
    score = f"{paper.score:.1f}" if paper.score is not None else "–"
    authors = ", ".join(paper.authors[:5]) + (" 等" if len(paper.authors) > 5 else "")
    link = paper.link if paper.link.lower().startswith(("http://", "https://")) else ""
    button = (
        f'<a href="{escape(link, quote=True)}" style="display:inline-block;background:#1b1a17;color:#f5efe3;'
        f'text-decoration:none;font-weight:600;font-size:14px;padding:8px 18px;border-radius:999px;">阅读原文 →</a>'
        if link else ""
    )
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" style="background:#fffdf8;border-radius:14px;margin-bottom:18px;">
  <tr><td style="background:{colour};color:#ffffff;font-size:12px;letter-spacing:1.5px;font-weight:700;
                 padding:9px 18px;border-radius:14px 14px 0 0;">
    {escape((paper.source or '').upper())} &nbsp;·&nbsp; {escape(paper.date or '')}
  </td></tr>
  <tr><td style="padding:18px;">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td width="64" valign="top">
        <div style="width:52px;height:52px;line-height:52px;text-align:center;border-radius:50%;
                    border:3px solid {_score_colour(paper.score)};color:{_score_colour(paper.score)};
                    font-family:{SERIF};font-weight:900;font-size:19px;">{score}</div>
      </td>
      <td valign="top" style="font-family:{SERIF};font-size:19px;line-height:1.3;font-weight:700;color:#1b1a17;">
        {escape(paper.title)}
      </td>
    </tr></table>
    <p style="margin:10px 0 0;font-size:13px;color:#6f685c;">{escape(authors)}</p>
    <p style="margin:10px 0 0;font-size:15px;line-height:1.7;color:#1b1a17;">{escape(paper.chinese_explanation or '暂无说明。')}</p>
    <p style="margin:10px 0 14px;font-size:12px;color:#6f685c;">关键词：{escape(', '.join(paper.matched_keywords) or '—')}</p>
    {button}
  </td></tr>
</table>"""


def build_html(papers: list[Paper], digest_date: date, site_url: str = "") -> str:
    ranked = sorted(papers, key=lambda p: p.score or 0, reverse=True)
    cards = "\n".join(_card(i, p) for i, p in enumerate(ranked))
    site_button = (
        f'<p style="text-align:center;margin:8px 0 0;"><a href="{escape(site_url, quote=True)}" '
        f'style="display:inline-block;border:2px solid #1b1a17;color:#1b1a17;text-decoration:none;'
        f'font-weight:700;font-size:15px;padding:10px 26px;border-radius:999px;">打开网页版 · 查看摘要与往期</a></p>'
        if site_url else ""
    )
    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5efe3;font-family:{SANS};">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f5efe3;"><tr><td align="center" style="padding:28px 14px;">
<table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">
  <tr><td style="text-align:center;padding:6px 0 18px;border-bottom:3px double #1b1a17;">
    <div style="font-family:{SERIF};font-size:44px;font-weight:900;color:#1b1a17;line-height:1;">Paper Digest</div>
    <div style="margin-top:10px;font-size:13px;letter-spacing:1px;color:#6f685c;">
      {digest_date.isoformat()} · 本期精选 {len(papers)} 篇
    </div>
  </td></tr>
  <tr><td style="padding:22px 0 4px;">{cards}{site_button}</td></tr>
  <tr><td style="text-align:center;padding:22px 0 0;color:#6f685c;font-size:12px;">由 GitHub Actions 自动生成</td></tr>
</table>
</td></tr></table>
</body></html>"""


def send_email_digest(papers: list[Paper], digest_date: date) -> None:
    api_key = os.environ.get("RESEND_API_KEY", "")
    from_addr = os.environ.get("EMAIL_FROM", "")
    to_addr = os.environ.get("EMAIL_TO", "")

    if not api_key:
        print("[email] RESEND_API_KEY not set – skipping.")
        return
    if not from_addr or not to_addr:
        print("[email] EMAIL_FROM / EMAIL_TO not set – skipping.")
        return

    payload = {
        "from": from_addr,
        "to": [to_addr],
        "subject": f"Paper Digest {digest_date.isoformat()} · {len(papers)} 篇精选",
        "html": build_html(papers, digest_date, os.environ.get("SITE_URL", "")),
    }
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Resend sits behind Cloudflare, which rejects urllib's default
            # "Python-urllib" User-Agent with HTTP 403 / error 1010.
            "User-Agent": "paper-digest/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            print(f"[email] Sent OK – id={json.loads(resp.read()).get('id')}")
    except urllib.error.HTTPError as exc:
        print(f"[email] HTTP {exc.code}: {exc.read().decode()}")
    except Exception as exc:
        print(f"[email] Failed: {exc}")
