"""Tier 1 — Rule-based dominance + 三維檢查（v4）。

設計原則：
- **不重度依賴 stock_profiles.json**：3686 達能等案例顯示 profile 三維本身可能錯
- **以 enrichment_pilot.json 的 industry 字段做主業 dominance** 判定（覆蓋 1733 檔）
- 既有 checks.py 的 c1/c2/c3 + hard_fail 仍然執行，但僅作為輔助

判定流程：
  1. 讀 enrichment.industry 字段前 800 字
  2. 找 spec.core_keywords 最早 char-offset：
     < 80   → STRONG (pure-play)
     80-300 → WEAK   (主業次要)
     > 300  → FAIL_LATE
     不命中 → FAIL_NO_KEYWORD
  3. role exclusion（鑽針/導線架/通路商）：若 exclusion 在 keyword 之前 → 強制 FAIL
  4. 取 stock_profile：若 c2.hard_fail or c3.hard_fail → REMOVE 直接退出
  5. 加權評分：dominance (0.50) + c1 (0.15) + c2 (0.20) + c3 (0.15)
  6. 映射 verdict

API：
    evaluate_tier1(ticker, group_spec, enrichment_record, stock_profile) -> Tier1Vote
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .schema import GroupSpec, StockProfile
from .checks import run_all_checks
from .evidence import build_primary_coverage_text


@dataclass
class Tier1Vote:
    verdict: str            # CORE / SATELLITE / ABSTAIN / REMOVE
    score: float            # 0.0 - 1.0
    dominance_verdict: str  # STRONG / WEAK / FAIL_LATE / FAIL_NO_KEYWORD / FAIL_ROLE / SKIP
    matched_keyword: str
    char_offset: int
    role_exclusion: str
    c1_ok: bool = True
    c2_ok: bool = True
    c3_ok: bool = True
    c2_strong: bool = False
    hard_fail: bool = False
    hard_fail_reason: str = ""
    reason: str = ""
    quote: str = ""


# 角色排除 keyword：若這些字在 core_keyword 之前出現，代表是供應商/設備商/通路商，
# 不是該族群的本業廠
ROLE_EXCLUSIONS = [
    # 設備類
    "製程設備", "微影設備", "封裝設備", "測試設備", "檢測設備",
    "設備廠", "設備供應商", "PCB 設備",
    # 上游材料 / 耗材 / 封裝材料
    "鑽針製造", "微鑽針", "鑽孔針",
    "功率導線架", "導線架製造", "Lead Frame 製造", "Lead Frame Manufacturing",
    "封裝材料", "封裝關鍵材料",
    # 通路類
    "代理商", "通路商", "經銷商", "分銷商",
    # 太陽能 / 綠能 業務（半導體族群中的常見誤分類來源）
    "太陽能矽晶圓", "太陽能電廠維運", "綠能資產經營",
    "電廠投資與資產管理", "[[FIT]] 躉購", "綠電轉供",
]


def _extract_intro(ticker: str, enrichment_record: dict) -> str:
    """從 enrichment 抽前 800 字當業務簡介。

    優先使用 My-TW-Coverage 關鍵章節，其次 enrichment industry/revenue。
    """
    coverage_text, _coverage_meta = build_primary_coverage_text(ticker)
    if not enrichment_record:
        return coverage_text[:3200]
    industry = enrichment_record.get("industry") or ""
    revenue = enrichment_record.get("revenue") or ""
    fallback = industry[:1200] if industry else revenue[:1200]
    if coverage_text:
        return f"{coverage_text}\n\n## enrichment\n{fallback}"[:4200]
    return fallback


def _find_earliest_keyword(text: str, keywords: list[str]) -> tuple[str, int]:
    """找 keywords 最早出現位置。回傳 (keyword, offset)。沒命中回 ('', -1)。"""
    if not text or not keywords:
        return "", -1
    earliest_kw = ""
    earliest_idx = -1
    for kw in keywords:
        if not kw:
            continue
        idx = text.find(kw)
        if idx >= 0 and (earliest_idx < 0 or idx < earliest_idx):
            earliest_idx = idx
            earliest_kw = kw
    return earliest_kw, earliest_idx


def _detect_role_exclusion(
    text: str,
    group_name: str,
    extra_keywords: list[str] | None = None,
) -> tuple[str, int]:
    """偵測 role exclusion keyword。回傳 (keyword, offset)，沒命中回 ('', -1)。"""
    earliest_kw = ""
    earliest_idx = -1
    keywords = list(ROLE_EXCLUSIONS)
    for kw in extra_keywords or []:
        if kw and kw not in keywords:
            keywords.append(kw)
    for kw in keywords:
        idx = text.find(kw)
        if idx >= 0 and (earliest_idx < 0 or idx < earliest_idx):
            earliest_idx = idx
            earliest_kw = kw
    return earliest_kw, earliest_idx


def evaluate_tier1(
    ticker: str,
    group_name: str,
    spec: GroupSpec,
    enrichment_record: Optional[dict],
    stock_profile: Optional[StockProfile],
) -> Tier1Vote:
    """Tier 1 主邏輯。

    - spec: GroupSpec 物件（含 core_keywords / allowed_segments / allowed_positions）
    - enrichment_record: enrichment_pilot.json[ticker]
    - stock_profile: stock_profiles.json[ticker] 轉的 StockProfile（可為 None）
    """
    if spec.hard_whitelist and ticker not in set(spec.hard_whitelist):
        return Tier1Vote(
            verdict="REMOVE",
            score=0.0,
            dominance_verdict="HARD_WHITELIST_FAIL",
            matched_keyword="",
            char_offset=-1,
            role_exclusion="",
            hard_fail=True,
            hard_fail_reason=(
                f"{group_name} 採硬白名單，{ticker} 不在 "
                f"{spec.hard_whitelist}，不得以上游/設備/耗材/通路商身分列入；"
                f"個股位階={stock_profile.supply_chain_position if stock_profile else 'UNKNOWN'}"
            ),
            reason="硬白名單外個股直接移除",
        )

    intro = _extract_intro(ticker, enrichment_record or {})
    hard_whitelisted = bool(spec.hard_whitelist and ticker in set(spec.hard_whitelist))

    # 0. 若 enrichment 空白（很多中小型股沒有資料）→ 直接 ABSTAIN（無證據可判定，不能 REMOVE）
    if len(intro.strip()) < 50:
        return Tier1Vote(
            verdict="ABSTAIN",
            score=0.45,
            dominance_verdict="NO_DATA",
            matched_keyword="",
            char_offset=-1,
            role_exclusion="",
            c1_ok=True, c2_ok=True, c3_ok=True, c2_strong=False,
            hard_fail=False,
            reason="enrichment.industry 字段空白或過短（< 50 字），無證據可判定 → ABSTAIN（待人工或補資料）",
        )

    # 1. Dominance — 找最早 keyword
    matched_kw, kw_idx = _find_earliest_keyword(intro, spec.core_keywords)
    excl_kw, excl_idx = _detect_role_exclusion(intro, group_name, spec.exclusion_keywords)

    if hard_whitelisted:
        dom_verdict = "STRONG"
        dom_score = 0.98
        matched_kw = matched_kw or "硬白名單"
        kw_idx = kw_idx if kw_idx >= 0 else 0
        reason_dom = f"{ticker} 在 {group_name} 硬白名單內（本體族群核心成分）"
    elif matched_kw and excl_kw and excl_idx >= 0 and kw_idx >= 0 and excl_idx < kw_idx:
        # role exclusion 在 keyword 之前 → 強制 FAIL
        dom_verdict = "FAIL_ROLE"
        dom_score = 0.10
        reason_dom = f"角色排除「{excl_kw}」(第 {excl_idx} 字) 在 keyword「{matched_kw}」(第 {kw_idx} 字) 之前 — 是供應商/設備/通路非主軸廠"
    elif kw_idx < 0:
        # keyword 完全沒在 intro 出現 → 通常代表確實不屬於該族群，但保守降 ABSTAIN（避免誤殺）
        dom_verdict = "FAIL_NO_KEYWORD"
        dom_score = 0.25
        reason_dom = f"主業簡介前 800 字未命中任何 core_keyword（檢查 keywords={spec.core_keywords[:5]}）"
    elif kw_idx < 80:
        dom_verdict = "STRONG"
        dom_score = 0.95
        reason_dom = f"keyword「{matched_kw}」出現在第 {kw_idx} 字（pure-play 證據）"
    elif kw_idx < 300:
        dom_verdict = "WEAK"
        dom_score = 0.65
        reason_dom = f"keyword「{matched_kw}」出現在第 {kw_idx} 字（主業有提，但不在開頭）"
    else:
        dom_verdict = "FAIL_LATE"
        dom_score = 0.30
        reason_dom = f"keyword「{matched_kw}」出現在第 {kw_idx} 字（過晚，非主業）"

    # 2. 三維檢查（c1/c2/c3）
    c1_ok = c2_ok = c3_ok = True
    c2_strong = False
    hard_fail = False
    hard_fail_reason = ""
    if stock_profile and stock_profile.is_complete():
        c1, c2, c3 = run_all_checks(stock_profile, spec)
        c1_ok, c2_ok, c3_ok = c1.ok, c2.ok, c3.ok
        c2_strong = bool(c2.strong)
        if c2.hard_fail:
            hard_fail = True
            hard_fail_reason = f"C2 hard fail: {c2.reason}"
        elif c3.hard_fail:
            hard_fail = True
            hard_fail_reason = f"C3 hard fail: {c3.reason}"

    # 3. Hard fail 直接退出
    if hard_fail:
        return Tier1Vote(
            verdict="REMOVE",
            score=0.0,
            dominance_verdict=dom_verdict,
            matched_keyword=matched_kw,
            char_offset=kw_idx,
            role_exclusion=excl_kw,
            c1_ok=c1_ok, c2_ok=c2_ok, c3_ok=c3_ok, c2_strong=c2_strong,
            hard_fail=True,
            hard_fail_reason=hard_fail_reason,
            reason=f"Hard fail: {hard_fail_reason}",
        )

    # 4. 加權評分
    rule_score = 0.0
    if stock_profile and stock_profile.is_complete():
        rule_score = 0.20 * c1_ok + 0.40 * c2_ok + 0.40 * c3_ok
    else:
        rule_score = 0.50  # 中性，避免懲罰沒 profile 的個股

    final_score = 0.55 * dom_score + 0.45 * rule_score

    # 5. Verdict 映射
    if dom_verdict == "FAIL_ROLE":
        verdict = "REMOVE"
    elif dom_verdict == "FAIL_NO_KEYWORD":
        # 保守：給 ABSTAIN 而非 REMOVE（避免中小型股因 enrichment 不完整被誤踢）
        # 仲裁仍會結合 tier2（產業 industry_blocked / forbidden_pct）來決定最終 verdict
        verdict = "ABSTAIN"
    elif dom_verdict == "FAIL_LATE":
        verdict = "ABSTAIN"
    elif dom_verdict == "STRONG":
        if final_score >= 0.80 and c2_strong:
            verdict = "CORE"
        elif final_score >= 0.70:
            verdict = "CORE"
        else:
            verdict = "SATELLITE"
    elif dom_verdict == "WEAK":
        if final_score >= 0.65:
            verdict = "SATELLITE"
        else:
            verdict = "ABSTAIN"
    else:
        verdict = "ABSTAIN"

    quote = ""
    if matched_kw and kw_idx >= 0:
        start = max(0, kw_idx - 30)
        end = min(len(intro), kw_idx + len(matched_kw) + 60)
        quote = intro[start:end].replace("\n", " ")

    reason = f"dominance={dom_verdict}; rule_score={rule_score:.2f}; final={final_score:.2f}; {reason_dom}"

    return Tier1Vote(
        verdict=verdict,
        score=final_score,
        dominance_verdict=dom_verdict,
        matched_keyword=matched_kw,
        char_offset=kw_idx,
        role_exclusion=excl_kw if excl_kw else "",
        c1_ok=c1_ok, c2_ok=c2_ok, c3_ok=c3_ok, c2_strong=c2_strong,
        hard_fail=False,
        reason=reason,
        quote=quote,
    )


# CLI demo
if __name__ == "__main__":
    import json
    from pathlib import Path

    ROOT = Path(__file__).resolve().parents[2]
    ep = json.loads((ROOT / "My-TW-Coverage" / "enrichment_pilot.json").read_text(encoding="utf-8"))
    sp_raw = json.loads((ROOT / "concept_taxonomy" / "stock_profiles.json").read_text(encoding="utf-8"))
    specs_raw = json.loads((ROOT / "concept_taxonomy" / "group_specs.json").read_text(encoding="utf-8"))
    fixtures = json.loads((ROOT / "concept_taxonomy" / "validator" / "regression_fixtures.json").read_text(encoding="utf-8"))["fixtures"]

    def make_profile(d: dict | None) -> StockProfile | None:
        if not d:
            return None
        return StockProfile(
            ticker=d.get("ticker", ""),
            name=d.get("name", ""),
            industry_segment=d.get("industry_segment", ""),
            supply_chain_position=d.get("supply_chain_position", ""),
            core_themes=d.get("core_themes", []),
            twse_industry=d.get("twse_industry", ""),
            confidence=d.get("confidence", 0.0),
        )

    def make_spec(name: str, raw: dict) -> GroupSpec:
        return GroupSpec(
            group_name=name,
            allowed_segments=raw.get("allowed_segments", []),
            allowed_positions=raw.get("allowed_positions", []),
            required_themes_any=raw.get("required_themes_any", []),
            required_themes_strong=raw.get("required_themes_strong", []),
            forbidden_positions=raw.get("forbidden_positions", []),
            forbidden_themes=raw.get("forbidden_themes", []),
            core_keywords=raw.get("core_keywords", []),
        )

    print(f"{'ID':<6}{'Ticker':<8}{'Group':<22}{'Expected':<12}{'Tier1':<10}{'Dom':<18}{'Score':<7}{'Reason'}")
    print("-" * 130)
    for f in fixtures:
        spec_raw = specs_raw.get(f["group"], {})
        if not spec_raw:
            print(f"{f['id']}: SKIP (no spec)")
            continue
        spec = make_spec(f["group"], spec_raw)
        prof = make_profile(sp_raw.get(f["ticker"]))
        v = evaluate_tier1(f["ticker"], f["group"], spec, ep.get(f["ticker"]), prof)
        print(f"{f['id']:<6}{f['ticker']:<8}{f['group'][:20]:<22}{f['expected_verdict']:<12}{v.verdict:<10}{v.dominance_verdict:<18}{v.score:.2f}   {v.reason[:55]}")
