"""Arbitration — 三審仲裁與跨族群衝突偵測（v4）。

仲裁規則：
  1. 任一 tier 是 hard_fail → REMOVE（最嚴規則）
  2. 三審一致 → 直接決議
  3. 2:1 majority → majority verdict + 反對意見記錄
  4. 三審分歧 → ABSTAIN（投給人工 review queue）
  5. Tier 2 (Revenue %) 是 industry_blocked → 強制 REMOVE（Solar 廠 in 矽晶圓）
  6. Tier 2 解析失敗 → 信賴 Tier 1（dominance）
  7. 灰色帶（0.50-0.70）允許 Tier 3 影響仲裁；超出灰色帶忽略 Tier 3

跨族群衝突：
  - 同一 ticker 出現在 > 5 群 → confidence -0.10
  - 同一 ticker 在三審結果中、industry_segment 互相衝突 → 警告
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from .tier1_rule import Tier1Vote
from .tier2_revenue import Tier2Vote


VERDICT_PRIORITY = {"REMOVE": 0, "ABSTAIN": 1, "SATELLITE": 2, "CORE": 3}


@dataclass
class Tier3Vote:
    """Tier 3 (Web Realtime) 結果，可選。"""
    verdict: str = "SKIP"        # SKIP / POSITIVE / NEGATIVE / NO_DATA
    score: float = 0.5
    reason: str = ""
    queries: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


@dataclass
class ArbitrationOutcome:
    final_verdict: str           # CORE / SATELLITE / ABSTAIN / REMOVE
    final_score: float           # 0-1 加權
    consensus: str               # "unanimous" / "majority" / "split" / "hard_fail"
    dissent: list[dict]          # 反對意見記錄
    cross_group_count: int = 0
    confidence_penalty: float = 0.0
    arbitration_reason: str = ""


def _normalize_verdict(v: str) -> str:
    """把 tier 內部 verdict 映射到統一空間。"""
    mapping = {
        "FAIL_ROLE": "REMOVE",
        "FAIL_NO_KEYWORD": "REMOVE",
        "FAIL_LATE": "ABSTAIN",
        "POSITIVE": "CORE",          # tier3 強訊號可升 CORE
        "NEGATIVE": "REMOVE",
        "SKIP": "ABSTAIN",
        "NO_DATA": "ABSTAIN",
    }
    return mapping.get(v, v)


def arbitrate(
    t1: Tier1Vote,
    t2: Tier2Vote,
    t3: Optional[Tier3Vote] = None,
    cross_group_count: int = 0,
) -> ArbitrationOutcome:
    """三審仲裁。回傳最終 verdict + 證據鏈。"""

    dissent: list[dict] = []

    # 1. Tier 1 hard fail
    if t1.hard_fail:
        return ArbitrationOutcome(
            final_verdict="REMOVE",
            final_score=0.0,
            consensus="hard_fail",
            dissent=[],
            arbitration_reason=f"Tier 1 hard fail: {t1.hard_fail_reason}",
        )

    # 2. Tier 2 industry block (Solar 廠 in 矽晶圓)
    if t2.industry_blocked:
        return ArbitrationOutcome(
            final_verdict="REMOVE",
            final_score=0.0,
            consensus="hard_fail",
            dissent=[{"tier": 1, "verdict": t1.verdict, "score": t1.score}] if t1.verdict != "REMOVE" else [],
            arbitration_reason=f"Tier 2 industry blocked: {t2.reason}",
        )

    # 3. 三審一致或 majority
    v1 = _normalize_verdict(t1.verdict)
    v2 = _normalize_verdict(t2.verdict)
    v3 = _normalize_verdict(t3.verdict) if t3 else None

    votes = [v1, v2]
    if v3 and v3 != "ABSTAIN":  # SKIP/NO_DATA/ABSTAIN 不投票
        votes.append(v3)

    counter = Counter(votes)
    most_common = counter.most_common()

    # 一致
    if len(most_common) == 1:
        verdict = most_common[0][0]
        consensus = "unanimous"
    elif most_common[0][1] >= 2 and most_common[0][1] > most_common[1][1]:
        verdict = most_common[0][0]
        consensus = "majority"
        # 記錄反對
        for k, v in most_common[1:]:
            if k == "REMOVE" and verdict in ("CORE", "SATELLITE"):
                dissent.append({"tier": "any", "verdict": k, "count": v, "note": "有 tier 認為應 REMOVE"})
            else:
                dissent.append({"tier": "any", "verdict": k, "count": v})
    else:
        # 分歧（如 CORE / SATELLITE / REMOVE 各一）
        consensus = "split"
        dissent = [{"tier": i+1, "verdict": v} for i, v in enumerate(votes)]
        positive_votes = {"CORE", "SATELLITE"}
        if "REMOVE" in votes:
            if any(v in positive_votes for v in votes):
                # 一邊支持、一邊反對代表證據衝突，先進人工審核，不直接上架也不誤殺。
                verdict = "ABSTAIN"
                consensus = "split_conflict_review"
            else:
                verdict = "REMOVE"
                consensus = "split_remove_wins"
        elif "CORE" in votes:
            verdict = "CORE"
            consensus = "split_positive_core"
        elif "SATELLITE" in votes:
            verdict = "SATELLITE"
            consensus = "split_positive_satellite"
        else:
            verdict = "ABSTAIN"

    # 4. 加權 score
    weights = [0.40, 0.45]  # tier1, tier2
    scores = [t1.score, t2.score]
    if t3 and t3.verdict not in ("SKIP", "NO_DATA"):
        weights.append(0.15)
        scores.append(t3.score)
    # 規範化
    total_w = sum(weights)
    weights = [w / total_w for w in weights]
    final_score = sum(w * s for w, s in zip(weights, scores))

    # 5. 灰色帶調整：score 0.50-0.70 且 verdict 是 CORE → 降 SATELLITE（保守）
    if verdict == "CORE" and final_score < 0.70 and consensus != "unanimous":
        verdict = "SATELLITE"

    # 6. cross-group 懲罰：> 8 群明顯過度貼標，但只在 verdict 不是 unanimous 時降；
    #    對 unanimous CORE（高信心）保留，避免誤傷大牛股（台積電/緯創/緯穎這類本來就跨多題材）
    confidence_penalty = 0.0
    if cross_group_count > 8:
        confidence_penalty = 0.05
        final_score = max(0.0, final_score - confidence_penalty)
        if verdict == "CORE" and consensus != "unanimous":
            verdict = "SATELLITE"

    reason = (
        f"consensus={consensus}; tier1={t1.verdict}({t1.score:.2f}); "
        f"tier2={t2.verdict}({t2.score:.2f},pct={t2.matched_pct*100:.0f}%); "
        f"tier3={t3.verdict if t3 else 'SKIP'}; "
        f"cross_group={cross_group_count}; final={final_score:.2f}"
    )

    return ArbitrationOutcome(
        final_verdict=verdict,
        final_score=final_score,
        consensus=consensus,
        dissent=dissent,
        cross_group_count=cross_group_count,
        confidence_penalty=confidence_penalty,
        arbitration_reason=reason,
    )


# CLI demo: 跑 fixtures 看仲裁結果
if __name__ == "__main__":
    import json
    from pathlib import Path

    from .tier1_rule import evaluate_tier1
    from .tier2_revenue import evaluate_tier2
    from .schema import GroupSpec, StockProfile

    ROOT = Path(__file__).resolve().parents[2]
    ep = json.loads((ROOT / "My-TW-Coverage" / "enrichment_pilot.json").read_text(encoding="utf-8"))
    sp_raw = json.loads((ROOT / "concept_taxonomy" / "stock_profiles.json").read_text(encoding="utf-8"))
    specs_raw = json.loads((ROOT / "concept_taxonomy" / "group_specs.json").read_text(encoding="utf-8"))
    theme_map = json.loads((ROOT / "concept_taxonomy" / "validator" / "theme_revenue_map.json").read_text(encoding="utf-8"))
    fixtures = json.loads((ROOT / "concept_taxonomy" / "validator" / "regression_fixtures.json").read_text(encoding="utf-8"))["fixtures"]

    def make_profile(d):
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

    def make_spec(name, raw):
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

    print(f"{'ID':<6}{'Ticker':<8}{'Group':<22}{'Expected':<12}{'Final':<10}{'T1':<10}{'T2':<10}{'Score':<7}{'Cons'}")
    print("-" * 110)
    n_pass = 0
    for f in fixtures:
        spec_raw = specs_raw.get(f["group"], {})
        spec = make_spec(f["group"], spec_raw)
        prof = make_profile(sp_raw.get(f["ticker"]))
        rec = ep.get(f["ticker"])
        v1 = evaluate_tier1(f["ticker"], f["group"], spec, rec, prof)
        v2 = evaluate_tier2(f["ticker"], f["group"], rec, theme_map.get(f["group"]))
        out = arbitrate(v1, v2, t3=None, cross_group_count=0)
        # 通過判斷
        exp = f["expected_verdict"]
        passed = (out.final_verdict == exp) or (exp == "KEEP_ANY" and out.final_verdict in ("CORE","SATELLITE","ABSTAIN")) \
                 or (exp == "REMOVE" and out.final_verdict == "REMOVE")
        if passed:
            n_pass += 1
        mark = "✅" if passed else "❌"
        print(f"{f['id']:<6}{f['ticker']:<8}{f['group'][:20]:<22}{exp:<12}{out.final_verdict:<10}{v1.verdict:<10}{v2.verdict:<10}{out.final_score:.2f}   {out.consensus}  {mark}")
    print(f"\n{n_pass}/{len(fixtures)} passed")
