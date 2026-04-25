"""
已知誤分類回歸測試（Hard Gate）。

對 _FINAL_REPORT.md 已記錄的 10+ 案例 + 使用者紅線（嘉澤反模式），逐一跑三道檢查
並驗證 verdict 與 reason 命中預期。任一失敗都是阻斷性問題。
"""
from __future__ import annotations

import pytest

from validator.checks import run_all_checks
from validator.confidence import build_validation_result
from validator.schema import GroupSpec, StockProfile, Verdict


def _build_profile(p: dict) -> StockProfile:
    return StockProfile(
        ticker=p["ticker"],
        name=p["name"],
        industry_segment=p["industry_segment"],
        supply_chain_position=p["supply_chain_position"],
        core_themes=p.get("core_themes", []),
        business_summary=p.get("business_summary", ""),
        twse_industry=p.get("twse_industry", ""),
    )


def _build_spec(name: str, s: dict) -> GroupSpec:
    return GroupSpec(
        group_name=name,
        allowed_segments=s.get("allowed_segments", []),
        allowed_positions=s.get("allowed_positions", []),
        required_themes_any=s.get("required_themes_any", []),
        required_themes_strong=s.get("required_themes_strong", []),
        forbidden_positions=s.get("forbidden_positions", []),
        forbidden_themes=s.get("forbidden_themes", []),
        downstream_demote=s.get("downstream_demote", []),
        deprecated=s.get("deprecated", False),
        merge_into=s.get("merge_into"),
        members_reclassify_to=s.get("members_reclassify_to", []),
    )


def _validate(spec: GroupSpec, profile: StockProfile):
    c1, c2, c3 = run_all_checks(profile, spec)
    return build_validation_result(
        profile=profile,
        spec=spec,
        c1=c1, c2=c2, c3=c3,
        coverage_present=False,   # Day 2 才接 Coverage
        web_recent_3m=False,      # Day 3 才接 Web
    )


def test_known_issues_loaded(known_issues: list):
    assert len(known_issues) >= 18, f"known_issues 案例數 {len(known_issues)} 不足"


def test_pair_level_known_issues(known_issues: list, specs: dict, profiles: dict):
    """pair-level 案例（ticker != __GROUP_LEVEL__）逐一回歸。"""
    failures = []
    for case in known_issues:
        if case["ticker"] == "__GROUP_LEVEL__":
            continue
        group_name = case["group"]
        ticker = case["ticker"]
        case_id = case["id"]

        if group_name not in specs:
            failures.append(f"[{case_id}] specs 缺族群「{group_name}」")
            continue
        if ticker not in profiles:
            failures.append(f"[{case_id}] profiles 缺個股 {ticker}")
            continue

        spec = _build_spec(group_name, specs[group_name])
        profile = _build_profile(profiles[ticker])
        result = _validate(spec, profile)

        # 1. verdict 比對
        expected = Verdict(case["expected_verdict"])
        if result.verdict != expected:
            failures.append(
                f"[{case_id}] {group_name} × {ticker} {profile.name}: "
                f"verdict 期望 {expected.value} 但得 {result.verdict.value}; "
                f"score={result.confidence}, rationale={result.rationale}"
            )
            continue

        # 2. reason 包含關鍵字
        for kw in case.get("expected_reason_contains", []):
            if kw not in result.rationale and kw not in result.hard_fail_reason:
                failures.append(
                    f"[{case_id}] reason 應含「{kw}」但實際：{result.rationale}"
                )

        # 3. position 必須等於指定值
        exp_pos = case.get("expected_position")
        if exp_pos and profile.supply_chain_position != exp_pos:
            failures.append(
                f"[{case_id}] position 期望 {exp_pos} 但實際 {profile.supply_chain_position}"
            )

        # 4. themes 必須包含
        for must_in in case.get("expected_themes_must_include", []):
            if must_in not in profile.core_themes:
                failures.append(
                    f"[{case_id}] themes 缺必要題材 {must_in}（實際 {profile.core_themes}）"
                )

        # 5. themes 禁止出現（反模式）
        for must_not in case.get("expected_themes_must_exclude", []):
            if must_not in profile.core_themes:
                failures.append(
                    f"[{case_id}] themes 含禁忌題材 {must_not}（反模式）"
                )

    assert not failures, "已知誤分類回歸測試失敗：\n" + "\n".join(f"  - {f}" for f in failures)


def test_group_level_structural_issues(known_issues: list, specs: dict):
    """族群層級結構問題：deprecated / merge_into / members_reclassify_to。"""
    failures = []
    for case in known_issues:
        if case["ticker"] != "__GROUP_LEVEL__":
            continue
        group = case["group"]
        case_id = case["id"]

        if group not in specs:
            failures.append(f"[{case_id}] specs 缺族群「{group}」")
            continue
        spec_dict = specs[group]

        if "expected_group_deprecated" in case:
            if not spec_dict.get("deprecated"):
                failures.append(f"[{case_id}] 族群「{group}」應 deprecated=true")

        if "expected_group_merge_into" in case:
            expected_merge = case["expected_group_merge_into"]
            if spec_dict.get("merge_into") != expected_merge:
                failures.append(
                    f"[{case_id}] merge_into 期望 {expected_merge} 但實際 {spec_dict.get('merge_into')}"
                )

        if "expected_members_reclassify_to" in case:
            expected = case["expected_members_reclassify_to"]
            actual = spec_dict.get("members_reclassify_to", [])
            for tgt in expected:
                if tgt not in actual:
                    failures.append(
                        f"[{case_id}] members_reclassify_to 缺 {tgt}（實際 {actual}）"
                    )

    assert not failures, "結構問題回歸測試失敗：\n" + "\n".join(f"  - {f}" for f in failures)


@pytest.mark.parametrize("case_id_prefix", ["HBM_", "AISERVER_", "THERMAL_", "SIPHO_", "CONN_", "PCB_"])
def test_each_group_has_at_least_one_case(known_issues: list, case_id_prefix: str):
    """每個試點族群至少要有一個 known issue 案例。"""
    matching = [c for c in known_issues if c["id"].startswith(case_id_prefix)]
    assert matching, f"族群前綴 {case_id_prefix} 無任何回歸案例"
