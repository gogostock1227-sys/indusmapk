"""Tier 3 — Web / market evidence 驗證（v4）。

啟動條件（trigger 規則，由 strict_pipeline_v4 控制）：
  - tier1.verdict != tier2.verdict（兩審意見不一）
  - 或 tier1.score 或 tier2.score 落在灰色帶 0.50–0.70

實作方式：
  - Python pipeline 不直接出網路，避免不可重現與速率限制。
  - 先讀 web_search.WebCache；快取由人工/代理在灰色案例外部 populate。
  - 命中官方/法說/年報/MOPS/FinLab/產業價值鏈/權威財經媒體且含題材 keyword 才投 POSITIVE。

API:
    evaluate_tier3(ticker, group_name, group_keywords, force=False) -> Tier3Vote
"""
from __future__ import annotations

from .arbitration import Tier3Vote
from .web_search import WebCache


TRUSTED_DOMAINS = {
    "mops.twse.com.tw": 1.00,
    "twse.com.tw": 0.95,
    "tpex.org.tw": 0.95,
    "finlab.tw": 0.90,
    "moneydj.com": 0.82,
    "money.udn.com": 0.80,
    "ctee.com.tw": 0.80,
    "cnyes.com": 0.78,
    "technews.tw": 0.75,
    "digitimes.com": 0.75,
}


def _domain_score(url: str) -> float:
    u = (url or "").lower()
    for domain, score in TRUSTED_DOMAINS.items():
        if domain in u:
            return score
    return 0.55 if u else 0.50


def _text_has_keyword(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    return any(k and k.lower() in lower for k in keywords)


def evaluate_tier3(
    ticker: str,
    group_name: str,
    group_keywords: list[str],
    force: bool = False,
) -> Tier3Vote:
    """用已快取的 WebSearch 結果做市場概念輔助判定。

    沒快取時回 NO_DATA，不把缺資料視為負面證據。
    """
    keywords = [group_name, *group_keywords[:5]]
    queries = [
        f"{ticker} {group_name}",
        f"{ticker} {' '.join(group_keywords[:3])}".strip(),
    ]
    cache = WebCache()
    matched_sources: list[str] = []
    best_score = 0.0
    checked = 0

    for query in queries:
        hits = cache.lookup(query)
        if not hits:
            continue
        for hit in hits[:8]:
            checked += 1
            title = hit.get("title", "")
            snippet = hit.get("snippet", "") or hit.get("summary", "")
            url = hit.get("url", "")
            haystack = f"{title}\n{snippet}"
            if not _text_has_keyword(haystack, keywords):
                continue
            score = _domain_score(url)
            best_score = max(best_score, score)
            matched_sources.append(url or title)

    if matched_sources:
        verdict = "POSITIVE" if best_score >= 0.70 else "NO_DATA"
        return Tier3Vote(
            verdict=verdict,
            score=max(0.55, best_score),
            reason=f"WebCache 命中 {len(matched_sources)} 筆市場/公開資料，最高來源信賴 {best_score:.2f}",
            queries=queries,
            sources=matched_sources[:5],
        )

    return Tier3Vote(
        verdict="NO_DATA",
        score=0.5,
        reason=f"WebCache 無可用灰色案例資料（查詢 {len(queries)} 組，命中 0 組）",
        queries=queries,
        sources=[],
    )
