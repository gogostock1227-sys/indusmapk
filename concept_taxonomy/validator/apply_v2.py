"""
Day 6：產出 master_patch_v2.json + 套用機制（相容 _apply_patches.py）。

入口：
    python -m validator.apply_v2                # 只產 master_patch_v2.json
    python -m validator.apply_v2 --apply        # 同上 + 真的寫回 concept_groups.py（含 .bak3 備份）

格式（與 _apply_patches.py 相容）：
    {
      "group_name": {
        "keep": ["ticker1", "ticker2", ...],
        "removed": [{"ticker": "X", "reason": "...", "reclassify_to": "...", "confidence": 0.91}],
        "source": "validator_v2",
        "validated_at": "2026-04-26T...",
        "avg_confidence": 0.83
      }
    }

策略：
  - core + satellite → keep
  - remove → 進 removed 並建議 reclassify
  - skipped → 保守保留（不動）
  - permissive 群（spec 沒嚴格定義）→ 不產 patch
  - deprecated 群 → keep=[]（整群移除）
  - merge_into 群 → keep=[] + 標記 merge_into
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

TAXONOMY_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = TAXONOMY_DIR.parent


def parse_concept_groups() -> dict[str, list[str]]:
    import re
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


def suggest_reclassify(removed_ticker: str, reason: str, profiles: dict, specs: dict) -> str:
    """根據被移除個股的 profile，建議該移到哪個族群。

    啟發式：找 spec 的 allowed_positions 包含該 ticker.position 的群，回第一個。
    """
    p = profiles.get(removed_ticker, {})
    pos = p.get("supply_chain_position", "")
    if not pos:
        return ""
    candidates = []
    for g_name, g_spec in specs.items():
        if g_name.startswith("_"):
            continue
        if g_spec.get("deprecated") or g_spec.get("merge_into"):
            continue
        if pos in g_spec.get("allowed_positions", []) and pos not in g_spec.get("forbidden_positions", []):
            candidates.append(g_name)
    return candidates[0] if candidates else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="跑 _apply_patches.py 寫回 concept_groups.py")
    args = ap.parse_args()

    print("[1/3] 載入資料 ...")
    df = pd.read_parquet(TAXONOMY_DIR / "validation_results.parquet")
    specs = json.loads((TAXONOMY_DIR / "group_specs.json").read_text(encoding="utf-8"))
    profiles = json.loads((TAXONOMY_DIR / "stock_profiles.json").read_text(encoding="utf-8"))
    groups_in_file = parse_concept_groups()

    print(f"  {len(df)} pair, {len(specs)} specs, {len(profiles)} profiles, {len(groups_in_file)} 群")

    print("[2/3] 產 master_patch_v2.json ...")
    patch: dict = {}
    stats = Counter()

    for group_name, members in groups_in_file.items():
        spec = specs.get(group_name, {})
        if spec.get("deprecated"):
            patch[group_name] = {
                "keep": [],
                "source": "validator_v2",
                "deprecated": True,
                "deprecation_reason": spec.get("deprecation_reason", ""),
                "members_reclassify_to": spec.get("members_reclassify_to", []),
                "validated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            stats["deprecated_groups"] += 1
            continue

        if spec.get("merge_into"):
            patch[group_name] = {
                "keep": [],
                "source": "validator_v2",
                "merge_into": spec["merge_into"],
                "validated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            stats["merge_groups"] += 1
            continue

        df_g = df[df["group"] == group_name]
        if len(df_g) == 0:
            # permissive group 或沒驗證 — 保留原成員
            patch[group_name] = {
                "keep": list(members),
                "source": "validator_v2_permissive_kept",
                "note": "spec 未嚴格定義，保留原成員待 LLM 升級",
                "validated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            stats["permissive_groups"] += 1
            continue

        # 嚴格驗證的群
        keep = []
        removed = []
        for _, row in df_g.iterrows():
            tk = row["ticker"]
            v = row["verdict"]
            if v in ("core", "satellite"):
                keep.append(tk)
            elif v == "remove":
                reclassify_to = suggest_reclassify(tk, row["hard_fail_reason"] or "", profiles, specs)
                removed.append({
                    "ticker": tk,
                    "name": row["name"],
                    "reason": (row["hard_fail_reason"] or row["rationale"])[:200],
                    "reclassify_to": reclassify_to,
                    "confidence": float(row["confidence"]),
                })
            elif v == "skipped":
                # 保守：profile 不完整時保留原成員
                keep.append(tk)
                stats["skipped_kept"] += 1

        avg_conf = float(df_g["confidence"].mean()) if len(df_g) else 0.0
        patch[group_name] = {
            "keep": keep,
            "removed": removed,
            "source": "validator_v2",
            "mode": "auto",
            "validated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "avg_confidence": round(avg_conf, 3),
        }
        stats["validated_groups"] += 1
        stats["total_kept"] += len(keep)
        stats["total_removed"] += len(removed)

    out = TAXONOMY_DIR / "master_patch_v2.json"
    out.write_text(json.dumps(patch, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ {out}")
    print(f"  統計：")
    for k, v in stats.items():
        print(f"    {k}: {v}")

    if args.apply:
        print("\n[3/3] 套用到 concept_groups.py ...")
        # 備份
        target = PROJECT_ROOT / "concept_groups.py"
        backup = PROJECT_ROOT / "concept_groups.py.bak3"
        shutil.copy(target, backup)
        print(f"  備份 → {backup}")

        # 把 v2 patch 暫時當 master_patch.json 給 _apply_patches.py 吃
        # 用 os.rename 而不是 _apply_patches.py 改路徑（保持向下相容）
        patch_path = TAXONOMY_DIR / "master_patch.json"
        backup_patch = TAXONOMY_DIR / "master_patch.json.preV2"
        if patch_path.exists():
            shutil.copy(patch_path, backup_patch)
            print(f"  原 master_patch.json 備份 → {backup_patch}")
        shutil.copy(out, patch_path)

        result = subprocess.run(
            [sys.executable, str(TAXONOMY_DIR / "_apply_patches.py")],
            capture_output=True, text=True, encoding="utf-8",
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"⚠ apply 失敗：{result.stderr}")
            print(f"  恢復原檔：cp {backup} {target}")
            shutil.copy(backup, target)
        else:
            print("  ✓ 套用成功")
    else:
        print("\n[3/3] (dry run，加 --apply 才會寫回 concept_groups.py)")


if __name__ == "__main__":
    main()
