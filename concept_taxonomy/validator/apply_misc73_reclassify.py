"""
把「其他（多元族群）」73 檔 reclassify 寫回 concept_groups.py。

策略：
  - 每檔依 target_groups 加進對應的群（如果還沒有）
  - 同檔可能加進多群（例：1443 立益物流 → 交通運輸/物流 + 營建/資產）
  - target_groups 為「其他（多元族群）」的（3 檔暫保留）→ 不動
  - 同步把「其他（多元族群）」list 縮成只剩 3 檔暫保留

入口：
    python -m validator.apply_misc73_reclassify          # dry run
    python -m validator.apply_misc73_reclassify --apply  # 寫入
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

TAXONOMY_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = TAXONOMY_DIR.parent
TARGET = PROJECT_ROOT / "concept_groups.py"
RECLASSIFY = TAXONOMY_DIR / "_other_misc_73_reclassify.json"


def load_groups(src: str) -> dict[str, list[tuple[str, str]]]:
    """解析 concept_groups.py，回 {group_name: [(ticker, name_comment), ...]}。"""
    pattern = re.compile(r'"([^"]+?)"\s*:\s*\[(.*?)\]', re.DOTALL)
    result = {}
    for m in pattern.finditer(src):
        group = m.group(1)
        if group == "_meta":
            continue
        block = m.group(2)
        items = []
        for tk_m in re.finditer(r'"(\d{4,5})"\s*,?\s*(?:#\s*([^\n]+))?', block):
            ticker = tk_m.group(1)
            comment = (tk_m.group(2) or ticker).strip()
            items.append((ticker, comment))
        if items or group in {"防疫/口罩", "宅經濟/遠距", "高速傳輸"}:
            result[group] = items
    return result


def build_block(group: str, items: list[tuple[str, str]]) -> str:
    lines = [f'    "{group}": [']
    for tk, comment in items:
        if comment and comment != tk:
            lines.append(f'        "{tk}",  # {comment}')
        else:
            lines.append(f'        "{tk}",')
    lines.append("    ],")
    return "\n".join(lines)


def replace_group_block(src: str, group: str, new_block: str) -> tuple[str, bool]:
    pattern = re.compile(
        rf'    "{re.escape(group)}"\s*:\s*\[(?:.*?)\n    \],',
        re.DOTALL,
    )
    m = pattern.search(src)
    if not m:
        return src, False
    return src[:m.start()] + new_block + src[m.end():], True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真的寫入 concept_groups.py（含 .bak4 備份）")
    args = ap.parse_args()

    print("[1/4] 讀取 reclassify 表 + concept_groups.py ...")
    reclassify = json.loads(RECLASSIFY.read_text(encoding="utf-8"))
    src = TARGET.read_text(encoding="utf-8")
    groups = load_groups(src)
    print(f"  73 mappings, {len(groups)} 群已存在")

    print("[2/4] 計算 patch ...")
    # 先計算每個 target_group 應加入哪些 ticker
    additions: dict[str, list[tuple[str, str]]] = {}
    keep_in_misc: list[tuple[str, str]] = []

    for tk, info in reclassify.items():
        if tk.startswith("_"):
            continue
        targets = info.get("target_groups", [])
        if targets == ["其他（多元族群）"]:
            keep_in_misc.append((tk, info.get("name", "")))
            continue
        for tgt in targets:
            if tgt == "其他（多元族群）":
                continue
            if tgt not in groups:
                print(f"  ⚠ 目標群「{tgt}」不存在於 concept_groups.py（{tk} {info.get('name','')}）")
                continue
            additions.setdefault(tgt, []).append((tk, info.get("name", "")))

    print(f"  {len(additions)} 目標群 / {sum(len(v) for v in additions.values())} 個股加入")
    print(f"  保留在「其他（多元族群）」：{len(keep_in_misc)} 檔")

    print("[3/4] 套用 patch ...")
    new_src = src
    n_groups_updated = 0

    # 加入到目標群
    for tgt, new_items in additions.items():
        existing = groups[tgt]
        existing_tickers = {t for t, _ in existing}
        merged = list(existing)
        added_n = 0
        for tk, name in new_items:
            if tk not in existing_tickers:
                merged.append((tk, name))
                added_n += 1
        if added_n > 0:
            new_block = build_block(tgt, merged)
            new_src, ok = replace_group_block(new_src, tgt, new_block)
            if ok:
                n_groups_updated += 1
                print(f"  ✓ {tgt}: +{added_n} 檔 → 共 {len(merged)}")
            else:
                print(f"  ⚠ {tgt}: regex 替換失敗")

    # 縮減「其他（多元族群）」
    new_misc_block = build_block("其他（多元族群）", keep_in_misc)
    new_src, ok = replace_group_block(new_src, "其他（多元族群）", new_misc_block)
    if ok:
        print(f"  ✓ 「其他（多元族群）」73 → {len(keep_in_misc)}（剩 Coverage 缺失暫保留）")

    print(f"\n  共更新 {n_groups_updated + 1} 群")

    if args.apply:
        backup = PROJECT_ROOT / "concept_groups.py.bak4_misc73"
        shutil.copy(TARGET, backup)
        TARGET.write_text(new_src, encoding="utf-8")
        print(f"\n[4/4] ✓ 寫入 {TARGET}（備份 → {backup}）")
        # Sanity check
        sys.path.insert(0, str(PROJECT_ROOT))
        if "concept_groups" in sys.modules:
            del sys.modules["concept_groups"]
        try:
            from concept_groups import CONCEPT_GROUPS as cg
            print(f"  [sanity] 載入成功，總族群數：{len(cg)}")
        except Exception as e:
            print(f"  ⚠ 載入失敗：{e}")
            print(f"  恢復備份：cp {backup} {TARGET}")
            shutil.copy(backup, TARGET)
    else:
        print("\n[4/4] (dry run，加 --apply 才會寫入)")


if __name__ == "__main__":
    main()
