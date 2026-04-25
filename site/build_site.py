"""
族群寶 - 網站建置主腳本

用法：
  python site/build_site.py                       # 產生完整站點到 site/dist/
  python site/build_site.py --skip-finlab         # 用快取資料（開發用）
  python site/build_site.py --open                # 建完自動開首頁

輸出：
  site/dist/
    index.html              # 每日焦點
    topics.html             # 題材總覽
    heatmap.html            # 全市場熱力圖
    topic/<slug>.html       # 每個題材頁
    company/<id>.html       # 每檔個股反查
    data/search.json        # 搜尋資料
    data/heatmap_<tf>.json  # 熱力圖資料（daily/weekly/monthly）
    static/                 # CSS/JS
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import shutil
import hashlib
import webbrowser
import warnings
from collections import defaultdict
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
from jinja2 import Environment, FileSystemLoader, select_autoescape

# ─────── 路徑設置 ───────
SITE_DIR = Path(__file__).resolve().parent
ROOT_DIR = SITE_DIR.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR.parent))

DIST_DIR = SITE_DIR / "dist"
TEMPLATE_DIR = SITE_DIR / "templates"
STATIC_SRC = SITE_DIR / "static"
CACHE_FILE = SITE_DIR / ".cache.parquet"
CACHE_META = SITE_DIR / ".cache_meta.json"

from concept_groups import CONCEPT_GROUPS
from industry_meta import INDUSTRY_META, CATEGORY_COLORS, get_meta
try:
    from stock_highlights import STOCK_HIGHLIGHTS
except ImportError:
    STOCK_HIGHLIGHTS = {}

RICH_PKL = SITE_DIR / ".company_rich.pkl"
EXTRAS_JSON = SITE_DIR / ".cache_extras.json"
TRENDING_JSON = SITE_DIR / ".cache_trending.json"
NAME_OVERRIDES_JSON = SITE_DIR / "stock_name_overrides.json"
COVERAGE_DIR = ROOT_DIR / "My-TW-Coverage" / "Pilot_Reports"

# 個股深度資料六大分頁：(UI 顯示名稱, MD 標頭關鍵字)
COVERAGE_TABS = [
    ("公司簡介",           "業務簡介"),
    ("供應鏈定位",         "供應鏈位置"),
    ("營收來源",           "營收來源"),
    ("近期營運狀況",       "近期營運狀況"),
    ("未來營運展望",       "未來營運展望"),
    ("產業趨勢與成長動能", "產業趨勢與成長動能"),
]

# 首頁熱門題材 chip 的最終 fallback（當 trending cache 完全不存在時使用）
DEFAULT_HOT_TOPICS = [
    "2奈米先進製程",
    "輝達概念股",
    "Google TPU",
    "量子電腦",
    "Chiplet 小晶片",
    "CoWoS先進封裝",
]


def refresh_trending_topics() -> None:
    """跑 fetch_trending_topics.py 抓當日熱門題材，寫入 .cache_trending.json。

    採 subprocess 隔離，避免爬蟲失敗影響本行程。
    任何異常都不中斷 build，load_hot_topics() 會降級到 cache 或 DEFAULT_HOT_TOPICS。
    """
    import subprocess
    script = SITE_DIR / "fetch_trending_topics.py"
    if not script.exists():
        print(f"[trending] 跳過：找不到 {script.name}")
        return
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--top", "10"],
            timeout=60,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if proc.returncode == 0:
            print(f"[trending] 已更新 {TRENDING_JSON.name}")
            # 印 fetch 腳本最後幾行（top N 列表）
            tail = [l for l in proc.stdout.splitlines() if l.strip()][-12:]
            for l in tail:
                print(f"  {l}")
        else:
            print(f"[trending] 抓取 exit {proc.returncode}（保留前次 cache，若有）")
            if proc.stderr:
                print(proc.stderr[-500:])
    except subprocess.TimeoutExpired:
        print("[trending] 抓取逾時 60s，沿用前次 cache")
    except Exception as e:
        print(f"[trending] 抓取例外：{e}（沿用前次 cache）")


def load_hot_topics(top_n: int = 6) -> list[dict]:
    """讀 .cache_trending.json，回傳 [{'name': ..., 'slug': ..., 'score': ...}, ...]。

    降級順序：
      1. cache 存在且有題材 → 取 top_n，過濾掉不在 CONCEPT_GROUPS 的
      2. cache 不存在 / 解析失敗 → DEFAULT_HOT_TOPICS（固定題材）
    """
    fallback = [
        {"name": n, "slug": slugify(n), "score": None}
        for n in DEFAULT_HOT_TOPICS if n in CONCEPT_GROUPS
    ][:top_n]

    if not TRENDING_JSON.exists():
        print(f"[hot_topics] 無 cache，使用預設題材 {[t['name'] for t in fallback]}")
        return fallback
    try:
        d = json.loads(TRENDING_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[hot_topics] 讀 cache 失敗：{e}，使用預設")
        return fallback

    topics = d.get("topics") or []
    picked: list[dict] = []
    for t in topics:
        name = t.get("name") if isinstance(t, dict) else None
        if not name or name not in CONCEPT_GROUPS:
            continue
        picked.append({
            "name": name,
            "slug": slugify(name),
            "score": t.get("score"),
        })
        if len(picked) >= top_n:
            break

    if not picked:
        print("[hot_topics] cache 無可用題材，使用預設")
        return fallback

    gen = d.get("generated_at", "?")
    print(f"[hot_topics] 從 cache 取 {len(picked)} 題材（@ {gen}）: {[t['name'] for t in picked]}")
    return picked


def load_extras() -> dict:
    """載入 fetch_extras.py 產的處置股 + 集保分級（15 級歷史）。"""
    empty = {"disposal": {}, "holders_history": {}, "holder_levels": []}
    if not EXTRAS_JSON.exists():
        print(f"[警告] 找不到 {EXTRAS_JSON.name}，個股頁將無處置警示/大戶資訊。")
        print(f"       先跑：python site/fetch_extras.py")
        return empty
    try:
        d = json.loads(EXTRAS_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[警告] 讀 {EXTRAS_JSON.name} 失敗：{e}")
        return empty
    disposal = d.get("disposal") or {}
    hist     = d.get("holders_history") or {}
    levels   = d.get("holder_levels") or []
    # 清洗 disposal 文字欄位殘留的 markdown link（如 "(./attention.html)"）
    import re as _re
    _URL_TAIL = _re.compile(r'\s*\((?:\./|https?://)[^\s)]+\)')
    _MD_LINK  = _re.compile(r'\[([^\]]+)\]\([^\)]+\)')
    for _sym, _info in disposal.items():
        for _k in ("reason", "action", "detail", "name"):
            _v = _info.get(_k)
            if isinstance(_v, str) and ('](' in _v or '(./' in _v or '(http' in _v):
                _v = _MD_LINK.sub(r'\1', _v)
                _v = _URL_TAIL.sub('', _v)
                _info[_k] = _re.sub(r'\s+', ' ', _v).strip()
    n_weeks = len({date for by_date in hist.values() for date in by_date.keys()})
    print(f"[extras] 處置股 {len(disposal)} 檔 / 集保分級 {len(hist)} 檔 / 歷史 {n_weeks} 週 / 抓取時間 {d.get('fetched_at','?')}")
    return {"disposal": disposal, "holders_history": hist, "holder_levels": levels}


# 三類歸屬：level index（0-based）
_RETAIL_IDX = list(range(0, 8))    # level 1-8 (≤50 張)
_MID_IDX    = list(range(8, 11))   # level 9-11 (50~400 張)
_BIG_IDX    = list(range(11, 15))  # level 12-15 (>400 張)


def build_holder_view(hist_by_date: dict, levels: list) -> dict | None:
    """把 {date: {h, s, p}} 轉成前端易用的結構：
      dates, levels,
      holders[N週][15級], pcts[N週][15級],
      retail_holders/mid_holders/big_holders: 每週人數,
      retail_pct/mid_pct/big_pct: 每週佔比,
      delta_retail/delta_mid/delta_big: 每週相對前週 delta 人數。"""
    if not hist_by_date:
        return None
    dates = sorted(hist_by_date.keys())
    holders_mat = [hist_by_date[d]["h"] for d in dates]
    shares_mat  = [hist_by_date[d]["s"] for d in dates]
    pct_mat     = [hist_by_date[d]["p"] for d in dates]

    def agg_h(idxs):
        return [sum(row[i] for i in idxs) for row in holders_mat]

    def agg_p(idxs):
        return [round(sum(row[i] for i in idxs), 2) for row in pct_mat]

    retail_h = agg_h(_RETAIL_IDX)
    mid_h    = agg_h(_MID_IDX)
    big_h    = agg_h(_BIG_IDX)

    def deltas(arr):
        return [None] + [arr[i] - arr[i-1] for i in range(1, len(arr))]

    return {
        "dates":   dates,
        "levels":  levels[:15] if levels else [str(i+1) for i in range(15)],
        "holders": holders_mat,
        "shares":  shares_mat,
        "pcts":    pct_mat,
        "retail_holders": retail_h,
        "mid_holders":    mid_h,
        "big_holders":    big_h,
        "retail_pct":     agg_p(_RETAIL_IDX),
        "mid_pct":        agg_p(_MID_IDX),
        "big_pct":        agg_p(_BIG_IDX),
        "delta_retail":   deltas(retail_h),
        "delta_mid":      deltas(mid_h),
        "delta_big":      deltas(big_h),
    }


def load_company_rich() -> dict:
    """載入 fetch_company_rich.py 輸出的 pkl。若不存在回空。"""
    if not RICH_PKL.exists():
        print(f"[警告] 找不到 {RICH_PKL.name}，個股頁將少公司基本資料。執行 site/fetch_company_rich.py 生成。")
        return {"basic": {}, "business": {}, "revenue": {}, "financials": {}, "dividends": {}, "director": {}}
    import pickle
    with open(RICH_PKL, "rb") as f:
        rich = pickle.load(f)
    print(f"[rich] 載入公司資料：basic {len(rich.get('basic', {}))} / business {len(rich.get('business', {}))} / revenue {len(rich.get('revenue', {}))} / financials {len(rich.get('financials', {}))} / dividends {len(rich.get('dividends', {}))}")
    return rich


# ─────── My-TW-Coverage 深度資料解析 ───────

import re as _re
import html as _html

_META_LINE_RE = _re.compile(r"^\*\*(板塊|產業|市值|企業價值)[:：]\*\*")
_BULLET_PREFIXES = ("- ", "* ", "• ", "・")
_WIKILINK_RE = _re.compile(r"\[\[([^\[\]]+?)\]\]")
_BOLD_RE = _re.compile(r"\*\*([^*\n]+?)\*\*")


def _coverage_inline(text: str) -> str:
    """Convert inline MD (wikilinks + bold) to HTML. Input may already contain raw chars."""
    out = _html.escape(text)
    out = _WIKILINK_RE.sub(lambda m: f'<span class="wiki-ref">{m.group(1)}</span>', out)
    out = _BOLD_RE.sub(r"<strong>\1</strong>", out)
    return out


def _coverage_block_to_html(block: str) -> str:
    """Convert a block of MD text (bullets / paragraphs / sub-headers) to HTML."""
    lines = [l.rstrip() for l in block.splitlines()]
    html_parts: list[str] = []
    in_list = False
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            continue
        if _META_LINE_RE.match(stripped):
            # 業務簡介區塊開頭的 metadata 列跳過（市值等已在別處顯示）
            continue
        if stripped.startswith("### "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<h4 class="coverage-sub">{_coverage_inline(stripped[4:])}</h4>')
            continue
        is_bullet = False
        body = stripped
        for p in _BULLET_PREFIXES:
            if body.startswith(p):
                body = body[len(p):].lstrip()
                is_bullet = True
                break
        if is_bullet:
            if not in_list:
                html_parts.append("<ul class=\"coverage-list\">")
                in_list = True
            html_parts.append(f"<li>{_coverage_inline(body)}</li>")
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<p>{_coverage_inline(stripped)}</p>")
    if in_list:
        html_parts.append("</ul>")
    return "\n".join(html_parts)


def _parse_coverage_md(content: str) -> dict:
    """Split one MD file by '## ' headers → {header_prefix: html}."""
    sections: dict[str, str] = {}
    current_name: str | None = None
    current_lines: list[str] = []
    for line in content.splitlines():
        if line.startswith("## "):
            if current_name is not None:
                sections[current_name] = _coverage_block_to_html("\n".join(current_lines).strip())
            header = line[3:].strip()
            # 只取 "(" 之前的標題主詞，例如 "財務概況 (單位:...)" → "財務概況"
            m = _re.match(r"([^(（]+)", header)
            current_name = (m.group(1).strip() if m else header)
            current_lines = []
        else:
            if current_name is not None:
                current_lines.append(line)
    if current_name is not None:
        sections[current_name] = _coverage_block_to_html("\n".join(current_lines).strip())
    return sections


def load_coverage() -> dict:
    """掃描 My-TW-Coverage/Pilot_Reports/**/{sym}_*.md，回傳 {sym: {section_name: html}}。

    六大分頁對應 MD 標頭由 COVERAGE_TABS 定義；檔案若沒有該標頭，UI 會顯示「尚未提供」。
    """
    coverage: dict[str, dict] = {}
    if not COVERAGE_DIR.exists():
        print(f"[coverage] 跳過：找不到 {COVERAGE_DIR}")
        return coverage
    n_files = 0
    n_sections = 0
    for md_file in COVERAGE_DIR.rglob("*.md"):
        stem = md_file.stem  # e.g., "1717_長興"
        m = _re.match(r"([0-9A-Za-z]+)_", stem)
        if not m:
            continue
        sym = m.group(1)
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue
        secs = _parse_coverage_md(content)
        if secs:
            coverage[sym] = secs
            n_files += 1
            n_sections += len(secs)
    print(f"[coverage] 載入 {n_files} 檔深度研究資料（共 {n_sections} 個章節）from {COVERAGE_DIR.name}")
    return coverage


def build_coverage_tabs(coverage_sections: dict | None) -> list[dict]:
    """對應 COVERAGE_TABS 產生給 template 用的 tab list。

    回傳 [{label, key, html, has_content}, ...]；若完全沒資料則回空 list。
    """
    if not coverage_sections:
        return []
    tabs = []
    for label, src in COVERAGE_TABS:
        html_body = coverage_sections.get(src, "")
        tabs.append({
            "label": label,
            "key": src,
            "html": html_body,
            "has_content": bool(html_body and html_body.strip()),
        })
    if not any(t["has_content"] for t in tabs):
        return []
    return tabs


# ═══════════════════════════════════════════
#   資料層
# ═══════════════════════════════════════════

# DataFrame 快取鍵。新增資料時只需加到這個 list。
CACHE_KEYS = [
    "close", "open", "high", "low", "volume", "amount",
    "foreign", "trust", "dealer",
    "foreign_buy", "foreign_sell",
    "trust_buy", "trust_sell",
    "dealer_buy", "dealer_sell",
    "margin_long_bal", "margin_long_buy", "margin_long_sell",
    "margin_short_bal", "margin_short_buy", "margin_short_sell",
    "disposal",
]


def _safe_get(data_mod, key: str):
    """包裝 data.get()，找不到回 None 而不是炸掉。"""
    try:
        return data_mod.get(key)
    except Exception as e:
        print(f"    [略過] {key}  ({type(e).__name__})")
        return None


def _load_finlab_data():
    """從 FinLab 載入必要資料"""
    from finlab import data
    print("  [FinLab] 下載 price/成交股數/成交金額...")
    d = {}
    d["close"]  = data.get("price:收盤價")
    d["open"]   = data.get("price:開盤價")
    d["high"]   = data.get("price:最高價")
    d["low"]    = data.get("price:最低價")
    d["volume"] = data.get("price:成交股數")
    d["amount"] = data.get("price:成交金額")

    print("  [FinLab] 下載三大法人買賣超...")
    d["foreign"] = _safe_get(data, "institutional_investors_trading_summary:外陸資買賣超股數(不含外資自營商)")
    d["trust"]   = _safe_get(data, "institutional_investors_trading_summary:投信買賣超股數")
    # 自營商 = 自行買賣 + 避險（合併後為完整自營商買賣超）
    dealer_self  = _safe_get(data, "institutional_investors_trading_summary:自營商買賣超股數(自行買賣)")
    dealer_hedge = _safe_get(data, "institutional_investors_trading_summary:自營商買賣超股數(避險)")
    if dealer_self is not None and dealer_hedge is not None:
        d["dealer"] = dealer_self.add(dealer_hedge, fill_value=0)
    else:
        d["dealer"] = dealer_self if dealer_self is not None else dealer_hedge

    print("  [FinLab] 下載三大法人買進/賣出明細...")
    d["foreign_buy"]  = _safe_get(data, "institutional_investors_trading_summary:外陸資買進股數(不含外資自營商)")
    d["foreign_sell"] = _safe_get(data, "institutional_investors_trading_summary:外陸資賣出股數(不含外資自營商)")
    d["trust_buy"]    = _safe_get(data, "institutional_investors_trading_summary:投信買進股數")
    d["trust_sell"]   = _safe_get(data, "institutional_investors_trading_summary:投信賣出股數")
    # 自營商 買進/賣出 同樣合併 自行買賣+避險
    db_self = _safe_get(data, "institutional_investors_trading_summary:自營商買進股數(自行買賣)")
    db_hedge= _safe_get(data, "institutional_investors_trading_summary:自營商買進股數(避險)")
    ds_self = _safe_get(data, "institutional_investors_trading_summary:自營商賣出股數(自行買賣)")
    ds_hedge= _safe_get(data, "institutional_investors_trading_summary:自營商賣出股數(避險)")
    d["dealer_buy"]  = (db_self.add(db_hedge, fill_value=0) if db_self is not None and db_hedge is not None else (db_self or db_hedge))
    d["dealer_sell"] = (ds_self.add(ds_hedge, fill_value=0) if ds_self is not None and ds_hedge is not None else (ds_self or ds_hedge))

    print("  [FinLab] 下載融資融券買賣...")
    d["margin_long_buy"]   = _safe_get(data, "margin_transactions:融資買進")
    d["margin_long_sell"]  = _safe_get(data, "margin_transactions:融資賣出")
    d["margin_short_buy"]  = _safe_get(data, "margin_transactions:融券買進")
    d["margin_short_sell"] = _safe_get(data, "margin_transactions:融券賣出")
    # 餘額直接抓不到時，以 rolling cumsum(買−賣) 近似（250 個交易日 ≈ 1 年信用週期）
    d["margin_long_bal"]  = _safe_get(data, "margin_transactions:融資餘額")
    d["margin_short_bal"] = _safe_get(data, "margin_transactions:融券餘額")
    if d["margin_long_bal"] is None and d["margin_long_buy"] is not None and d["margin_long_sell"] is not None:
        print("    [融資餘額] 用 買−賣 rolling 250 日 cumsum 近似")
        d["margin_long_bal"] = (d["margin_long_buy"] - d["margin_long_sell"]).rolling(250, min_periods=20).sum()
    if d["margin_short_bal"] is None and d["margin_short_buy"] is not None and d["margin_short_sell"] is not None:
        print("    [融券餘額] 用 買−賣 rolling 250 日 cumsum 近似")
        d["margin_short_bal"] = (d["margin_short_buy"] - d["margin_short_sell"]).rolling(250, min_periods=20).sum()

    # 處置股：FinLab 此帳號無該資料集，跳過（前端會自動不顯示警告 banner）
    d["disposal"] = None

    print("  [FinLab] 下載公司基本資料...")
    info = data.get("company_basic_info")
    d["name_map"]     = info.set_index("symbol")["公司簡稱"].to_dict()
    d["industry_map"] = info.set_index("symbol")["產業類別"].to_dict() if "產業類別" in info.columns else {}
    d["market_map"]   = info.set_index("symbol")["市場別"].to_dict() if "市場別" in info.columns else {}
    return d


def _apply_name_overrides(d: dict) -> None:
    """把 stock_name_overrides.json 的 ETF / 特別股 / KY 等名稱補進 name_map。
    只會覆蓋『FinLab name_map 查不到或值等於代號本身』的條目，不動現有對應。"""
    if not NAME_OVERRIDES_JSON.exists():
        return
    try:
        overrides = json.loads(NAME_OVERRIDES_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[警告] 讀 {NAME_OVERRIDES_JSON.name} 失敗：{e}")
        return
    nm = d.get("name_map") or {}
    added = 0
    for sym, name in overrides.items():
        if not (isinstance(name, str) and name.strip()):
            continue
        cur = nm.get(sym)
        if not (isinstance(cur, str) and cur.strip()) or cur == sym:
            nm[sym] = name
            added += 1
    d["name_map"] = nm
    print(f"[name_overrides] 補上 {added} 檔名稱（候選 {len(overrides)} 筆）")


def load_data(use_cache=False) -> dict:
    """載入資料（支援快取）"""
    if use_cache and CACHE_META.exists() and CACHE_FILE.exists():
        print(f"[快取] 從 {CACHE_FILE.name} 讀取")
        meta = json.loads(CACHE_META.read_text(encoding="utf-8"))
        combo = pd.read_parquet(CACHE_FILE)
        d = {}
        for key in CACHE_KEYS:
            cols = [c for c in combo.columns if c.startswith(f"{key}|")]
            if not cols:
                d[key] = None
                continue
            sub = combo[cols].copy()
            sub.columns = [c.split("|", 1)[1] for c in cols]
            d[key] = sub
        d["name_map"]     = meta.get("name_map", {})
        d["industry_map"] = meta.get("industry_map", {})
        d["market_map"]   = meta.get("market_map", {})
        _apply_name_overrides(d)
        return d

    d = _load_finlab_data()
    _apply_name_overrides(d)

    # 寫快取
    try:
        frames = []
        for key in CACHE_KEYS:
            df = d.get(key)
            if df is None or (hasattr(df, "empty") and df.empty):
                continue
            df2 = df.copy()
            df2.columns = [f"{key}|{c}" for c in df2.columns]
            frames.append(df2)
        combo = pd.concat(frames, axis=1)
        combo.to_parquet(CACHE_FILE)
        CACHE_META.write_text(
            json.dumps(
                {
                    "name_map": d["name_map"],
                    "industry_map": d["industry_map"],
                    "market_map": d["market_map"],
                    "ts": datetime.now().isoformat(),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"[快取] 已寫入 {CACHE_FILE.name}")
    except Exception as e:
        print(f"[警告] 快取寫入失敗：{e}")

    return d


# ═══════════════════════════════════════════
#   指標計算
# ═══════════════════════════════════════════

def compute_stock_metrics(d: dict) -> pd.DataFrame:
    """個股多時間維度指標。回傳 index=symbol, columns=[ret_1d, ret_5d, ret_20d, amount, ...]"""
    close = d["close"]
    amount = d["amount"]
    foreign = d["foreign"]
    trust = d["trust"]

    last = close.iloc[-1]
    prev = close.iloc[-2]
    ret_1d = (last - prev) / prev

    # 5日、20日報酬
    ret_5d  = (last - close.iloc[-6])  / close.iloc[-6]  if len(close) >= 6  else pd.Series(dtype=float)
    ret_20d = (last - close.iloc[-21]) / close.iloc[-21] if len(close) >= 21 else pd.Series(dtype=float)

    # 漲停旗標（收盤 >= 前日 * 1.095 粗估，簡化版）
    limit_up = (ret_1d >= 0.095).fillna(False)
    limit_down = (ret_1d <= -0.095).fillna(False)

    # 今日成交金額（百萬元）
    amt_last = amount.iloc[-1] / 1_000_000 if amount is not None else pd.Series(dtype=float)

    df = pd.DataFrame({
        "close":      last,
        "ret_1d":     ret_1d,
        "ret_5d":     ret_5d,
        "ret_20d":    ret_20d,
        "limit_up":   limit_up,
        "limit_down": limit_down,
        "amount_mn":  amt_last,
    })

    # 法人
    if foreign is not None and not foreign.empty:
        foreign_last = foreign.iloc[-1] / 1000  # 張
        foreign_5d_sum = foreign.iloc[-5:].sum() / 1000
        df["foreign_1d"] = foreign_last
        df["foreign_5d"] = foreign_5d_sum
    else:
        df["foreign_1d"] = 0.0
        df["foreign_5d"] = 0.0

    if trust is not None and not trust.empty:
        trust_last = trust.iloc[-1] / 1000
        trust_5d_sum = trust.iloc[-5:].sum() / 1000
        df["trust_1d"] = trust_last
        df["trust_5d"] = trust_5d_sum
    else:
        df["trust_1d"] = 0.0
        df["trust_5d"] = 0.0

    return df


def compute_group_metrics(stock_metrics: pd.DataFrame) -> dict:
    """每個族群的彙總指標。回傳 dict: group_name -> summary"""
    result = {}
    for group, members in CONCEPT_GROUPS.items():
        rows = stock_metrics.loc[stock_metrics.index.intersection(members)]
        if rows.empty:
            continue
        result[group] = {
            "members":        list(rows.index),
            "n_stocks":       len(rows),
            "ret_1d_mean":    float(rows["ret_1d"].mean(skipna=True) or 0),
            "ret_1d_median":  float(rows["ret_1d"].median(skipna=True) or 0),
            "ret_5d_mean":    float(rows["ret_5d"].mean(skipna=True) or 0),
            "ret_20d_mean":   float(rows["ret_20d"].mean(skipna=True) or 0),
            "amount_sum_mn":  float(rows["amount_mn"].sum(skipna=True) or 0),
            "n_limit_up":     int(rows["limit_up"].sum()),
            "n_limit_down":   int(rows["limit_down"].sum()),
            "n_foreign_buy":  int((rows["foreign_1d"] > 0).sum()),
            "n_trust_buy":    int((rows["trust_1d"] > 0).sum()),
            "top_stock":      rows["ret_1d"].idxmax() if not rows["ret_1d"].isna().all() else None,
            "worst_stock":    rows["ret_1d"].idxmin() if not rows["ret_1d"].isna().all() else None,
        }
    return result


def compute_related_topics(top_n=5) -> dict:
    """以共同成分股推導相關題材。每檔股票是一個 bag，兩族群的 Jaccard 相似度"""
    groups = {g: set(m) for g, m in CONCEPT_GROUPS.items()}
    related = {}
    for g1, s1 in groups.items():
        scores = []
        for g2, s2 in groups.items():
            if g1 == g2:
                continue
            inter = len(s1 & s2)
            if inter == 0:
                continue
            union = len(s1 | s2)
            jac = inter / union
            scores.append((g2, jac, inter))
        scores.sort(key=lambda x: (-x[1], -x[2]))
        related[g1] = [
            {"name": g2, "jaccard": round(j, 3), "shared": n}
            for g2, j, n in scores[:top_n]
        ]
    return related


def compute_company_topics() -> dict:
    """每檔股票反查所屬題材"""
    result = defaultdict(list)
    for group, members in CONCEPT_GROUPS.items():
        for s in members:
            result[s].append(group)
    return dict(result)


def compute_category_aggregates(stock_metrics: pd.DataFrame, group_metrics: dict) -> list:
    """彙總每個 category 層級資料：成分股（去重）、總成交額、平均漲跌、代表題材 Top 3、顏色"""
    cat_groups = defaultdict(list)
    for group in CONCEPT_GROUPS:
        cat = get_meta(group)["category"]
        cat_groups[cat].append(group)

    result = []
    for cat, groups in cat_groups.items():
        # 該 category 下 unique 成分股
        unique_syms = set()
        for g in groups:
            unique_syms.update(CONCEPT_GROUPS[g])
        unique_syms &= set(stock_metrics.index)
        if not unique_syms:
            continue
        rows = stock_metrics.loc[list(unique_syms)]
        total_amt = float(rows["amount_mn"].sum(skipna=True) or 0)
        # 加權平均（以成交額加權）
        if total_amt > 0:
            cat_ret = float((rows["ret_1d"] * rows["amount_mn"]).sum(skipna=True) / total_amt)
        else:
            cat_ret = float(rows["ret_1d"].mean(skipna=True) or 0)
        # 代表題材：該 category 下按成交額排序取 Top 3
        top_groups = sorted(
            [(g, group_metrics.get(g, {}).get("amount_sum_mn", 0)) for g in groups],
            key=lambda x: -x[1],
        )[:3]
        top_names = [g for g, _ in top_groups]
        # color 用 CATEGORY_COLORS
        result.append({
            "name":        cat,
            "n_groups":    len(groups),
            "n_stocks":    len(unique_syms),
            "total_amt":   total_amt,
            "ret_mean":    cat_ret,
            "top_groups":  top_names,
            "color":       CATEGORY_COLORS.get(cat, "#64748b"),
        })
    result.sort(key=lambda x: -x["total_amt"])
    return result


def compute_topic_return_series(d: dict, members: list, days=125) -> dict | None:
    """計算族群當成等權重組合的 6 個月累積報酬曲線 + 近 1D/1W/1M 報酬。
    days=125 ≈ 6 個月交易日。回傳 dates, returns(%), ret_1d, ret_5d, ret_20d 全是百分比。"""
    close = d["close"]
    cols = [c for c in members if c in close.columns]
    if not cols:
        return None
    sub = close[cols].iloc[-(days + 1):]  # 多取一天算首日報酬
    if len(sub) < 5:
        return None
    # 每日各股報酬，跨股等權取平均（skipna 處理個股缺值）
    stock_rets = sub.pct_change()
    port_rets = stock_rets.mean(axis=1, skipna=True).fillna(0)
    # 第一列是首日，accum 起點 0
    port_rets.iloc[0] = 0
    cum = (1 + port_rets).cumprod() - 1

    # 近 1D/5D/20D 投組報酬（組合日報酬乘積）
    def trailing(n):
        if len(port_rets) < n + 1:
            return None
        return float((1 + port_rets.iloc[-n:]).prod() - 1)

    return {
        "dates":   [t.strftime("%Y-%m-%d") for t in cum.index],
        "values":  [round(float(v) * 100, 2) for v in cum.values],
        "ret_1d":  round(float(port_rets.iloc[-1] * 100), 2) if len(port_rets) else None,
        "ret_1w":  round(trailing(5)  * 100, 2) if trailing(5)  is not None else None,
        "ret_1m":  round(trailing(20) * 100, 2) if trailing(20) is not None else None,
        "ret_3m":  round(trailing(60) * 100, 2) if trailing(60) is not None else None,
        "ret_6m":  round(trailing(125) * 100, 2) if trailing(125) is not None else None,
    }


def compute_company_chart(d: dict, sym: str, days=240) -> dict | None:
    """技術分析：240 日 OHLCV + MA5/10/20/60 + Bollinger(20,2σ) + KD(9)。無資料回 None"""
    close = d["close"]
    if sym not in close.columns:
        return None
    try:
        c = close[sym].dropna()
        if len(c) < 5:
            return None
        # 暖機：多抓 60 日算指標，顯示只給 days 天
        lookback = min(len(c), days + 60)
        end_idx = len(c)
        start_idx = max(0, end_idx - lookback)
        idx = c.index[start_idx:end_idx]
        o  = d["open"][sym].reindex(idx)
        h  = d["high"][sym].reindex(idx)
        l  = d["low"][sym].reindex(idx)
        cc = d["close"][sym].reindex(idx)
        v  = d["volume"][sym].reindex(idx)

        # 均線
        ma5  = cc.rolling(5).mean()
        ma10 = cc.rolling(10).mean()
        ma20 = cc.rolling(20).mean()
        ma60 = cc.rolling(60).mean()

        # Bollinger Bands (20, 2σ)
        std20 = cc.rolling(20).std()
        bb_up = ma20 + 2 * std20
        bb_lo = ma20 - 2 * std20

        # KD 指標 (9)
        low9  = l.rolling(9).min()
        high9 = h.rolling(9).max()
        rng   = (high9 - low9).replace(0, np.nan)
        rsv   = (cc - low9) / rng * 100
        k_list, d_list = [], []
        prev_k, prev_d = 50.0, 50.0
        for i in range(len(rsv)):
            r = rsv.iloc[i]
            if pd.isna(r):
                k_list.append(None)
                d_list.append(None)
                continue
            prev_k = (2/3) * prev_k + (1/3) * float(r)
            prev_d = (2/3) * prev_d + (1/3) * prev_k
            k_list.append(round(prev_k, 2))
            d_list.append(round(prev_d, 2))

        # MACD (12, 26, 9)：DIF=EMA12-EMA26, DEA=EMA(DIF,9), MACD_hist=2*(DIF-DEA)
        ema12 = cc.ewm(span=12, adjust=False).mean()
        ema26 = cc.ewm(span=26, adjust=False).mean()
        macd_dif  = ema12 - ema26
        macd_dea  = macd_dif.ewm(span=9, adjust=False).mean()
        macd_hist = (macd_dif - macd_dea) * 2

        # RSI(14) — Wilder's smoothing（等價 ewm alpha=1/14）
        delta = cc.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
        rs  = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))

        def r2(s, i):
            val = s.iloc[i]
            return round(float(val), 2) if pd.notna(val) else None

        # 三大法人買賣超（張 = 股數 / 1000）— 對齊 K 線日期軸
        def chip_series(key):
            df = d.get(key)
            if df is None or sym not in df.columns:
                return None
            return df[sym].reindex(idx) / 1000.0

        foreign_s = chip_series("foreign")
        trust_s   = chip_series("trust")
        dealer_s  = chip_series("dealer")

        def r0(s, i):
            if s is None:
                return None
            val = s.iloc[i]
            return round(float(val), 0) if pd.notna(val) else None

        # 主力 = 外資 + 投信 + 自營（缺值視為 0；但若三者全缺則回 None）
        def main_at(i):
            vals = []
            for s in (foreign_s, trust_s, dealer_s):
                if s is None:
                    continue
                v = s.iloc[i]
                if pd.notna(v):
                    vals.append(float(v))
            if not vals:
                return None
            return round(sum(vals), 0)

        show_from = max(0, len(idx) - days)
        rng_slice = range(show_from, len(idx))

        has_foreign = foreign_s is not None and bool(foreign_s.notna().any())
        has_trust   = trust_s   is not None and bool(trust_s.notna().any())
        has_dealer  = dealer_s  is not None and bool(dealer_s.notna().any())
        has_main    = has_foreign or has_trust or has_dealer

        return {
            "dates":   [t.strftime("%Y-%m-%d") for t in idx[show_from:]],
            "ohlc":    [[r2(o,i), r2(cc,i), r2(l,i), r2(h,i)] for i in rng_slice],
            "volume":  [round(float(v.iloc[i]) / 1000, 0) if pd.notna(v.iloc[i]) else 0 for i in rng_slice],
            "ma5":     [r2(ma5,  i) for i in rng_slice],
            "ma10":    [r2(ma10, i) for i in rng_slice],
            "ma20":    [r2(ma20, i) for i in rng_slice],
            "ma60":    [r2(ma60, i) for i in rng_slice],
            "bb_up":   [r2(bb_up, i) for i in rng_slice],
            "bb_lo":   [r2(bb_lo, i) for i in rng_slice],
            "k":       [k_list[i] for i in rng_slice],
            "d":       [d_list[i] for i in rng_slice],
            # MACD (12,26,9)
            "macd_dif":  [r2(macd_dif,  i) for i in rng_slice],
            "macd_dea":  [r2(macd_dea,  i) for i in rng_slice],
            "macd_hist": [r2(macd_hist, i) for i in rng_slice],
            # RSI(14)
            "rsi":       [r2(rsi, i) for i in rng_slice],
            # 籌碼（與 K 線同一時間軸，單位：張）
            "foreign_net": [r0(foreign_s, i) for i in rng_slice] if has_foreign else None,
            "trust_net":   [r0(trust_s,   i) for i in rng_slice] if has_trust else None,
            "dealer_net":  [r0(dealer_s,  i) for i in rng_slice] if has_dealer else None,
            "main_net":    [main_at(i) for i in rng_slice] if has_main else None,
            "has_chip": {
                "main":    has_main,
                "foreign": has_foreign,
                "trust":   has_trust,
                "dealer":  has_dealer,
            },
        }
    except Exception:
        return None


def compute_company_chip_data(d: dict, sym: str, days: int = 30) -> dict | None:
    """個股籌碼資料：三大法人買賣超 + 融資融券。
    單位：張（整張）。回傳 None 表示無任何資料。"""
    def series_tail(key, to_lots=True):
        df = d.get(key)
        if df is None or sym not in df.columns:
            return None
        s = df[sym].dropna().iloc[-days:]
        if s.empty:
            return None
        if to_lots:
            s = s / 1000
        return s

    dates_ref = None
    out: dict = {}

    # 三大法人：買賣超（net）
    for k in ["foreign", "trust", "dealer"]:
        s = series_tail(k)
        if s is not None:
            out[k + "_net"] = [round(float(x), 0) for x in s.values]
            dates_ref = s.index if dates_ref is None else dates_ref.union(s.index)

    # 買進/賣出明細
    for k in [
        "foreign_buy", "foreign_sell",
        "trust_buy",   "trust_sell",
        "dealer_buy",  "dealer_sell",
    ]:
        s = series_tail(k)
        if s is not None:
            out[k] = [round(float(x), 0) for x in s.values]
            dates_ref = s.index if dates_ref is None else dates_ref.union(s.index)

    # 融資融券（資料單位是「張」或「股」看 FinLab，一律再除 1 保原值；餘額這欄本來就是張）
    for k in [
        "margin_long_bal", "margin_long_buy", "margin_long_sell",
        "margin_short_bal", "margin_short_buy", "margin_short_sell",
    ]:
        s = series_tail(k, to_lots=False)
        if s is not None:
            out[k] = [round(float(x), 0) for x in s.values]
            dates_ref = s.index if dates_ref is None else dates_ref.union(s.index)

    if not out or dates_ref is None:
        return None

    dates_ref = dates_ref.sort_values()
    out["dates"] = [t.strftime("%Y-%m-%d") for t in dates_ref[-days:]]
    return out


def get_disposal_info(disposal_map: dict, sym: str) -> dict | None:
    """從 fetch_extras 的處置股字典查該檔。也嘗試 .lstrip('0') 容錯。"""
    if not disposal_map:
        return None
    info = disposal_map.get(sym)
    if info is None:
        info = disposal_map.get(sym.lstrip("0"))
    if info is None:
        # 字母後綴（例：1522A）主代號 fallback
        base = "".join(c for c in sym if c.isdigit())
        if base and base != sym:
            info = disposal_map.get(base)
    return info


def get_holder_info(holder_history: dict, levels: list, sym: str) -> dict | None:
    """從 holders_history 查該檔所有週的 15 級資料，轉成前端用的 view。"""
    if not holder_history:
        return None
    hist_by_date = holder_history.get(sym)
    if hist_by_date is None:
        hist_by_date = holder_history.get(sym.lstrip("0"))
    if hist_by_date is None:
        base = "".join(c for c in sym if c.isdigit())
        if base and base != sym:
            hist_by_date = holder_history.get(base)
    if not hist_by_date:
        return None
    return build_holder_view(hist_by_date, levels)


# ═══════════════════════════════════════════
#   輸出：熱力圖 JSON + 搜尋 JSON
# ═══════════════════════════════════════════

_HEATMAP_COLORS_11 = (
    "#0b4a26", "#1a6e3a", "#2e8b4d", "#4fa66a", "#7dbf92",
    "#6e7681",
    "#c89e9e", "#d77272", "#d1344f", "#b91c34", "#8b0b22",
)
_BREAKS_DAILY       = (-9, -7, -5, -3, -1,  1,  3,  5,  7,  9)   # ±10 scale / 2% per step
_BREAKS_WEEK_MONTH  = (-27, -21, -15, -9, -3, 3, 9, 15, 21, 27)  # ±30 scale / 6% per step


def ret_to_color(ret_pct: float | None, tf: str = "daily") -> str:
    """ret_pct 已 × 100。daily 用 ±10% 色階（2%/檔）、週月用 ±30% 色階（6%/檔）"""
    if ret_pct is None or (isinstance(ret_pct, float) and pd.isna(ret_pct)):
        return "#6e7681"
    breaks = _BREAKS_DAILY if tf == "daily" else _BREAKS_WEEK_MONTH
    idx = 0
    for b in breaks:
        if ret_pct < b:
            break
        idx += 1
    return _HEATMAP_COLORS_11[idx]


def build_heatmap_data(stock_metrics: pd.DataFrame, name_map: dict, top_n_per_group=15) -> dict:
    """產生 ECharts treemap 格式。分三層：category > group > stock。
    每個節點的顏色 Python 端就算好塞進 itemStyle.color，繞開 ECharts 多層 color mapping 的坑。"""
    data_by_tf = {}
    for tf, col in [("daily", "ret_1d"), ("weekly", "ret_5d"), ("monthly", "ret_20d")]:
        cat_nodes = defaultdict(list)
        for group, members in CONCEPT_GROUPS.items():
            meta = get_meta(group)
            category = meta["category"]
            rows = stock_metrics.loc[stock_metrics.index.intersection(members)].copy()
            if rows.empty:
                continue
            rows_sorted = rows.sort_values("amount_mn", ascending=False).head(top_n_per_group)
            stock_leaves = []
            for sym in rows_sorted.index:
                ret = rows_sorted.at[sym, col]
                if pd.isna(ret):
                    continue
                amt = float(rows_sorted.at[sym, "amount_mn"] or 0)
                ret_pct = float(ret) * 100
                stock_leaves.append({
                    "name":      f"{name_map.get(sym, sym)} ({sym})",
                    "value":     [max(amt, 1), ret_pct],
                    "symbol":    sym,
                    "itemStyle": {"color": ret_to_color(ret_pct, tf)},
                })
            if not stock_leaves:
                continue
            avg_ret_pct = float(rows[col].mean(skipna=True) or 0) * 100
            total_amt_group = sum(s["value"][0] for s in stock_leaves)
            cat_nodes[category].append({
                "name":      group,
                "value":     [total_amt_group, avg_ret_pct],
                "children":  stock_leaves,
                "itemStyle": {"color": ret_to_color(avg_ret_pct, tf)},
            })
        # Category 層去重：同一個股在 category 下多個 group 都有時只算一次成交額
        result = []
        cat_stats = {}
        for cat, groups in cat_nodes.items():
            unique_stocks = {}  # sym -> (amt_mn, ret_pct)
            for g_node in groups:
                for leaf in g_node["children"]:
                    sym = leaf["symbol"]
                    if sym not in unique_stocks:
                        unique_stocks[sym] = (leaf["value"][0], leaf["value"][1])
            unique_amt = sum(v[0] for v in unique_stocks.values())
            # 以成交額加權平均報酬
            cat_ret = (
                sum(v[1] * v[0] for v in unique_stocks.values()) / unique_amt
                if unique_amt > 0 else 0
            )
            cat_stats[cat] = (unique_amt, cat_ret)

        # 依 unique 成交額大→小排序 category
        for cat in sorted(cat_stats, key=lambda c: -cat_stats[c][0]):
            groups = cat_nodes[cat]
            if not groups:
                continue
            groups = sorted(groups, key=lambda g: -g["value"][0])
            unique_amt, cat_ret = cat_stats[cat]
            result.append({
                "name":      cat,
                "value":     [unique_amt, cat_ret],
                "children":  groups,
                "itemStyle": {"color": ret_to_color(cat_ret, tf)},
            })
        data_by_tf[tf] = result
    return data_by_tf


def build_search_data(
    stock_metrics: pd.DataFrame,
    name_map: dict,
    industry_map: dict,
    company_topics: dict,
    disposal_map: dict | None = None,
    market_map: dict | None = None,
) -> list:
    """搜尋用資料。[{type, label, sub, href, keywords}]

    個股：全 stock_metrics symbol 都納入。keywords 多包一層「狀態 tag」
    讓使用者打關鍵字能命中：
      處置 / 處置股 / 處置中 / 注意股 / 漲停 / 跌停 / 大漲 / 大跌 /
      上市 / 上櫃 / 興櫃 / ETF / 熱門 / 旗艦
    """
    disposal_map = disposal_map or {}
    market_map = market_map or {}
    items = []
    for group in CONCEPT_GROUPS:
        meta = get_meta(group)
        items.append({
            "type":  "topic",
            "label": group,
            "sub":   meta["desc"][:50] + ("..." if len(meta["desc"]) > 50 else ""),
            "href":  f"topic/{slugify(group)}.html",
            "keywords": f"{group} {meta['en']} {meta['category']} 題材 族群 概念",
        })
    market_label_map = {"sii": "上市", "otc": "上櫃", "rotc": "興櫃"}
    for sym in stock_metrics.index:
        name_raw = name_map.get(sym)
        name = name_raw if isinstance(name_raw, str) and name_raw.strip() else sym
        topics = company_topics.get(sym, [])
        industry = industry_map.get(sym, "")

        # ── 狀態 tag 收集 ──
        tags: list[str] = []
        badges: list[str] = []

        disp_info = get_disposal_info(disposal_map, sym)
        if disp_info:
            tags += ["處置", "處置股", "處置中", "警示"]
            status = (disp_info.get("status") or "").strip()
            if "注意" in status:
                tags += ["注意股"]
            badges.append("⚠處置中")

        mkt_disp = market_label_map.get(market_map.get(sym, ""), "")
        if mkt_disp:
            tags.append(mkt_disp)

        # ETF 判斷：名稱含 ETF 或代號 00 開頭 5~6 碼
        name_upper = name.upper()
        is_etf = ("ETF" in name_upper) or (sym.startswith("00") and len(sym) >= 4 and len(sym) <= 6)
        if is_etf:
            tags.append("ETF")

        # 漲跌停/大漲大跌（依當日報酬）
        ret1 = stock_metrics.loc[sym].get("ret_1d") if sym in stock_metrics.index else None
        if ret1 is not None and pd.notna(ret1):
            r = float(ret1)
            if r >= 0.094:
                tags.append("漲停")
                badges.append("🔺漲停")
            elif r <= -0.094:
                tags.append("跌停")
                badges.append("🔻跌停")
            elif r >= 0.05:
                tags.append("大漲")
            elif r <= -0.05:
                tags.append("大跌")

        # 熱門個股（STOCK_HIGHLIGHTS 有登錄者）
        hl = STOCK_HIGHLIGHTS.get(sym) if STOCK_HIGHLIGHTS else None
        hl_extra = ""
        if hl:
            tags += ["熱門", "熱點"]
            hl_extra = " ".join(
                str(hl.get(k, "")) for k in ("ranking", "tech", "moat")
            )

        # ── sub 顯示：徽章 + 題材/產業 ──
        if topics:
            sub_main = " / ".join(topics[:3])
        elif industry:
            sub_main = industry
        else:
            sub_main = ""
        if badges:
            sub = " · ".join(badges) + (" · " + sub_main if sub_main else "")
        else:
            sub = sub_main

        items.append({
            "type":  "company",
            "label": f"{name} ({sym})",
            "sub":   sub,
            "href":  f"company/{sym}.html",
            "keywords": f"{name} {sym} {industry} {' '.join(topics)} {' '.join(tags)} {hl_extra}",
        })
    return items


# ═══════════════════════════════════════════
#   模板渲染
# ═══════════════════════════════════════════

def slugify(name: str) -> str:
    """把中文題材名轉成可用的檔名 slug（用 hash 避免系統路徑問題）"""
    safe = name.replace("/", "_").replace("\\", "_").replace(" ", "")
    # 保留中文但限制長度
    if len(safe) > 30:
        safe = hashlib.md5(name.encode("utf-8")).hexdigest()[:12]
    return safe


def pct(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{v*100:+.2f}%"


def fmt_amount(v) -> str:
    """v 單位 = 百萬元。顯示兩檔「億 / 萬」，不用千萬、不用 M（1 億 = 100 百萬）"""
    if v is None or pd.isna(v) or v <= 0:
        return "—"
    if v >= 100:                        # >= 1 億 → X.X 億
        return f"{v/100:.1f} 億"
    return f"{int(round(v*100))} 萬"    # < 1 億 → XXXX 萬


def tv_symbol_digits(sym: str) -> str:
    """抽出數字部份給 TradingView 用（例：00631L → 00631）"""
    return "".join(c for c in (sym or "") if c.isdigit())


def build_env():
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["pct"] = pct
    env.filters["fmt_amount"] = fmt_amount
    env.filters["slugify"] = slugify
    env.filters["tv_symbol"] = tv_symbol_digits
    env.globals["CATEGORY_COLORS"] = CATEGORY_COLORS
    env.globals["get_meta"] = get_meta
    env.globals["STOCK_HIGHLIGHTS"] = STOCK_HIGHLIGHTS
    return env


def compute_rankings(stock_metrics: pd.DataFrame, rich: dict, extras: dict,
                     name_map: dict, industry_map: dict, company_topics: dict,
                     top_n: int = 20) -> dict:
    """產出四類排行榜資料供 rankings.html 使用。

    返回 dict:
      chips_foreign_buy / chips_foreign_sell  — 近 5 日外資 Top 20
      chips_trust_buy   / chips_trust_sell    — 近 5 日投信 Top 20
      revenue_yoy_up    / revenue_yoy_down    — 最新月營收 YoY Top/Bottom 20
      eps_growth_up     / eps_growth_down     — EPS vs 去年同季成長 Top/Bottom 20
      big_holders_up    / big_holders_down    — 近 N 週大戶佔比變化 Top/Bottom 20
    每個 item = {sym, name, industry, topics_txt, value, sub_value, close, ret_1d}
    """
    def _has_valid_name(sym):
        """過濾掉無正式名稱的證券（ETF、權證、已下市等）"""
        name_raw = name_map.get(sym)
        return isinstance(name_raw, str) and name_raw.strip() and name_raw.strip() != sym

    def _base_row(sym):
        name = name_map.get(sym, sym)
        row = stock_metrics.loc[sym] if sym in stock_metrics.index else None
        topics = company_topics.get(sym, [])
        return {
            "sym":        sym,
            "name":       name,
            "industry":   industry_map.get(sym, ""),
            "topics":     topics[:3],
            "close":      float(row["close"]) if row is not None and row["close"] == row["close"] else None,
            "ret_1d":     float(row["ret_1d"]) if row is not None and row["ret_1d"] == row["ret_1d"] else None,
        }

    # ─── 籌碼排行 ───
    syms = [s for s in stock_metrics.index if _has_valid_name(s)]
    chips_foreign = [
        {**_base_row(s), "value": float(stock_metrics.at[s, "foreign_5d"])}
        for s in syms if "foreign_5d" in stock_metrics.columns
        and pd.notna(stock_metrics.at[s, "foreign_5d"])
    ]
    chips_trust = [
        {**_base_row(s), "value": float(stock_metrics.at[s, "trust_5d"])}
        for s in syms if "trust_5d" in stock_metrics.columns
        and pd.notna(stock_metrics.at[s, "trust_5d"])
    ]
    chips_foreign_buy = sorted(chips_foreign, key=lambda r: -r["value"])[:top_n]
    chips_foreign_sell = sorted(chips_foreign, key=lambda r: r["value"])[:top_n]
    chips_trust_buy = sorted(chips_trust, key=lambda r: -r["value"])[:top_n]
    chips_trust_sell = sorted(chips_trust, key=lambda r: r["value"])[:top_n]

    # ─── 月營收 YoY 排行（統一月份 + 基期過小濾除 + YoY 合理區間）───
    rev_map = rich.get("revenue", {})
    from collections import Counter as _C
    _ym_count = _C()
    for _s, _items in rev_map.items():
        if _items and _has_valid_name(_s):
            _ym_count[_items[-1]["ym"]] += 1
    base_ym = _ym_count.most_common(1)[0][0] if _ym_count else None
    REV_MIN_THOUSAND = 10000  # 千元 = 1000 萬元（當期&去年同期門檻）
    rev_rows = []
    for sym, items in rev_map.items():
        if not items or not _has_valid_name(sym):
            continue
        last = items[-1]
        if last.get("ym") != base_ym:                  # 非眾數月份 → 老資料
            continue
        yoy = last.get("yoy")
        rev_now = last.get("rev")
        if yoy is None or rev_now is None or rev_now < REV_MIN_THOUSAND:
            continue
        if yoy <= -99 or yoy > 300:                    # 極端值通常是基期扭曲
            continue
        rev_ly = rev_now / (1 + yoy / 100.0)
        if rev_ly < REV_MIN_THOUSAND:
            continue
        rev_rows.append({
            **_base_row(sym),
            "value":     float(yoy),
            "sub_value": float(rev_now),
            "ym":        last["ym"],
        })
    revenue_yoy_up = sorted(rev_rows, key=lambda r: -r["value"])[:top_n]
    revenue_yoy_down = sorted(rev_rows, key=lambda r: r["value"])[:top_n]

    # ─── EPS 年增排行（最新季 vs 4 季前；基期 EPS 絕對值 >= 0.3 元 + YoY -200%~500%）───
    fin_map = rich.get("financials", {})
    # 統一季別：取眾數季作為 base_q
    _q_count = _C()
    for _s, _rows in fin_map.items():
        if _rows and _has_valid_name(_s):
            _q_count[_rows[-1].get("q")] += 1
    base_q = _q_count.most_common(1)[0][0] if _q_count else None
    EPS_BASE_MIN = 0.3  # 去年同期 |EPS| 至少 0.3 元才能算年增率
    eps_rows = []
    for sym, rows in fin_map.items():
        if not rows or len(rows) < 5 or not _has_valid_name(sym):
            continue
        if rows[-1].get("q") != base_q:                # 非眾數季 → 舊資料
            continue
        eps_now = rows[-1].get("eps")
        eps_yoy = rows[-5].get("eps")
        if eps_now is None or eps_yoy is None:
            continue
        if abs(eps_yoy) < EPS_BASE_MIN:                # 基期太小，算出來扭曲
            continue
        growth = (eps_now - eps_yoy) / abs(eps_yoy) * 100
        if growth < -200 or growth > 500:              # 合理區間
            continue
        eps_rows.append({
            **_base_row(sym),
            "value":     round(growth, 1),
            "sub_value": eps_now,
            "prev_eps":  eps_yoy,
            "quarter":   rows[-1].get("q"),
        })
    eps_growth_up = sorted(eps_rows, key=lambda r: -r["value"])[:top_n]
    eps_growth_down = sorted(eps_rows, key=lambda r: r["value"])[:top_n]

    # ─── 大戶（>400 張）佔比變化排行 ───
    holders_hist = extras.get("holders_history", {}) or {}
    big_rows = []
    for sym, by_date in holders_hist.items():
        if not by_date or not _has_valid_name(sym):
            continue
        dates = sorted(by_date.keys())
        if len(dates) < 2:
            continue
        first_pcts = by_date[dates[0]].get("p", [])
        last_pcts = by_date[dates[-1]].get("p", [])
        if len(first_pcts) < 15 or len(last_pcts) < 15:
            continue
        big_first = sum(first_pcts[11:15])
        big_last = sum(last_pcts[11:15])
        delta = big_last - big_first
        big_rows.append({
            **_base_row(sym),
            "value":     round(delta, 2),
            "sub_value": round(big_last, 2),
            "weeks":     len(dates),
        })
    big_holders_up = sorted(big_rows, key=lambda r: -r["value"])[:top_n]
    big_holders_down = sorted(big_rows, key=lambda r: r["value"])[:top_n]

    return {
        "chips_foreign_buy":  chips_foreign_buy,
        "chips_foreign_sell": chips_foreign_sell,
        "chips_trust_buy":    chips_trust_buy,
        "chips_trust_sell":   chips_trust_sell,
        "revenue_yoy_up":     revenue_yoy_up,
        "revenue_yoy_down":   revenue_yoy_down,
        "eps_growth_up":      eps_growth_up,
        "eps_growth_down":    eps_growth_down,
        "big_holders_up":     big_holders_up,
        "big_holders_down":   big_holders_down,
    }


def load_ai_summaries() -> dict:
    """AI 題材分析摘要（fetch by background agent）。"""
    fp = SITE_DIR / ".ai_summaries.json"
    if not fp.exists():
        return {}
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return {}


def compute_limit_up_stats(limit_up_by_date: dict, close_df) -> dict:
    """對歷史漲停資料計算：
       1) daily_summary     — 每日漲停家數、隔日平均/中位/正報酬率
       2) next_day_returns  — 所有漲停股的隔日報酬 list（做直方圖）
       3) heatmap_dates / heatmap_groups / heatmap_matrix — 族群 × 日期熱力圖（家數）
       4) group_stats       — 各族群總漲停次數 + 隔日平均報酬
       5) recent_detail     — 近 20 日逐檔：code, name, group, date, next_ret
    """
    if not limit_up_by_date or close_df is None:
        return None
    dates = sorted(limit_up_by_date.keys())
    # 把 DataFrame 的 date 轉 'YYYY-MM-DD' 字串對照
    close_ix_str = [t.strftime("%Y-%m-%d") for t in close_df.index]
    date_to_pos = {s: i for i, s in enumerate(close_ix_str)}

    daily_summary = []
    all_next_returns = []       # (date, sym, group, next_ret)
    group_count = defaultdict(int)
    group_next_ret = defaultdict(list)
    # 族群熱力圖：用整體出現過的族群集合
    all_groups = set()
    heatmap_matrix = []         # [{date, group, n}]

    prev_codes: set[str] = set()   # 前一交易日的漲停代號集合
    for d in dates:
        payload = limit_up_by_date[d]
        stocks = payload.get("stocks", [])
        if d not in date_to_pos:
            continue
        pos = date_to_pos[d]
        next_pos = pos + 1 if pos + 1 < len(close_ix_str) else None

        # 族群家數 + 今日漲停代號集合
        grp_count_today = defaultdict(int)
        today_codes: set[str] = set()
        for s in stocks:
            g = s.get("group", "其他")
            grp_count_today[g] += 1
            all_groups.add(g)
            c = s.get("code")
            if c:
                today_codes.add(c)

        # 續漲停：今日漲停清單 ∩ 前一交易日漲停清單
        n_continued = len(today_codes & prev_codes)

        # 隔日報酬
        next_rets = []
        n_next_limit_up = 0        # 隔日仍漲停檔數（≥ 9.5%）
        if next_pos is not None:
            for s in stocks:
                sym = s.get("code")
                if not sym or sym not in close_df.columns:
                    continue
                try:
                    p_now = close_df.iloc[pos][sym]
                    p_next = close_df.iloc[next_pos][sym]
                    if pd.isna(p_now) or pd.isna(p_next) or p_now == 0:
                        continue
                    r = float(p_next / p_now - 1) * 100
                    next_rets.append(r)
                    if r >= 9.5:                     # 續漲停門檻
                        n_next_limit_up += 1
                    all_next_returns.append({
                        "date": d, "sym": sym,
                        "name": s.get("name", sym),
                        "group": s.get("group", ""),
                        "next_ret": round(r, 2),
                    })
                    group_count[s.get("group", "其他")] += 1
                    group_next_ret[s.get("group", "其他")].append(r)
                except Exception:
                    continue

        summary_row = {
            "date":            d,
            "n_limit_up":      len(stocks),
            "n_continued":     n_continued,       # 今日與昨日重疊檔數（續漲停）
            "n_next_limit_up": n_next_limit_up,   # 舊欄位保留：隔日 ≥9.5% 檔數
            "next_avg":        round(sum(next_rets) / len(next_rets), 2) if next_rets else None,
            "next_median":     round(sorted(next_rets)[len(next_rets)//2], 2) if next_rets else None,
            "next_pos_rate":   round(sum(1 for r in next_rets if r > 0) / len(next_rets) * 100, 1) if next_rets else None,
            "next_max":        round(max(next_rets), 2) if next_rets else None,
            "next_min":        round(min(next_rets), 2) if next_rets else None,
        }
        daily_summary.append(summary_row)
        prev_codes = today_codes

        # 族群熱力圖行
        for g, n in grp_count_today.items():
            heatmap_matrix.append({"date": d, "group": g, "n": n})

    # 族群出現次數排序（熱力圖 Y 軸）
    group_stats = []
    for g in all_groups:
        rets = group_next_ret.get(g, [])
        group_stats.append({
            "group":     g,
            "count":     group_count.get(g, 0),
            "avg_next":  round(sum(rets) / len(rets), 2) if rets else None,
            "pos_rate":  round(sum(1 for r in rets if r > 0) / len(rets) * 100, 1) if rets else None,
        })
    # 排除不屬於具體題材的歸類（「其他」、「其他族群」、「未歸類」等）
    def _is_generic(name: str) -> bool:
        if not name:
            return True
        s = name.strip()
        return (
            s in {"—", "未歸類", "N/A"} or
            s.startswith("其他") or         # 其他 / 其他族群 / 其他電子業 / 其他工業
            "未分類" in s
        )
    group_stats.sort(key=lambda x: -x["count"])
    heatmap_groups = [
        g["group"] for g in group_stats
        if not _is_generic(g["group"]) and g["count"] >= 2
    ][:30]

    # 近 20 日明細（倒序）
    recent_detail = sorted(all_next_returns, key=lambda x: x["date"], reverse=True)[:300]

    # 全體統計
    all_rets = [r["next_ret"] for r in all_next_returns]
    overall = {
        "total_limit_up":   sum(d["n_limit_up"] for d in daily_summary),
        "total_scored":     len(all_rets),
        "avg_next":         round(sum(all_rets) / len(all_rets), 2) if all_rets else None,
        "median_next":      round(sorted(all_rets)[len(all_rets)//2], 2) if all_rets else None,
        "pos_rate":         round(sum(1 for r in all_rets if r > 0) / len(all_rets) * 100, 1) if all_rets else None,
        "date_range":       f"{dates[0]} ~ {dates[-1]}" if dates else "",
        "n_days":           len(dates),
    }

    return {
        "daily_summary":     daily_summary,
        "next_day_returns":  all_rets,
        "heatmap_dates":     dates[-40:],   # 熱力圖顯示近 40 日
        "heatmap_groups":    heatmap_groups,
        "heatmap_matrix":    [h for h in heatmap_matrix if h["group"] in set(heatmap_groups) and h["date"] in set(dates[-40:])],
        "group_stats":       group_stats[:40],
        "recent_detail":     recent_detail,
        "overall":           overall,
    }


def render_all(data, stock_metrics, group_metrics, related, company_topics, rich=None, extras=None, coverage=None):
    env = build_env()
    rich = rich or {"basic": {}, "business": {}, "revenue": {}, "financials": {}, "dividends": {}, "director": {}}
    extras = extras or {"disposal": {}, "holders": {}}
    coverage = coverage or {}
    name_map = data["name_map"]
    last_date = data["close"].index[-1].strftime("%Y-%m-%d")

    limit_up_by_date = load_all_limit_up_data()
    has_limit_up = bool(limit_up_by_date)
    limit_up_dates = sorted(limit_up_by_date.keys()) if limit_up_by_date else []
    latest_lu_date = limit_up_dates[-1] if limit_up_dates else None
    limit_up_data = limit_up_by_date.get(latest_lu_date) if latest_lu_date else None

    # 共用資料
    base_ctx = {
        "now": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "last_date": last_date,
        "nav_topics": sorted(
            CONCEPT_GROUPS.keys(),
            key=lambda g: -group_metrics.get(g, {}).get("amount_sum_mn", 0)
        )[:8],
        "has_limit_up": has_limit_up,
    }

    # Index（每日焦點）
    total_groups = len(CONCEPT_GROUPS)
    total_limit_up = int(stock_metrics["limit_up"].sum())
    total_limit_down = int(stock_metrics["limit_down"].sum())
    top_gain = sorted(
        [(g, m) for g, m in group_metrics.items()],
        key=lambda x: -x[1]["ret_1d_mean"],
    )[:10]
    top_loss = sorted(
        [(g, m) for g, m in group_metrics.items()],
        key=lambda x: x[1]["ret_1d_mean"],
    )[:10]
    top_flow = sorted(
        [(g, m) for g, m in group_metrics.items()],
        key=lambda x: -x[1]["amount_sum_mn"],
    )[:10]
    top_limit = sorted(
        [(g, m) for g, m in group_metrics.items()],
        key=lambda x: -x[1]["n_limit_up"],
    )[:10]

    # 個股漲幅榜（用 display_name 避開 pandas Series 的 .name 屬性衝突）
    # name_map 查不到的 symbol（ETF 等）fallback 成 symbol 本身，避免顯示 "nan"
    movers = stock_metrics.dropna(subset=["ret_1d"]).copy()
    movers["display_name"] = [
        (name_map.get(s) if isinstance(name_map.get(s), str) and name_map.get(s).strip() else s)
        for s in movers.index
    ]
    movers_up = movers.sort_values("ret_1d", ascending=False).head(20)
    movers_down = movers.sort_values("ret_1d", ascending=True).head(20)

    category_aggs = compute_category_aggregates(stock_metrics, group_metrics)

    total_stocks = len(stock_metrics)
    hot_topics = load_hot_topics(top_n=6)
    index_html = env.get_template("index.html").render(
        **base_ctx,
        total_groups=total_groups,
        total_stocks=total_stocks,
        total_limit_up=total_limit_up,
        total_limit_down=total_limit_down,
        top_flow=top_flow,
        category_aggs=category_aggs,
        hot_topics=hot_topics,
    )
    (DIST_DIR / "index.html").write_text(index_html, encoding="utf-8")

    # 漲停分析（多日期版本：每個交易日都產一頁 + 日期下拉導航）
    if has_limit_up:
        known_groups = set(CONCEPT_GROUPS.keys())
        tpl_lu = env.get_template("limit_up.html")

        def _render_one(lu_date: str, lu_payload: dict, is_latest: bool):
            stocks = lu_payload.get("stocks", [])
            group_order = lu_payload.get("groupOrder", [])
            groups_by_name = defaultdict(list)
            for s in stocks:
                groups_by_name[s.get("group", "其他")].append(s)
            ordered_groups = []
            for g in group_order:
                if g in groups_by_name:
                    ordered_groups.append((g, groups_by_name[g]))
            for g, lst in groups_by_name.items():
                if g not in group_order:
                    ordered_groups.append((g, lst))
            return tpl_lu.render(
                **base_ctx,
                lu_date=lu_payload.get("tradingDate", lu_date),
                lu_stocks=stocks,
                lu_ordered_groups=ordered_groups,
                lu_group_analysis=lu_payload.get("groupAnalysis", []),
                lu_chip=lu_payload.get("chipObservation", {}),
                lu_known_groups=known_groups,
                lu_total=len(stocks),
                lu_n_groups=len(groups_by_name),
                lu_all_dates=limit_up_dates,      # 全部可選日期（升冪）
                lu_current_date=lu_date,          # 當前頁日期
                lu_is_latest=is_latest,
                name_map=name_map,
                get_meta=get_meta,
            )

        # 每個日期獨立頁
        for d in limit_up_dates:
            html = _render_one(d, limit_up_by_date[d], d == latest_lu_date)
            (DIST_DIR / f"limit-up-{d}.html").write_text(html, encoding="utf-8")

        # limit-up.html = 最新一天
        latest_html = _render_one(latest_lu_date, limit_up_by_date[latest_lu_date], True)
        (DIST_DIR / "limit-up.html").write_text(latest_html, encoding="utf-8")

        # 漲停統計頁：隔日趨勢 + 族群熱力圖
        try:
            stats = compute_limit_up_stats(limit_up_by_date, data.get("close"))
        except Exception as _e:
            print(f"       ⚠ 漲停統計計算失敗：{_e}")
            stats = None
        if stats:
            stats_html = env.get_template("limit_up_stats.html").render(
                **base_ctx,
                stats=stats,
                stats_daily_json=json.dumps(stats["daily_summary"], ensure_ascii=False),
                stats_returns_json=json.dumps(stats["next_day_returns"], ensure_ascii=False),
                stats_heatmap_json=json.dumps(stats["heatmap_matrix"], ensure_ascii=False),
                stats_groups_json=json.dumps(stats["heatmap_groups"], ensure_ascii=False),
                stats_dates_json=json.dumps(stats["heatmap_dates"], ensure_ascii=False),
            )
            (DIST_DIR / "limit-up-stats.html").write_text(stats_html, encoding="utf-8")
            print(f"       ✓ 漲停統計：{stats['overall']['total_limit_up']} 檔次｜隔日均 {stats['overall']['avg_next']}% ｜勝率 {stats['overall']['pos_rate']}%")
        # 清舊 iframe 遺留
        for stale in ("limit-up-inner.html",):
            p = DIST_DIR / stale
            if p.exists():
                p.unlink()
        print(f"       ✓ 漲停分析頁 {len(limit_up_dates)} 天 + 主頁 limit-up.html（最新 {latest_lu_date}）")

    # Today（今日焦點：原 index 的動態內容搬移過來）
    today_html = env.get_template("today.html").render(
        **base_ctx,
        top_gain=top_gain,
        top_loss=top_loss,
        top_flow=top_flow,
        top_limit=top_limit,
        movers_up=movers_up,
        movers_down=movers_down,
        name_map=name_map,
        company_topics=company_topics,
        industry_map=data["industry_map"],
    )
    (DIST_DIR / "today.html").write_text(today_html, encoding="utf-8")

    # Topics overview
    topics_html = env.get_template("topics.html").render(
        **base_ctx,
        groups=sorted(
            CONCEPT_GROUPS.keys(),
            key=lambda g: (
                get_meta(g)["category"],
                -group_metrics.get(g, {}).get("amount_sum_mn", 0),
            ),
        ),
        group_metrics=group_metrics,
        get_meta=get_meta,
        categories=sorted({get_meta(g)["category"] for g in CONCEPT_GROUPS}),
    )
    (DIST_DIR / "topics.html").write_text(topics_html, encoding="utf-8")

    # Heatmap（內嵌 JSON 避 file:// CORS）
    heatmap_json = {
        tf: json.dumps(nodes, ensure_ascii=False)
        for tf, nodes in build_heatmap_data(stock_metrics, name_map).items()
    }
    heatmap_html = env.get_template("heatmap.html").render(
        **base_ctx,
        heatmap_daily=heatmap_json["daily"],
        heatmap_weekly=heatmap_json["weekly"],
        heatmap_monthly=heatmap_json["monthly"],
    )
    (DIST_DIR / "heatmap.html").write_text(heatmap_html, encoding="utf-8")

    # AI 分析頁（族群輪動 + 落後補漲）
    # 落後補漲：20D 弱但 5D 轉強
    laggards = []
    for g, m in group_metrics.items():
        if m["ret_20d_mean"] < -0.03 and m["ret_5d_mean"] > 0.01:
            laggards.append((g, m))
    laggards.sort(key=lambda x: -x[1]["ret_5d_mean"])
    # 強勢延續：20D 強 + 5D 強 + 今日強
    leaders = []
    for g, m in group_metrics.items():
        if m["ret_20d_mean"] > 0.05 and m["ret_5d_mean"] > 0.02 and m["ret_1d_mean"] > 0:
            leaders.append((g, m))
    leaders.sort(key=lambda x: -(x[1]["ret_5d_mean"] + x[1]["ret_1d_mean"]))
    ai_html = env.get_template("ai_analysis.html").render(
        **base_ctx,
        laggards=laggards[:10],
        leaders=leaders[:10],
        get_meta=get_meta,
    )
    (DIST_DIR / "ai.html").write_text(ai_html, encoding="utf-8")

    # AI 題材摘要（背景 agent 產出）
    ai_summaries = load_ai_summaries()

    # 每個題材頁 + 快取 topic_series 供 compare 頁共用
    topic_dir = DIST_DIR / "topic"
    topic_dir.mkdir(exist_ok=True)
    tpl_topic = env.get_template("topic_detail.html")
    all_topic_series = {}
    all_topic_meta   = {}
    for group, members in CONCEPT_GROUPS.items():
        meta = get_meta(group)
        rows = stock_metrics.loc[stock_metrics.index.intersection(members)].copy()
        rows["display_name"] = [
            (name_map.get(s) if isinstance(name_map.get(s), str) and name_map.get(s).strip() else s)
            for s in rows.index
        ]
        rows_sorted = rows.sort_values("amount_mn", ascending=False)
        topic_series = compute_topic_return_series(data, members, days=125)
        ai_sum = ai_summaries.get(group)
        html = tpl_topic.render(
            **base_ctx,
            group=group,
            meta=meta,
            stocks=rows_sorted,
            summary=group_metrics.get(group, {}),
            related=related.get(group, []),
            name_map=name_map,
            company_topics=company_topics,
            topic_series_json=json.dumps(topic_series, ensure_ascii=False) if topic_series else "null",
            ai_summary=ai_sum,
        )
        (topic_dir / f"{slugify(group)}.html").write_text(html, encoding="utf-8")
        if topic_series:
            all_topic_series[group] = topic_series
            all_topic_meta[group] = {
                "category": meta.get("category", ""),
                "color":    meta.get("color", "#64748b"),
                "slug":     slugify(group),
                "n_stocks": len(rows),
            }

    # 題材對比頁（前端選 2-5 個題材疊加走勢）
    compare_html = env.get_template("compare.html").render(
        **base_ctx,
        topic_series_json=json.dumps(all_topic_series, ensure_ascii=False),
        topic_meta_json=json.dumps(all_topic_meta, ensure_ascii=False),
    )
    (DIST_DIR / "compare.html").write_text(compare_html, encoding="utf-8")

    # 排行榜頁（籌碼 / 月營收 YoY / EPS 年增 / 大戶變化）
    rankings = compute_rankings(
        stock_metrics, rich, extras,
        name_map, data["industry_map"], company_topics, top_n=20,
    )
    rankings_html = env.get_template("rankings.html").render(
        **base_ctx,
        rankings=rankings,
    )
    (DIST_DIR / "rankings.html").write_text(rankings_html, encoding="utf-8")

    # 公司資料庫頁（全上市櫃清單 + 前端搜尋/篩選/排序）
    industries_list = sorted({
        v for v in data["industry_map"].values()
        if isinstance(v, str) and v.strip()
    })
    db_rows = []
    for sym in stock_metrics.index:
        row = stock_metrics.loc[sym]
        name_raw = name_map.get(sym)
        name = name_raw if isinstance(name_raw, str) and name_raw.strip() else sym
        market_code = data["market_map"].get(sym, "")
        market_disp = {"sii": "上市", "otc": "上櫃", "rotc": "興櫃"}.get(market_code, market_code)
        topics = company_topics.get(sym, [])
        def _num(v):
            return float(v) if (v is not None and v == v) else None
        db_rows.append({
            "sym":         sym,
            "name":        name,
            "industry":    data["industry_map"].get(sym, ""),
            "market":      market_disp,
            "market_code": market_code,
            "close":       _num(row.get("close")),
            "ret_1d":      _num(row.get("ret_1d")),
            "ret_5d":      _num(row.get("ret_5d")),
            "ret_20d":     _num(row.get("ret_20d")),
            "amount":      _num(row.get("amount_mn")),
            "topics_txt":  "、".join(topics) if topics else "",
        })
    # 預設按成交額大→小
    db_rows.sort(key=lambda r: -(r["amount"] or 0))
    db_html = env.get_template("database.html").render(
        **base_ctx,
        rows=db_rows,
        industries=industries_list,
        total_stocks=len(db_rows),
    )
    (DIST_DIR / "database.html").write_text(db_html, encoding="utf-8")

    # 每檔個股頁：全上市櫃覆蓋（有題材無題材都產頁），加上 FinLab 豐富資料
    # [FILTER] 過濾 strict 下市：無正式股名 AND 近 20 日完全無成交。ETF / 特別股保留（有股名就活）。
    amount_df = data.get("amount")
    delisted = set()
    for sym in stock_metrics.index:
        nm = name_map.get(sym)
        has_name = isinstance(nm, str) and nm.strip() and nm.strip() != sym
        if has_name:
            continue  # 有名就保留（ETF 權證特別股不殺）
        if amount_df is not None and sym in amount_df.columns:
            recent_amt = amount_df[sym].iloc[-20:].fillna(0).sum()
            if recent_amt == 0:
                delisted.add(sym)
    if delisted:
        print(f"       ↳ 過濾 {len(delisted)} 檔已下市/停牌")
        (DIST_DIR / "data").mkdir(exist_ok=True)
        (DIST_DIR / "data" / "delisted.json").write_text(
            json.dumps(sorted(delisted), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # 同步刪除殘留 HTML（避免舊 build 留下的下市股頁仍可被索引）
        stale = 0
        for s in delisted:
            f = DIST_DIR / "company" / f"{s}.html"
            if f.exists():
                f.unlink()
                stale += 1
        if stale:
            print(f"       ↳ 清除 {stale} 個殘留 HTML")

    company_dir = DIST_DIR / "company"
    company_dir.mkdir(exist_ok=True)
    tpl_company = env.get_template("company.html")
    n_pages = 0
    for sym in stock_metrics.index:
        if sym in delisted:
            continue
        row = stock_metrics.loc[sym]
        name_raw = name_map.get(sym)
        name = name_raw if isinstance(name_raw, str) and name_raw.strip() else sym
        market = data["market_map"].get(sym, "")
        market_disp = {"sii": "上市", "otc": "上櫃", "rotc": "興櫃"}.get(market, market)
        chart_data = compute_company_chart(data, sym, days=240)
        chip_data  = compute_company_chip_data(data, sym, days=30)
        disposal   = get_disposal_info(extras.get("disposal", {}), sym)
        holder     = get_holder_info(
            extras.get("holders_history", {}),
            extras.get("holder_levels", []),
            sym,
        )
        topics = company_topics.get(sym, [])
        basic = rich["basic"].get(sym)
        business = rich["business"].get(sym)
        revenue = rich["revenue"].get(sym)
        financials = rich["financials"].get(sym)
        dividends = rich["dividends"].get(sym)
        director_pct = rich["director"].get(sym)
        coverage_tabs = build_coverage_tabs(coverage.get(sym))
        html = tpl_company.render(
            **base_ctx,
            symbol=sym,
            name=name,
            industry=data["industry_map"].get(sym, ""),
            market=market_disp,
            row=row,
            topics=[(t, get_meta(t)) for t in topics],
            chart_json=json.dumps(chart_data, ensure_ascii=False) if chart_data else "null",
            chip_json=json.dumps(chip_data, ensure_ascii=False) if chip_data else "null",
            holder=holder,
            holder_json=json.dumps(holder, ensure_ascii=False) if holder else "null",
            disposal=disposal,
            basic=basic,
            business=business,
            revenue=revenue,
            revenue_json=json.dumps(revenue, ensure_ascii=False) if revenue else "[]",
            financials=financials,
            dividends=dividends,
            director_pct=director_pct,
            coverage_tabs=coverage_tabs,
        )
        (company_dir / f"{sym}.html").write_text(html, encoding="utf-8")
        n_pages += 1
    print(f"       ✓ 個股頁 {n_pages} 檔（全上市櫃）")


def copy_static():
    """複製靜態檔案"""
    dst = DIST_DIR / "static"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(STATIC_SRC, dst)


ROBOTS_TXT_CONTENT = """# 族群寶 robots.txt
# 允許：主流搜尋引擎（Google / Bing / DuckDuckGo 等）
# 禁止：AI 訓練爬蟲與內容抓取機器人

