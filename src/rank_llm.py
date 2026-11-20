from __future__ import annotations

import json
import os
import time
from typing import Any

from .models import Paper


INTEREST_TERMS = {
    "mendelian randomization": 3.0,
    "instrumental variable": 2.5,
    "pleiotropy": 2.5,
    "gwas": 2.0,
    "eqtl": 2.0,
    "twas": 2.0,
    "single-cell": 2.0,
    "single cell": 2.0,
    "differential expression": 2.0,
    "causal inference": 1.8,
    "perturb-seq": 1.8,
    "multi-outcome": 1.5,
    "multi-response": 1.5,
    "robust": 1.2,
    "method": 1.0,
    "inference": 1.0,
}


def _fallback_explanation(paper: Paper, fallback_note: str) -> str:
    keywords = "、".join(paper.matched_keywords[:4]) or "相关主题"
    title_hint = paper.title[:80]
    return (
        f"这篇文章《{title_hint}》命中了 {keywords}。{fallback_note}，"
        "这里只能基于标题、摘要长度和关键词做粗略判断，并非 LLM 生成的解读。"
    )


def rank_with_placeholder(
    papers: list[Paper],
    selected_count: int,
    fallback_note: str = "当前没有调用 LLM",
) -> list[Paper]:
    for paper in papers:
        text = f"{paper.title}\n{paper.abstract}".lower()
        keyword_score = len(paper.matched_keywords) * 1.5
        interest_score = sum(weight for term, weight in INTEREST_TERMS.items() if term in text)
        abstract_bonus = min(len(paper.abstract) / 1200, 1.0)
        paper.score = round(min(10.0, keyword_score + interest_score + abstract_bonus), 2)
        paper.score_reason = (
            f"Matched {len(paper.matched_keywords)} configured keywords; "
            "fallback scorer weighted MR, IV, pleiotropy, GWAS/eQTL/TWAS, causal inference, "
            "single-cell, and methodological terms."
        )
        paper.chinese_explanation = _fallback_explanation(paper, fallback_note)

    return sorted(papers, key=lambda item: item.score or 0, reverse=True)[:selected_count]


def _openai_prompt(papers: list[Paper], selected_count: int, keywords: list[str]) -> str:
    compact_papers = [
        {
            "index": index,
            "title": paper.title,
            "authors": paper.authors[:8],
            "source": paper.source,
            "date": paper.date,
            "abstract": paper.abstract[:2500],
            "matched_keywords": paper.matched_keywords,
        }
        for index, paper in enumerate(papers)
    ]
    return f"""
You are ranking new academic papers for a researcher whose interests are:
- Mendelian randomization and instrumental variables
- multi-outcome / multi-response MR
- robust inference under horizontal pleiotropy
- GWAS, eQTL, TWAS, and genetic causal inference
- single-cell RNA-seq, perturb-seq, differential expression, and eQTL analysis

The researcher's current keyword watchlist (treat these as interests too): {', '.join(keywords)}

Select exactly {selected_count} papers that are most methodologically interesting or most likely to be useful
for that research agenda. Prefer papers with reusable statistical ideas, inference strategies, study designs,
or genomics/single-cell methods over papers that only mention a keyword superficially.

Return JSON only with this schema:
{{
  "selected": [
    {{
      "index": 0,
      "score": 0.0,
      "reason": "Brief English reason grounded in the title/abstract.",
      "chinese_explanation": "用自然、直观的中文解释为什么这篇具体论文值得关注。必须引用论文题目或摘要里的具体问题、方法、数据类型或结论；不要写泛泛的模板话。"
    }}
  ]
}}

For each selected paper:
- score must be from 0 to 10;
- reason should mention the specific methodological or scientific hook;
- chinese_explanation should be 2-4 Chinese sentences, concrete and readable;
- do not invent details that are not supported by the title or abstract.

Papers:
{json.dumps(compact_papers, ensure_ascii=False)}
""".strip()


# OpenAI-compatible endpoints. Any other provider works too: set llm.base_url in config.yaml.
BASE_URLS = {
    "openai": None,
    "deepseek": "https://api.deepseek.com",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "openrouter": "https://openrouter.ai/api/v1",
}


def _parse_json(text: str) -> dict:
    """Tolerate models that wrap the JSON in ``` fences or add a sentence around it."""
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start : end + 1]) if start != -1 and end > start else {}


