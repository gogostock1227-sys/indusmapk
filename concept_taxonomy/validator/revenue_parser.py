"""Revenue Parser — 從 enrichment_pilot.json 抽取營收 % 拆解。

實際格式多樣（從觀察 2330 / 3017 / 3231 / 2454 / 3105 / 5285 / 2308 等樣本）：

A. 條列式（最標準，2330 格式）：
   - **[[HPC]] 高效能運算**: 佔合併營收 **61%**
   - **[[Smartphone]] 智慧型手機**: 佔營收 **26%**

B. 段落式（3017 格式）：
   [[伺服器]]與[[網通]] (含散熱模組與機殼) 佔合併營收 66%、[[筆電]] 24%、[[家電]] 10%

C. 業務拆解括號式（3231 格式）：
   **(1) [[AI 伺服器]] 與企業級伺服器 (2025 占營收約 70%)**

D. 區間式（2454 / 3105 格式）：
   智慧型手機 [[SoC]]（約 55-59%）
   光電元件 ... 占比約 20%

API:
    parse_revenue_breakdown(text: str) -> list[RevenueLine]
    sum_pct_for_keywords(lines, keywords) -> float
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class RevenueLine:
    """單筆 (描述, 百分比) 對。"""
    description: str          # 包含 [[wikilinks]] 的原始描述
    keywords: list[str]       # 從描述抽出的 [[wikilinks]] 片語
    pct: float                # 0-1 之間（25% → 0.25）
    pct_text: str             # 原文 "25%" 或 "55-59%"
    pattern: str              # which regex matched: A/B/C/D


# Pattern A: - **[[X]] 名稱**: 佔/占...營收 **N%** （**N**%）
PATTERN_A = re.compile(
    r"\*\*\[\[([^\]]+)\]\][^*\n]{0,40}\*\*[:：]\s*[佔占][^*]{0,15}\*\*(\d+(?:\.\d+)?)\s*[~\-－]?\s*(\d+(?:\.\d+)?)?%\*\*"
)
# Pattern A2 (條列式，允許區間 N-N%)
PATTERN_A2 = re.compile(
    r"^[\-•]\s*\*\*\[\[([^\]]+)\]\]([^*\n]{0,80})\*\*[:：]\s*[佔占][^\d\n]{0,15}\*\*(\d+(?:\.\d+)?)\s*[~\-－]?\s*(\d+(?:\.\d+)?)?%",
    re.MULTILINE,
)
# Pattern B: [[X]]...佔/占合併營收 N% / 佔 N% / 占整體營收 N%
PATTERN_B = re.compile(
    r"\[\[([^\]]+)\]\][^，。\n]{0,60}[佔占](?:合併|整體)?營收(?:約)?\s*(\d+(?:\.\d+)?)\s*[~\-－]?\s*(\d+(?:\.\d+)?)?%"
)
# Pattern C: (... 占/佔營收 N% ...) 或 (2025 占營收約 N%)
PATTERN_C = re.compile(
    r"\[\[([^\]]+)\]\][^（()\n]{0,80}[（(](?:\d{4}\s*[^（()\n]{0,20})?[占佔]\s*(?:合併|整體)?營收(?:約)?\s*(\d+(?:\.\d+)?)\s*[~\-－]?\s*(\d+(?:\.\d+)?)?%"
)
# Pattern D: [[X]] ... (約|占|占比約) N% 或 N-M%（取上限）
PATTERN_D = re.compile(
    r"\[\[([^\]]+)\]\][^\n]{0,80}?(?:約|占比約|佔比約|占|佔)\s*(\d+(?:\.\d+)?)\s*[~\-－]?\s*(\d+(?:\.\d+)?)?%"
)
# Pattern E (fallback): 佔合併營收 X%（無 wikilink，整段抓）
# 這個風險高（容易抓到財報數字），暫時不啟用


def _extract_keywords_from_description(desc: str) -> list[str]:
    """從含 [[X]] 的描述抽出所有 wikilinks。"""
    return re.findall(r"\[\[([^\]]+)\]\]", desc)


def parse_revenue_breakdown(text: str) -> list[RevenueLine]:
    """解析 revenue 字段，回傳所有 (描述, %) pairs。

    去重：同一 (keyword, pct) 多次出現只保留第一筆（避免段落 + 條列式重複）。
    """
    if not text or not isinstance(text, str):
        return []

    lines: list[RevenueLine] = []
    seen: set[tuple[str, float]] = set()

    def _add(kw: str, pct_str: str, pct_str2: str | None, pattern: str, raw: str):
        # 區間取上限
        try:
            pct1 = float(pct_str)
            pct2 = float(pct_str2) if pct_str2 else None
            pct = max(pct1, pct2) if pct2 else pct1
        except ValueError:
            return
        if pct <= 0 or pct > 100:
            return
        key = (kw.strip(), round(pct, 1))
        if key in seen:
            return
        seen.add(key)
        # 抽 raw line 的 wikilinks（可能有多個）
        full_keywords = _extract_keywords_from_description(raw) or [kw.strip()]
        lines.append(RevenueLine(
            description=raw[:200],
            keywords=full_keywords,
            pct=pct / 100,
            pct_text=f"{pct1}%" if not pct_str2 else f"{pct1}-{pct_str2}%",
            pattern=pattern,
        ))

    # 嘗試 A2 (條列式)
    for m in PATTERN_A2.finditer(text):
        # 抓含 wikilink 那行的整段
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        if line_end < 0:
            line_end = len(text)
        raw_line = text[line_start:line_end]
        _add(m.group(1), m.group(3), m.group(4), "A2", raw_line)

    # Pattern A (簡化版)
    for m in PATTERN_A.finditer(text):
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        if line_end < 0:
            line_end = len(text)
        raw_line = text[line_start:line_end]
        _add(m.group(1), m.group(2), m.group(3), "A", raw_line)

    # Pattern B
    for m in PATTERN_B.finditer(text):
        # 抓 ±60 字 context
        context = text[max(0, m.start()-30):min(len(text), m.end()+60)]
        _add(m.group(1), m.group(2), m.group(3), "B", context)

    # Pattern C
    for m in PATTERN_C.finditer(text):
        context = text[max(0, m.start()-20):min(len(text), m.end()+40)]
        _add(m.group(1), m.group(2), m.group(3), "C", context)

    # Pattern D（最寬鬆，最後跑且只在已有 pattern 沒抓到時補）
    if not lines:
        for m in PATTERN_D.finditer(text):
            context = text[max(0, m.start()-20):min(len(text), m.end()+40)]
            _add(m.group(1), m.group(2), m.group(3), "D", context)

    return lines


_DOWNSTREAM_CONTEXT_MARKERS = [
    "應用於", "應用为", "應用為", "終端應用", "終端為",
    "卖给", "賣給", "下游客戶", "下游應用",
    "服務 ", "服務於",
    "客戶涵蓋", "客戶結構",
]


def _is_downstream_context(line_desc: str, keyword: str) -> bool:
    """檢查 keyword 是否落在「應用於 / 終端應用 / 客戶」之後 — 代表這是下游不是主業。"""
    desc_lower = line_desc.lower()
    kw_lower = keyword.lower()
    kw_idx = desc_lower.find(kw_lower)
    if kw_idx < 0:
        return False
    # 看 keyword 之前 60 字內是否有 downstream marker
    window_start = max(0, kw_idx - 60)
    window = desc_lower[window_start:kw_idx]
    for marker in _DOWNSTREAM_CONTEXT_MARKERS:
        if marker.lower() in window:
            return True
    return False


def _kw_match_with_boundary(text: str, kw: str) -> list[int]:
    """找 keyword 在 text 出現的所有位置，使用 word boundary 避免子字串誤判。

    對英文 keyword（如 SiC），用 regex \\b 邊界
    對中文 keyword（如 碳化矽），用直接子字串（中文沒 word boundary 概念）

    回傳所有 idx list（沒命中回 []）
    """
    if not kw:
        return []
    # 判斷是否含中文
    has_chinese = any('一' <= ch <= '鿿' for ch in kw)
    indices: list[int] = []
    if has_chinese:
        # 直接子字串（case-sensitive 但中文無大小寫）
        start = 0
        while True:
            idx = text.find(kw, start)
            if idx < 0:
                break
            indices.append(idx)
            start = idx + len(kw)
    else:
        # 英文：用 \b boundary（case-insensitive）
        try:
            for m in re.finditer(rf"\b{re.escape(kw)}\b", text, flags=re.IGNORECASE):
                indices.append(m.start())
        except re.error:
            # fallback
            text_lower = text.lower()
            kw_lower = kw.lower()
            start = 0
            while True:
                idx = text_lower.find(kw_lower, start)
                if idx < 0:
                    break
                indices.append(idx)
                start = idx + len(kw_lower)
    return indices


def sum_pct_for_keywords(lines: list[RevenueLine], keywords: list[str]) -> tuple[float, list[RevenueLine]]:
    """累加營收行中、描述含任一 keyword 的 pct 總和。

    匹配規則（v4 修正）：
    - 英文 keyword 用 \\b word boundary（避免 "SiC" 誤匹配 "ASIC"）
    - 中文 keyword 用直接子字串
    - Anti-pattern: 若 keyword 出現在「應用於 / 終端應用 / 客戶涵蓋」之後，視為下游應用不算

    回傳 (total_pct, matched_lines) — total_pct 0-1 之間。
    """
    total = 0.0
    matched: list[RevenueLine] = []
    for line in lines:
        desc = line.description
        line_matched = False
        for kw in keywords:
            indices = _kw_match_with_boundary(desc, kw)
            if not indices:
                continue
            # 若該 keyword 所有出現位置「都」落在下游 context → 不算
            # 至少一處不是下游 → 算主業
            all_downstream = True
            for idx in indices:
                window = desc.lower()[max(0, idx - 60):idx]
                if not any(m.lower() in window for m in _DOWNSTREAM_CONTEXT_MARKERS):
                    all_downstream = False
                    break
            if not all_downstream:
                line_matched = True
                break
        if line_matched:
            total += line.pct
            matched.append(line)
    return min(total, 1.0), matched


# CLI demo
if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    ROOT = Path(__file__).resolve().parents[2]
    ep = json.loads((ROOT / "My-TW-Coverage" / "enrichment_pilot.json").read_text(encoding="utf-8"))
    targets = sys.argv[1:] or ["2330", "3017", "3231", "2454", "3105", "3686", "5285", "2308"]
    for tk in targets:
        rec = ep.get(tk, {})
        rev = rec.get("revenue") or ""
        lines = parse_revenue_breakdown(rev)
        print(f"\n=== {tk} ({len(lines)} lines) ===")
        for L in lines[:8]:
            print(f"  [{L.pattern}] {L.pct*100:5.1f}% | kws={L.keywords[:3]} | desc={L.description[:80]!r}")