# ---- AI 訓練爬蟲（禁止） ----
User-agent: GPTBot
Disallow: /

User-agent: ChatGPT-User
Disallow: /

User-agent: OAI-SearchBot
Disallow: /

User-agent: ClaudeBot
Disallow: /

User-agent: Claude-Web
Disallow: /

User-agent: anthropic-ai
Disallow: /

User-agent: CCBot
Disallow: /

User-agent: PerplexityBot
Disallow: /

User-agent: Perplexity-User
Disallow: /

User-agent: Google-Extended
Disallow: /

User-agent: Bytespider
Disallow: /

User-agent: Amazonbot
Disallow: /

User-agent: Applebot-Extended
Disallow: /

User-agent: FacebookBot
Disallow: /

User-agent: Meta-ExternalAgent
Disallow: /

User-agent: Meta-ExternalFetcher
Disallow: /

User-agent: cohere-ai
Disallow: /

User-agent: Diffbot
Disallow: /

User-agent: ImagesiftBot
Disallow: /

User-agent: Omgilibot
Disallow: /

User-agent: Omgili
Disallow: /

User-agent: YouBot
Disallow: /

User-agent: Timpibot
Disallow: /

User-agent: MistralAI-User
Disallow: /

# ---- 一般資料抓取爬蟲（禁止） ----
User-agent: SemrushBot
Disallow: /

