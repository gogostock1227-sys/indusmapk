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
    "其他": "MATERIALS",        # finlab "其他" 多為傳產（化工/食品/雜貨）→ 給 MATERIALS 兜底
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
    "其他業": "MATERIALS",      # 多數為傳統製造/化工
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
