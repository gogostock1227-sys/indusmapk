"""
證據抽取：Coverage（My-TW-Coverage 深度報告） + finlab（產業類別、市場別）。

設計原則：
  - Coverage：用 Path.glob 找 `Pilot_Reports/**/{sym}_*.md`，對 keywords 抓 ±60 字 window 引用
  - finlab：snapshot 一次到 parquet，後續驗證讀 parquet（10s vs 90s）
  - 兩者都 sqlite/parquet 快取，可重現

入口：
  - extract_coverage(sym, keywords) -> dict {path, found_quotes[], section_hits[]}
  - load_finlab_snapshot(force_refresh=False) -> pd.DataFrame
  - lookup_finlab(sym, snapshot=None) -> dict {name, twse_industry, market}
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# 專案路徑
TAXONOMY_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = TAXONOMY_DIR.parent
COVERAGE_DIR = PROJECT_ROOT / "My-TW-Coverage" / "Pilot_Reports"
SNAPSHOT_PATH = TAXONOMY_DIR / "validator" / "cache" / "finlab_snapshot.parquet"
SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Coverage 抽取
# ─────────────────────────────────────────────────────────────────────────────
QUOTE_WINDOW = 60  # 關鍵字前後各取 60 字
PRIMARY_COVERAGE_SECTIONS = (
    "業務簡介",
    "供應鏈位置",
    "主要客戶及供應商",
    "營收來源",
    "產業趨勢與成長動能",
)


def find_coverage_file(sym: str) -> Optional[Path]:
    """找 Pilot_Reports/**/{sym}_*.md。回最早匹配的一份（理論上只有一份）。"""
    if not COVERAGE_DIR.exists():
        return None
    for path in COVERAGE_DIR.glob(f"**/{sym}_*.md"):
        return path
    return None


def _strip_markdown(text: str) -> str:
    """簡易把 markdown 結構化格式轉純文字（去除 wikilinks 殼，保留內容）。"""
    text = re.sub(r"\[\[([^\]]+?)\]\]", r"\1", text)        # wikilinks
    text = re.sub(r"\*\*([^\*]+?)\*\*", r"\1", text)        # bold
    text = re.sub(r"`([^`]+?)`", r"\1", text)               # inline code
    return text


def read_coverage_sections(sym: str) -> dict:
    """讀 My-TW-Coverage 個股報告並切成章節。

    回傳格式：
        {
          "found": bool,
          "path": str | None,
          "industry_folder": str | None,
          "sections": {"業務簡介": "...", ...},
        }
    """
    path = find_coverage_file(sym)
    if path is None:
        return {"found": False, "path": None, "industry_folder": None, "sections": {}}

    text = path.read_text(encoding="utf-8")
    sections: dict[str, str] = {}
    current = "_PREAMBLE"
    buffer: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            sections[current] = "\n".join(buffer)
            current = m.group(1).strip()
            buffer = []
        else:
            buffer.append(line)
    sections[current] = "\n".join(buffer)

    return {
        "found": True,
        "path": str(path.relative_to(PROJECT_ROOT)),
        "industry_folder": path.parent.name,
        "sections": sections,
    }


def build_primary_coverage_text(sym: str, max_chars: int = 3200) -> tuple[str, dict]:
    """把 Coverage 關鍵章節合併成驗證用主證據文字。

    只取業務、供應鏈、客戶/供應商、營收來源等章節，避免財務表格噪音。
    """
    data = read_coverage_sections(sym)
    if not data["found"]:
        return "", data

    chunks: list[str] = []
    sections = data.get("sections", {})
    for sec in PRIMARY_COVERAGE_SECTIONS:
        body = sections.get(sec, "")
        if body:
            chunks.append(f"## {sec}\n{_strip_markdown(body)}")
    if not chunks:
        chunks.append(_strip_markdown("\n".join(sections.values())))
    return "\n\n".join(chunks)[:max_chars], data


def extract_coverage(sym: str, keywords: list[str]) -> dict:
    """讀個股 Coverage，對 keywords 抓引用片段。

    Returns:
        {
          "found": bool,
          "path": str | None,
          "section_hits": [{"section": "業務簡介", "keyword": "ABF", "quote": "..."}],
          "industry_folder": str | None,  # Pilot_Reports 所屬產業（Coverage 自身分類）
        }
    """
    path = find_coverage_file(sym)
    if path is None:
        return {"found": False, "path": None, "section_hits": [], "industry_folder": None}

    text = path.read_text(encoding="utf-8")
    industry_folder = path.parent.name  # 例: "Electronic Components"

    # 切 sections（## ）
    sections: dict[str, str] = {}
    current = "_PREAMBLE"
    buffer: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            sections[current] = "\n".join(buffer)
            current = m.group(1)
            buffer = []
        else:
            buffer.append(line)
    sections[current] = "\n".join(buffer)

    section_hits: list[dict] = []
    for sec_name, sec_text in sections.items():
        clean = _strip_markdown(sec_text)
        for kw in keywords:
            for m in re.finditer(re.escape(kw), clean):
                start = max(0, m.start() - QUOTE_WINDOW)
                end = min(len(clean), m.end() + QUOTE_WINDOW)
                quote = clean[start:end].strip().replace("\n", " ")
                # 去掉前後不完整 token 殘留
                quote = re.sub(r"^\S*?\s", "", quote, count=1) if start > 0 else quote
                quote = re.sub(r"\s\S*?$", "", quote, count=1) if end < len(clean) else quote
                section_hits.append({
                    "section": sec_name,
                    "keyword": kw,
                    "quote": quote[:200],   # 最多 200 字截斷
                })
                if len(section_hits) >= 6:  # 每 sym 最多 6 條，避免冗長
                    break
            if len(section_hits) >= 6:
                break

    return {
        "found": True,
        "path": str(path.relative_to(PROJECT_ROOT)),
        "section_hits": section_hits,
        "industry_folder": industry_folder,
    }


def coverage_mentions_exclusion(sym: str, exclusion_keywords: list[str]) -> list[str]:
    """反證查詢：個股 Coverage 中是否提及任一 exclusion_keyword？回命中清單。"""
    path = find_coverage_file(sym)
    if path is None:
        return []
    text = _strip_markdown(path.read_text(encoding="utf-8"))
    return [kw for kw in exclusion_keywords if kw in text]


# ─────────────────────────────────────────────────────────────────────────────
# finlab snapshot
# ─────────────────────────────────────────────────────────────────────────────
def load_finlab_snapshot(force_refresh: bool = False):
    """
    Snapshot finlab.data.get('company_basic_info') 到 parquet。

    若 parquet 存在且 force_refresh=False，直接讀檔（10s）；
    否則重新跑 finlab（~90s，需要登入）。

    Returns:
        DataFrame with columns: symbol, 公司簡稱, 產業類別, 市場別
    """
    import pandas as pd

    if SNAPSHOT_PATH.exists() and not force_refresh:
        return pd.read_parquet(SNAPSHOT_PATH)

    from finlab import data
    info = data.get("company_basic_info")
    cols = ["symbol", "公司簡稱", "產業類別", "市場別"]
    snapshot = info[cols].copy()
    snapshot.attrs["snapshotted_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    snapshot.to_parquet(SNAPSHOT_PATH, index=False)
    return snapshot


def lookup_finlab(sym: str, snapshot=None) -> dict:
    """
    Returns:
        {"found": bool, "name": str, "twse_industry": str, "market": str}
    """
    if snapshot is None:
        snapshot = load_finlab_snapshot()
    row = snapshot[snapshot["symbol"] == sym]
    if row.empty:
        return {"found": False, "name": "", "twse_industry": "", "market": ""}
    r = row.iloc[0]
    return {
        "found": True,
        "name": r["公司簡稱"],
        "twse_industry": r["產業類別"],
        "market": r["市場別"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 板塊推論：finlab.產業類別 → INDUSTRY_SEGMENTS enum
# ─────────────────────────────────────────────────────────────────────────────
TWSE_TO_SEGMENT = {
    # AI / 半導體
    "半導體業": "AI_SEMI",
    # 電子零組件
    "電子零組件業": "ELEC_COMP",
    # 網通
    "通信網路業": "NETCOM",
    # 電腦及週邊
    "電腦及週邊設備業": "COMP_HW",
    # 電源 / 綠能
    "電器電纜": "POWER_GREEN",
    "其他電子業": "ELEC_COMP",  # 多數工控/電源/雜項都歸電子零組件
    "電機機械": "ELEC_COMP",    # 重電 / 馬達 / 機電
    "電子通路業": "ELEC_COMP",  # DISTRIB 通路
    "居家生活": "CONSUMER",
    "數位雲端": "SOFTWARE",
    "綠能環保": "POWER_GREEN",
    "運動休閒": "CONSUMER",
    "貿易百貨": "CONSUMER",
    "建材營造": "MATERIALS",
    # "其他" / "其他業" 故意 mapping 為 None → 強制走 Coverage industry_folder 二次推論
    # （金融租賃/保全/殯葬/教育 等都會被 finlab 標「其他」，不能用 MATERIALS 兜底）
    "其他": None,
    # 車用
    "汽車工業": "EV_AUTO",
    # 軍工 / 國防
    "鋼鐵工業": "MATERIALS",    # 但軍工部分歸 DEFENSE
    # 生技
    "生技醫療業": "MED_BIO",
    # 金融
    "金融保險業": "FIN",
    "證券業": "FIN",
    # 消費
    "食品工業": "CONSUMER",
    "貿易百貨業": "CONSUMER",
    "觀光餐旅": "CONSUMER",
    "其他業": None,             # 同上，走 Coverage 二次推論
    # 原物料
    "塑膠工業": "MATERIALS",
    "化學工業": "MATERIALS",
    "水泥工業": "MATERIALS",
    "造紙工業": "MATERIALS",
    "橡膠工業": "MATERIALS",
    "玻璃陶瓷": "MATERIALS",
    # 物流
    "航運業": "LOGISTICS",
    # 軟體服務
    "資訊服務業": "SOFTWARE",
    "文化創意業": "SOFTWARE",
    # 光電
    "光電業": "ELEC_COMP",      # 多數光電廠歸電子零組件
    # 建材營造
    "建材營造": None,
    # 油電燃氣
    "油電燃氣業": "POWER_GREEN",
    # 紡織
    "紡織纖維": "MATERIALS",
    # 機電
    "電機機械": None,           # 細分困難
    # 其他電子
    "電子通路業": None,         # 多為 DISTRIB
}


def infer_segment_from_twse(twse_industry: str) -> Optional[str]:
    """從 finlab 產業類別粗估 industry_segment。回 None 表示需 Coverage / LLM 細分。"""
    return TWSE_TO_SEGMENT.get(twse_industry)


# Coverage industry_folder（My-TW-Coverage 自身英文分類）→ INDUSTRY_SEGMENTS
COVERAGE_FOLDER_TO_SEGMENT = {
    "Semiconductors": "AI_SEMI",
    "Semiconductor Equipment": "AI_SEMI",
    "Communication Equipment": "NETCOM",
    "Computer Hardware": "COMP_HW",
    "Electronic Components": "ELEC_COMP",
    "Electronics & Computer Distribution": "ELEC_COMP",
    "Information Technology Services": "SOFTWARE",
    "Software—Application": "SOFTWARE",
    "Software—Infrastructure": "SOFTWARE",
    "Internet Content & Information": "SOFTWARE",
    "Banks—Regional": "FIN",
    "Banks—Diversified": "FIN",
    "Capital Markets": "FIN",
    "Insurance—Diversified": "FIN",
    "Insurance—Life": "FIN",
    "Insurance—Property & Casualty": "FIN",
    "Credit Services": "FIN",
    "Asset Management": "FIN",
    "Financial Conglomerates": "FIN",
    "Conglomerates": "FIN",
    "Auto Manufacturers": "EV_AUTO",
    "Auto Parts": "EV_AUTO",
    "Auto & Truck Dealerships": "EV_AUTO",
    "Aerospace & Defense": "DEFENSE",
    "Biotechnology": "MED_BIO",
    "Drug Manufacturers—General": "MED_BIO",
    "Drug Manufacturers—Specialty & Generic": "MED_BIO",
    "Medical Devices": "MED_BIO",
    "Medical Distribution": "MED_BIO",
    "Diagnostics & Research": "MED_BIO",
    "Healthcare Plans": "MED_BIO",
    "Medical Care Facilities": "MED_BIO",
    "Pharmaceutical Retailers": "MED_BIO",
    "Marine Shipping": "LOGISTICS",
    "Airlines": "LOGISTICS",
    "Trucking": "LOGISTICS",
    "Integrated Freight & Logistics": "LOGISTICS",
    "Railroads": "LOGISTICS",
    "Steel": "MATERIALS",
    "Aluminum": "MATERIALS",
    "Copper": "MATERIALS",
    "Other Industrial Metals & Mining": "MATERIALS",
    "Specialty Chemicals": "MATERIALS",
    "Chemicals": "MATERIALS",
    "Paper & Paper Products": "MATERIALS",
    "Building Products & Equipment": "MATERIALS",
    "Building Materials": "MATERIALS",
    "Lumber & Wood Production": "MATERIALS",
    "Packaging & Containers": "MATERIALS",
    "Rubber & Plastics": "MATERIALS",
    "Textile Manufacturing": "MATERIALS",
    "Apparel Manufacturing": "CONSUMER",
    "Footwear & Accessories": "CONSUMER",
    "Apparel Retail": "CONSUMER",
    "Consumer Electronics": "COMP_HW",
    "Electronic Gaming & Multimedia": "SOFTWARE",
    "Personal Services": "CONSUMER",
    "Specialty Retail": "CONSUMER",
    "Department Stores": "CONSUMER",
    "Grocery Stores": "CONSUMER",
    "Restaurants": "CONSUMER",
    "Lodging": "CONSUMER",
    "Travel Services": "CONSUMER",
    "Leisure": "CONSUMER",
    "Furnishings, Fixtures & Appliances": "CONSUMER",
    "Household & Personal Products": "CONSUMER",
    "Education & Training Services": "CONSUMER",
    "Real Estate Services": "MATERIALS",
    "Real Estate—Diversified": "MATERIALS",
    "Real Estate—Development": "MATERIALS",
    "REIT—Diversified": "FIN",
    "Engineering & Construction": "MATERIALS",
    "Specialty Industrial Machinery": "ELEC_COMP",
    "Farm & Heavy Construction Machinery": "MATERIALS",
    "Industrial Distribution": "ELEC_COMP",
    "Tools & Accessories": "MATERIALS",
    "Metal Fabrication": "MATERIALS",
    "Pollution & Treatment Controls": "POWER_GREEN",
    "Waste Management": "POWER_GREEN",
    "Utilities—Regulated Electric": "POWER_GREEN",
    "Utilities—Independent Power Producers": "POWER_GREEN",
    "Utilities—Renewable": "POWER_GREEN",
    "Utilities—Diversified": "POWER_GREEN",
    "Solar": "POWER_GREEN",
    "Oil & Gas Integrated": "POWER_GREEN",
    "Oil & Gas E&P": "POWER_GREEN",
    "Oil & Gas Refining & Marketing": "POWER_GREEN",
    "Oil & Gas Equipment & Services": "POWER_GREEN",
    "Coking Coal": "MATERIALS",
    "Security & Protection Services": "SOFTWARE",
    "Staffing & Employment Services": "SOFTWARE",
    "Specialty Business Services": "SOFTWARE",
    "Consulting Services": "SOFTWARE",
    "Rental & Leasing Services": "FIN",
    "Beverages—Wineries & Distilleries": "CONSUMER",
    "Beverages—Non-Alcoholic": "CONSUMER",
    "Confectioners": "CONSUMER",
    "Packaged Foods": "CONSUMER",
    "Farm Products": "CONSUMER",
    "Tobacco": "CONSUMER",
    "Recreational Vehicles": "CONSUMER",
}


def infer_segment_with_coverage(
    twse_industry: str,
    coverage_folder: str = "",
) -> Optional[str]:
    """雙來源推論 segment：finlab 主，Coverage industry_folder 為次（finlab 落空時兜底）。"""
    primary = TWSE_TO_SEGMENT.get(twse_industry)
    if primary:
        return primary
    # 落空 → 用 Coverage folder
    if coverage_folder:
        return COVERAGE_FOLDER_TO_SEGMENT.get(coverage_folder)
    return None
