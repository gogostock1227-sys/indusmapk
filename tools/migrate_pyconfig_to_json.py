"""一次性遷移：把 concept_groups.py 與 site/industry_meta.py 的 dict 抽到 JSON。

雙軌策略：
  1. ast.literal_eval 從 .py 取出純資料 dict 作為 JSON 真理源
  2. 行掃描 + regex 抽出 concept_groups.py 每個 ticker 的 inline 註解作為 sidecar notes

產出：
  data/concept_groups.json          ── {"族群": ["ticker", ...], ...}
  data/concept_groups_notes.json    ── {"族群": {"ticker": "註解", ...}, ...}
  data/industry_meta.json           ── {"族群": {meta dict}, ...}

跑法：
  python tools/migrate_pyconfig_to_json.py [--dry-run]

dry-run 模式：產出到 data/.preview/，方便人工 diff，不覆蓋正式檔。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONCEPT_GROUPS_PY = ROOT / "concept_groups.py"
INDUSTRY_META_PY = ROOT / "site" / "industry_meta.py"


def _extract_assign_dict(source: str, var_name: str) -> dict:
    """從 Python 原始碼裡找出 `var_name = {...}` 的 dict literal 並回傳成 Python dict。"""
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == var_name:
                return ast.literal_eval(node.value)
    raise RuntimeError(f"找不到 {var_name} 賦值")


# concept_groups.py 行模式
_GROUP_OPEN = re.compile(r'^\s*"([^"]+)"\s*:\s*\[\s*$')
_GROUP_CLOSE = re.compile(r"^\s*\],?\s*$")
_TICKER_LINE = re.compile(
    r'^\s*"([^"]+)"\s*,?\s*'      # "5269",
    r"(?:#\s*(.*?))?\s*$"          # # 祥碩 — ground_truth：人工標記真核心
)


def extract_concept_groups_notes(py_path: Path) -> dict[str, dict[str, str]]:
    """掃 concept_groups.py，建 {group: {ticker: note}} sidecar map。

    note 是 ticker 後面 `#` 之後的純文字（已 strip）。沒註解則該 ticker 不會出現在 map 裡。
    """
    notes: dict[str, dict[str, str]] = {}
    current_group: str | None = None

    with py_path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if current_group is None:
                m = _GROUP_OPEN.match(line)
                if m:
                    current_group = m.group(1)
                    notes[current_group] = {}
                continue

            if _GROUP_CLOSE.match(line):
                current_group = None
                continue

            m = _TICKER_LINE.match(line)
            if m:
                ticker = m.group(1)
                note = (m.group(2) or "").strip()
                if note:
                    notes[current_group][ticker] = note

    # 移除空 group（沒任何 ticker 有註解）以縮小 sidecar
    return {g: n for g, n in notes.items() if n}


def _hash_dict(d: dict) -> str:
    """穩定雜湊，用來做 zero-diff 驗證。"""
    payload = json.dumps(d, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.md5(payload).hexdigest()


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"  ✓ wrote {path.relative_to(ROOT)}  ({path.stat().st_size:,} bytes)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="輸出到 data/.preview/ 而非正式位置",
    )
    args = parser.parse_args()

    out_root = ROOT / ("data/.preview" if args.dry_run else "data")
    print(f"輸出目錄：{out_root.relative_to(ROOT)}")
    print()

    # ── concept_groups ───────────────────────────────────────────────
    print("解析 concept_groups.py …")
    cg_source = CONCEPT_GROUPS_PY.read_text(encoding="utf-8")
    cg_dict = _extract_assign_dict(cg_source, "CONCEPT_GROUPS")
    cg_hash = _hash_dict(cg_dict)
    print(f"  CONCEPT_GROUPS 共 {len(cg_dict)} 個族群，雜湊 {cg_hash}")
    _write_json(out_root / "concept_groups.json", cg_dict)

    print("掃 concept_groups.py 抽 inline 註解 …")
    notes = extract_concept_groups_notes(CONCEPT_GROUPS_PY)
    total_notes = sum(len(v) for v in notes.values())
    print(f"  收錄 {len(notes)} 個族群、共 {total_notes} 條 ticker 註解")
    _write_json(out_root / "concept_groups_notes.json", notes)

    # ── industry_meta ────────────────────────────────────────────────
    print()
    print("解析 site/industry_meta.py …")
    im_source = INDUSTRY_META_PY.read_text(encoding="utf-8")
    im_dict = _extract_assign_dict(im_source, "INDUSTRY_META")
    im_hash = _hash_dict(im_dict)
    print(f"  INDUSTRY_META 共 {len(im_dict)} 個族群 meta，雜湊 {im_hash}")
    _write_json(out_root / "industry_meta.json", im_dict)

    # ── 雜湊備案文字檔，方便 refactor 後比對 ─────────────────────────
    hash_file = out_root / ".hashes.txt"
    hash_file.write_text(
        f"CONCEPT_GROUPS={cg_hash}\nINDUSTRY_META={im_hash}\n",
        encoding="utf-8",
    )
    print(f"\n  ✓ 雜湊存檔：{hash_file.relative_to(ROOT)}")

    print("\n完成。")
    if args.dry_run:
        print("（dry-run 模式，未動正式檔）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
