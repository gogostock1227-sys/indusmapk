"""
族群寶：題材元資料
每個族群的介紹、CAGR、市場規模、關鍵指標、icon 色彩
沒有在 META 中的族群，build_site 會自動補簡版資料。
最後更新: 2026-04-24
"""

try:
    from moneydj_industry_meta import MONEYDJ_INDUSTRY_META
except ImportError:
    MONEYDJ_INDUSTRY_META = {}

import json as _json
import pathlib as _pathlib
INDUSTRY_META = _json.load(
    (_pathlib.Path(__file__).parent / '../data/industry_meta.json').open(encoding="utf-8")
)


# 概念股／供應鏈題材：屬於跨產業的「主題包」，不是單一產業分類。
# 用於股期儀表板等場景，需要過濾掉避免污染「族群分布」之類圖表。
CONCEPT_STOCK_TOPICS = frozenset({
    "CPU 概念股",
    "輝達概念股",
    "Google TPU",
    "蘋果概念股",
    "特斯拉概念股",
})


# Category 顏色（側邊導覽用）
CATEGORY_COLORS = {
    "AI / 半導體":    "#ff7847",
    "封裝 / 測試":    "#f97316",
    "基板 / PCB":     "#a855f7",
    "散熱 / 電源":    "#0ea5e9",
    "光通訊 / 網通":  "#10b981",
    "連接器 / 被動":  "#6366f1",
    "車用 / 機器人":  "#84cc16",
    "國防 / 資安":    "#dc2626",
    "消費電子":       "#71717a",
    "面板 / 光電":    "#7c3aed",
    "航運 / 傳產":    "#2563eb",
    "金融":           "#0369a1",
    "傳產":           "#525252",
    "生技 / 醫療":    "#16a34a",
    "事件驅動":       "#a3a3a3",
    "第三代半導體":   "#f59e0b",
    "利基零組件":     "#14b8a6",
    "傳產利基":       "#78350f",
    "政策驅動":       "#15803d",
    "電子通路 / 服務": "#4338ca",
    "雲端 / 軟體":    "#7c3aed",
    "運動 / 休閒":    "#be185d",
    "綠能 / 環保":    "#059669",
    "化工 / 特化":    "#9a3412",
    "建材 / 居家":    "#a16207",
    "傳媒 / 文創":    "#a21caf",
}


def get_meta(group_name: str) -> dict:
    """取得題材 meta，沒有則回傳預設值"""
    if group_name in INDUSTRY_META:
        return INDUSTRY_META[group_name]
    if group_name in MONEYDJ_INDUSTRY_META:
        return MONEYDJ_INDUSTRY_META[group_name]
    return {
        "en": group_name,
        "category": "其他",
        "color": "#64748b",
        "desc": f"「{group_name}」相關概念股，資料彙整中。",
        "cagr": "—",
        "market_size": "—",
        "indicators": [
            {"label": "題材類型", "value": "概念股"},
            {"label": "資料狀態", "value": "彙整中"},
            {"label": "成分股數", "value": ""},
            {"label": "更新頻率", "value": "每日"},
        ],
    }
