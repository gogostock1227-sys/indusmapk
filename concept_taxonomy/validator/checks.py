"""
三道驗證：

  C1 (weight 0.25)  — industry_segment 板塊比對
  C2 (weight 0.40)  — core_themes 與族群必要題材交集
  C3 (weight 0.35)  — supply_chain_position 在族群允許位階白名單

任一 hard_fail（forbidden_position 或 forbidden_theme）→ 直接 REMOVE。
"""
from __future__ import annotations

from .schema import GroupSpec, StockProfile, CheckResult


def check_industry_segment(profile: StockProfile, spec: GroupSpec) -> CheckResult:
    """C1: profile.industry_segment 必須在 spec.allowed_segments 內。

    例：
      - HBM 族群 allowed_segments=[AI_SEMI]；3533 嘉澤 industry_segment=ELEC_COMP → fail
      - AI伺服器 allowed_segments=[COMP_HW, ELEC_COMP, POWER_GREEN, AI_SEMI]；2317 鴻海 (COMP_HW) → pass
    """
    ok = profile.industry_segment in spec.allowed_segments
    reason = (
        f"產業板塊匹配 ({profile.industry_segment})"
        if ok
        else f"產業板塊不匹配（個股 {profile.industry_segment} vs 族群允許 {spec.allowed_segments}）"
    )
    return CheckResult(
        name="C1_industry",
        ok=ok,
        weight=0.25,
        reason=reason,
        evidence=[f"finlab.產業類別={profile.twse_industry}"] if profile.twse_industry else [],
    )


def check_themes(profile: StockProfile, spec: GroupSpec) -> CheckResult:
    """C2: profile.core_themes ∩ spec.required_themes_any ≥ 1，且不命中 forbidden_themes。

    強升條件：profile.core_themes ∩ spec.required_themes_strong ≥ 2 → strong=True (core 升級)
    Hard fail：命中 spec.forbidden_themes → 直接 REMOVE
    """
    profile_themes = set(profile.core_themes)

    forbidden_hit = profile_themes & set(spec.forbidden_themes)
    if forbidden_hit:
        return CheckResult(
            name="C2_themes",
            ok=False,
            weight=0.40,
            reason=f"命中禁忌題材：{sorted(forbidden_hit)}",
            hard_fail=True,
            evidence=[f"profile.core_themes={profile.core_themes}"],
        )

    inter_any = profile_themes & set(spec.required_themes_any)
    inter_strong = profile_themes & set(spec.required_themes_strong)
    # 若 spec 沒指定 required_themes_any（傳統產業如鋼鐵/航運），視為 vacuous true
    if not spec.required_themes_any:
        ok = True
        strong = False
    else:
        ok = len(inter_any) >= 1
        strong = len(inter_strong) >= 2

    if ok:
        reason = f"必要題材交集：{sorted(inter_any)}"
        if strong:
            reason += f"（強：{sorted(inter_strong)}）"
    else:
        reason = (
            f"未命中任何必要題材（個股題材 {sorted(profile_themes)} "
            f"vs 族群必要 {sorted(spec.required_themes_any)}）"
        )
    return CheckResult(
        name="C2_themes",
        ok=ok,
        weight=0.40,
        reason=reason,
        strong=strong,
        evidence=[f"profile.core_themes={profile.core_themes}"],
    )


def check_position(profile: StockProfile, spec: GroupSpec) -> CheckResult:
    """C3: profile.supply_chain_position 在 allowed_positions 內，且不在 forbidden_positions。

    Hard fail：命中 forbidden_positions → 直接 REMOVE
    例：HBM 族群 forbidden=[IDM_NAND, END_USER, SVC_SAAS]；6206 飛捷 position=END_USER → REMOVE。
    """
    pos = profile.supply_chain_position

    if spec.hard_whitelist and profile.ticker not in set(spec.hard_whitelist):
        return CheckResult(
            name="C3_position",
            ok=False,
            weight=0.35,
            reason=(
                f"{spec.group_name} 採硬白名單；{profile.ticker} 不在 "
                f"{spec.hard_whitelist}；個股位階={pos}，供應商/設備/耗材/通路不得列入本體族群"
            ),
            hard_fail=True,
        )

    if pos in spec.forbidden_positions:
        return CheckResult(
            name="C3_position",
            ok=False,
            weight=0.35,
            reason=f"位階「{pos}」在禁區（族群 forbidden={spec.forbidden_positions}）",
            hard_fail=True,
        )

    ok = pos in spec.allowed_positions
    reason = (
        f"位階「{pos}」在允許白名單內"
        if ok
        else f"位階「{pos}」不在白名單（族群 allowed={spec.allowed_positions}）"
    )
    return CheckResult(
        name="C3_position",
        ok=ok,
        weight=0.35,
        reason=reason,
    )


def run_all_checks(
    profile: StockProfile, spec: GroupSpec
) -> tuple[CheckResult, CheckResult, CheckResult]:
    """跑完三道。回傳順序固定：C1, C2, C3。"""
    return (
        check_industry_segment(profile, spec),
        check_themes(profile, spec),
        check_position(profile, spec),
    )
