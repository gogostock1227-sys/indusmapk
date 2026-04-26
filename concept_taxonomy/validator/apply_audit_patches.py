"""
Phase 5：把 _audit_phase5_patches.json 套到 concept_groups.py。

格式：每群 {add: [{ticker, name, reason}], remove: [{ticker, reason}]}
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
PATCH = TAXONOMY_DIR / "_audit_phase5_patches.json"


def get_block(src: str, group: str) -> tuple[int, int, str]:
    pattern = re.compile(rf'    "{re.escape(group)}"\s*:\s*\[(.*?)\n    \],', re.DOTALL)
    m = pattern.search(src)
    if not m:
        return -1, -1, ""
    return m.start(), m.end(), m.group(0)


def parse_existing(block: str) -> list[tuple[str, str]]:
    """從 block 抓出 (ticker, comment) list。"""
    items = []
    for tk_m in re.finditer(r'"(\d{4,5})"\s*,?\s*(?:#\s*([^\n]*))?', block):
        items.append((tk_m.group(1), (tk_m.group(2) or "").strip()))
    return items


def build_new_block(group: str, items: list[tuple[str, str]]) -> str:
    lines = [f'    "{group}": [']
    for tk, comment in items:
        if comment:
            lines.append(f'        "{tk}",  # {comment}')
        else:
            lines.append(f'        "{tk}",')
    lines.append("    ],")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    patches = json.loads(PATCH.read_text(encoding="utf-8"))
    src = TARGET.read_text(encoding="utf-8")

    print(f"載入 {len([k for k in patches if not k.startswith('_')])} 群 patch")

    n_changes = 0
    for group, p in patches.items():
        if group.startswith("_"):
            continue
        start, end, block = get_block(src, group)
        if start < 0:
            print(f"  ⚠ 找不到群「{group}」，跳過")
            continue
        items = parse_existing(block)
        existing_tickers = {t for t, _ in items}

        # remove
        remove_set = {r["ticker"] for r in p.get("remove", [])}
        items_after_remove = [(t, c) for t, c in items if t not in remove_set]

        # add
        new_items = list(items_after_remove)
        for a in p.get("add", []):
            if a["ticker"] not in {t for t, _ in new_items}:
                new_items.append((a["ticker"], a.get("name", "")))

        added = len(new_items) - len(items_after_remove)
        removed = len(items) - len(items_after_remove)
        net = len(new_items) - len(items)

        if added == 0 and removed == 0:
            continue

        new_block = build_new_block(group, new_items)
        src = src[:start] + new_block + src[end:]
        n_changes += 1
        print(f"  ✓ {group}: 原 {len(items)} → 新 {len(new_items)} （+{added} / -{removed}）")

    print(f"\n共 {n_changes} 群更新")

    if args.apply:
        backup = PROJECT_ROOT / "concept_groups.py.bak5_audit"
        shutil.copy(TARGET, backup)
        TARGET.write_text(src, encoding="utf-8")
        print(f"\n✓ 寫入 {TARGET}（備份 → {backup}）")
        # sanity
        sys.path.insert(0, str(PROJECT_ROOT))
        if "concept_groups" in sys.modules:
            del sys.modules["concept_groups"]
        try:
            from concept_groups import CONCEPT_GROUPS as cg
            print(f"  [sanity] 載入成功，總族群 {len(cg)}")
        except Exception as e:
            print(f"  ⚠ 載入失敗：{e}")
            shutil.copy(backup, TARGET)
    else:
        print("\n(dry run，加 --apply)")


if __name__ == "__main__":
    main()
