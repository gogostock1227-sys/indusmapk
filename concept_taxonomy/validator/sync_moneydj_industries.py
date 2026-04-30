"""同步 Moneydj 產業 CSV 到網站族群資料。

規則重點：
- 以 Moneydj產業/_產業清單.csv 為主索引。
- 網站族群名稱使用「細產業」，Moneydj「族群」寫入 meta category。
- 既有概念股/題材股不覆蓋。
- Moneydj 同名細產業若為空檔，不把既有族群清空。
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import re
from collections import Counter, OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
CONCEPT_GROUPS_PATH = ROOT / "concept_groups.py"
SITE_DIR = ROOT / "site"
MONEYDJ_META_PATH = SITE_DIR / "moneydj_industry_meta.py"
STOCK_NAME_OVERRIDES_PATH = SITE_DIR / "stock_name_overrides.json"

PROTECTED_NAMES = {
    "ABF載板",
    "Google TPU",
    "輝達概念股",
    "CPU 概念股",
    "AI伺服器",
}

PROTECTED_MARKERS = (
    "概念股",
    "Google",
    "TPU",
    "NVIDIA",
    "輝達",
    "Apple",
    "蘋果",
    "特斯拉",
    "Tesla",
    "AI",
    "CoWoS",
    "HBM",
    "EUV",
    "CPO",
    "HVDC",
    "GLP",
    "ESG",
    "2奈米",
    "先進製程",
    "資料中心",
)

META_COLORS = (
    "#ff7847",
    "#f97316",
    "#a855f7",
    "#0ea5e9",
    "#10b981",
    "#6366f1",
    "#84cc16",
    "#dc2626",
    "#71717a",
    "#7c3aed",
    "#2563eb",
    "#0369a1",
    "#525252",
    "#16a34a",
    "#14b8a6",
    "#78350f",
    "#15803d",
    "#4338ca",
    "#059669",
    "#9a3412",
    "#a16207",
    "#a21caf",
)


@dataclass(frozen=True)
class MoneydjEntry:
    parent: str
    child: str
    file_name: str
    industry_code: str
    reported_count: int
    source_url: str
    members: tuple[tuple[str, str], ...]

    @property
    def actual_count(self) -> int:
        return len(self.members)


def js(value: str) -> str:
    """輸出 Python 原始碼用的雙引號字串。"""
    return json.dumps(value, ensure_ascii=False)


def clean_comment(text: str) -> str:
    return (text or "").replace("\n", " ").replace("\r", " ").replace("#", "").strip()


def unique_codes(rows: Iterable[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for code, name in rows:
        code = code.strip()
        name = name.strip()
        if not code or code in seen:
            continue
        seen.add(code)
        result.append((code, name))
    return tuple(result)


def find_moneydj_dir() -> Path:
    candidates = [p for p in ROOT.iterdir() if p.is_dir() and p.name.startswith("Moneydj")]
    if not candidates:
        raise FileNotFoundError("找不到 Moneydj 產業資料夾")
    return candidates[0]


def find_index_file(moneydj_dir: Path) -> Path:
    candidates = [p for p in moneydj_dir.glob("*.csv") if p.name.startswith("_")]
    if not candidates:
        raise FileNotFoundError("找不到 Moneydj 產業清單 CSV")
    return candidates[0]


def parse_int(value: str) -> int:
    value = (value or "").strip()
    if not value:
        return 0
    try:
        return int(value)
    except ValueError:
        return 0


def read_member_csv(path: Path) -> tuple[tuple[str, str], ...]:
    if not path.exists():
        return tuple()
    rows: list[tuple[str, str]] = []
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) < 2:
                continue
            rows.append((row[0], row[1]))
    return unique_codes(rows)


def load_moneydj_entries() -> tuple[list[MoneydjEntry], Path]:
    moneydj_dir = find_moneydj_dir()
    index_file = find_index_file(moneydj_dir)
    entries: list[MoneydjEntry] = []
    with index_file.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) < 6:
                continue
            parent, child, file_name, industry_code, reported_count, source_url = [
                col.strip() for col in row[:6]
            ]
            if not parent or not child or not file_name:
                continue
            entries.append(
                MoneydjEntry(
                    parent=parent,
                    child=child,
                    file_name=file_name,
                    industry_code=industry_code,
                    reported_count=parse_int(reported_count),
                    source_url=source_url,
                    members=read_member_csv(moneydj_dir / file_name),
                )
            )
    return entries, index_file


def load_existing_groups() -> OrderedDict[str, list[str]]:
    text = CONCEPT_GROUPS_PATH.read_text(encoding="utf-8")
    module = ast.parse(text)
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "CONCEPT_GROUPS":
                data = ast.literal_eval(node.value)
                return OrderedDict((str(k), [str(x) for x in v]) for k, v in data.items())
    raise ValueError("concept_groups.py 找不到 CONCEPT_GROUPS")


def load_stock_name_overrides() -> dict[str, str]:
    if not STOCK_NAME_OVERRIDES_PATH.exists():
        return {}
    return json.loads(STOCK_NAME_OVERRIDES_PATH.read_text(encoding="utf-8"))


def parse_existing_comments() -> dict[str, dict[str, str]]:
    group_re = re.compile(r'^\s{4}"(?P<group>.+)": \[\s*$')
    member_re = re.compile(r'^\s{8}"(?P<code>[^"]+)",\s*(?:#\s*(?P<name>.*))?$')
    comments: dict[str, dict[str, str]] = {}
    current_group: str | None = None
    for line in CONCEPT_GROUPS_PATH.read_text(encoding="utf-8").splitlines():
        group_match = group_re.match(line)
        if group_match:
            current_group = group_match.group("group")
            comments.setdefault(current_group, {})
            continue
        if current_group is None:
            continue
        if line.startswith("    ],"):
            current_group = None
            continue
        member_match = member_re.match(line)
        if member_match:
            comments.setdefault(current_group, {})[member_match.group("code")] = clean_comment(
                member_match.group("name") or ""
            )
    return comments


def is_protected_group(name: str) -> bool:
    if name in PROTECTED_NAMES:
        return True
    lowered = name.lower()
    return any(marker.lower() in lowered for marker in PROTECTED_MARKERS)


def merge_groups(
    existing: OrderedDict[str, list[str]],
    entries: list[MoneydjEntry],
    stock_overrides: dict[str, str],
    existing_comments: dict[str, dict[str, str]],
) -> tuple[OrderedDict[str, list[str]], dict[str, dict[str, str]], dict[str, object]]:
    pruned_empty_existing = [name for name, members in existing.items() if not members]
    result = OrderedDict((name, list(members)) for name, members in existing.items() if members)
    member_names: dict[str, dict[str, str]] = {
        group: {
            code: stock_overrides.get(code) or existing_comments.get(group, {}).get(code, "")
            for code in members
        }
        for group, members in result.items()
    }

    name_counts = Counter(entry.child for entry in entries)
    duplicate_names = sorted(name for name, count in name_counts.items() if count > 1)
    duplicate_set = set(duplicate_names)

    stats: dict[str, object] = {
        "moneydj_entries": len(entries),
        "moneydj_parents": len({entry.parent for entry in entries}),
        "nonempty_entries": sum(1 for entry in entries if entry.actual_count > 0),
        "empty_entries": sum(1 for entry in entries if entry.actual_count == 0),
        "added": [],
        "updated_existing": [],
        "protected_skipped": [],
        "empty_entries_skipped": [],
        "pruned_empty_existing": pruned_empty_existing,
        "duplicate_skipped": duplicate_names,
        "count_mismatches": [],
    }

    for entry in entries:
        if entry.reported_count != entry.actual_count:
            stats["count_mismatches"].append(
                {
                    "name": entry.child,
                    "file": entry.file_name,
                    "reported": entry.reported_count,
                    "actual": entry.actual_count,
                }
            )
        if entry.child in duplicate_set:
            continue

        moneydj_codes = [code for code, _ in entry.members]
        moneydj_names = {
            code: stock_overrides.get(code) or clean_comment(name) for code, name in entry.members
        }
        if not moneydj_codes:
            stats["empty_entries_skipped"].append(entry.child)
            continue

        if entry.child in result:
            if is_protected_group(entry.child):
                stats["protected_skipped"].append(entry.child)
                continue
            result[entry.child] = moneydj_codes
            member_names[entry.child] = moneydj_names
            stats["updated_existing"].append(entry.child)
            continue

        result[entry.child] = moneydj_codes
        member_names[entry.child] = moneydj_names
        stats["added"].append(entry.child)

    stats["final_groups"] = len(result)
    return result, member_names, stats


def render_concept_groups(
    groups: OrderedDict[str, list[str]],
    member_names: dict[str, dict[str, str]],
) -> str:
    lines: list[str] = [
        '"""網站題材與 Moneydj 產業族群清單。',
        "",
        "此檔由 concept_taxonomy/validator/sync_moneydj_industries.py 更新。",
        "Moneydj CSV 以「細產業」作為網站族群名稱；大族群分類寫入 site/moneydj_industry_meta.py。",
        "既有概念股與題材股依保護規則保留，不被 Moneydj 同名產業覆蓋。",
        '"""',
        "",
        "CONCEPT_GROUPS = {",
    ]
    for group, members in groups.items():
        lines.append(f"    {js(group)}: [")
        lines.append(f"        # count={len(members)}")
        for code in members:
            name = clean_comment(member_names.get(group, {}).get(code, ""))
            suffix = f"  # {name}" if name else ""
            lines.append(f"        {js(code)},{suffix}")
        lines.append("    ],")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def color_for_parent(parent: str, parents: list[str]) -> str:
    try:
        idx = parents.index(parent)
    except ValueError:
        idx = 0
    return META_COLORS[idx % len(META_COLORS)]


