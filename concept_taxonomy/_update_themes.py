"""批次同步 themes/*.md 為 concept_taxonomy 重組後的版本。

策略：
- 對每個 theme.md，標記為「已重組，請看 concept_taxonomy/{group}.md」
- 列出新 keep list（從 master_patch.json）
- 標註已從原版本移除的標的數量
- 保留原 theme.md 的 description（如有）
- HBM.md 跳過（已手動精修）
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from concept_groups import CONCEPT_GROUPS  # noqa

THEMES_DIR = ROOT / "My-TW-Coverage" / "themes"
PATCH_JSON = ROOT / "concept_taxonomy" / "master_patch.json"

# theme.md filename → concept_groups key
THEME_TO_GROUP = {
    "AI_伺服器": "AI伺服器",
    "CoWoS": "CoWoS先進封裝",
    "HBM": "HBM 高頻寬記憶體",  # 已手動修正，跳過
    "矽光子": "矽光子",
    "CPO": "光通訊/CPO",
    "ABF_載板": "ABF載板",
    "Apple": "蘋果概念股",
    "NVIDIA": "輝達概念股",
    "低軌衛星": "低軌衛星",
    "光阻液": "特用化學/光阻劑",
    "氮化鎵": "氮化鎵/GaN",
    "碳化矽": "碳化矽/SiC",
    "矽晶圓": "矽晶圓",
    "電動車": "電動車",
    "5G": "5G 通訊",
    "EUV": "EUV 極紫外光微影",
    "Tesla": "特斯拉概念股",
    "VCSEL": "VCSEL 雷射",
    "磷化銦": "磷化銦/InP",
    "資料中心": "資料中心",
}


def extract_description(text: str) -> str:
    """從原 theme.md 提取首段 description（quote 區塊）"""
    m = re.search(r'^>\s*(.+?)(?:\n\n|\n##)', text, re.MULTILINE | re.DOTALL)
    if m:
        return m.group(1).strip()
    # fallback: 找首個非空白非 # 的段落
    for line in text.split('\n')[1:5]:
        line = line.strip()
        if line and not line.startswith('#'):
            return line
    return ""


def load_ticker_names() -> dict[str, str]:
    """從 concept_groups.py 提取 ticker→name 映射（從註解）"""
    src = (ROOT / "concept_groups.py").read_text(encoding='utf-8')
    names = {}
    for m in re.finditer(r'"(\d{4,6}[A-Z]?)"\s*,\s*#\s*(.+?)$', src, re.MULTILINE):
        tk, name = m.group(1), m.group(2).strip()
        # 去掉括號內額外註解
        name = re.split(r'[（(]', name)[0].strip()
        if tk not in names and name and len(name) < 20:
            names[tk] = name
    return names


def render_theme(theme_name: str, group: str, keep: list[str], names: dict[str, str], desc: str) -> str:
    """生成新 theme.md 內容"""
    # 列成分股
    lines_keep = []
    for tk in keep:
        name = names.get(tk, '')
        if name:
            lines_keep.append(f"- **{tk} {name}**")
        else:
            lines_keep.append(f"- **{tk}**")

    # 統計原始 vs 新
    original = CONCEPT_GROUPS.get(group, [])
    removed_count = len(set(original) - set(keep)) if original else 0

    out = [f"# {theme_name.replace('_', ' ')}", ""]
    if desc:
        out += [f"> {desc}", ""]
    out += [
        f"**涵蓋公司數:** {len(keep)}（依 `concept_taxonomy/_FINAL_REPORT.md` 重組，2026-04-25 更新）",
        "",
        f"**對應族群（concept_groups.py）：** `{group}`",
        "",
        "---",
        "",
        "## 成分股清單",
        "",
        *lines_keep,
        "",
        "---",
        "",
        "## 變更摘要",
        "",
        f"- 原始 {len(original)} 檔 → 重組後 {len(keep)} 檔（移除 {removed_count} 檔）",
        "- 移除原因詳見 `concept_taxonomy/batch_*.md`",
        "- 三維分類體系字典：`concept_taxonomy/_TAXONOMY_SCHEMA.md`",
        "",
        "## 修正歷程",
        "",
        "- **2026-04-25**：依三維分類體系重新驗證成分股，移除誤分類標的。"
        "原始 `themes/build_themes.py` 自動生成的「上中下游」分類已知有錯誤（例如把"
        "伺服器主機板列為 HBM 上游、晶圓代工列為下游），不應作為投資決策依據。"
        "本主題現以「對應族群」為準，詳見 `concept_groups.py`。",
    ]
    return '\n'.join(out) + '\n'


def main():
    patches = json.loads(PATCH_JSON.read_text(encoding='utf-8'))
    names = load_ticker_names()
    print(f"載入 ticker→name 映射 {len(names)} 筆")

    updated = 0
    skipped = 0
    for theme_name, group in THEME_TO_GROUP.items():
        if theme_name == "HBM":
            print(f"  [SKIP] HBM.md 已手動精修，保留")
            skipped += 1
            continue
        theme_file = THEMES_DIR / f"{theme_name}.md"
        if not theme_file.exists():
            print(f"  [MISS] {theme_file.name} 不存在")
            continue
        if group not in patches:
            print(f"  [MISS] {group} 不在 master_patch.json")
            continue

        old_text = theme_file.read_text(encoding='utf-8')
        desc = extract_description(old_text)
        keep = patches[group].get("keep", [])
        if not keep:
            keep = list(CONCEPT_GROUPS.get(group, []))

        new_text = render_theme(theme_name, group, keep, names, desc)
        theme_file.write_text(new_text, encoding='utf-8')
        print(f"  [OK] {theme_file.name}: {len(keep)} 檔")
        updated += 1

    print(f"\n[DONE] 更新 {updated} 個 themes，跳過 {skipped} 個")


if __name__ == '__main__':
    main()
