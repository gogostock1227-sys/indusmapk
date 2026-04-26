"""
從 site/industry_meta.py 的 desc 自動抓公司名 → finlab 反查 ticker → 補 GROUND_TRUTH。

底層邏輯：
  industry_meta.py 每群 desc 已標明龍頭（茂達/致新/類比科/...）
  finlab 提供 ticker → 公司簡稱
  反向：公司簡稱 → ticker
  結果：每群 desc 提到的所有公司都加進 GROUND_TRUTH，確保「ai 分析提到 = 成分股一定有」

入口：
  python -m validator.sync_ground_truth          # dry run，印不一致清單
  python -m validator.sync_ground_truth --emit   # 印出可貼進 pure_play_pipeline.py 的 dict
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TAXONOMY_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = TAXONOMY_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(TAXONOMY_DIR))


def load_industry_meta() -> dict:
    """讀 industry_meta.py 的 INDUSTRY_META dict（直接 exec）。"""
    import importlib.util
    path = PROJECT_ROOT / "site" / "industry_meta.py"
    spec = importlib.util.spec_from_file_location("industry_meta", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.INDUSTRY_META


def load_name_to_ticker() -> dict[str, str]:
    """從 finlab snapshot 建 name → ticker map。"""
    snapshot_path = TAXONOMY_DIR / "validator" / "cache" / "finlab_snapshot.parquet"
    if not snapshot_path.exists():
        return {}
    import pandas as pd
    df = pd.read_parquet(snapshot_path)
    # 反查：公司簡稱 → symbol
    return df.set_index("公司簡稱")["symbol"].to_dict()


# 預設別名表（finlab 簡稱可能與描述用詞不同）
NAME_ALIASES = {
    "茂達": "茂達", "致新": "致新", "類比科": "類比科", "大中": "大中",
    "矽力": "矽力*-KY", "矽力-KY": "矽力*-KY",
    "沛亨": "沛亨", "杰力": "杰力", "凱鈺": "凱鈺", "晶焱": "晶焱",
    "宏碁智醫": "宏碁智醫", "雲象": "雲象", "長佳智能": "長佳智能",
    "訊聯": "訊聯", "基米": "基米", "慧智": "慧智生技",
    "大樹": "大樹", "杏一": "杏一", "鳳凰": "鳳凰",
    # 半導體
    "台積電": "台積電", "聯發科": "聯發科", "聯電": "聯電", "日月光": "日月光投控", "日月光投控": "日月光投控",
    "鴻海": "鴻海", "廣達": "廣達", "緯創": "緯創", "緯穎": "緯穎",
    "技嘉": "技嘉", "華碩": "華碩", "微星": "微星", "仁寶": "仁寶", "和碩": "和碩",
    "英業達": "英業達", "光寶科": "光寶科", "台達電": "台達電",
    # 載板
    "欣興": "欣興", "南電": "南電", "景碩": "景碩",
    # PCB
    "健鼎": "健鼎", "金像電": "金像電", "台光電": "台光電", "聯茂": "聯茂", "台燿": "台燿",
    # 連接器
    "嘉澤": "嘉澤", "貿聯-KY": "貿聯-KY", "貿聯": "貿聯-KY", "信邦": "信邦", "健和興": "健和興",
    # 散熱
    "奇鋐": "奇鋐", "雙鴻": "雙鴻", "健策": "健策", "建準": "建準",
    # 被動
    "國巨": "國巨*", "華新科": "華新科", "禾伸堂": "禾伸堂", "奇力新": "奇力新",
    # 記憶體 / HBM
    "南亞科": "南亞科", "華邦電": "華邦電", "旺宏": "旺宏", "群聯": "群聯",
    "力成": "力成", "力積電": "力積電", "台勝科": "台勝科", "擎亞": "擎亞", "宜特": "宜特",
    # 矽晶圓
    "環球晶": "環球晶", "中美晶": "中美晶", "合晶": "合晶", "嘉晶": "嘉晶",
    # 光學光電
    "大立光": "大立光", "玉晶光": "玉晶光", "亞光": "亞光",
    # 矽光子
    "聯亞": "聯亞", "穩懋": "穩懋", "上詮": "上詮", "聯鈞": "聯鈞", "波若威": "波若威",
    # 設備
    "弘塑": "弘塑", "辛耘": "辛耘", "家登": "家登精密", "家登精密": "家登精密",
    # 車用 / 電動車
    "東陽": "東陽", "和大": "和大-KY", "和大-KY": "和大-KY",
    # 通路
    "大聯大": "大聯大", "文曄": "文曄",
    # 軍工
    "雷虎": "雷虎",
    # 軸承
    "上銀": "上銀",
    # 太陽能
    "茂迪": "茂迪", "聯合再生": "聯合再生",
    # 鋼鐵
    "中鋼": "中鋼", "豐興": "豐興",
    # 紡織
    "儒鴻": "儒鴻", "聚陽": "聚陽",
    # 食品
    "統一": "統一", "大成": "大成",
    # 金融
    "國泰金": "國泰金", "富邦金": "富邦金", "中信金": "中信金", "兆豐金": "兆豐金",
}


def _load_auto_aliases() -> dict[str, str]:
    """讀 expand_name_aliases.py 產的 2546 個自動 alias。"""
    p = TAXONOMY_DIR / "validator" / "cache" / "name_aliases_auto.json"
    if p.exists():
        import json
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


# 歧義詞黑名單 — 這些詞既是公司簡稱也是常用詞，不應自動抓
# 規則：除非 desc 中出現「ticker 號」或全名，否則不視為公司
AMBIGUOUS_NAME_BLACKLIST = {
    "國產",   # 國產實業 (2504) vs 形容詞「本土製造」
    "全新",   # 全新光電 (2455) vs 形容詞「全新」
    "聯發",   # 聯發 (1459) vs 簡稱聯發科 (2454)
    "長榮",   # 長榮 (2603) vs 長榮航 (2618) / 長榮鋼 / 長榮航宇
    "中華",   # 中華電 (2412) vs 中華 (2204) vs 中華食 (1217)
    "南亞",   # 南亞 (1303 塑膠) vs 南亞科 (2408 DRAM)
    "光寶",   # 光寶科 (2301)
    "和大",   # 和大-KY (1536)
    "新光",   # 新光金 / 新光鋼 多個
    "台塑",   # 台塑 (1301) vs 台塑化 (6505)
    "台泥",   # 台泥 (1101)
    "華新",   # 華新 (1605) vs 華新科 (2492)
    "永豐",   # 永豐金 / 永豐餘
    "鴻海",   # too generic context
    "日月",   # 日月光投控 (3711)
    "美達",   # 美達科 (6735)
    "穩懋",   # 穩懋 (3105) — 通常 OK
    "創見",   # 創見 (2451) — OK
    "華邦",   # 華邦電 (2344) vs 華邦食品
    "智邦",   # 智邦 (2345)
    "仁寶",   # 仁寶 (2324)
}


def extract_companies_from_desc(desc: str, name_to_ticker: dict[str, str]) -> list[str]:
    """從 desc 抓出公司名 → ticker。

    用兩層 alias：
      Layer 1: 手動 NAME_ALIASES（高信心，含罕見別名）
      Layer 2: expand_name_aliases.py 自動產的 2546 個 alias（finlab 真名 + 變體）
    """
    auto_aliases = _load_auto_aliases()
    combined = {**auto_aliases, **NAME_ALIASES}  # 手動覆蓋自動

    tickers = []
    # 按 key 長度遞減排序（避免「致新」被「致」吃掉）
    sorted_names = sorted(combined.keys(), key=len, reverse=True)
    matched_positions = []
    for name in sorted_names:
        if len(name) < 2:
            continue
        # 歧義詞：除非 desc 同時出現 ticker 號碼（如 "(2504)"），否則跳過
        if name in AMBIGUOUS_NAME_BLACKLIST:
            full_name = combined[name]
            ticker = name_to_ticker.get(full_name, "")
            # 必須 desc 明確含 ticker 號碼才接受
            if ticker and ticker not in desc and f"({ticker})" not in desc:
                continue
        idx = desc.find(name)
        if idx < 0:
            continue
        # 避免重疊
        overlap = any(start <= idx < end for start, end in matched_positions)
        if overlap:
            continue
        full_name = combined[name]
        ticker = name_to_ticker.get(full_name)
        if ticker:
            tickers.append(ticker)
            matched_positions.append((idx, idx + len(name)))
    return tickers


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit", action="store_true", help="輸出可貼進 pure_play_pipeline.py 的 dict")
    args = ap.parse_args()

    meta = load_industry_meta()
    n2t = load_name_to_ticker()
    print(f"industry_meta: {len(meta)} 群 / finlab name_map: {len(n2t)} ticker")

    discovered = {}
    for group, info in meta.items():
        if not isinstance(info, dict):
            continue
        desc = info.get("desc", "")
        # 從 indicators 也抓
        indicators = info.get("indicators", [])
        all_text = desc
        for ind in indicators:
            if isinstance(ind, dict) and ind.get("label") in ("台廠", "代表廠商", "龍頭", "本土廠"):
                all_text += " " + ind.get("value", "")
        tickers = extract_companies_from_desc(all_text, n2t)
        if tickers:
            discovered[group] = tickers

    print(f"從 desc 抓出 {sum(len(v) for v in discovered.values())} ticker，跨 {len(discovered)} 群")

    if args.emit:
        print("\n# === GROUND_TRUTH 自動補強（從 industry_meta desc 抓） ===")
        print("AUTO_GROUND_TRUTH_FROM_DESC = {")
        for g in sorted(discovered.keys()):
            print(f'    "{g}": {discovered[g]},')
        print("}")
    else:
        # Show top 20
        for g, ts in list(discovered.items())[:20]:
            print(f"  {g}: {ts}")


if __name__ == "__main__":
    main()