def _rank_with_openai(
    papers: list[Paper], config: dict[str, Any], selected_count: int, llm_config: dict[str, Any]
) -> list[Paper]:
    from openai import OpenAI

    provider = llm_config.get("provider", "openai")
    client = OpenAI(
        api_key=os.environ.get(llm_config.get("api_key_env", "OPENAI_API_KEY")),
        base_url=llm_config.get("base_url") or BASE_URLS.get(provider),
        timeout=120,  # seconds per request; the SDK itself also retries twice quickly
    )
    extra: dict[str, Any] = {}
    if provider in ("openai", "deepseek"):
        extra["response_format"] = {"type": "json_object"}
    if provider == "deepseek":
        # DeepSeek thinks by default; a ranking task doesn't need it (faster, cheaper).
        extra["extra_body"] = {"thinking": {"type": "disabled"}}
    response = client.chat.completions.create(
        model=llm_config.get("model", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": "You are a careful academic literature triage assistant."},
            {"role": "user", "content": _openai_prompt(papers, selected_count, config.get("keywords", []))},
        ],
        temperature=float(config.get("llm", {}).get("temperature", 0.2)),
        **extra,
    )
    payload = _parse_json(response.choices[0].message.content or "")

    selected: list[Paper] = []
    for item in payload.get("selected", []):
        index = int(item["index"])
        if not 0 <= index < len(papers):
            continue
        paper = papers[index]
        paper.score = float(item.get("score", 0))
        paper.score_reason = item.get("reason", "")
        paper.chinese_explanation = item.get("chinese_explanation", "")
        selected.append(paper)
    return selected[:selected_count]


def _providers(config: dict[str, Any]) -> list[dict[str, Any]]:
    """llm.providers is tried in order; a flat llm block still works as a single provider."""
    llm_config = config.get("llm", {})
    return list(llm_config.get("providers") or [llm_config])


# Errors that usually clear up on their own (network drops, 429, 5xx / overloaded).
_TRANSIENT = {"APIConnectionError", "APITimeoutError", "RateLimitError", "InternalServerError"}


def _is_transient(exc: Exception) -> bool:
    return any(cls.__name__ in _TRANSIENT for cls in type(exc).__mro__)


def _try_providers(papers: list[Paper], config: dict[str, Any], selected_count: int) -> tuple[list[Paper], list[str], bool]:
    """One pass over the providers. Returns (selected, problems, any_transient_failure)."""
    problems: list[str] = []
    transient = False
    for llm_config in _providers(config):
        provider = llm_config.get("provider", "openai")
        model = llm_config.get("model")
        api_key_env = llm_config.get("api_key_env", "OPENAI_API_KEY")
        label = f"{provider} / {model}"
        if provider not in BASE_URLS and not llm_config.get("base_url"):
            problems.append(f"{label}: 不支持的 provider（可选 {', '.join(BASE_URLS)}，或设置 base_url）")
        elif not os.environ.get(api_key_env):
            problems.append(f"{label}: 环境变量 {api_key_env} 未设置")
        else:
            print(f"[llm] 调用 {label}，候选 {len(papers)} 篇 …")
            try:
                selected = _rank_with_openai(papers, config, selected_count, llm_config)
                if selected:
                    print(f"[llm] 成功（{label}），选出 {len(selected)} 篇。")
                    return selected, problems, transient
                problems.append(f"{label}: 返回了空结果或无法解析的 JSON")
                transient = True  # usually a one-off glitch
            except Exception as exc:
                problems.append(f"{label}: 调用失败 – {exc}")
                transient = transient or _is_transient(exc)
        print(f"[llm] 跳过 {problems[-1]}")
    return [], problems, transient


def rank_papers(papers: list[Paper], config: dict[str, Any], dry_run: bool = False) -> list[Paper]:
    selected_count = int(config.get("selected_count", 2))
    if not papers:
        return []
    if dry_run:
        print("[llm] --dry-run: LLM 未调用，使用关键词占位评分（没有中文解读）。")
        return rank_with_placeholder(papers, selected_count)

    # If every provider failed for a temporary reason, wait and try the whole list again.
    waits = [float(m) for m in config.get("llm", {}).get("retry_wait_minutes", [2, 10])]
    for round_no in range(len(waits) + 1):
        selected, problems, transient = _try_providers(papers, config, selected_count)
        if selected:
            return selected
        if not transient or round_no == len(waits):
            break
        print(f"[llm] 全部失败，像是临时故障；{waits[round_no]:g} 分钟后重试（第 {round_no + 2}/{len(waits) + 1} 轮）…")
        time.sleep(waits[round_no] * 60)

    hint = (
        "GitHub Actions 会在当天稍后的时段自动再试。"
        if os.environ.get("GITHUB_ACTIONS")
        else "本地运行请在项目根目录的 .env 里填入 key，或加 --dry-run 只测试流程。"
    )
    raise RuntimeError("所有 LLM 都不可用：\n  - " + "\n  - ".join(problems) + "\n" + hint)
