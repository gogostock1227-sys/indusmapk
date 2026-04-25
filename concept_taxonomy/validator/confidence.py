"""
信心分數演算法 + verdict 分級。

公式（_TAXONOMY_SCHEMA.md L168-176 加權版）：
    score = 0.25*c1 + 0.40*c2 + 0.35*c3
          + 0.10 * coverage_present
          + 0.05 * web_recent_3m
          - 0.20 * any_hard_fail
          - 0.10 * downstream_demote_hit
    score = clamp(score, 0, 1)

分級：
    any hard_fail              → REMOVE
    score < 0.55               → REMOVE
    downstream_demote 且 not REMOVE → 強制 SATELLITE
    score ≥ 0.80               → CORE
    0.55 ≤ score < 0.80        → SATELLITE

註：core 不要求 c2_strong（HBM.md 樣本中 6770 力積電 themes=[HBM3E_HBM4, WOW] 只有 1 個
strong 重疊但仍被人工判為 core）。c2_strong 改為「rank within core」用途，由 report.py 排序時參考。
"""
from __future__ import annotations

from datetime import datetime, timezone

from .schema import (
    CheckResult,
    GroupSpec,
    StockProfile,
    ValidationResult,
    Verdict,
)


# 邊界仲裁區間（落於此區間觸發 LLM second-opinion）
LLM_SECOND_OPINION_BAND = (0.50, 0.70)


def compute_confidence(
    c1: CheckResult,
    c2: CheckResult,
    c3: CheckResult,
    coverage_present: bool,
    web_recent_3m: bool,
    downstream_demote_hit: bool,
) -> tuple[float, bool]:
    """回傳 (score, any_hard_fail)。"""
    any_hard_fail = c1.hard_fail or c2.hard_fail or c3.hard_fail

    score = (
        c1.weight * (1.0 if c1.ok else 0.0)
        + c2.weight * (1.0 if c2.ok else 0.0)
        + c3.weight * (1.0 if c3.ok else 0.0)
        + (0.10 if coverage_present else 0.0)
        + (0.05 if web_recent_3m else 0.0)
        - (0.20 if any_hard_fail else 0.0)
        - (0.10 if downstream_demote_hit else 0.0)
    )
    score = max(0.0, min(1.0, score))
    return score, any_hard_fail


def classify_verdict(
    score: float,
    any_hard_fail: bool,
    c2_strong: bool,
    downstream_demote_hit: bool,
) -> Verdict:
    """依分數與 hard_fail 決定 verdict。c2_strong 留欄位但已不影響 verdict。"""
    if any_hard_fail:
        return Verdict.REMOVE
    if score < 0.55:
        return Verdict.REMOVE
    if downstream_demote_hit:
        return Verdict.SATELLITE
    if score >= 0.80:
        return Verdict.CORE
    return Verdict.SATELLITE


def needs_llm_second_opinion(score: float, any_hard_fail: bool) -> bool:
    """落於 (0.50, 0.70) 邊界區間且無 hard_fail → 觸發 LLM 仲裁。"""
    if any_hard_fail:
        return False
    lo, hi = LLM_SECOND_OPINION_BAND
    return lo < score < hi


def build_validation_result(
    profile: StockProfile,
    spec: GroupSpec,
    c1: CheckResult,
    c2: CheckResult,
    c3: CheckResult,
    coverage_present: bool,
    web_recent_3m: bool,
    evidence_coverage: str = "",
    evidence_web: list[dict] | None = None,
) -> ValidationResult:
    """整合三道檢查結果，回傳完整 ValidationResult。"""
    downstream_demote_hit = profile.supply_chain_position in spec.downstream_demote

    score, any_hard_fail = compute_confidence(
        c1, c2, c3,
        coverage_present=coverage_present,
        web_recent_3m=web_recent_3m,
        downstream_demote_hit=downstream_demote_hit,
    )

    verdict = classify_verdict(
        score=score,
        any_hard_fail=any_hard_fail,
        c2_strong=c2.strong,
        downstream_demote_hit=downstream_demote_hit,
    )

    hard_fail_reason = ""
    if c1.hard_fail:
        hard_fail_reason = f"C1: {c1.reason}"
    elif c2.hard_fail:
        hard_fail_reason = f"C2: {c2.reason}"
    elif c3.hard_fail:
        hard_fail_reason = f"C3: {c3.reason}"

    rationale_parts = [c1.reason, c2.reason, c3.reason]
    if downstream_demote_hit:
        rationale_parts.append(f"位階「{profile.supply_chain_position}」屬下游應用，自動降為衛星")
    rationale = "；".join(rationale_parts)

    return ValidationResult(
        group=spec.group_name,
        ticker=profile.ticker,
        name=profile.name,
        verdict=verdict,
        confidence=round(score, 3),
        c1=c1,
        c2=c2,
        c3=c3,
        coverage_present=coverage_present,
        web_recent_3m=web_recent_3m,
        downstream_demote_hit=downstream_demote_hit,
        hard_fail_reason=hard_fail_reason,
        evidence_coverage=evidence_coverage,
        evidence_web=evidence_web or [],
        rationale=rationale,
        validated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
