"""strict_pipeline_v4 — 三審合議驗證主流程（v4 主入口）。

Usage:
    # 跑完整全量驗證
    python -m concept_taxonomy.validator.strict_pipeline_v4

    # 只跑指定族群
    python -m concept_taxonomy.validator.strict_pipeline_v4 --group "AI伺服器"

    # 只跑 regression fixtures（fail-fast）
    python -m concept_taxonomy.validator.strict_pipeline_v4 --regression-only

    # 跑完並寫入 validation_runs/{ts}_strict_v4/
    python -m concept_taxonomy.validator.strict_pipeline_v4 --write

    # apply 不在這支處理；apply_validation_run.py 才負責套用到 concept_groups.py

主流程：
  1. 載入 concept_groups.py（成員清單）+ group_specs.json + stock_profiles.json
     + enrichment_pilot.json + theme_revenue_map.json
  2. 對每個 (group, ticker) pair：
     - Tier 1 (rule + dominance)
     - Tier 2 (revenue %)
     - Tier 3 (web, 目前 SKIP)
     - Arbitration → final_verdict
  3. 跨族群衝突偵測（同 ticker 出現 > 5 群懲罰）
  4. 產出：
     - master_patch_v4.json
     - evidence_trail.jsonl
     - abstain_queue.csv
     - manifest.json
     - regression_test.json（自動跑 fixtures）
     - diff_vs_previous.md（與上次 approved run 對比）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .arbitration import arbitrate, ArbitrationOutcome, Tier3Vote
from .schema import GroupSpec, StockProfile
from .tier1_rule import evaluate_tier1, Tier1Vote
from .tier2_revenue import evaluate_tier2, Tier2Vote
from .tier3_web import evaluate_tier3

ROOT = Path(__file__).resolve().parents[2]
TAXONOMY_DIR = ROOT / "concept_taxonomy"
VALIDATOR_DIR = TAXONOMY_DIR / "validator"
VALIDATION_RUNS_DIR = TAXONOMY_DIR / "validation_runs"

# 政策/事件概念股暫時走 conservative mode；客戶/供應鏈型概念股已改用
# My-TW-Coverage 的供應鏈/客戶章節 + Tier 2/3 驗證，不再整群豁免。
CUSTOMER_OR_POLICY_GROUPS = {
    "川普概念/關稅戰", "新南向/東南亞產能", "印度產能/印度概念",
    "日圓貶值受惠/台日合作", "美國製造回流/晶片法案",
    "重建/災後/基礎建設",
}


def parse_concept_groups() -> dict[str, list[str]]:
    """從 concept_groups.py 解析每群的 ticker list。"""
    src = (ROOT / "concept_groups.py").read_text(encoding="utf-8")
    groups: dict[str, list[str]] = {}
    cur = None
    for line in src.split("\n"):
        m = re.match(r'\s*"([^"]+)":\s*\[', line)
        if m:
            cur = m.group(1)
            groups[cur] = []
            continue
        m2 = re.search(r'"(\d{4,5})"', line)
        if m2 and cur is not None:
            groups[cur].append(m2.group(1))
    return groups


def make_spec(name: str, raw: dict) -> GroupSpec:
    return GroupSpec(
        group_name=name,
        allowed_segments=raw.get("allowed_segments", []),
        allowed_positions=raw.get("allowed_positions", []),
        required_themes_any=raw.get("required_themes_any", []),
        required_themes_strong=raw.get("required_themes_strong", []),
        forbidden_positions=raw.get("forbidden_positions", []),
        forbidden_themes=raw.get("forbidden_themes", []),
        downstream_demote=raw.get("downstream_demote", []),
        core_keywords=raw.get("core_keywords", []),
        exclusion_keywords=raw.get("exclusion_keywords", []),
        validation_mode=raw.get("validation_mode", "evidence"),
        hard_whitelist=raw.get("hard_whitelist", []),
        market_keywords=raw.get("market_keywords", []),
        market_evidence_required=raw.get("market_evidence_required", False),
        deprecated=raw.get("deprecated", False),
        merge_into=raw.get("merge_into"),
    )


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


def synthesize_theme_map_entry(group_name: str, spec: GroupSpec) -> dict | None:
    """從 group_specs 合成最低限度的 Tier 2 keyword map。

    用途：讓尚未手工建 `theme_revenue_map` 的族群也能全站驗證一輪，
    不再整群保守 abstain。這是「可追溯候選驗證」，不是人工精修 map。
    """
    required: list[str] = []
    for kw in [group_name, *spec.core_keywords, *spec.market_keywords]:
        if kw and kw not in required:
            required.append(kw)
    forbidden: list[str] = []
    for kw in [*spec.exclusion_keywords, *spec.forbidden_themes, *spec.forbidden_positions]:
        if kw and kw not in forbidden:
            forbidden.append(kw)
    if not required:
        return None
    return {
        "required_keywords": required,
        "forbidden_keywords": forbidden,
        "industry_must_not_be": [],
        "min_pct_for_core": 0.30,
        "min_pct_for_satellite": 0.05,
        "_synthetic": True,
    }


def evaluate_pair(
    ticker: str,
    group_name: str,
    spec: GroupSpec,
    enrichment_record: dict | None,
    profile: StockProfile | None,
    theme_map_entry: dict | None,
    cross_group_count: int,
    use_tier3: bool = False,
) -> tuple[ArbitrationOutcome, Tier1Vote, Tier2Vote, Tier3Vote | None]:
    """單個 pair 的完整三審合議。"""
    t1 = evaluate_tier1(ticker, group_name, spec, enrichment_record, profile)
    t2 = evaluate_tier2(ticker, group_name, enrichment_record, theme_map_entry)
    t3: Tier3Vote | None = None
    if use_tier3:
        # 灰色帶 trigger
        triggered = (
            t1.verdict != t2.verdict
            or 0.50 <= t1.score <= 0.70
            or 0.50 <= t2.score <= 0.70
        )
        if triggered:
            t3 = evaluate_tier3(ticker, group_name, spec.core_keywords)
    out = arbitrate(t1, t2, t3, cross_group_count=cross_group_count)
    return out, t1, t2, t3


def run_full_validation(
    groups_filter: str | None = None,
    use_tier3: bool = False,
    regression_only: bool = False,
) -> dict:
    """跑完整 v4 驗證。回傳 results dict。"""
    print(f"[strict_v4] 載入資料源 ...")
    groups = parse_concept_groups()
    specs_raw = json.loads((TAXONOMY_DIR / "group_specs.json").read_text(encoding="utf-8"))
    sp_raw = json.loads((TAXONOMY_DIR / "stock_profiles.json").read_text(encoding="utf-8"))
    ep = json.loads((ROOT / "My-TW-Coverage" / "enrichment_pilot.json").read_text(encoding="utf-8"))
    theme_map = json.loads((VALIDATOR_DIR / "theme_revenue_map.json").read_text(encoding="utf-8"))
    fixtures_data = json.loads((VALIDATOR_DIR / "regression_fixtures.json").read_text(encoding="utf-8"))
    fixtures = fixtures_data["fixtures"]

    print(f"  {len(groups)} 群、{sum(len(v) for v in groups.values())} 成員、"
          f"{len(specs_raw) - 1} specs（扣 _meta）、{len(sp_raw)} profiles、"
          f"{len(ep)} enrichment、{len(theme_map) - 1} theme maps")

    # 跨族群統計：每 ticker 在幾個群
    ticker_group_count: Counter = Counter()
    for g, members in groups.items():
        for tk in members:
            ticker_group_count[tk] += 1

    # Filter
    if groups_filter:
        targets = {groups_filter: groups.get(groups_filter, [])}
    else:
        targets = groups

    if regression_only:
        # 只跑 fixtures 列出的 (ticker, group) pair
        targets = defaultdict(list)
        for f in fixtures:
            targets[f["group"]].append(f["ticker"])

    # 逐 pair 跑
    print(f"\n[strict_v4] 對 {len(targets)} 群執行三審合議 ...")
    results: dict[str, dict] = {}
    evidence_trail: list[dict] = []
    abstain_queue: list[dict] = []
    overall = Counter()

    for g, members in targets.items():
        if not members:
            continue
        spec_raw_dict = specs_raw.get(g)
        if not spec_raw_dict or g.startswith("_"):
            # 沒 spec → permissive，跳過詳細驗證（後續 Phase 2 處理）
            results[g] = {
                "kind": "permissive_no_spec",
                "core": [],
                "satellite": [],
                "abstain": list(members),
                "removed": [],
                "source": "strict_v4_permissive_pending",
            }
            overall["permissive_groups"] += 1
            continue
        spec = make_spec(g, spec_raw_dict)
        if spec.deprecated:
            results[g] = {"kind": "deprecated", "core": [], "satellite": [], "abstain": [], "removed": [], "source": "strict_v4_deprecated"}
            overall["deprecated_groups"] += 1
            continue
        if spec.merge_into:
            results[g] = {"kind": "merge", "core": [], "satellite": [], "abstain": [], "removed": [], "source": "strict_v4_merge", "merge_into": spec.merge_into}
            overall["merge_groups"] += 1
            continue

        theme_entry = theme_map.get(g)
        synthetic_theme_map = False

        # 政策/事件概念股不使用既有人工 theme map；改用 specs 合成 map 跑可追溯驗證。
        if g in CUSTOMER_OR_POLICY_GROUPS:
            theme_entry = None
        if theme_entry is None:
            theme_entry = synthesize_theme_map_entry(g, spec)
            synthetic_theme_map = bool(theme_entry)

        # 保守模式：若沒 theme_revenue_map（多數族群目前未建模），不執行上架。
        # 嚴格口徑：ABSTAIN 不再寫入 keep；只有硬白名單可先進 CORE。
        if theme_entry is None:
            cores: list[str] = []
            satellites: list[str] = []
            abstains: list[str] = []
            removeds: list[dict] = []
            for tk in members:
                rec = ep.get(tk)
                prof = make_profile(sp_raw.get(tk))
                t1 = evaluate_tier1(tk, g, spec, rec, prof)
                if t1.hard_fail:
                    removeds.append({
                        "ticker": tk,
                        "name": (sp_raw.get(tk, {}) or {}).get("name", ""),
                        "reason": f"Tier 1 hard fail（保守模式）: {t1.hard_fail_reason}",
                    })
                elif spec.hard_whitelist and tk in set(spec.hard_whitelist):
                    cores.append(tk)
                else:
                    abstains.append(tk)
                    abstain_queue.append({
                        "group": g, "ticker": tk,
                        "reason": "缺 theme_revenue_map，證據不足，先不上架",
                        "tier1_verdict": t1.verdict, "tier2_verdict": "SKIP",
                        "matched_pct": 0.0,
                        "industry_tag": "",
                    })
                evidence_trail.append({
                    "group": g,
                    "ticker": tk,
                    "ticker_name": (sp_raw.get(tk, {}) or {}).get("name", ""),
                    "verdict": "CORE" if tk in cores else ("REMOVE" if any((r.get("ticker") == tk) for r in removeds) else "ABSTAIN"),
                    "score": round(t1.score, 4),
                    "consensus": "tier1_conservative",
                    "tier1": {
                        "verdict": t1.verdict,
                        "score": round(t1.score, 4),
                        "dominance": t1.dominance_verdict,
                        "matched_keyword": t1.matched_keyword,
                        "char_offset": t1.char_offset,
                        "role_exclusion": t1.role_exclusion,
                        "quote": t1.quote[:200],
                        "reason": t1.reason[:300],
                    },
                    "tier2": {"verdict": "SKIP", "reason": "no theme_revenue_map"},
                    "tier3": None,
                    "cross_group_count": ticker_group_count.get(tk, 0),
                    "dissent": [],
                    "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                })
            results[g] = {
                "kind": "strict_v4_conservative",
                "core": cores,
                "satellite": satellites,
                "abstain": abstains,
                "removed": removeds,
                "keep": cores + satellites,
                "source": "strict_v4_no_theme_map",
                "validated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "note": "尚未建立 theme_revenue_map，採嚴格上架：除硬白名單外全部 abstain，不顯示於網站。",
            }
            overall["conservative_groups"] += 1
            overall["core"] += len(cores)
            overall["satellite"] += len(satellites)
            overall["abstain"] += len(abstains)
            overall["remove"] += len(removeds)
            continue

        cores: list[str] = []
        satellites: list[str] = []
        abstains: list[str] = []
        removeds: list[dict] = []

        for tk in members:
            rec = ep.get(tk)
            prof = make_profile(sp_raw.get(tk))
            cgc = ticker_group_count.get(tk, 0)
            outcome, t1, t2, t3 = evaluate_pair(
                tk, g, spec, rec, prof, theme_entry, cgc, use_tier3=use_tier3
            )
            v = outcome.final_verdict
            if v == "CORE":
                cores.append(tk)
            elif v == "SATELLITE":
                satellites.append(tk)
            elif v == "ABSTAIN":
                abstains.append(tk)
                abstain_queue.append({
                    "group": g, "ticker": tk,
                    "reason": outcome.arbitration_reason,
                    "tier1_verdict": t1.verdict, "tier2_verdict": t2.verdict,
                    "matched_pct": round(t2.matched_pct, 4),
                    "industry_tag": t2.industry_tag,
                })
            elif v == "REMOVE":
                removeds.append({
                    "ticker": tk,
                    "name": (sp_raw.get(tk, {}) or {}).get("name", ""),
                    "reason": outcome.arbitration_reason,
                })

            # Evidence trail 一行一筆
            evidence_trail.append({
                "group": g,
                "ticker": tk,
                "ticker_name": (sp_raw.get(tk, {}) or {}).get("name", ""),
                "verdict": v,
                "score": round(outcome.final_score, 4),
                "consensus": outcome.consensus,
                "tier1": {
                    "verdict": t1.verdict,
                    "score": round(t1.score, 4),
                    "dominance": t1.dominance_verdict,
                    "matched_keyword": t1.matched_keyword,
                    "char_offset": t1.char_offset,
                    "role_exclusion": t1.role_exclusion,
                    "quote": t1.quote[:200],
                    "reason": t1.reason[:300],
                },
                "tier2": {
                    "verdict": t2.verdict,
                    "score": round(t2.score, 4),
                    "matched_pct": round(t2.matched_pct, 4),
                    "forbidden_pct": round(t2.forbidden_pct, 4),
                    "industry_tag": t2.industry_tag,
                    "industry_blocked": t2.industry_blocked,
                    "matched_keywords": t2.matched_keywords[:5],
                    "matched_lines": t2.matched_lines[:3],
                    "parse_failed": t2.parse_failed,
                    "reason": t2.reason[:300],
                },
                "tier3": {
                    "verdict": t3.verdict if t3 else "SKIP",
                    "reason": t3.reason if t3 else "not triggered",
                } if t3 else None,
                "cross_group_count": cgc,
                "dissent": outcome.dissent,
                "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })

        results[g] = {
            "kind": "strict_v4",
            "core": cores,
            "satellite": satellites,
            "abstain": abstains,
            "removed": removeds,
            "keep": cores + satellites,
            "source": "strict_v4_synthetic_theme_map" if synthetic_theme_map else "strict_v4",
            "theme_map_source": "synthetic_from_group_specs" if synthetic_theme_map else "theme_revenue_map",
            "validated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        overall["strict_groups"] += 1
        if synthetic_theme_map:
            overall["synthetic_theme_map_groups"] += 1
        overall["core"] += len(cores)
        overall["satellite"] += len(satellites)
        overall["abstain"] += len(abstains)
        overall["remove"] += len(removeds)

    # Regression fixtures pass/fail
    reg_results: list[dict] = []
    n_pass = 0
    for f in fixtures:
        g = f["group"]
        tk = f["ticker"]
        # 從 results lookup verdict
        rec = results.get(g, {})
        if tk in rec.get("core", []):
            actual = "CORE"
        elif tk in rec.get("satellite", []):
            actual = "SATELLITE"
        elif tk in rec.get("abstain", []):
            actual = "ABSTAIN"
        elif any((isinstance(r, dict) and r.get("ticker") == tk) for r in rec.get("removed", [])):
            actual = "REMOVE"
        else:
            actual = "NOT_IN_GROUP"
        exp = f["expected_verdict"]
        passed = (
            (actual == exp)
            or (exp == "KEEP_ANY" and actual in {"CORE", "SATELLITE", "ABSTAIN"})
            or (exp == "REMOVE" and actual in {"REMOVE", "NOT_IN_GROUP"})
        )
        if passed:
            n_pass += 1
        reg_results.append({
            "fixture_id": f["id"],
            "ticker": tk,
            "group": g,
            "expected": exp,
            "actual": actual,
            "passed": passed,
            "reason": f["reason"],
        })

    summary = {
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "groups_evaluated": len(results),
        "overall_counts": dict(overall),
        "regression": {
            "passed": n_pass,
            "failed": len(fixtures) - n_pass,
            "total": len(fixtures),
            "results": reg_results,
        },
    }

    return {
        "results": results,
        "evidence_trail": evidence_trail,
        "abstain_queue": abstain_queue,
        "summary": summary,
    }


def write_run(payload: dict, run_dir: Path):
    run_dir.mkdir(parents=True, exist_ok=True)
    # master_patch_v4
    (run_dir / "master_patch_v4.json").write_text(
        json.dumps(payload["results"], ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    # evidence_trail.jsonl
    with (run_dir / "evidence_trail.jsonl").open("w", encoding="utf-8") as f:
        for e in payload["evidence_trail"]:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    # regression_test.json
    (run_dir / "regression_test.json").write_text(
        json.dumps(payload["summary"]["regression"], ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    # abstain_queue.csv
    import csv
    with (run_dir / "abstain_queue.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["group", "ticker", "tier1_verdict", "tier2_verdict", "matched_pct", "industry_tag", "reason", "decision", "reviewer", "notes"])
        for a in payload["abstain_queue"]:
            w.writerow([a["group"], a["ticker"], a["tier1_verdict"], a["tier2_verdict"], a["matched_pct"], a.get("industry_tag", ""), a["reason"][:200], "", "", ""])
    # manifest
    (run_dir / "manifest.json").write_text(
        json.dumps({
            "run_id": run_dir.name,
            "ran_at": payload["summary"]["ran_at"],
            "validator_version": "v4.0.0",
            "fixtures_pass": f"{payload['summary']['regression']['passed']}/{payload['summary']['regression']['total']}",
            "groups_evaluated": payload["summary"]["groups_evaluated"],
            "overall_counts": payload["summary"]["overall_counts"],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"\n[strict_v4] 寫入 {run_dir.relative_to(ROOT)}/")
    for fn in ["master_patch_v4.json", "evidence_trail.jsonl", "regression_test.json", "abstain_queue.csv", "manifest.json"]:
        p = run_dir / fn
        if p.exists():
            print(f"  {fn} ({p.stat().st_size:,} bytes)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", help="只跑單群")
    ap.add_argument("--write", action="store_true", help="寫入 validation_runs/{ts}_strict_v4/")
    ap.add_argument("--regression-only", action="store_true", help="只跑 fixture 涉及的 (ticker, group)")
    ap.add_argument("--use-tier3", action="store_true", help="啟用 Tier 3 web (目前 stub)")
    ap.add_argument("--strict", action="store_true", help="regression 任一 fail 即 exit 1")
    args = ap.parse_args()

    payload = run_full_validation(
        groups_filter=args.group,
        use_tier3=args.use_tier3,
        regression_only=args.regression_only,
    )

    s = payload["summary"]
    reg = s["regression"]
    print("\n" + "=" * 70)
    print(f"[strict_v4] 完成。groups={s['groups_evaluated']}，"
          f"core={s['overall_counts'].get('core',0)}，"
          f"satellite={s['overall_counts'].get('satellite',0)}，"
          f"abstain={s['overall_counts'].get('abstain',0)}，"
          f"remove={s['overall_counts'].get('remove',0)}")
    print(f"[regression] {reg['passed']}/{reg['total']} passed, {reg['failed']} failed")
    if reg["failed"] > 0:
        print("[regression] FAILED fixtures:")
        for r in reg["results"]:
            if not r["passed"]:
                print(f"  - {r['fixture_id']} {r['ticker']} in {r['group']}: expected={r['expected']} actual={r['actual']}")

    if args.write:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = VALIDATION_RUNS_DIR / f"{ts}_strict_v4"
        write_run(payload, run_dir)

    if args.strict and reg["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
