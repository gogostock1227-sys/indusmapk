"""V3 提取腳本：雙模式
模式 A: 直接 grep `"群名": [...]` Python list 區塊（用於 batch_1/2 等寫了 list 的）
模式 B: 反向定位 group name + 段落分析（用於 batch_3-9 等沒寫 list 的）

合併兩模式結果產出 master_patch.json
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


# ============ 模式 A: Python list 精準提取 ============
def extract_python_lists(text: str) -> dict[str, list[str]]:
    """提取 `"群名": [\n ... \n],` 格式的 Python list"""
    results = {}
    # match `"GROUP": [` ... `\n],` 區塊
    pattern = re.compile(
        r'^"([^"]+)":\s*\[\n(.*?)^\],',
        re.MULTILINE | re.DOTALL,
    )
    for m in pattern.finditer(text):
        group = m.group(1)
        body = m.group(2)
        # 提取所有 "XXXX" — 包含 4-6 位代號
        tickers = re.findall(r'"(\d{4,6}[A-Z]?)"', body)
        # 去重保序
        seen = set()
        uniq = []
        for t in tickers:
            if t in seen:
                continue
            seen.add(t)
            uniq.append(t)
        if uniq:
            results[group] = uniq
    return results


# ============ 模式 B: 反向定位（normalize 匹配） ============
def normalize(s: str) -> str:
    """去空格/標點/反斜線，方便 fuzzy match"""
    return re.sub(r'[\s\-\.,/\\（）\(\)【】\[\]]+', '', s).lower()


def find_group_blocks(text: str, group: str) -> list[str]:
    """用 normalize 匹配在 batch.md 中找到該 group 的所有 section
    block 結束於同級或更高級的標題（避免子段 ### 把 block 切短）
    """
    g_norm = normalize(group)
    blocks = []
    for m in re.finditer(r'^(#{2,4})\s+(.+)$', text, re.MULTILINE):
        hash_level = len(m.group(1))  # 2/3/4
        title = m.group(2)
        cand = re.sub(
            r'^[【\[]?[一二三四五六七八九十0-9０-９.]+[】\].、\s]*',
            '',
            title,
        )
        cand = re.sub(r'[（\(].*$', '', cand).strip()
        if normalize(cand) == g_norm:
            start = m.end()
            # 找下一個同級或更高級標題（hash 數 ≤ hash_level）
            # 例如當前是 ## (level 2)，下一個只看 ## 或 #
            next_pat = rf'^#{{1,{hash_level}}}\s+\S'
            next_m = re.search(next_pat, text[start:], re.MULTILINE)
            end = start + next_m.start() if next_m else len(text)
            blocks.append(text[start:end])
    return blocks


def extract_keep_from_block(block: str) -> list[str]:
    """從 block 中提取保留 ticker
    過濾規則：
    1. 切「應移除/移除」段標題之前
    2. 對每行，跳過含「移除」「reclassify」「→」等關鍵字的行
    3. 收集剩下行的所有 4-6 位代號
    """
    # Step 1: 切「應移除」段標題之前
    remove_split = re.split(
        r'#{2,4}\s*(?:\d+[\.、]?\s*)?(?:應移除|移除|建議移除)',
        block,
        maxsplit=1,
    )
    keep_section = remove_split[0]
    remove_section = remove_split[1] if len(remove_split) > 1 else ''

    # Step 2: 對 keep_section 每行做 line filter
    REMOVE_KEYWORDS = (
        '移除', '應移除', 'reclassify', '重分類', '誤入', '誤分類',
        '誤列', '應移到', '應歸', '無關', '不在 HBM', '應從',
    )
    keep_lines = []
    for line in keep_section.split('\n'):
        # 跳過含移除關鍵字的行
        if any(kw in line for kw in REMOVE_KEYWORDS):
            continue
        keep_lines.append(line)
    keep_section_clean = '\n'.join(keep_lines)

    keep_raw = re.findall(r'\b(\d{4}[A-Z]?)\b', keep_section_clean)
    remove_raw = re.findall(r'\b(\d{4}[A-Z]?)\b', remove_section)

    # 從「應移除」段中收集明確要排除的 ticker
    seen_r = set(remove_raw)

    seen_k = set()
    final = []
    for t in keep_raw:
        if t in seen_k or t in seen_r:
            continue
        seen_k.add(t)
        final.append(t)
    return final


def main():
    batch_files = sorted(TAXONOMY.glob("batch_*.md"))

    # 模式 A: 對每個 batch 提取所有 Python list
    mode_a = {}
    for f in batch_files:
        text = f.read_text(encoding='utf-8')
        lists = extract_python_lists(text)
        for g, tl in lists.items():
            # 模糊匹配到 GROUP_NAMES
            actual = None
            for ag in GROUP_NAMES:
                if ag == g or ag.replace('\\', '/') == g or ag.replace('/', '\\') == g:
                    actual = ag
                    break
            if not actual:
                # try strip
                for ag in GROUP_NAMES:
                    if ag.replace(' ', '') == g.replace(' ', ''):
                        actual = ag
                        break
            if actual:
                mode_a[actual] = (tl, f.stem)

    print(f"[模式 A] 從 Python list 抓到: {len(mode_a)} 群")

    # 模式 B: 對 GROUP_NAMES 沒在 mode_a 的，用反向定位
    mode_b = {}
    for group in GROUP_NAMES:
        if group == "HBM 高頻寬記憶體" or group in mode_a:
            continue
        best_keep = []
        best_source = None
        for f in batch_files:
            text = f.read_text(encoding='utf-8')
            blocks = find_group_blocks(text, group)
            for block in blocks:
                keep = extract_keep_from_block(block)
                # 過濾合理 ticker 範圍
                keep = [t for t in keep if 1100 <= int(t[:4]) <= 9999]
                if len(keep) > len(best_keep):
                    best_keep = keep
                    best_source = f.stem
        if best_keep:
            mode_b[group] = (best_keep, best_source)

    print(f"[模式 B] 反向定位抓到: {len(mode_b)} 群")

    # 合併
    patches = {}
    for g, (tl, src) in mode_a.items():
        patches[g] = {"keep": tl, "source": src, "mode": "A"}
    for g, (tl, src) in mode_b.items():
        if g not in patches:
            patches[g] = {"keep": tl, "source": src, "mode": "B"}

    OUT_JSON.write_text(
        json.dumps(patches, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    total_groups = len(GROUP_NAMES) - 1  # 排除 HBM
    coverage = len(patches) * 100 / total_groups
    print(f"\n[DONE] {len(patches)} / {total_groups} 群 ({coverage:.1f}%) → {OUT_JSON}")
    missing = [g for g in GROUP_NAMES if g not in patches and g != "HBM 高頻寬記憶體"]
    print(f"\nMissing ({len(missing)}):")
    for g in missing[:40]:
        print(f"  - {g}")


if __name__ == '__main__':
    main()