def render_moneydj_meta(entries: list[MoneydjEntry]) -> str:
    name_counts = Counter(entry.child for entry in entries)
    parents = sorted({entry.parent for entry in entries})
    lines: list[str] = [
        '"""產業分類 meta。',
        "",
        "此檔由 concept_taxonomy/validator/sync_moneydj_industries.py 自動產生。",
        '"""',
        "",
        "MONEYDJ_INDUSTRY_META = {",
    ]
    for entry in entries:
        if entry.actual_count == 0:
            continue
        if name_counts[entry.child] > 1:
            continue
        color = color_for_parent(entry.parent, parents)
        count_text = f"{entry.actual_count} 檔成分股" if entry.actual_count else "目前尚無成分股"
        representatives = "、".join(
            f"{code} {name}".strip()
            for code, name in entry.members[:2]
        ) or "代表公司"
        desc = f"{entry.child}聚焦{entry.parent}產業鏈中的細分需求與代表公司表現，目前收錄 {count_text}。"
        lines.append(f"    {js(entry.child)}: {{")
        lines.append(f"        \"en\": {js(entry.child)},")
        lines.append(f"        \"category\": {js(entry.parent)},")
        lines.append(f"        \"color\": {js(color)},")
        lines.append(f"        \"desc\": {js(desc)},")
        lines.append('        "cagr": "—",')
        lines.append('        "market_size": "—",')
        lines.append(f"        \"parent\": {js(entry.parent)},")
        lines.append(f"        \"actual_count\": {entry.actual_count},")
        lines.append('        "indicators": [')
        lines.append(f"            {{\"label\": \"產業鏈位\", \"value\": {js(entry.parent)}}},")
        lines.append(f"            {{\"label\": \"研究重點\", \"value\": {js(entry.child)}}},")
        lines.append(f"            {{\"label\": \"代表公司\", \"value\": {js(representatives)}}},")
        lines.append(f"            {{\"label\": \"成分規模\", \"value\": {js(count_text)}}},")
        lines.append("        ],")
        lines.append("    },")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def compact_stats(stats: dict[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in stats.items():
        if isinstance(value, list):
            result[key] = {"count": len(value), "sample": value[:20]}
        else:
            result[key] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="同步 Moneydj 產業 CSV 到 concept_groups.py")
    parser.add_argument("--write", action="store_true", help="實際寫入 concept_groups.py 與 moneydj_industry_meta.py")
    parser.add_argument("--json", action="store_true", help="以 JSON 輸出同步摘要")
    args = parser.parse_args()

    entries, index_file = load_moneydj_entries()
    existing = load_existing_groups()
    stock_overrides = load_stock_name_overrides()
    existing_comments = parse_existing_comments()
    groups, member_names, stats = merge_groups(existing, entries, stock_overrides, existing_comments)

    concept_text = render_concept_groups(groups, member_names)
    meta_text = render_moneydj_meta(entries)

    if args.write:
        CONCEPT_GROUPS_PATH.write_text(concept_text, encoding="utf-8", newline="\n")
        MONEYDJ_META_PATH.write_text(meta_text, encoding="utf-8", newline="\n")

    output = {
        "mode": "write" if args.write else "dry-run",
        "index_file": str(index_file.relative_to(ROOT)),
        **compact_stats(stats),
    }
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"模式: {output['mode']}")
        print(f"索引: {output['index_file']}")
        print(f"Moneydj 細產業: {stats['moneydj_entries']}")
        print(f"Moneydj 大族群: {stats['moneydj_parents']}")
        print(f"非空/空細產業: {stats['nonempty_entries']} / {stats['empty_entries']}")
        print(f"新增產業: {len(stats['added'])}")
        print(f"更新既有純產業: {len(stats['updated_existing'])}")
        print(f"概念題材保護跳過: {len(stats['protected_skipped'])}")
        print(f"空產業跳過: {len(stats['empty_entries_skipped'])}")
        print(f"既有空族群移除: {len(stats['pruned_empty_existing'])}")
        print(f"重名細產業跳過: {len(stats['duplicate_skipped'])}")
        print(f"最終族群數: {stats['final_groups']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
