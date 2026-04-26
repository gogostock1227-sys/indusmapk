"""apply_validation_run — 把 v4 驗證結果套用到 concept_groups.py（4 道 safety gate）。

Usage:
    # Dry-run 看 diff
    python -m concept_taxonomy.validator.apply_validation_run --run-id LATEST --dry-run

    # 實際 apply
    python -m concept_taxonomy.validator.apply_validation_run --run-id LATEST --approve

    # 強制（churn > 15% 時）
    python -m concept_taxonomy.validator.apply_validation_run --run-id LATEST --approve --force

Safety gates（任一 fail 即 abort，需 --force 才繞過 churn）：
  G1. 必須有 --approve flag
  G2. regression_test.json 必須全綠（任何 fixture fail 即 abort）
  G3. churn rate（變動成員占比）≤ 15%（除非 --force）
  G4. git working tree 必須乾淨（concept_groups.py 不能有未提交修改）

apply 行為：
  - 對每群：keep = core + satellite（abstain 只留審核清單，不上架）
  - 直接覆寫 concept_groups.py 的對應 group block
  - 自動備份原檔到 concept_groups.py.bak_v4_{timestamp}
  - 把套用後的 snapshot 存到 validation_runs/{run_id}/snapshot_concept_groups.py
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TAXONOMY_DIR = ROOT / "concept_taxonomy"
VALIDATION_RUNS_DIR = TAXONOMY_DIR / "validation_runs"
TARGET = ROOT / "concept_groups.py"


def find_run(run_id: str) -> Path:
    if run_id == "LATEST":
        runs = sorted(VALIDATION_RUNS_DIR.glob("*_strict_v4"))
        if not runs:
            print("[ERR] 沒有 strict_v4 run", file=sys.stderr)
            sys.exit(2)
        return runs[-1]
    p = VALIDATION_RUNS_DIR / run_id
    if not p.exists():
        print(f"[ERR] run not found: {p}", file=sys.stderr)
        sys.exit(2)
    return p


def gate_regression(run_dir: Path) -> tuple[bool, str]:
    p = run_dir / "regression_test.json"
    if not p.exists():
        return False, f"找不到 regression_test.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("failed", 0) > 0:
        return False, f"regression {data['failed']} fail（必須全綠）"
    return True, f"regression {data['passed']}/{data['total']} ✅"


def _parse_groups_filter(groups: str | None) -> set[str] | None:
    if not groups:
        return None
    return {g.strip() for g in groups.split(",") if g.strip()}


def compute_churn(run_dir: Path, groups_filter: set[str] | None = None) -> dict:
    """計算 v4 vs current concept_groups.py 的變動率。"""
    patch = json.loads((run_dir / "master_patch_v4.json").read_text(encoding="utf-8"))
    src = TARGET.read_text(encoding="utf-8")

    cur_groups: dict[str, list[str]] = {}
    cur_g = None
    for line in src.split("\n"):
        m = re.match(r'\s*"([^"]+)":\s*\[', line)
        if m:
            cur_g = m.group(1); cur_groups[cur_g] = []; continue
        m2 = re.search(r'"(\d{4,5})"', line)
        if m2 and cur_g is not None:
            cur_groups[cur_g].append(m2.group(1))

    total_old = total_new = added = removed = 0
    per_group = []
    for g, rec in patch.items():
        if groups_filter and g not in groups_filter:
            continue
        if rec.get("kind") in ("deprecated", "merge"):
            continue
        if "keep" in rec:
            new_keep = rec.get("keep") or []
        else:
            new_keep = rec.get("core", []) + rec.get("satellite", [])
        new_set = set(new_keep)
        old_set = set(cur_groups.get(g, []))
        added_g = new_set - old_set
        removed_g = old_set - new_set
        total_old += len(old_set)
        total_new += len(new_set)
        added += len(added_g)
        removed += len(removed_g)
        if added_g or removed_g:
            per_group.append({"group": g, "old": len(old_set), "new": len(new_set), "added": sorted(added_g), "removed": sorted(removed_g)})
    churn = (added + removed) / max(total_old, 1)
    return {
        "total_old": total_old,
        "total_new": total_new,
        "added": added,
        "removed": removed,
        "churn_rate": churn,
        "per_group": per_group,
    }


def gate_git_clean() -> tuple[bool, str]:
    try:
        out = subprocess.check_output(["git", "status", "--porcelain", str(TARGET.relative_to(ROOT))], cwd=ROOT, text=True).strip()
    except Exception as e:
        return False, f"git status 失敗：{e}"
    if out:
        return False, f"concept_groups.py 有未提交修改（請先 commit 或 stash）：\n{out}"
    return True, "git working tree 乾淨"


def render_diff(diff: dict, top_n: int = 30) -> str:
    """產出 markdown diff（最大變動 top_n 群）。"""
    lines = []
    lines.append(f"# v4 驗證 vs current concept_groups.py")
    lines.append(f"")
    lines.append(f"- 總成員：{diff['total_old']} → {diff['total_new']}")
    lines.append(f"- 新增：+{diff['added']}")
    lines.append(f"- 移除：−{diff['removed']}")
    lines.append(f"- Churn rate：{diff['churn_rate']*100:.1f}%")
    lines.append(f"")
    lines.append(f"## 變動最大的 {top_n} 群")
    sorted_grp = sorted(diff["per_group"], key=lambda x: len(x["added"]) + len(x["removed"]), reverse=True)
    for g in sorted_grp[:top_n]:
        lines.append(f"\n### {g['group']}（{g['old']} → {g['new']}）")
        if g["removed"]:
            lines.append(f"- **移除 {len(g['removed'])} 檔**: {', '.join(g['removed'])}")
        if g["added"]:
            lines.append(f"- **新增 {len(g['added'])} 檔**: {', '.join(g['added'])}")
    return "\n".join(lines)


def build_new_block(group_name: str, rec: dict) -> str:
    """產出新的 concept_groups.py 內 group block。

    格式（保留 v3 風格）：
        "群名": [
            # ── [核心 v4] ──
            "1234",  # name1
            ...
            # ── [衛星 v4] ──
            ...
            # ── [待人工 v4] ──
            ...
            # ── [已移除 v4] ──
            # 5285 界霖 ABSTAIN（reason）
            ...
        ],
    """
    cores = rec.get("core", [])
    satellites = rec.get("satellite", [])
    abstains = rec.get("abstain", [])
    removeds = rec.get("removed", [])

    lines = [f'    "{group_name}": [']
    if cores:
        lines.append(f'        # ── [核心 v4] dominance + revenue ≥ {len(cores)} 檔 ──')
        for tk in cores:
            lines.append(f'        "{tk}",')
    if satellites:
        lines.append(f'        # ── [衛星 v4] {len(satellites)} 檔 ──')
        for tk in satellites:
            lines.append(f'        "{tk}",')
    if abstains:
        lines.append(f'        # ── [待人工 v4 ABSTAIN，不上架] {len(abstains)} 檔 ──')
        for tk in abstains[:30]:
            lines.append(f'        # {tk} — 證據不足或分歧，保留於 abstain_queue.csv')
        if len(abstains) > 30:
            lines.append(f'        # ... 另 {len(abstains) - 30} 檔見 abstain_queue.csv')
    if removeds:
        lines.append(f'        # ── [v4 移除] {len(removeds)} 檔 ──')
        for r in removeds[:30]:  # 限制前 30 個註解
            tk = r.get("ticker") if isinstance(r, dict) else r
            name = r.get("name", "") if isinstance(r, dict) else ""
            reason = (r.get("reason", "") if isinstance(r, dict) else "")[:80]
            lines.append(f'        # {tk} {name} — {reason}')
    lines.append('    ],')
    return "\n".join(lines)


def replace_group_block(src: str, group_name: str, new_block: str) -> tuple[str, bool]:
    pattern = re.compile(
        rf'\s*"{re.escape(group_name)}":\s*\[[\s\S]*?\n\s*\],',
        re.MULTILINE,
    )
    m = pattern.search(src)
    if not m:
        return src, False
    return src[:m.start()] + "\n" + new_block + src[m.end():], True


def apply(run_dir: Path, force: bool, churn_pct_limit: float = 0.15, groups_filter: set[str] | None = None):
    print(f"[apply] run_dir={run_dir.relative_to(ROOT)}")
    if groups_filter:
        print(f"  scope: {', '.join(sorted(groups_filter))}")

    # ── G2: regression ──
    ok, msg = gate_regression(run_dir)
    print(f"  G2 regression: {msg}")
    if not ok:
        print("[abort] regression 不通過，禁止 apply", file=sys.stderr)
        sys.exit(1)

    # ── G3: churn ──
    diff = compute_churn(run_dir, groups_filter=groups_filter)
    print(f"  G3 churn: {diff['churn_rate']*100:.1f}% (added=+{diff['added']}, removed=−{diff['removed']})")
    if diff["churn_rate"] > churn_pct_limit and not force:
        print(f"[abort] churn rate {diff['churn_rate']*100:.1f}% > {churn_pct_limit*100:.0f}%；如確認可加 --force", file=sys.stderr)
        sys.exit(1)

    # ── G4: git clean ──
    ok, msg = gate_git_clean()
    print(f"  G4 git: {msg}")
    if not ok:
        if force:
            print("  G4 略過（--force）")
        else:
            print("[abort] git working tree 不乾淨；需先 commit 或加 --force", file=sys.stderr)
            sys.exit(1)

    # ── 落實 apply ──
    patch = json.loads((run_dir / "master_patch_v4.json").read_text(encoding="utf-8"))
    src = TARGET.read_text(encoding="utf-8")

    # 備份
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = TARGET.with_name(f"concept_groups.py.bak_v4_{ts}")
    shutil.copy(TARGET, backup)
    print(f"  備份 → {backup.name}")

    n_applied = 0
    n_skipped = []
    for g, rec in patch.items():
        if groups_filter and g not in groups_filter:
            continue
        if rec.get("kind") in ("deprecated", "merge"):
            continue
        new_block = build_new_block(g, rec)
        src, ok = replace_group_block(src, g, new_block)
        if ok:
            n_applied += 1
        else:
            n_skipped.append(g)

    TARGET.write_text(src, encoding="utf-8")
    print(f"  ✅ 套用 {n_applied} 群 → {TARGET.relative_to(ROOT)}")
    if n_skipped:
        print(f"  ⚠️ {len(n_skipped)} 群 regex 未命中（保留原樣）：{n_skipped[:5]}")

    # 寫 snapshot 到 run_dir
    shutil.copy(TARGET, run_dir / "snapshot_concept_groups.py")
    print(f"  snapshot → {run_dir.name}/snapshot_concept_groups.py")

    # 更新 _approved.json
    approved_file = VALIDATION_RUNS_DIR / "_approved.json"
    approved_data = {}
    if approved_file.exists():
        approved_data = json.loads(approved_file.read_text(encoding="utf-8"))
    approved_data[run_dir.name] = {
        "approved_at": datetime.now().isoformat(timespec="seconds"),
        "applied": True,
        "churn_rate": diff["churn_rate"],
        "added": diff["added"],
        "removed": diff["removed"],
    }
    approved_file.write_text(json.dumps(approved_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  _approved.json 已更新")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="LATEST", help="validation run id；LATEST 自動選最新 strict_v4")
    ap.add_argument("--dry-run", action="store_true", help="只看 diff 不寫")
    ap.add_argument("--approve", action="store_true", help="實際 apply")
    ap.add_argument("--force", action="store_true", help="繞過 churn / git clean gate")
    ap.add_argument("--groups", help="只套用指定族群，逗號分隔（例如：ABF載板,CPU 概念股）")
    ap.add_argument("--diff-out", help="寫 diff markdown 到此檔")
    args = ap.parse_args()

    run_dir = find_run(args.run_id)
    groups_filter = _parse_groups_filter(args.groups)

    if args.dry_run or not args.approve:
        ok, msg = gate_regression(run_dir); print(f"  G2 regression: {msg}")
        diff = compute_churn(run_dir, groups_filter=groups_filter)
        diff_md = render_diff(diff)
        if args.diff_out:
            Path(args.diff_out).write_text(diff_md, encoding="utf-8")
            print(f"  diff → {args.diff_out}")
        else:
            print("\n" + diff_md[:5000])
        # 寫到 run_dir
        (run_dir / "diff_vs_current.md").write_text(diff_md, encoding="utf-8")
        print(f"\n  diff_vs_current.md → {run_dir.name}/")
        if not args.approve:
            print("\n[note] dry-run 完成。確認 OK 後加 --approve 真正套用。")
            return
        else:
            print("\n[note] --dry-run 與 --approve 同時指定，僅產 diff 不 apply。")
            return

    apply(run_dir, args.force, groups_filter=groups_filter)


if __name__ == "__main__":
    main()
