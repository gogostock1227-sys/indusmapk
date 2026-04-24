"""
台股 AI 產業寶 - 網站建置主腳本

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


# ═══════════════════════════════════════════
#   資料層
# ═══════════════════════════════════════════

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
    print("  [FinLab] 下載法人資料...")
    try:
        d["foreign"] = data.get(
            "institutional_investors_trading_summary:外陸資買賣超股數(不含外資自營商)"
        )
    except Exception:
        d["foreign"] = None
    try:
        d["trust"] = data.get(
            "institutional_investors_trading_summary:投信買賣超股數"
        )
    except Exception:
        d["trust"] = None
    print("  [FinLab] 下載公司基本資料...")
    info = data.get("company_basic_info")
    d["name_map"]     = info.set_index("symbol")["公司簡稱"].to_dict()
    d["industry_map"] = info.set_index("symbol")["產業類別"].to_dict() if "產業類別" in info.columns else {}
    d["market_map"]   = info.set_index("symbol")["市場別"].to_dict() if "市場別" in info.columns else {}
    return d


def load_data(use_cache=False) -> dict:
    """載入資料（支援快取）"""
    if use_cache and CACHE_META.exists() and CACHE_FILE.exists():
        print(f"[快取] 從 {CACHE_FILE.name} 讀取")
        meta = json.loads(CACHE_META.read_text(encoding="utf-8"))
        combo = pd.read_parquet(CACHE_FILE)
        d = {}
        for key in ["close", "open", "high", "low", "volume", "amount", "foreign", "trust"]:
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
        return d

    d = _load_finlab_data()

    # 寫快取
    try:
        frames = []
        for key in ["close", "open", "high", "low", "volume", "amount", "foreign", "trust"]:
            df = d.get(key)
            if df is None or df.empty:
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
    }


def compute_company_chart(d: dict, sym: str, days=60) -> dict | None:
    """計算個股 K 棒資料：最近 N 日 OHLCV + MA20 + MA60。沒資料回 None"""
    close = d["close"]
    if sym not in close.columns:
        return None
    try:
        # 取需要的視窗 + 多抓 60 日算 MA60
        c = close[sym].dropna()
        if len(c) < 5:
            return None
        lookback = min(len(c), days + 60)
        end_idx = len(c)
        start_idx = max(0, end_idx - lookback)
        idx = c.index[start_idx:end_idx]
        o = d["open"][sym].reindex(idx)
        h = d["high"][sym].reindex(idx)
        l = d["low"][sym].reindex(idx)
        cc = d["close"][sym].reindex(idx)
        v = d["volume"][sym].reindex(idx)
        ma20 = cc.rolling(20).mean()
        ma60 = cc.rolling(60).mean()

        # 只回顯示區間（後 days 天）
        show_from = max(0, len(idx) - days)
        dates = [t.strftime("%Y-%m-%d") for t in idx[show_from:]]
        ohlc = [
            [
                round(float(o.iloc[i]), 2) if pd.notna(o.iloc[i]) else None,
                round(float(cc.iloc[i]), 2) if pd.notna(cc.iloc[i]) else None,
                round(float(l.iloc[i]), 2) if pd.notna(l.iloc[i]) else None,
                round(float(h.iloc[i]), 2) if pd.notna(h.iloc[i]) else None,
            ]
            for i in range(show_from, len(idx))
        ]
        volumes = [
            round(float(v.iloc[i]) / 1000, 0) if pd.notna(v.iloc[i]) else 0
            for i in range(show_from, len(idx))
        ]
        ma20_arr = [
            round(float(ma20.iloc[i]), 2) if pd.notna(ma20.iloc[i]) else None
            for i in range(show_from, len(idx))
        ]
        ma60_arr = [
            round(float(ma60.iloc[i]), 2) if pd.notna(ma60.iloc[i]) else None
            for i in range(show_from, len(idx))
        ]
        return {
            "dates":   dates,
            "ohlc":    ohlc,      # ECharts candlestick 順序：[open, close, low, high]
            "volume":  volumes,   # 千股
            "ma20":    ma20_arr,
            "ma60":    ma60_arr,
        }
    except Exception:
        return None


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


def build_search_data(stock_metrics: pd.DataFrame, name_map: dict, industry_map: dict, company_topics: dict) -> list:
    """搜尋用資料。[{type, label, sub, href}]
    個股：所有 stock_metrics 中的 symbol 都納入（全上市櫃），有題材顯示題材、沒題材顯示產業類別。"""
    items = []
    for group in CONCEPT_GROUPS:
        meta = get_meta(group)
        items.append({
            "type":  "topic",
            "label": group,
            "sub":   meta["desc"][:50] + ("..." if len(meta["desc"]) > 50 else ""),
            "href":  f"topic/{slugify(group)}.html",
            "keywords": f"{group} {meta['en']} {meta['category']}",
        })
    for sym in stock_metrics.index:
        name_raw = name_map.get(sym)
        name = name_raw if isinstance(name_raw, str) and name_raw.strip() else sym
        topics = company_topics.get(sym, [])
        industry = industry_map.get(sym, "")
        # sub 優先顯示題材，fallback 顯示產業類別
        if topics:
            sub = " / ".join(topics[:3])
        elif industry:
            sub = industry
        else:
            sub = ""
        items.append({
            "type":  "company",
            "label": f"{name} ({sym})",
            "sub":   sub,
            "href":  f"company/{sym}.html",
            "keywords": f"{name} {sym} {industry} {' '.join(topics)}",
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


def build_env():
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["pct"] = pct
    env.filters["fmt_amount"] = fmt_amount
    env.filters["slugify"] = slugify
    env.globals["CATEGORY_COLORS"] = CATEGORY_COLORS
    env.globals["get_meta"] = get_meta
    env.globals["STOCK_HIGHLIGHTS"] = STOCK_HIGHLIGHTS
    return env


def render_all(data, stock_metrics, group_metrics, related, company_topics, rich=None):
    env = build_env()
    rich = rich or {"basic": {}, "business": {}, "revenue": {}, "financials": {}, "dividends": {}, "director": {}}
    name_map = data["name_map"]
    last_date = data["close"].index[-1].strftime("%Y-%m-%d")

    # 共用資料
    base_ctx = {
        "now": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "last_date": last_date,
        "nav_topics": sorted(
            CONCEPT_GROUPS.keys(),
            key=lambda g: -group_metrics.get(g, {}).get("amount_sum_mn", 0)
        )[:8],
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
    index_html = env.get_template("index.html").render(
        **base_ctx,
        total_groups=total_groups,
        total_stocks=total_stocks,
        total_limit_up=total_limit_up,
        total_limit_down=total_limit_down,
        top_flow=top_flow,
        category_aggs=category_aggs,
    )
    (DIST_DIR / "index.html").write_text(index_html, encoding="utf-8")

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

    # 每個題材頁
    topic_dir = DIST_DIR / "topic"
    topic_dir.mkdir(exist_ok=True)
    tpl_topic = env.get_template("topic_detail.html")
    for group, members in CONCEPT_GROUPS.items():
        meta = get_meta(group)
        rows = stock_metrics.loc[stock_metrics.index.intersection(members)].copy()
        rows["display_name"] = [
            (name_map.get(s) if isinstance(name_map.get(s), str) and name_map.get(s).strip() else s)
            for s in rows.index
        ]
        rows_sorted = rows.sort_values("amount_mn", ascending=False)
        topic_series = compute_topic_return_series(data, members, days=125)
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
        )
        (topic_dir / f"{slugify(group)}.html").write_text(html, encoding="utf-8")

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
    company_dir = DIST_DIR / "company"
    company_dir.mkdir(exist_ok=True)
    tpl_company = env.get_template("company.html")
    n_pages = 0
    for sym in stock_metrics.index:
        row = stock_metrics.loc[sym]
        name_raw = name_map.get(sym)
        name = name_raw if isinstance(name_raw, str) and name_raw.strip() else sym
        market = data["market_map"].get(sym, "")
        market_disp = {"sii": "上市", "otc": "上櫃", "rotc": "興櫃"}.get(market, market)
        chart_data = compute_company_chart(data, sym, days=60)
        topics = company_topics.get(sym, [])
        basic = rich["basic"].get(sym)
        business = rich["business"].get(sym)
        revenue = rich["revenue"].get(sym)
        financials = rich["financials"].get(sym)
        dividends = rich["dividends"].get(sym)
        director_pct = rich["director"].get(sym)
        html = tpl_company.render(
            **base_ctx,
            symbol=sym,
            name=name,
            industry=data["industry_map"].get(sym, ""),
            market=market_disp,
            row=row,
            topics=[(t, get_meta(t)) for t in topics],
            chart_json=json.dumps(chart_data, ensure_ascii=False) if chart_data else "null",
            basic=basic,
            business=business,
            revenue=revenue,
            revenue_json=json.dumps(revenue, ensure_ascii=False) if revenue else "[]",
            financials=financials,
            dividends=dividends,
            director_pct=director_pct,
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
    print("  台股 AI 產業寶 - 網站建置")
    print("═" * 60)

    DIST_DIR.mkdir(parents=True, exist_ok=True)

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
    heatmap_data = build_heatmap_data(stock_metrics, data["name_map"])
    search_data = build_search_data(stock_metrics, data["name_map"], data["industry_map"], company_topics)
    write_json_data(heatmap_data, search_data)

    print("[5/5] 渲染 HTML...")
    copy_static()
    rich = load_company_rich()
    render_all(data, stock_metrics, group_metrics, related, company_topics, rich=rich)

    idx = DIST_DIR / "index.html"
    print(f"\n✓ 建置完成！打開：{idx}")
    if args.open:
        webbrowser.open(idx.as_uri())


if __name__ == "__main__":
    main()
