"""
Phase 6 票 2 — 主業 dominance 判定（純文字分析，無 LLM）。

底層邏輯：
  打開 My-TW-Coverage/Pilot_Reports/{sector}/{ticker}_{name}.md
  抓 `## 業務簡介` 的「主簡介段落」（metadata block 之後第一段）
  看 spec.core_keywords 第一次出現的 char-offset：

    < 80 字  → STRONG_PASS（族群業務寫在主簡介開頭，pure-play）
    80-300 字 → WEAK_PASS（主簡介有提，但不在開頭）
    > 300 字 或 整個業務簡介都沒提 → FAIL（不是主業）

不命中時，第二輪 fallback：找「核心競爭優勢 (1)」、「核心產品」「主力產品」段落第一句。

API：
    score_dominance(ticker, spec) -> DominanceVote
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

TAXONOMY_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = TAXONOMY_DIR.parent
COVERAGE_DIR = PROJECT_ROOT / "My-TW-Coverage" / "Pilot_Reports"


@dataclass
class DominanceVote:
    verdict: str          # "STRONG_PASS" | "WEAK_PASS" | "FAIL" | "ABSTAIN"
    matched_keyword: str = ""
    char_offset: int = -1
    section: str = ""     # 在哪個段落命中
    quote: str = ""       # ±60 字 window
    reason: str = ""
    excluded_role: str = ""  # 命中排除角色（設備/耗材/通路）時記錄

    @property
    def is_pass(self) -> bool:
        return self.verdict in ("STRONG_PASS", "WEAK_PASS")

    @property
    def is_strong(self) -> bool:
        return self.verdict == "STRONG_PASS"


# 排除角色關鍵字 — 出現在簡介前 250 字代表「公司是供應商/設備商/通路而非主軸廠」
# 命中即降為 FAIL_ROLE_EXCLUDED（不論 core keyword 位置多前面）
ROLE_EXCLUSION_KEYWORDS = [
    # 設備類
    "製程設備", "濕製程", "微影設備", "封裝設備", "測試設備", "檢測設備", "烤箱設備",
    "設備廠", "設備供應商", "曝光機", "蝕刻機", "薄膜設備", "鍍膜設備", "印刷設備",
    "模組化設備", "自動化設備", "工業設備", "雷射鑽孔設備", "鑽孔設備", "鑽孔機",
    "雷射代工", "代工服務供應商", "代工服務", "CO2 雷射", "成型加工",
    # 耗材 / 上游材料類
    "鑽孔墊板", "鑽孔用板", "墊板", "化學品原料", "電鍍化學品", "光阻原料",
    "原料供應商", "耗材供應", "耗材製造", "代工耗材",
    # 通路 / 代理 / 分銷
    "代理 ", "代理商", "通路商", "經銷商", "分銷商", "電子通路",
    # 軟板 / PCB（被歸 ABF 載板時排除）— 這個排除依族群動態加，不放這
]


# 族群特定的排除關鍵字（強排除，命中直接 FAIL）
GROUP_SPECIFIC_EXCLUSIONS = {
    "ABF載板": ["軟板", "FPC", "PCB 製造商", "PCB 大廠", "PCB 廠"],
    "矽光子": ["LED 製造", "Mini LED", "Micro LED", "毫米波"],
    "HBM 高頻寬記憶體": ["NAND Flash 控制", "POS", "Wi-Fi", "工業電腦"],
    "石英元件": ["有線電視", "環保工程", "工業電腦", "測試設備"],
    "連接器": ["IC 設計", "晶圓代工"],
    "散熱/液冷": ["UPS", "電源供應器主業"],
    "矽晶圓": ["晶圓代工", "晶圓代工廠"],
}


def find_coverage_file(ticker: str) -> Optional[Path]:
    if not COVERAGE_DIR.exists():
        return None
    for path in COVERAGE_DIR.glob(f"**/{ticker}_*.md"):
        return path
    return None


def _strip_markdown(text: str) -> str:
    """移除 wikilinks / bold / code，方便 keyword 位置比對。"""
    text = re.sub(r"\[\[([^\]]+?)\]\]", r"\1", text)
    text = re.sub(r"\*\*([^\*]+?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+?)`", r"\1", text)
    return text


def _extract_main_intro(coverage_text: str) -> str:
    """抓 `## 業務簡介` 區段中 metadata block 之後的第一段業務描述。

    pattern：metadata 結束（**企業價值:** 那行後的第一個空行）→ 直到下一個 ## 或 區塊結束 / 或下一個空行
    """
    m = re.search(r"##\s+業務簡介\s*\n(.*?)(?=\n##\s|\Z)", coverage_text, re.DOTALL)
    if not m:
        return ""
    body = m.group(1)

    # 跳過 metadata block（**XX:** value 連續行）
    lines = body.split("\n")
    i = 0
    # 跳前置空行
    while i < len(lines) and not lines[i].strip():
        i += 1
    # 跳 metadata 行（** 開頭）
    while i < len(lines) and (lines[i].strip().startswith("**") or not lines[i].strip()):
        i += 1
    # 第一段業務描述：直到下一個空行
    paragraph = []
    while i < len(lines) and lines[i].strip():
        paragraph.append(lines[i])
        i += 1
    return _strip_markdown(" ".join(paragraph)).strip()


def _extract_customers_section(coverage_text: str) -> str:
    """抓 `## 主要客戶及供應商` 中『主要客戶』子段落（純文字，去 wikilinks）。"""
    m = re.search(r"##\s+主要客戶[及與]?供應商?\s*\n(.*?)(?=\n##\s|\Z)", coverage_text, re.DOTALL)
    if not m:
        # fallback：用整個供應鏈位置 + 主要客戶段
        m2 = re.search(r"##\s+(?:主要客戶|供應鏈位置)\s*\n(.*?)(?=\n##\s|\Z)", coverage_text, re.DOTALL)
        if not m2:
            return ""
        body = m2.group(1)
    else:
        body = m.group(1)
    # 抓「主要客戶」開始到「供應商」之前
    cust = re.search(r"###?\s*主要客戶\s*\n(.*?)(?=###?\s*主要供應商|\Z)", body, re.DOTALL)
    if cust:
        body = cust.group(1)
    return _strip_markdown(body).strip()


def _extract_supplychain_self(coverage_text: str) -> str:
    """抓 `## 供應鏈位置` 中『中游 (xxx)』段落（公司自身業務定位），fallback 用。"""
    m = re.search(r"##\s+供應鏈位置\s*\n(.*?)(?=\n##\s|\Z)", coverage_text, re.DOTALL)
    if not m:
        return ""
    body = m.group(1)
    # 找「**中游」「**核心產品」「**主力產品」段
    mid = re.search(
        r"\*\*(中游|核心產品|主力產品|核心競爭優勢)[^*]*?\*\*[:：]?\s*(.*?)(?=\*\*|\n\n|\Z)",
        body,
        re.DOTALL,
    )
    return _strip_markdown(mid.group(2)).strip() if mid else ""


def _detect_role_exclusion(intro: str, group_name: str = "") -> tuple[str, int]:
    """偵測排除角色關鍵字（設備/耗材/通路/特定族群排除詞）。

    回 (matched_keyword, position) 或 ("", -1) 沒命中。
    只看簡介前 250 字（避免下游應用段落的誤命中）。
    """
    head = intro[:250]
    # 通用 role exclusion
    earliest_idx = -1
    earliest_kw = ""
    for kw in ROLE_EXCLUSION_KEYWORDS:
        idx = head.find(kw)
        if idx >= 0 and (earliest_idx < 0 or idx < earliest_idx):
            earliest_idx = idx
            earliest_kw = kw
    # 族群特定排除
    if group_name:
        for kw in GROUP_SPECIFIC_EXCLUSIONS.get(group_name, []):
            idx = head.find(kw)
            if idx >= 0 and (earliest_idx < 0 or idx < earliest_idx):
                earliest_idx = idx
                earliest_kw = kw
    return earliest_kw, earliest_idx


def score_dominance(
    ticker: str,
    core_keywords: list[str],
    coverage_path: Optional[Path] = None,
    group_name: str = "",
) -> DominanceVote:
    """
    Args:
        ticker: 股票代號
        core_keywords: spec.core_keywords + 同義詞
        coverage_path: 直接給 path 跳過 glob（測試用）
        group_name: 族群名稱（用於 GROUP_SPECIFIC_EXCLUSIONS 查詢）

    Returns:
        DominanceVote
    """
    path = coverage_path or find_coverage_file(ticker)
    if path is None:
        return DominanceVote(verdict="ABSTAIN", reason="Coverage 報告不存在")

    text = path.read_text(encoding="utf-8")

    # === 第一輪：主業簡介第一段 ===
    intro = _extract_main_intro(text)
    if intro:
        # 先找 role exclusion（角色排除優先）
        excl_kw, excl_idx = _detect_role_exclusion(intro, group_name)

        for kw in core_keywords:
            idx = intro.find(kw)
            if idx < 0:
                continue
            start = max(0, idx - 30)
            end = min(len(intro), idx + len(kw) + 60)
            quote = intro[start:end].replace("\n", " ")

            # 角色排除：若 role exclusion 出現在 core keyword 之前 → FAIL
            if excl_kw and excl_idx < idx:
                return DominanceVote(
                    verdict="FAIL",
                    matched_keyword=kw,
                    char_offset=idx,
                    section="業務簡介(角色被排除)",
                    quote=quote,
                    excluded_role=excl_kw,
                    reason=f"角色「{excl_kw}」(第 {excl_idx} 字) 出現在 keyword「{kw}」(第 {idx} 字) 之前 → 是供應商/設備/通路非主軸廠",
                )

            if idx < 80:
                return DominanceVote(
                    verdict="STRONG_PASS",
                    matched_keyword=kw,
                    char_offset=idx,
                    section="業務簡介(開頭)",
                    quote=quote,
                    reason=f"keyword「{kw}」出現在主業簡介第 {idx} 字（pure-play 證據）",
                )
            if idx < 300:
                return DominanceVote(
                    verdict="WEAK_PASS",
                    matched_keyword=kw,
                    char_offset=idx,
                    section="業務簡介(中後段)",
                    quote=quote,
                    reason=f"keyword「{kw}」出現在第 {idx} 字（主業有提，但不在第一句）",
                )

    # === 第二輪：供應鏈中游 / 核心產品 段落 ===
    supply_self = _extract_supplychain_self(text)
    if supply_self:
        for kw in core_keywords:
            if kw in supply_self:
                return DominanceVote(
                    verdict="WEAK_PASS",
                    matched_keyword=kw,
                    section="供應鏈位置(中游/核心產品)",
                    quote=supply_self[:200],
                    reason=f"keyword「{kw}」出現在供應鏈中游段（自我定位）",
                )

    # === 完全沒命中 ===
    return DominanceVote(
        verdict="FAIL",
        reason="業務簡介 + 供應鏈中游段都沒提族群 keyword（非主業）",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 客戶模式 — 用於「客戶概念股」群（蘋果/輝達/特斯拉等）
# 不看主業簡介，看「主要客戶」段落是否明列該客戶
# ─────────────────────────────────────────────────────────────────────────────
def score_customer_dominance(
    ticker: str,
    customer_keywords: list[str],
    coverage_path: Optional[Path] = None,
) -> DominanceVote:
    """
    客戶概念股驗證：在 `## 主要客戶及供應商` 段落找客戶 keyword。

    < 80 字   → STRONG_PASS（明確主要客戶，列在前列）
    80-300 字 → WEAK_PASS（次要客戶 / 供應鏈內提及）
    > 300 字 / 不出現 → FAIL（非該客戶供應鏈）
    """
    path = coverage_path or find_coverage_file(ticker)
    if path is None:
        return DominanceVote(verdict="ABSTAIN", reason="Coverage 不存在")

    text = path.read_text(encoding="utf-8")
    customers = _extract_customers_section(text)
    if not customers:
        # fallback to 主業簡介（有些 Coverage 把客戶寫進業務簡介）
        intro = _extract_main_intro(text)
        target = intro
        section = "業務簡介(fallback)"
    else:
        target = customers
        section = "主要客戶"

    if not target:
        return DominanceVote(verdict="FAIL", reason="主要客戶段落空")

    # 找最早 hit 的 customer keyword
    earliest_idx = -1
    earliest_kw = ""
    for kw in customer_keywords:
        idx = target.find(kw)
        if idx >= 0 and (earliest_idx < 0 or idx < earliest_idx):
            earliest_idx = idx
            earliest_kw = kw

    if earliest_idx < 0:
        return DominanceVote(verdict="FAIL", reason=f"主要客戶段落未提及 {customer_keywords[:3]}")

    start = max(0, earliest_idx - 30)
    end = min(len(target), earliest_idx + len(earliest_kw) + 60)
    quote = target[start:end].replace("\n", " ")

    if earliest_idx < 80:
        return DominanceVote(
            verdict="STRONG_PASS",
            matched_keyword=earliest_kw,
            char_offset=earliest_idx,
            section=section,
            quote=quote,
            reason=f"主要客戶第 {earliest_idx} 字命中「{earliest_kw}」(主軸客戶)",
        )
    if earliest_idx < 300:
        return DominanceVote(
            verdict="WEAK_PASS",
            matched_keyword=earliest_kw,
            char_offset=earliest_idx,
            section=section,
            quote=quote,
            reason=f"主要客戶第 {earliest_idx} 字命中「{earliest_kw}」(次要客戶)",
        )
    return DominanceVote(
        verdict="FAIL",
        matched_keyword=earliest_kw,
        char_offset=earliest_idx,
        reason=f"keyword「{earliest_kw}」太後（第 {earliest_idx} 字）→ 邊緣客戶",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 自我測試 / CLI demo
# ─────────────────────────────────────────────────────────────────────────────
def _demo():
    """python -m validator.dominance"""
    cases = [
        ("3037", "ABF載板", ["ABF 載板", "ABF", "IC 載板"], "STRONG_PASS"),
        ("8046", "ABF載板", ["ABF 載板", "ABF", "IC 載板"], "STRONG_PASS"),
        ("3189", "ABF載板", ["ABF 載板", "ABF", "IC 載板"], "STRONG_PASS"),
        ("8074", "ABF載板", ["ABF 載板", "ABF"], "FAIL"),       # 鉅橡是耗材廠
        ("4577", "ABF載板", ["ABF 載板", "ABF"], "FAIL"),       # 科嘉 是製程設備
        ("3485", "ABF載板", ["ABF 載板", "ABF"], "FAIL"),       # 敘豐是濕製程設備
        ("3114", "ABF載板", ["ABF 載板", "ABF"], "FAIL"),       # 好德是通路代理
        ("4958", "ABF載板", ["ABF 載板", "ABF"], "FAIL"),       # 臻鼎-KY 主業是 PCB / 軟板
        ("3093", "ABF載板", ["ABF 載板", "ABF"], "FAIL"),       # 港建
        ("6664", "ABF載板", ["ABF 載板", "ABF"], "FAIL"),       # 群翊是載板烤箱設備
        ("3042", "石英元件", ["石英", "石英晶體", "石英元件"], "STRONG_PASS"),
        ("6488", "矽晶圓", ["矽晶圓"], "STRONG_PASS"),                  # 環球晶
    ]
    print(f"{'ticker':<8}{'group':<10}{'expected':<14}{'verdict':<14}{'kw':<14}{'offset':<8}{'reason'}")
    print("=" * 130)
    for ticker, group, kws, expected in cases:
        v = score_dominance(ticker, kws, group_name=group)
        ok = "✓" if (
            (expected == "STRONG_PASS" and v.verdict == "STRONG_PASS") or
            (expected == "FAIL" and v.verdict == "FAIL")
        ) else "✗"
        print(f"{ok} {ticker:<6}{group:<10}{expected:<14}{v.verdict:<14}{v.matched_keyword:<14}{v.char_offset:<8}{v.reason[:60]}")


if __name__ == "__main__":
    _demo()