User-agent: AhrefsBot
Disallow: /

User-agent: MJ12bot
Disallow: /

User-agent: DotBot
Disallow: /

User-agent: DataForSeoBot
Disallow: /

User-agent: BLEXBot
Disallow: /

User-agent: PetalBot
Disallow: /

# ---- 其他所有爬蟲（允許，給 Google / Bing 等） ----
User-agent: *
Allow: /
Disallow: /data/
Crawl-delay: 2

Sitemap: https://indusmapk.com/sitemap.xml
"""


def write_robots_txt():
    """寫入 robots.txt（禁止 AI 訓練爬蟲、允許搜尋引擎）"""
    (DIST_DIR / "robots.txt").write_text(ROBOTS_TXT_CONTENT, encoding="utf-8")


LIMIT_UP_REPORT_DIR = Path(r"C:/Users/user/Desktop/程式雜/AI股票網頁建構/reports")


def load_limit_up_data():
    """向下相容：回傳最新一天資料（舊 API）。"""
    by_date = load_all_limit_up_data()
    if not by_date:
        return None
    latest = sorted(by_date.keys())[-1]
    return by_date[latest]


_LU_HTML_TAG = re.compile(r'</?span[^>]*>|</?b[^>]*>|</?i[^>]*>|</?em[^>]*>|</?strong[^>]*>')


def _strip_inline_html(s):
    """把 enriched JSON 文字欄位殘留的 HTML 標籤（span/b/em/strong 等）去掉，保留內容文字。"""
    if not isinstance(s, str):
        return s
    return _LU_HTML_TAG.sub('', s).strip()


def _clean_limit_up_payload(payload: dict) -> dict:
    """清洗 payload：groupAnalysis.text、stocks.reason、chipObservation.* 的文字欄位。"""
    for ga in payload.get("groupAnalysis", []) or []:
        if "text" in ga:
            ga["text"] = _strip_inline_html(ga["text"])
        if "name" in ga:
            ga["name"] = _strip_inline_html(ga["name"])
    for s in payload.get("stocks", []) or []:
        for k in ("reason", "name"):
            if k in s:
                s[k] = _strip_inline_html(s[k])
    chip = payload.get("chipObservation") or {}
    for key, items in chip.items():
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict):
                    for k in ("name", "note", "reason"):
                        if k in it:
                            it[k] = _strip_inline_html(it[k])
    return payload


def load_all_limit_up_data() -> dict:
    """讀取所有 `enriched-YYYY-MM-DD.json`，回傳 {date: data}。"""
    if not LIMIT_UP_REPORT_DIR.exists():
        print(f"       ⚠ 漲停報告來源不存在：{LIMIT_UP_REPORT_DIR}")
        return {}
    candidates = sorted(LIMIT_UP_REPORT_DIR.glob("enriched-*.json"))
    if not candidates:
        print(f"       ⚠ 找不到 enriched-*.json：{LIMIT_UP_REPORT_DIR}")
        return {}
    out = {}
    for src in candidates:
        m = re.search(r"enriched-(\d{4}-\d{2}-\d{2})\.json$", src.name)
        if not m:
            continue
        date = m.group(1)
        try:
            payload = json.loads(src.read_text(encoding="utf-8"))
            out[date] = _clean_limit_up_payload(payload)
        except Exception as e:
            print(f"       ⚠ 讀 {src.name} 失敗：{e}")
    print(f"       ✓ 漲停分析：{len(out)} 個交易日（{min(out) if out else '—'} ~ {max(out) if out else '—'}）")
    return out


def write_json_data(heatmap_data, search_data):
    data_dir = DIST_DIR / "data"
    data_dir.mkdir(exist_ok=True)
    for tf, nodes in heatmap_data.items():
        (data_dir / f"heatmap_{tf}.json").write_text(
            json.dumps(nodes, ensure_ascii=False), encoding="utf-8",
        )
    # 搜尋資料輸出 .js 檔（script 載入避免 file:// CORS）
    (data_dir / "search-data.js").write_text(
        "window.SEARCH_DATA = " + json.dumps(search_data, ensure_ascii=False) + ";",
        encoding="utf-8",
    )


# ═══════════════════════════════════════════
#   主流程
# ═══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-finlab", action="store_true", help="使用快取資料")
    parser.add_argument("--open", action="store_true", help="建置完畢自動開啟首頁")
    args = parser.parse_args()

    print("═" * 60)
    print("  族群寶 - 網站建置")
    print("═" * 60)

    DIST_DIR.mkdir(parents=True, exist_ok=True)

    print("\n[0/5] 更新首頁熱門題材（從 Yahoo 熱股 + 鉅亨關鍵字合成）...")
    refresh_trending_topics()

    print("\n[1/5] 載入資料...")
    data = load_data(use_cache=args.skip_finlab)

    print("[2/5] 計算個股指標...")
    stock_metrics = compute_stock_metrics(data)
    print(f"       ✓ {len(stock_metrics)} 檔個股")

    print("[3/5] 計算族群指標 + 相關題材...")
    group_metrics = compute_group_metrics(stock_metrics)
    related = compute_related_topics()
    company_topics = compute_company_topics()
    print(f"       ✓ {len(group_metrics)} 個族群")

    print("[4/5] 產生 JSON 資料（熱力圖 + 搜尋）...")
    extras = load_extras()
    heatmap_data = build_heatmap_data(stock_metrics, data["name_map"])
    search_data = build_search_data(
        stock_metrics,
        data["name_map"],
        data["industry_map"],
        company_topics,
        disposal_map=extras.get("disposal", {}),
        market_map=data.get("market_map", {}),
    )
    write_json_data(heatmap_data, search_data)

    print("[5/5] 渲染 HTML...")
    copy_static()
    write_robots_txt()
    rich = load_company_rich()
    coverage = load_coverage()
    render_all(data, stock_metrics, group_metrics, related, company_topics, rich=rich, extras=extras, coverage=coverage)

    idx = DIST_DIR / "index.html"
    print(f"\n✓ 建置完成！打開：{idx}")
    if args.open:
        webbrowser.open(idx.as_uri())


if __name__ == "__main__":
    main()
