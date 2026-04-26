"""Regression Runner — 比對 fixtures 期望 verdict 與 v3/v4 master_patch 的實際結果。

Usage:
    python -m concept_taxonomy.validator.regression_runner --pipeline=v3
    python -m concept_taxonomy.validator.regression_runner --pipeline=v4 --strict
    python -m concept_taxonomy.validator.regression_runner --baseline   # 跑 v3 並寫入 baseline 目錄

設計原則:
- 不重新跑 pipeline，僅讀既有 master_patch_*.json 結果
- 若 master_patch 不存在，提示使用者先跑 pure_play_pipeline.py / strict_pipeline_v4.py
- 輸出 regression_test.json 與 stdout summary
- 任何 fixture 未通過時 exit code = 1（CI/Phase fail-fast 用）
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TAXONOMY_DIR = ROOT / "concept_taxonomy"
VALIDATOR_DIR = TAXONOMY_DIR / "validator"
VALIDATION_RUNS_DIR = TAXONOMY_DIR / "validation_runs"

FIXTURES_PATH = VALIDATOR_DIR / "regression_fixtures.json"


@dataclass
class FixtureResult:
    fixture_id: str
    ticker: str
    ticker_name: str
    group: str
    expected: str
    actual: str
    passed: bool
    reason: str
    evidence_source: str
    bucket_breakdown: dict


def lookup_verdict(group_record: dict, ticker: str) -> str:
    """從 v3/v4 master_patch 的單群記錄中查 ticker 落在哪個 bucket。

    v3 schema: {keep, core, satellite, abstain, removed[{ticker,name,reason}], source}
    v4 schema: {core, satellite, abstain, removed, evidence_trail, source}

    回傳: CORE / SATELLITE / ABSTAIN / REMOVE / NOT_IN_GROUP
    """
    if not isinstance(group_record, dict):
        return "GROUP_MISSING"

    # core
    if ticker in (group_record.get("core") or []):
        return "CORE"
    # satellite
    if ticker in (group_record.get("satellite") or []):
        return "SATELLITE"
    # abstain
    if ticker in (group_record.get("abstain") or []):
        return "ABSTAIN"
    # removed (list of dict)
    for rm in group_record.get("removed") or []:
        if isinstance(rm, dict) and rm.get("ticker") == ticker:
            return "REMOVE"
        if isinstance(rm, str) and rm == ticker:
            return "REMOVE"
    # permissive fallback: 只有 keep 沒拆 core/satellite
    if (group_record.get("source") or "").endswith("permissive"):
        if ticker in (group_record.get("keep") or []):
            return "PERMISSIVE_KEEP"
    # keep 通常只是 union，不單獨判斷
    return "NOT_IN_GROUP"


def verdict_match(expected: str, actual: str) -> bool:
    """判斷 actual verdict 是否符合 expected。

    - KEEP_ANY 接受 CORE / SATELLITE / ABSTAIN / PERMISSIVE_KEEP
    - REMOVE / NOT_IN_GROUP 視為「不在族群成員清單內」也算通過 REMOVE 預期
      （v3 永遠不會輸出 removed=[...] 因為它只把 keep 寫回 concept_groups.py）
    - 其他為精確比對
    """
    if expected == actual:
        return True
    if expected == "KEEP_ANY" and actual in {"CORE", "SATELLITE", "ABSTAIN", "PERMISSIVE_KEEP"}:
        return True
    if expected == "REMOVE" and actual in {"REMOVE", "NOT_IN_GROUP"}:
        # v3 把 REMOVE 的 ticker 直接從 concept_groups.py 清掉，所以可能也呈 NOT_IN_GROUP
        return True
    return False


def load_fixtures() -> list[dict]:
    data = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    return data["fixtures"]


def load_master_patch(pipeline: str) -> tuple[dict, Path]:
    """載入指定 pipeline 的 master_patch JSON。

    pipeline=v3 → concept_taxonomy/master_patch_v3.json
    pipeline=v4 → 取最新的 validation_runs/{ts}_strict_v4/master_patch_v4.json
    """
    if pipeline == "v3":
        p = TAXONOMY_DIR / "master_patch_v3.json"
        if not p.exists():
            print(f"[ERR] {p} not found；先跑 pure_play_pipeline.py 產生 v3 baseline。", file=sys.stderr)
            sys.exit(2)
        return json.loads(p.read_text(encoding="utf-8")), p
    if pipeline == "v4":
        # 找最新的 v4 run
        candidates = sorted(VALIDATION_RUNS_DIR.glob("*_strict_v4")) if VALIDATION_RUNS_DIR.exists() else []
        if not candidates:
            print("[ERR] 找不到 validation_runs/*_strict_v4/；先跑 strict_pipeline_v4.py。", file=sys.stderr)
            sys.exit(2)
        latest = candidates[-1]
        p = latest / "master_patch_v4.json"
        if not p.exists():
            print(f"[ERR] {p} not found", file=sys.stderr)
            sys.exit(2)
        return json.loads(p.read_text(encoding="utf-8")), p
    raise ValueError(f"unknown pipeline: {pipeline}")


def run(pipeline: str, baseline: bool = False) -> int:
    fixtures = load_fixtures()
    patch, patch_path = load_master_patch(pipeline)
    print(f"[regression] pipeline={pipeline} fixtures={len(fixtures)} source={patch_path.name}")

    results: list[FixtureResult] = []
    for f in fixtures:
        group_record = patch.get(f["group"], {})
        actual = lookup_verdict(group_record, f["ticker"])
        passed = verdict_match(f["expected_verdict"], actual)
        bucket = {
            "core_count": len(group_record.get("core") or []),
            "satellite_count": len(group_record.get("satellite") or []),
            "abstain_count": len(group_record.get("abstain") or []),
            "removed_count": len(group_record.get("removed") or []),
            "keep_count": len(group_record.get("keep") or []),
            "kind": group_record.get("source", "n/a"),
        }
        results.append(FixtureResult(
            fixture_id=f["id"],
            ticker=f["ticker"],
            ticker_name=f["ticker_name"],
            group=f["group"],
            expected=f["expected_verdict"],
            actual=actual,
            passed=passed,
            reason=f["reason"],
            evidence_source=f["evidence_source"],
            bucket_breakdown=bucket,
        ))

    # Summary
    n_pass = sum(1 for r in results if r.passed)
    n_fail = len(results) - n_pass
    print(f"\n[summary] {n_pass}/{len(results)} passed, {n_fail} failed\n")
    print(f"{'ID':<6}{'Ticker':<8}{'Name':<10}{'Group':<22}{'Expected':<12}{'Actual':<18}{'Result'}")
    print("-" * 96)
    for r in results:
        mark = "✅" if r.passed else "❌"
        name = (r.ticker_name or "")[:8]
        grp = (r.group or "")[:20]
        print(f"{r.fixture_id:<6}{r.ticker:<8}{name:<10}{grp:<22}{r.expected:<12}{r.actual:<18}{mark}")

    # 寫 regression_test.json
    if baseline:
        out_dir = VALIDATION_RUNS_DIR / f"baseline_{pipeline}"
    else:
        # 寫到最新 run 目錄（v4）或 baseline_v3
        if pipeline == "v3":
            out_dir = VALIDATION_RUNS_DIR / "baseline_v3"
        else:
            out_dir = patch_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "regression_test.json"
    out_payload = {
        "_meta": {
            "pipeline": pipeline,
            "fixtures_path": str(FIXTURES_PATH.relative_to(ROOT)),
            "patch_path": str(patch_path.relative_to(ROOT)),
            "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "passed": n_pass,
            "failed": n_fail,
            "total": len(results),
        },
        "results": [asdict(r) for r in results],
        "failed_ids": [r.fixture_id for r in results if not r.passed],
    }
    out_file.write_text(json.dumps(out_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[output] → {out_file.relative_to(ROOT)}")

    return 0 if n_fail == 0 else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pipeline", choices=["v3", "v4"], default="v3", help="比對哪個 pipeline 的結果")
    ap.add_argument("--baseline", action="store_true", help="寫到 validation_runs/baseline_{pipeline}/ 並當基準")
    ap.add_argument("--strict", action="store_true", help="任何 fixture 未通過即 exit 1（CI 用）")
    args = ap.parse_args()
    rc = run(args.pipeline, baseline=args.baseline)
    if args.strict:
        sys.exit(rc)


if __name__ == "__main__":
    main()
