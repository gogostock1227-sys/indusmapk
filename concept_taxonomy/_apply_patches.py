"""讀 concept_taxonomy/master_patch.json，批量 apply 到 concept_groups.py。

策略：
1. 讀 master_patch.json
2. 對每個族群，重組 list 為「核心+衛星」
3. 用 regex 在 concept_groups.py 中找到該族群的當前 list 並替換
4. 寫回 concept_groups.py
5. 驗證載入正常
"""
from __future__ import annotations
import re
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "concept_groups.py"
PATCH_JSON = ROOT / "concept_taxonomy" / "master_patch.json"
BACKUP = ROOT / "concept_groups.py.bak2"


def load_stock_names() -> dict[str, str]:
    """從 stock_highlights.py 嘗試載入個股中文名（盡力而為）"""
    sys.path.insert(0, str(ROOT))
    try:
        # 用 daily_group_tracker 之類的腳本可能有 ticker→name mapping
        # 先空字典，後續 fallback 為「ticker」
        return {}
    except Exception:
        return {}


def build_new_list_block(group: str, keep: list[str], names: dict[str, str]) -> str:
    """組裝修正後的 Python list 區塊，含 # 註解"""
    lines = [f'    "{group}": [']
    for tk in keep:
        name = names.get(tk, '')
        comment = f'  # {name}' if name else f'  # {tk}'
        lines.append(f'        "{tk}",{comment}')
    lines.append('    ],')
    return '\n'.join(lines)


def replace_group_in_file(content: str, group: str, new_block: str) -> tuple[str, bool]:
    """在 concept_groups.py 內容中找到 "group": [...] 並替換為 new_block"""
    # 構造 group key 的正則（escape 反斜線）
    key_pattern = re.escape(f'"{group}":')
    # 匹配 "group": [\n ... \n    ], 整個 block
    pattern = re.compile(
        rf'    {key_pattern}\s*\[(?:.*?)\n    \],',
        re.DOTALL,
    )
    m = pattern.search(content)
    if not m:
        return content, False
    new_content = content[:m.start()] + new_block + content[m.end():]
    return new_content, True


def main():
    if not PATCH_JSON.exists():
        print(f"[ERROR] {PATCH_JSON} 不存在，先跑整合 agent 產出 master_patch.json")
        return

    patches = json.loads(PATCH_JSON.read_text(encoding='utf-8'))
    print(f"載入 {len(patches)} 個族群 patch")

    # 備份
    content = TARGET.read_text(encoding='utf-8')
    BACKUP.write_text(content, encoding='utf-8')
    print(f"備份 → {BACKUP}")

    names = load_stock_names()

    applied = 0
    skipped = 0
    not_found = []
    null_keep = []

    for group, info in patches.items():
        keep = info.get('keep')
        if keep is None or not keep:
            null_keep.append(group)
            skipped += 1
            continue
        new_block = build_new_list_block(group, keep, names)
        content, ok = replace_group_in_file(content, group, new_block)
        if ok:
            applied += 1
            print(f"  [OK] {group}: {len(keep)} 檔")
        else:
            not_found.append(group)

    TARGET.write_text(content, encoding='utf-8')
    print(f"\n[DONE]")
    print(f"  Applied: {applied}")
    print(f"  Skipped (keep=null): {skipped}")
    print(f"  Not found in file: {len(not_found)}")
    if not_found:
        print(f"  Not found list: {not_found[:20]}")
    if null_keep:
        print(f"  Null keep groups: {null_keep[:20]}")

    # Sanity check
    print(f"\n=== Sanity Check ===")
    sys.path.insert(0, str(ROOT))
    # 強制重新 import
    if 'concept_groups' in sys.modules:
        del sys.modules['concept_groups']
    try:
        from concept_groups import CONCEPT_GROUPS as cg
        print(f"  載入成功，總族群數: {len(cg)}")
    except Exception as e:
        print(f"  [ERROR] 載入失敗: {e}")
        print(f"  從備份還原: cp {BACKUP} {TARGET}")


if __name__ == '__main__':
    main()
