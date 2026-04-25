"""
Day 2 Demo CLI：對 ABF載板 / HBM 等試點族群跑一次端到端驗證，並印出帶證據鏈的判決。

用法：
  python -m concept_taxonomy.validator.demo_evidence --group ABF載板
  python -m concept_taxonomy.validator.demo_evidence --group "HBM 高頻寬記憶體"

輸出：
  - 標準輸出：每檔個股的 verdict / score / 三道檢查 / Coverage 引用片段 / finlab 板塊推論
  - 證明 Day 2 evidence.py 真的能跑出帶證據的判決
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 讓 `python -m validator.demo_evidence` 與 `python demo_evidence.py` 都能跑
TAXONOMY_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TAXONOMY_DIR))

from validator.checks import run_all_checks  # noqa: E402
from validator.confidence import build_validation_result  # noqa: E402
from validator.evidence import (  # noqa: E402
    coverage_mentions_exclusion,
    extract_coverage,
    infer_segment_from_twse,
    load_finlab_snapshot,
    lookup_finlab,
)
from validator.schema import GroupSpec, StockProfile  # noqa: E402


def _load_specs() -> dict:
    return json.loads((TAXONOMY_DIR / "group_specs.json").read_text(encoding="utf-8"))


def _build_spec(name: str, d: dict) -> GroupSpec:
    return GroupSpec(
        group_name=name,
        allowed_segments=d.get("allowed_segments", []),
        allowed_positions=d.get("allowed_positions", []),
        required_themes_any=d.get("required_themes_any", []),
        required_themes_strong=d.get("required_themes_strong", []),
        forbidden_positions=d.get("forbidden_positions", []),
        forbidden_themes=d.get("forbidden_themes", []),
        downstream_demote=d.get("downstream_demote", []),
        core_keywords=d.get("core_keywords", []),
        exclusion_keywords=d.get("exclusion_keywords", []),
    )


def _read_concept_groups(group_name: str) -> list[str]:
    """從 concept_groups.py 抓出指定族群的成分股代號。"""
    src = (TAXONOMY_DIR.parent / "concept_groups.py").read_text(encoding="utf-8")
    # 簡易正則：找 "group_name": [ ... ]
    import re
    pattern = re.compile(
        rf'"{re.escape(group_name)}"\s*:\s*\[(.*?)\]',
        re.DOTALL,
    )
    m = pattern.search(src)
    if not m:
        return []
    block = m.group(1)
    return re.findall(r'"(\d{4,5})"', block)


def _profile_from_evidence(sym: str, spec: GroupSpec, snapshot) -> StockProfile | None:
    """
    從 finlab + Coverage 半自動建一個 StockProfile（給 demo 用）。
    - industry_segment 來自 TWSE 推論
    - supply_chain_position 與 core_themes 暫由 fixture 或 None（Day 3 LLM 才補完）
    """
    fl = lookup_finlab(sym, snapshot)
    if not fl["found"]:
        return None

    # 嘗試先從 fixtures 拿（如果該 sym 已在 Day 1 fixture 中）
    fixture_path = TAXONOMY_DIR / "tests" / "fixtures" / "test_profiles.json"
    fixtures = json.loads(fixture_path.read_text(encoding="utf-8"))
    if sym in fixtures:
        p = fixtures[sym]
        return StockProfile(
            ticker=sym,
            name=p["name"],
            industry_segment=p["industry_segment"],
            supply_chain_position=p["supply_chain_position"],
            core_themes=p.get("core_themes", []),
            business_summary=p.get("business_summary", ""),
            twse_industry=fl["twse_industry"],
        )

    # 沒在 fixture：用 finlab 推論板塊，position/themes 留空（Day 3 LLM 補）
    seg = infer_segment_from_twse(fl["twse_industry"]) or ""
    return StockProfile(
        ticker=sym,
        name=fl["name"],
        industry_segment=seg,
        supply_chain_position="",   # 待 Day 3 LLM
        core_themes=[],             # 待 Day 3 LLM
        twse_industry=fl["twse_industry"],
    )


def main():
    ap = argparse.ArgumentParser(description="Day 2 evidence-aware validation demo")
    ap.add_argument("--group", required=True, help="族群名稱（concept_groups.py key）")
    ap.add_argument("--no-finlab", action="store_true", help="跳過 finlab snapshot（離線測試用）")
    args = ap.parse_args()

    specs = _load_specs()
    if args.group not in specs:
        print(f"❌ specs 未定義族群「{args.group}」")
        sys.exit(1)
    spec = _build_spec(args.group, specs[args.group])

    if spec.deprecated if hasattr(spec, "deprecated") else specs[args.group].get("deprecated"):
        print(f"⚠️  族群「{args.group}」已標 deprecated，跳過 pair 驗證")
        return

    members = _read_concept_groups(args.group)
    print(f"\n══════════════════════════════════════════════════════════")
    print(f"  族群驗證：{args.group}（{len(members)} 檔成分股）")
    print(f"══════════════════════════════════════════════════════════\n")
    print(f"Spec 摘要：")
    print(f"  allowed_segments  = {spec.allowed_segments}")
    print(f"  allowed_positions = {spec.allowed_positions}")
    print(f"  required_any      = {spec.required_themes_any}")
    print(f"  forbidden_pos     = {spec.forbidden_positions[:8]}{'...' if len(spec.forbidden_positions) > 8 else ''}")
    print()

    snapshot = None if args.no_finlab else load_finlab_snapshot()

    counts = {"core": 0, "satellite": 0, "remove": 0, "skipped": 0}
    for sym in members:
        profile = _profile_from_evidence(sym, spec, snapshot)
        if profile is None:
            print(f"  {sym}  ⚠️ finlab 查無此檔（可能下市），SKIP")
            counts["skipped"] += 1
            continue

        c1, c2, c3 = run_all_checks(profile, spec)

        # Coverage 證據
        cov = extract_coverage(sym, spec.core_keywords) if spec.core_keywords else {"found": False}
        excl_hits = coverage_mentions_exclusion(sym, spec.exclusion_keywords)
        cov_quote = ""
        if cov.get("found") and cov["section_hits"]:
            top = cov["section_hits"][0]
            cov_quote = f"[{top['section']}] {top['quote']}"

        result = build_validation_result(
            profile=profile,
            spec=spec,
            c1=c1, c2=c2, c3=c3,
            coverage_present=cov.get("found", False),
            web_recent_3m=False,
            evidence_coverage=cov_quote,
        )

        counts[result.verdict.value] += 1

        verdict_icon = {"core": "🟢", "satellite": "🟡", "remove": "🔴"}[result.verdict.value]
        print(f"  {sym}  {profile.name:8s}  {verdict_icon} {result.verdict.value:<10s}  "
              f"score={result.confidence:.2f}  twse={profile.twse_industry}")
        if result.hard_fail_reason:
            print(f"        ↪ HARD FAIL: {result.hard_fail_reason}")
        if cov_quote:
            print(f"        📄 Coverage: {cov_quote[:120]}{'...' if len(cov_quote) > 120 else ''}")
        if excl_hits:
            print(f"        🚫 反證命中: {excl_hits}")
        if not profile.supply_chain_position:
            print(f"        ⚠ position 待 Day 3 LLM 補完（profile 未在 fixture）")

    print(f"\n────────────────────────────────────────────────────────")
    print(f"  小結：core={counts['core']}  satellite={counts['satellite']}  "
          f"remove={counts['remove']}  skipped={counts['skipped']}")
    print(f"────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    main()
