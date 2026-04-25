"""V2 提取腳本：用 group name 反向定位，不依賴標題格式。

策略：
1. 從 CONCEPT_GROUPS 取所有 190 個 group name
2. 對每個 batch.md，搜尋每個 group name 第一次出現的位置（含上下文判斷）
3. 從該位置抓「該 section」的內容（直到下一個 group name 或 ## 標題）
4. 在 section 中找所有 4-6 位代號（不論是否粗體）
5. 排除「應移除」/「移除」段落中的代號
"""
from __future__ import annotations
import re
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAXONOMY = ROOT / "concept_taxonomy"
OUT_JSON = TAXONOMY / "master_patch.json"

sys.path.insert(0, str(ROOT))
from concept_groups import CONCEPT_GROUPS  # noqa
GROUP_NAMES = list(CONCEPT_GROUPS.keys())


def find_group_blocks(text: str, group: str) -> list[str]:
    """在 batch.md 中找到該 group 的所有 section 內容"""
    # group name 可能含特殊字符（/, \, 空格），escape
    g_escaped = re.escape(group)
    # 嘗試多種出現格式：「## N. {group}」「### 【N】 {group}」「{group} (X →」「## {group}」
    patterns = [
        rf'^#{{2,4}}\s*[【\[]?\d*[】\].、\s]*{g_escaped}\s*[（\(]',
        rf'^#{{2,4}}\s*\d*\.\s*{g_escaped}\s*[（\(]',
        rf'^#{{2,4}}\s*[一二三四五六七八九十]+[、.]\s*{g_escaped}\s*[（\(]',
        rf'^#{{2,4}}\s*{g_escaped}\b',
    ]
    blocks = []
    for pat in patterns:
        for m in re.finditer(pat, text, re.MULTILINE):
            start = m.end()
            # 找下一個 ## 或 ### 標題
            next_m = re.search(r'^#{2,4}\s+', text[start:], re.MULTILINE)
            end = start + next_m.start() if next_m else len(text)
            blocks.append(text[start:end])
    return blocks


def extract_keep_tickers(block: str) -> tuple[list[str], list[str]]:
    """從一個 section block 中提取保留代號和移除代號"""
    # 切「應移除」「移除」「### 修正後」之前
    # 注意：要保留 ### 三維拆解、### 核心、### 衛星 等段落
    remove_split = re.split(
        r'#{2,4}\s*(?:\d+[\.、]?\s*)?(?:應移除|移除|建議移除)|---\s*\n.*移除',
        block,
        maxsplit=1,
    )
    keep_section = remove_split[0]
    remove_section = remove_split[1] if len(remove_split) > 1 else ''

    # 在 keep_section 中找所有 4-6 位代號
    # 各種出現格式：**XXXX**, | XXXX |, - **XXXX** ..., | **XXXX** |
    keep_tickers = re.findall(r'\b(\d{4}[A-Z]?)\b', keep_section)
    remove_tickers = re.findall(r'\b(\d{4}[A-Z]?)\b', remove_section)

    # 去重保序
    seen_k = set()
    keep_uniq = []
    for t in keep_tickers:
        # 過濾掉年份、檔數等非 ticker（4 位數但不是台股代號的）
        # 台股代號範圍 1xxx-9xxx；過濾常見非 ticker 數字
        if t in seen_k:
            continue
        if t.startswith(('19', '20', '21', '22')) and len(t) == 4:
            # 可能是年份 1900-2299，但台股 2xxx 是金融股，要保留
            # 簡單規則：保留 1xxx (水泥/食品)、2xxx (金融/電子)、3-8xxx (科技/服務)、9xxx (傳產)
            # 排除 2026, 2027 之類常見年份用上下文判斷困難，先全保留再 sanity check
            pass
        seen_k.add(t)
        keep_uniq.append(t)

    seen_r = set()
    remove_uniq = []
    for t in remove_tickers:
        if t in seen_r:
            continue
        seen_r.add(t)
        remove_uniq.append(t)

    # keep - remove
    final_keep = [t for t in keep_uniq if t not in seen_r]
    return final_keep, remove_uniq


def main():
    batch_files = sorted(TAXONOMY.glob("batch_*.md"))
    all_text = {f.stem: f.read_text(encoding='utf-8') for f in batch_files}

    patches = {}
    for group in GROUP_NAMES:
        if group == "HBM 高頻寬記憶體":
            continue  # 已個別處理
        # 在每個 batch 中找該 group 的 block
        best_keep = []
        best_remove = []
        source = None
        for batch_name, text in all_text.items():
            blocks = find_group_blocks(text, group)
            for block in blocks:
                keep, remove = extract_keep_tickers(block)
                # 過濾掉年份、無效 ticker
                # 台股 ticker 通常 4 位數字 1100-9999
                keep = [t for t in keep if 1100 <= int(t[:4]) <= 9999]
                remove = [t for t in remove if 1100 <= int(t[:4]) <= 9999]
                # 取 keep 較長的 block（通常是詳細 section 而非摘要表）
                if len(keep) > len(best_keep):
                    best_keep = keep
                    best_remove = remove
                    source = batch_name
        if best_keep:
            patches[group] = {
                "keep": best_keep,
                "removed": [{"ticker": t} for t in best_remove],
                "source_batch": source,
            }

    OUT_JSON.write_text(
        json.dumps(patches, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    print(f"\n[DONE] {len(patches)} 群 → {OUT_JSON}")
    print(f"未匹配族群數: {len(GROUP_NAMES) - len(patches) - 1}")  # -1 for HBM
    missing = [g for g in GROUP_NAMES if g not in patches and g != "HBM 高頻寬記憶體"]
    print(f"\nMissing ({len(missing)}):")
    for g in missing[:50]:
        print(f"  - {g}")


if __name__ == '__main__':
    main()
