"""Tier 2 — Revenue % 驗證（v4 核心新增）。

從 enrichment_pilot.json 抽取個股的營收拆解 %，比對族群題材 keyword，
判定該個股對該族群的「實際營收曝險」。

邏輯：
  1. 從 enrichment_pilot[ticker].revenue 解析 (描述, %) pairs
  2. 用 theme_revenue_map.json 裡的族群 keyword 累加 matched_pct
  3. 累加 forbidden_pct（命中禁忌詞的營收 % — 太陽能廠 in 矽晶圓 群）
  4. 額外檢查 enrichment_pilot[ticker].revenue 開頭的「板塊/產業」標記是否命中 industry_must_not_be
  5. 結合判定：
     - industry_must_not_be 命中           → REMOVE（hard fail）
     - forbidden_pct >= 0.40                → REMOVE（主業在禁區）
     - matched_pct >= min_pct_for_core      → CORE
     - matched_pct >= min_pct_for_satellite → SATELLITE
     - matched_pct in (0, satellite)        → ABSTAIN
     - 解析失敗或全 0                       → ABSTAIN（降級，不直接 REMOVE）

API：
    evaluate_tier2(ticker, group_name, enrichment_data, theme_map) -> Tier2Vote
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .revenue_parser import parse_revenue_breakdown, sum_pct_for_keywords, RevenueLine, _kw_match_with_boundary

VALIDATOR_DIR = Path(__file__).resolve().parent
ROOT = VALIDATOR_DIR.parent.parent

# 從 enrichment 開頭的 "**板塊:** Technology **產業:** Solar" 抓 industry tag
_INDUSTRY_TAG_PAT = re.compile(r"\*\*產業[:：]\*\*\s*([A-Za-z][A-Za-z\s/]+)")
_BOARD_TAG_PAT = re.compile(r"\*\*板塊[:：]\*\*\s*([A-Za-z][A-Za-z\s]+)")


@dataclass
class Tier2Vote:
    verdict: str            # CORE / SATELLITE / ABSTAIN / REMOVE
    score: float            # 0.0 - 1.0
    matched_pct: float      # 命中 group keyword 的營收 % 累加
    forbidden_pct: float    # 命中 forbidden keyword 的營收 % 累加
    industry_tag: str       # enrichment 抓到的 "產業" 標記（如 Solar）
    industry_blocked: bool  # 該標記命中 industry_must_not_be
    matched_keywords: list[str] = field(default_factory=list)
    matched_lines: list[dict] = field(default_factory=list)
    parse_failed: bool = False
    reason: str = ""


def _extract_industry_tag(rev_text: str) -> tuple[str, str]:
    """從 revenue 開頭抓「板塊」「產業」標記。"""
    if not rev_text:
        return "", ""
    board = ""
    industry = ""
    m = _BOARD_TAG_PAT.search(rev_text[:300])
    if m:
        board = m.group(1).strip()
    m = _INDUSTRY_TAG_PAT.search(rev_text[:300])
    if m:
        industry = m.group(1).strip()
    return board, industry


def evaluate_tier2(
    ticker: str,
    group_name: str,
    enrichment_record: dict | None,
    theme_map_entry: dict | None,
) -> Tier2Vote:
    """單檔 ticker 對單個 group 的 Tier 2 判定。

    enrichment_record: enrichment_pilot.json[ticker] 的 dict（含 revenue/industry 等）
    theme_map_entry: theme_revenue_map.json[group_name] 的 dict
    """
    # No mapping entry → 中性，回傳 ABSTAIN
    if theme_map_entry is None:
        return Tier2Vote(
            verdict="ABSTAIN",
            score=0.5,
            matched_pct=0.0,
            forbidden_pct=0.0,
            industry_tag="",
            industry_blocked=False,
            reason=f"theme_revenue_map 沒有族群 {group_name!r} 的映射，跳過 Tier 2",
            parse_failed=False,
        )

    if not enrichment_record:
        return Tier2Vote(
            verdict="ABSTAIN",
            score=0.4,
            matched_pct=0.0,
            forbidden_pct=0.0,
            industry_tag="",
            industry_blocked=False,
            reason=f"enrichment_pilot 缺 {ticker} 資料",
            parse_failed=True,
        )

    rev_text = enrichment_record.get("revenue") or ""
    industry_text = enrichment_record.get("industry") or ""
    combined_text = f"{rev_text}\n{industry_text}"  # 兩個欄位都看

    # 1. 抓 industry tag（板塊/產業）
    board, industry_tag = _extract_industry_tag(rev_text)
    industry_must_not_be = theme_map_entry.get("industry_must_not_be", [])
    industry_blocked = False
    if industry_tag:
        for bad in industry_must_not_be:
            if bad.lower() in industry_tag.lower():
                industry_blocked = True
                break

    # 2. 解析營收拆解
    lines = parse_revenue_breakdown(combined_text)
    parse_failed = len(lines) == 0

    # 3. 累加 matched_pct & forbidden_pct
    required_kws = theme_map_entry.get("required_keywords", [])
    forbidden_kws = theme_map_entry.get("forbidden_keywords", [])
    matched_pct, matched_lines = sum_pct_for_keywords(lines, required_kws)
    forbidden_pct, forbidden_lines = sum_pct_for_keywords(lines, forbidden_kws)

    # 4. 也對「整段 revenue text」做 keyword 命中（不只 % lines）— 用 word boundary 避免子字串誤判
    matched_kw_in_text = [k for k in required_kws if _kw_match_with_boundary(combined_text, k)]
    forbidden_kw_in_text = [k for k in forbidden_kws if _kw_match_with_boundary(combined_text, k)]

    # 5. 判定
    min_core = theme_map_entry.get("min_pct_for_core", 0.40)
    min_sat = theme_map_entry.get("min_pct_for_satellite", 0.10)

    # 5a. industry hard block
    if industry_blocked:
        return Tier2Vote(
            verdict="REMOVE",
            score=0.0,
            matched_pct=matched_pct,
            forbidden_pct=forbidden_pct,
            industry_tag=industry_tag,
            industry_blocked=True,
            matched_keywords=matched_kw_in_text,
            matched_lines=[_line_dict(L) for L in matched_lines],
            parse_failed=parse_failed,
            reason=f"產業標記「{industry_tag}」命中 industry_must_not_be={industry_must_not_be}",
        )

    # 5b. forbidden 主導
    if forbidden_pct >= 0.40 and forbidden_pct > matched_pct:
        return Tier2Vote(
            verdict="REMOVE",
            score=0.10,
            matched_pct=matched_pct,
            forbidden_pct=forbidden_pct,
            industry_tag=industry_tag,
            industry_blocked=False,
            matched_keywords=matched_kw_in_text,
            matched_lines=[_line_dict(L) for L in matched_lines + forbidden_lines],
            parse_failed=parse_failed,
            reason=f"營收主要在禁區（forbidden_pct={forbidden_pct:.2f} > matched_pct={matched_pct:.2f}）",
        )

    # 5c. parse 失敗 → 看 keyword 有沒有出現在 text
    if parse_failed:
        # 純 keyword 出現次數投票
        if matched_kw_in_text and not forbidden_kw_in_text:
            return Tier2Vote(
                verdict="ABSTAIN",
                score=0.55,
                matched_pct=0.0,
                forbidden_pct=0.0,
                industry_tag=industry_tag,
                industry_blocked=False,
                matched_keywords=matched_kw_in_text,
                matched_lines=[],
                parse_failed=True,
                reason=f"營收拆解解析失敗，但有命中 keyword：{matched_kw_in_text[:5]}",
            )
        if forbidden_kw_in_text and not matched_kw_in_text:
            return Tier2Vote(
                verdict="REMOVE",
                score=0.20,
                matched_pct=0.0,
                forbidden_pct=0.0,
                industry_tag=industry_tag,
                industry_blocked=False,
                matched_keywords=[],
                matched_lines=[],
                parse_failed=True,
                reason=f"營收解析失敗，且只命中禁忌 keyword：{forbidden_kw_in_text[:5]}",
            )
        return Tier2Vote(
            verdict="ABSTAIN",
            score=0.40,
            matched_pct=0.0,
            forbidden_pct=0.0,
            industry_tag=industry_tag,
            industry_blocked=False,
            matched_keywords=[],
            matched_lines=[],
            parse_failed=True,
            reason="營收解析失敗，無 keyword 命中",
        )

    # 5d. 正常營收 % 判定
    if matched_pct >= min_core:
        verdict = "CORE"
        score = min(0.70 + matched_pct * 0.30, 1.0)
        reason = f"營收 {matched_pct*100:.1f}% 來自族群題材（>= core 門檻 {min_core*100:.0f}%）"
    elif matched_pct >= min_sat:
        verdict = "SATELLITE"
        score = 0.50 + matched_pct * 0.40
        reason = f"營收 {matched_pct*100:.1f}% 落在衛星區間（{min_sat*100:.0f}%-{min_core*100:.0f}%）"
    elif matched_pct > 0:
        verdict = "ABSTAIN"
        score = 0.30 + matched_pct * 0.30
        reason = f"營收 {matched_pct*100:.1f}% 偏低，待人工確認"
    else:
        # matched_pct == 0
        if matched_kw_in_text:
            verdict = "ABSTAIN"
            score = 0.45
            reason = f"未抓到 % 但 keyword 命中：{matched_kw_in_text[:3]}"
        else:
            verdict = "REMOVE"
            score = 0.10
            reason = "營收完全不含族群題材"

    return Tier2Vote(
        verdict=verdict,
        score=score,
        matched_pct=matched_pct,
        forbidden_pct=forbidden_pct,
        industry_tag=industry_tag,
        industry_blocked=False,
        matched_keywords=matched_kw_in_text,
        matched_lines=[_line_dict(L) for L in matched_lines],
        parse_failed=parse_failed,
        reason=reason,
    )


def _line_dict(L: RevenueLine) -> dict:
    return {
        "pct": round(L.pct, 4),
        "pct_text": L.pct_text,
        "keywords": L.keywords[:5],
        "description": L.description[:120],
        "pattern": L.pattern,
    }


# CLI demo
if __name__ == "__main__":
    import sys

    ep = json.loads((ROOT / "My-TW-Coverage" / "enrichment_pilot.json").read_text(encoding="utf-8"))
    theme_map = json.loads((VALIDATOR_DIR / "theme_revenue_map.json").read_text(encoding="utf-8"))

    # 跑 fixtures
    fixtures = json.loads((VALIDATOR_DIR / "regression_fixtures.json").read_text(encoding="utf-8"))["fixtures"]
    print(f"{'ID':<6}{'Ticker':<8}{'Group':<22}{'Expected':<12}{'Tier2':<10}{'Pct':<7}{'Reason'}")
    print("-" * 110)
    for f in fixtures:
        rec = ep.get(f["ticker"])
        entry = theme_map.get(f["group"])
        v = evaluate_tier2(f["ticker"], f["group"], rec, entry)
        pct_str = f"{v.matched_pct*100:.0f}%"
        print(f"{f['id']:<6}{f['ticker']:<8}{f['group'][:20]:<22}{f['expected_verdict']:<12}{v.verdict:<10}{pct_str:<7}{v.reason[:60]}")
