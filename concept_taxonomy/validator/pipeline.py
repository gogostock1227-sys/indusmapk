"""
Day 5：主 orchestrator — 對 ~2500 (group, ticker) pair 跑全量驗證。

入口：
    python -m validator.pipeline               # dry run，只印小結
    python -m validator.pipeline --apply       # 寫入 validation_results.parquet

依賴：
  - group_specs.json  (Day 4 產出)
  - stock_profiles.json (Day 5 build_profiles 產出)
  - finlab snapshot (cache)
  - Coverage（懶載入，pair-level 用）

產出：
  - concept_taxonomy/validation_results.parquet
  - 標準輸出：每群驗證小結（core/satellite/remove counts）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

TAXONOMY_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = TAXONOMY_DIR.parent
sys.path.insert(0, str(TAXONOMY_DIR))

from validator.checks import run_all_checks  # noqa: E402
from validator.confidence import build_validation_result  # noqa: E402
from validator.evidence import extract_coverage  # noqa: E402
from validator.schema import GroupSpec, StockProfile  # noqa: E402


def parse_concept_groups() -> dict[str, list[str]]:
    src = (PROJECT_ROOT / "concept_groups.py").read_text(encoding="utf-8")
    pattern = re.compile(r'"([^"]+?)"\s*:\s*\[(.*?)\]', re.DOTALL)
    result = {}
    for m in pattern.finditer(src):
        name = m.group(1)
        if name == "_meta":
            continue
        tickers = re.findall(r'"(\d{4,5})"', m.group(2))
        if tickers:
            result[name] = tickers
    return result


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
        deprecated=d.get("deprecated", False),
        merge_into=d.get("merge_into"),
    )


def _build_profile(p: dict) -> StockProfile:
    return StockProfile(
        ticker=p["ticker"],
        name=p.get("name", ""),
        industry_segment=p.get("industry_segment", ""),
        supply_chain_position=p.get("supply_chain_position", ""),
        core_themes=p.get("core_themes", []),
        business_summary=p.get("business_summary", ""),
        twse_industry=p.get("twse_industry", ""),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="寫入 validation_results.parquet")
    ap.add_argument("--with-coverage", action="store_true", help="每 pair 都拉 Coverage 引文（慢）")
    args = ap.parse_args()

    print("[1/4] 載入 specs / profiles / concept_groups ...")
    specs_dict = json.loads((TAXONOMY_DIR / "group_specs.json").read_text(encoding="utf-8"))
    profiles_dict = json.loads((TAXONOMY_DIR / "stock_profiles.json").read_text(encoding="utf-8"))
    groups = parse_concept_groups()

    permissive_groups = {n for n, s in specs_dict.items()
                         if not n.startswith("_") and s.get("allowed_positions") == []
                         and s.get("required_themes_any") == []}
    deprecated_groups = {n for n, s in specs_dict.items()
                         if not n.startswith("_") and s.get("deprecated")}
    merge_groups = {n: s.get("merge_into") for n, s in specs_dict.items()
                    if not n.startswith("_") and s.get("merge_into")}

    print(f"  {len(groups)} 群（permissive {len(permissive_groups)} / deprecated {len(deprecated_groups)} / merge {len(merge_groups)}）")
    print(f"  {len(profiles_dict)} 個股 profile")

    print("[2/4] 跑 pair validation ...")
    rows = []
    by_group_counts: dict[str, Counter] = defaultdict(Counter)
    skipped_no_profile = 0
    skipped_deprecated = 0
    skipped_permissive = 0

    for group_name, members in groups.items():
        if group_name in deprecated_groups:
            skipped_deprecated += len(members)
            continue
        if group_name in permissive_groups:
            # permissive 群不跑驗證（沒嚴格 spec）；後續 LLM 升級時再跑
            skipped_permissive += len(members)
            continue
        if group_name not in specs_dict:
            continue

        spec = _build_spec(group_name, specs_dict[group_name])

        for sym in members:
            if sym not in profiles_dict:
                skipped_no_profile += 1
                continue
            p = profiles_dict[sym]
            if p.get("_skip_reason"):
                skipped_no_profile += 1
                continue
            profile = _build_profile(p)

            # 三維是否完整？缺 position 或 segment 直接降信心並跳過 hard fail 判斷
            if not profile.industry_segment or not profile.supply_chain_position:
                # 這檔 profile 不夠完整無法判斷，標記為待 LLM
                rows.append({
                    "group": group_name,
                    "ticker": sym,
                    "name": profile.name,
                    "verdict": "skipped",
                    "confidence": 0.0,
                    "c1_industry": False,
                    "c2_themes": False,
                    "c2_strong": False,
                    "c3_position": False,
                    "hard_fail_reason": "profile_incomplete",
                    "coverage_present": False,
                    "web_recent_3m": False,
                    "downstream_demote": False,
                    "evidence_coverage": "",
                    "evidence_web": "[]",
                    "rationale": f"profile 缺 segment={profile.industry_segment!r} 或 position={profile.supply_chain_position!r}",
                    "validated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                })
                by_group_counts[group_name]["skipped"] += 1
                continue

            c1, c2, c3 = run_all_checks(profile, spec)

            # 是否拉 Coverage（慢，只在 --with-coverage 開）
            coverage_present = False
            evidence_coverage = ""
            if args.with_coverage:
                cov = extract_coverage(sym, spec.core_keywords) if spec.core_keywords else None
                if cov and cov["found"]:
                    coverage_present = True
                    if cov["section_hits"]:
                        top = cov["section_hits"][0]
                        evidence_coverage = f"[{top['section']}] {top['quote']}"

            result = build_validation_result(
                profile=profile,
                spec=spec,
                c1=c1, c2=c2, c3=c3,
                coverage_present=coverage_present,
                web_recent_3m=False,
                evidence_coverage=evidence_coverage,
            )
            rows.append(result.to_row())
            by_group_counts[group_name][result.verdict.value] += 1

    print(f"  ✓ 跑完 {len(rows)} pair")
    print(f"    skipped: incomplete_profile={skipped_no_profile}, "
          f"deprecated={skipped_deprecated}, permissive={skipped_permissive}")

    # 全局統計
    overall = Counter()
    for cnt in by_group_counts.values():
        overall.update(cnt)
    print(f"\n[3/4] 全局判決分布：")
    for v, n in overall.most_common():
        print(f"  {v:<10s}: {n}")

    # Top REMOVE 族群
    print(f"\n  TOP 10 應移除最多的族群：")
    sorted_by_remove = sorted(by_group_counts.items(),
                              key=lambda kv: kv[1].get("remove", 0),
                              reverse=True)
    for g, cnt in sorted_by_remove[:10]:
        total = sum(cnt.values())
        if cnt.get("remove", 0) > 0:
            print(f"    {g:<25s} core={cnt.get('core',0)}  sat={cnt.get('satellite',0)}  remove={cnt.get('remove',0)}  total={total}")

    if args.apply:
        import pandas as pd
        out = TAXONOMY_DIR / "validation_results.parquet"
        df = pd.DataFrame(rows)
        df.to_parquet(out, index=False)
        print(f"\n[4/4] ✓ 寫入 {out}（{len(df)} rows）")

        # 同步寫一份 csv 方便人工 review
        csv_out = TAXONOMY_DIR / "validation_results.csv"
        df.to_csv(csv_out, index=False, encoding="utf-8-sig")
        print(f"        + {csv_out}")
    else:
        print("\n[4/4] (dry run，加 --apply 才會寫 parquet)")


if __name__ == "__main__":
    main()
