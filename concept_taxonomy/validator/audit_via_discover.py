"""
Day 8：批次審計工具——對每個嚴格群跑 discover.py，比對 concept_groups.py 找出：
  - missing：discover.py 列在「核心業務相關」但 concept_groups.py 沒收錄
  - extra：concept_groups.py 收錄但 discover.py 完全沒提

入口：
    python -m validator.audit_via_discover                    # 跑全部映射
    python -m validator.audit_via_discover --topic 矽光子      # 單群
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

TAXONOMY_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = TAXONOMY_DIR.parent
DISCOVER_SCRIPT = PROJECT_ROOT / "My-TW-Coverage" / "scripts" / "discover.py"

# topic 關鍵字 → concept_groups.py key
TOPIC_TO_GROUP = {
    "矽光子": "矽光子",
    "CPO": "矽光子",
    "VCSEL": "VCSEL 雷射",
    "InP": "磷化銦/InP",
    "GaN": "氮化鎵/GaN",
    "SiC": "碳化矽/SiC",
    "EUV": "EUV 極紫外光微影",
    "矽晶圓": "矽晶圓",
    "AI 眼鏡": "AI 眼鏡 / Meta Ray-Ban",
    "穿戴": "穿戴/智慧眼鏡",
    "射頻": "射頻 RF/PA",
    "BBU": "電源供應器/BBU",
    "MLCC": "被動元件",
    "CoWoS": "CoWoS先進封裝",
    "HBM": "HBM 高頻寬記憶體",
    "ASIC": "ASIC/IP矽智財",
    "ABF 載板": "ABF載板",
    "光通訊": "光通訊",
    "石英": "石英元件",
    "Wi-Fi 7": "Wi-Fi 7/5G",
    "PCIe": "PCIe Gen5/Gen6",
    "DDR5": "DDR5/LPDDR5 記憶體",
    "TPU": "Google TPU",
    "Trainium": "ASIC/IP矽智財",
    "Apple AI": "蘋果概念股",
    "電動車": "電動車",
    "低軌衛星": "低軌衛星",
    "機器人": "機器人/工業自動化",
    "GLP-1": "GLP-1 減重新藥",
}


def get_current_members(group: str) -> list[str]:
    src = (PROJECT_ROOT / "concept_groups.py").read_text(encoding="utf-8")
    m = re.search(rf'"{re.escape(group)}"\s*:\s*\[(.*?)\]', src, re.DOTALL)
    if not m:
        return []
    return re.findall(r'"(\d{4,5})"', m.group(1))


def run_discover(topic: str) -> dict[str, list[str]]:
    """Return {核心: [tickers], 供應鏈: [tickers], 客戶: [tickers]}."""
    res = subprocess.run(
        [sys.executable, str(DISCOVER_SCRIPT), topic],
        capture_output=True, text=True, encoding="utf-8",
    )
    out = res.stdout
    sections = {"核心": [], "供應鏈": [], "客戶": []}
    current = None
    for line in out.splitlines():
        if "核心業務相關" in line:
            current = "核心"
            continue
        if "供應鏈相關" in line:
            current = "供應鏈"
            continue
        if "客戶相關" in line:
            current = "客戶"
            continue
        m = re.match(r'\s*[✓○]\s+(\d{4,5})', line)
        if m and current:
            sections[current].append(m.group(1))
    return sections


def audit_group(topic: str, group: str) -> dict:
    current_set = set(get_current_members(group))
    discovered = run_discover(topic)
    core_set = set(discovered["核心"])
    supply_set = set(discovered["供應鏈"])
    discover_all = core_set | supply_set

    missing_core = sorted(core_set - current_set)
    missing_supply = sorted(supply_set - current_set)
    extra = sorted(current_set - discover_all - {""})

    return {
        "topic": topic,
        "group": group,
        "current": sorted(current_set),
        "current_n": len(current_set),
        "discover_core": sorted(core_set),
        "discover_supply": sorted(supply_set),
        "missing_core": missing_core,           # 應加入但缺漏（高優先）
        "missing_supply": missing_supply,        # 供應鏈應加（中優先）
        "extra": extra,                          # 雜質（建議移除）
    }


def format_audit(audit: dict) -> str:
    lines = []
    lines.append(f"## {audit['topic']} → 族群「{audit['group']}」")
    lines.append(f"- 現有 {audit['current_n']} 檔；discover.py 核心 {len(audit['discover_core'])} 檔 / 供應鏈 {len(audit['discover_supply'])} 檔")
    if audit["missing_core"]:
        lines.append(f"- ⚠ **應補入核心**（{len(audit['missing_core'])} 檔）：{', '.join(audit['missing_core'])}")
    if audit["missing_supply"]:
        lines.append(f"- 💡 可補入供應鏈（{len(audit['missing_supply'])} 檔）：{', '.join(audit['missing_supply'][:15])}{'...' if len(audit['missing_supply']) > 15 else ''}")
    if audit["extra"]:
        lines.append(f"- 🔴 **建議移除**（{len(audit['extra'])} 檔）：{', '.join(audit['extra'])}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", help="只跑單一 topic（如「矽光子」）")
    ap.add_argument("--out", default=str(TAXONOMY_DIR / "_AUDIT_BY_DISCOVER.md"))
    args = ap.parse_args()

    targets = [args.topic] if args.topic else list(TOPIC_TO_GROUP.keys())

    out_lines = ["# 族群審計報告（My-TW-Coverage discover.py 交叉驗證）",
                 "", "> 自動比對 concept_groups.py 現有成員 vs My-TW-Coverage 提及該關鍵字的個股",
                 "> 「應補入核心」= discover 標核心業務但 concept_groups 沒收 → false negative",
                 "> 「建議移除」= concept_groups 收但 discover 完全沒提 → false positive (高度疑慮)", ""]

    for topic in targets:
        if topic not in TOPIC_TO_GROUP:
            print(f"⚠ 未知 topic: {topic}")
            continue
        group = TOPIC_TO_GROUP[topic]
        try:
            audit = audit_group(topic, group)
        except Exception as e:
            print(f"⚠ {topic}: {e}")
            continue
        out_lines.append(format_audit(audit))
        out_lines.append("")
        print(f"  {topic:<10s} → {group:<25s} 缺核心 {len(audit['missing_core']):>3d} ｜雜質 {len(audit['extra']):>3d}")

    Path(args.out).write_text("\n".join(out_lines), encoding="utf-8")
    print(f"\n✓ 完整報告 → {args.out}")


if __name__ == "__main__":
    main()
