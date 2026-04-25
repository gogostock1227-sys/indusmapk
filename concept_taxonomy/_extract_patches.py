"""從 concept_taxonomy/batch_*.md 提取每個族群的修正後成分股清單。

策略：
1. 對每個 batch.md，按 ## 切 section
2. 從每個 section 的 group name 識別族群
3. 找「應移除」之前的所有粗體代號 **XXXX**，作為「保留」清單
4. 寫到 master_patch.json
"""
from __future__ import annotations
import re
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAXONOMY = ROOT / "concept_taxonomy"
OUT_JSON = TAXONOMY / "master_patch.json"

# 載入 concept_groups.py 的當前族群名稱（用來模糊匹配 agent 寫的群名）
sys.path.insert(0, str(ROOT))
from concept_groups import CONCEPT_GROUPS  # noqa
GROUP_NAMES = list(CONCEPT_GROUPS.keys())


def normalize(s: str) -> str:
    """正規化群名：去空白、去全形/半形差異、去標點"""
    return re.sub(r'[\s\u3000\u00a0\.、\(\)（）/／\\]', '', s).lower()


def find_group_name(candidate: str) -> str | None:
    """模糊匹配 agent 寫的群名到實際 concept_groups 中的族群名"""
    cand_norm = normalize(candidate)
    if not cand_norm:
        return None
    for g in GROUP_NAMES:
        if normalize(g) == cand_norm:
            return g
    # 子字串匹配（例如 agent 寫「記憶體」對應「記憶體」）
    for g in GROUP_NAMES:
        g_norm = normalize(g)
        if cand_norm in g_norm or g_norm in cand_norm:
            return g
    return None


def parse_batch(batch_path: Path) -> dict[str, list[str]]:
    text = batch_path.read_text(encoding='utf-8')
    # 同時抓 ## 和 ### 標題
    sections = re.split(r'^#{2,4}\s+', text, flags=re.MULTILINE)[1:]
    patches = {}
    for section in sections:
        first_line = section.split('\n', 1)[0]
        # 群名提取 — 兼容多種格式：
        # 「1. 記憶體 (21 → 14)」、「一、網通 (58 → 26)」、「【1】 AI PC/邊緣AI（11 檔）」
        # 「記憶體 (21 → 14)」、「6. 量子電腦」（沒括號也接受）
        m = re.match(
            r'(?:[【\[]?[一二三四五六七八九十0-9０-９]+[】\].、\)）]?\s*)?(.+?)(?:\s*[（\(]\s*\d|$)',
            first_line,
        )
        if not m:
            continue
        candidate = m.group(1).strip().rstrip('）)】]')
        # 跳過 meta section
        skip_kw = ['摘要', '說明', '結論', '附錄', '整體', '執行', '範圍', '族群成分股決策表',
                   '處理範圍', '族群定位', '三維拆解', '應移除', '修正後', '現狀問題',
                   '主要問題', '重複族群', '過時族群', '建議', '族群類型']
        if any(kw in candidate for kw in skip_kw):
            continue
        group = find_group_name(candidate)
        if not group:
            continue
        # 切「應移除」之前
        body_before_remove = re.split(
            r'#{2,4}\s*\d?\.?\s*(?:應移除|移除|建議移除|.*?移除)', section
        )[0]
        # 「**結論**」「**決策**」之前
        body_before_remove = re.split(r'\*\*(?:結論|決策)\*\*', body_before_remove)[0]
        # 提取粗體代號（4-6 位數字 + 可選字母）
        tickers = re.findall(r'\*\*(\d{4,6}[A-Z]?)\b', body_before_remove)
        # 去重、保序
        seen = set()
        uniq = []
        for t in tickers:
            if t not in seen:
                seen.add(t)
                uniq.append(t)
        if not uniq:
            continue
        # 同族群可能多次出現，取較大的版本
        if group in patches:
            if len(uniq) > len(patches[group]):
                patches[group] = uniq
        else:
            patches[group] = uniq
    return patches


def main():
    all_patches = {}
    for batch_md in sorted(TAXONOMY.glob("batch_*.md")):
        print(f"\n=== {batch_md.name} ===")
        p = parse_batch(batch_md)
        for g, tl in p.items():
            print(f"  {g}: {len(tl)} 檔 → {tl[:8]}{'...' if len(tl) > 8 else ''}")
        all_patches.update(p)

    OUT_JSON.write_text(
        json.dumps(all_patches, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    print(f"\n[DONE] {len(all_patches)} 族群 → {OUT_JSON}")
    print(f"未匹配族群（仍保留原狀）: {len(GROUP_NAMES) - len(all_patches)}")
    missing = [g for g in GROUP_NAMES if g not in all_patches]
    print("Missing:")
    for g in missing[:30]:
        print(f"  {g}")


if __name__ == '__main__':
    main()
