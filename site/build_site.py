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
import time
import webbrowser
import warnings
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

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


def write_text_retry(path: Path, text: str, encoding: str = "utf-8", retries: int = 6) -> None:
    """Windows 大量重建時偶爾會遇到短暫寫檔失敗，重試避免整個 build 中斷。"""
    last_err: OSError | None = None
    for attempt in range(retries):
        try:
            path.write_text(text, encoding=encoding)
            return
        except OSError as exc:
            last_err = exc
            if attempt == retries - 1:
                break
            time.sleep(0.35 * (attempt + 1))
    raise last_err
CACHE_META = SITE_DIR / ".cache_meta.json"

from concept_groups import CONCEPT_GROUPS
from industry_meta import INDUSTRY_META, CATEGORY_COLORS, CONCEPT_STOCK_TOPICS, get_meta
try:
    from stock_highlights import STOCK_HIGHLIGHTS
except ImportError:
    STOCK_HIGHLIGHTS = {}

RICH_PKL = SITE_DIR / ".company_rich.pkl"
EXTRAS_JSON = SITE_DIR / ".cache_extras.json"
TRENDING_JSON = SITE_DIR / ".cache_trending.json"
FUTURES_JSON = SITE_DIR / ".cache_futures.json"
STOCK_FUTURES_RANKING_JSON = SITE_DIR / ".cache_stock_futures_ranking.json"
INDEX_MARGINING_URL = "https://www.taifex.com.tw/cht/5/indexMarging"
DAILY_CHIP_JSON = SITE_DIR / ".cache_daily_chip_report.json"
RS_HISTORY = SITE_DIR / ".cache_rs_history.parquet"
RS_HISTORY_QUARTER = SITE_DIR / ".cache_rs_history_quarter.parquet"
TAIEX_CACHE = SITE_DIR / ".cache_taiex.parquet"  # 舊：只存加權指數，保留以利向後兼容
INDICES_CACHE = SITE_DIR / ".cache_market_indices.parquet"  # 新：上市加權 + 櫃買
NAME_OVERRIDES_JSON = SITE_DIR / "stock_name_overrides.json"
MEMOS_JSON = SITE_DIR / "memos.json"
COVERAGE_DIR = ROOT_DIR / "My-TW-Coverage" / "Pilot_Reports"
TAIPEI_TZ = timezone(timedelta(hours=8))

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

# 今日強弱題材只比較成交值超過 1 億的族群，避免低流動性題材扭曲焦點榜。
FOCUS_TOPIC_MIN_AMOUNT_MN = 100.0
FOCUS_TOPIC_MIN_AMOUNT_LABEL = "1 億"


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


def refresh_futures_list(max_age_days: float = 1.0) -> None:
    """跑 fetch_futures_list.py 抓期交所個股期貨清單。

    cache 在 max_age_days 內不重抓（期交所清單變動慢，週更即可）。
    任何異常都不中斷 build。
    """
    import subprocess, time
    if FUTURES_JSON.exists():
        age = (time.time() - FUTURES_JSON.stat().st_mtime) / 86400
        if age < max_age_days:
            print(f"[futures] cache {age:.1f} 日內，跳過抓取（{FUTURES_JSON.name}）")
            return
    script = SITE_DIR / "fetch_futures_list.py"
    if not script.exists():
        print(f"[futures] 跳過：找不到 {script.name}")
        return
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            timeout=60,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if proc.returncode == 0:
            tail = [l for l in proc.stdout.splitlines() if l.strip()][-6:]
            for l in tail:
                print(f"  {l}")
        else:
            print(f"[futures] exit {proc.returncode}（沿用前次 cache）")
            if proc.stderr:
                print(proc.stderr[-300:])
    except subprocess.TimeoutExpired:
        print("[futures] 抓取逾時 60s，沿用前次 cache")
    except Exception as e:
        print(f"[futures] 抓取例外：{e}（沿用前次 cache）")


def refresh_stock_futures_ranking(max_age_hours: float = 6.0) -> None:
    """跑 fetch_stock_futures_ranking.py，建立股期曝險頁使用的排行資料。

    任何異常都不中斷 build；若沒有 cache，頁面會用站內股價資料建立降級樣板。
    """
    import subprocess, time
    if STOCK_FUTURES_RANKING_JSON.exists():
        age_hours = (time.time() - STOCK_FUTURES_RANKING_JSON.stat().st_mtime) / 3600
        if age_hours < max_age_hours:
            print(f"[stock-futures] cache {age_hours:.1f} 小時內，跳過抓取（{STOCK_FUTURES_RANKING_JSON.name}）")
            return
    script = SITE_DIR / "fetch_stock_futures_ranking.py"
    if not script.exists():
        print(f"[stock-futures] 跳過：找不到 {script.name}")
        return
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            timeout=120,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        tail = [l for l in proc.stdout.splitlines() if l.strip()][-8:]
        for l in tail:
            print(f"  {l}")
        if proc.returncode != 0:
            print(f"[stock-futures] exit {proc.returncode}（沿用前次 cache / 降級資料）")
            if proc.stderr:
                print(proc.stderr[-400:])
    except subprocess.TimeoutExpired:
        print("[stock-futures] 抓取逾時 120s，沿用前次 cache / 降級資料")
    except Exception as e:
        print(f"[stock-futures] 抓取例外：{e}（沿用前次 cache / 降級資料）")


def refresh_stock_futures_finlab_history(max_age_hours: float = 22.0) -> None:
    """跑 fetch_stock_futures_history.py，從 FinLab 拉股期「收盤價 + OI」近 1 年。

    用途：
      1. ranking 的 OI 增減 fallback（解決本地 80 天 cache 空白問題）
      2. 前端「以歷史價修正全部」按鈕的修正源
    任何異常都不中斷 build。
    """
    import subprocess
    script = SITE_DIR / "fetch_stock_futures_history.py"
    if not script.exists():
        return
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            timeout=300,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        tail = [l for l in proc.stdout.splitlines() if l.strip()][-4:]
        for l in tail:
            print(f"  {l}")
        if proc.returncode != 0 and proc.stderr:
            print(proc.stderr[-400:])
    except subprocess.TimeoutExpired:
        print("[stock-futures-history] 抓取逾時 300s（不致命，沿用前次 cache）")
    except Exception as e:
        print(f"[stock-futures-history] 例外：{e}（不致命）")


def today_taipei() -> date:
    return datetime.now(TAIPEI_TZ).date()


def normalize_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    candidates = [text[:10], text[:10].replace("/", "-"), text[:10].replace("-", "/"), text[:8]]
    for candidate in candidates:
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except Exception:
                continue
    try:
        return pd.Timestamp(text).date()
    except Exception:
        return None


def _market_source(name: str, url: str, status: str, note: str = "") -> dict:
    return {"name": name, "url": url, "status": status, "note": note}


def _twse_holiday_from_rows(rows, target_date: date) -> dict | None:
    target_iso = target_date.isoformat()
    for row in rows or []:
        if isinstance(row, dict):
            values = list(row.values())
            date_text = str(row.get("日期") or row.get("date") or row.get("Date") or (values[0] if values else "")).strip()
            name = str(row.get("名稱") or row.get("name") or row.get("Name") or (values[1] if len(values) > 1 else "")).strip()
            description = str(row.get("說明") or row.get("description") or row.get("Description") or (values[2] if len(values) > 2 else "")).strip()
        else:
            values = list(row) if isinstance(row, (list, tuple)) else [row]
            date_text = str(values[0]).strip() if values else ""
            name = str(values[1]).strip() if len(values) > 1 else ""
            description = str(values[2]).strip() if len(values) > 2 else ""
        if target_iso in date_text:
            return {"name": name, "description": description}
    return None


def fetch_twse_holiday_reason(target_date: date) -> tuple[dict | None, list[dict]]:
    """查 TWSE 市場開休市表；失敗只回傳來源狀態，不阻斷 build。"""
    import requests
    from io import StringIO

    base_url = "https://www.twse.com.tw/holidaySchedule/holidaySchedule"
    params = {"queryYear": str(target_date.year - 1911), "response": "json"}
    checked: list[dict] = []

    try:
        r = requests.get(base_url, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=8, verify=False)
        r.raise_for_status()
        payload = r.json()
        reason = _twse_holiday_from_rows(payload.get("data") or payload.get("tables") or [], target_date)
        checked.append(_market_source("TWSE holidaySchedule", r.url, "ok", "json"))
        if reason:
            return reason, checked
    except Exception as exc:
        checked.append(_market_source("TWSE holidaySchedule", base_url, "error", str(exc)[:160]))

    html_params = {"queryYear": str(target_date.year - 1911), "response": "html"}
    try:
        r = requests.get(base_url, params=html_params, headers={"User-Agent": "Mozilla/5.0"}, timeout=8, verify=False)
        r.raise_for_status()
        rows = []
        for df in pd.read_html(StringIO(r.text)):
            rows.extend(df.astype(str).values.tolist())
        reason = _twse_holiday_from_rows(rows, target_date)
        checked.append(_market_source("TWSE holidaySchedule HTML", r.url, "ok", "html"))
        if reason:
            return reason, checked
    except Exception as exc:
        checked.append(_market_source("TWSE holidaySchedule HTML", base_url, "error", str(exc)[:160]))

    return None, checked


def fetch_dgpa_weather_closure(target_date: date) -> tuple[dict | None, list[dict]]:
    """查 DGPA 天然災害停班停課；只把台北市全日或上午停班視為全日停市。"""
    import requests

    url = "https://www.dgpa.gov.tw/typh/daily/nds.html"
    checked: list[dict] = []
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        r.raise_for_status()
        text = r.text
        checked.append(_market_source("DGPA typhoon daily", url, "ok"))
    except Exception as exc:
        return None, [_market_source("DGPA typhoon daily", url, "error", str(exc)[:160])]

    compact = re.sub(r"\s+", "", text.replace("台北市", "臺北市"))
    if "無停班停課訊息" in compact:
        return None, checked
    pos = compact.find("臺北市")
    if pos < 0:
        return None, checked
    window = compact[pos: pos + 240]
    has_closure = "停止上班" in window
    afternoon_only = "下午停止上班" in window and "上午停止上班" not in window and "全日停止上班" not in window
    if has_closure and not afternoon_only:
        return {"name": "天然災害停市", "description": "臺北市停止上班，集中交易市場全日休市"}, checked
    return None, checked


def describe_market_status(latest_trade_date) -> dict:
    today = today_taipei()
    latest = normalize_date(latest_trade_date)
    status = {
        "date": today.isoformat(),
        "latest_trade_date": latest.isoformat() if latest else "",
        "is_trading_day": bool(latest and today <= latest),
        "reason": "trading_day",
        "reason_label": "今日已有交易資料",
        "checked_sources": [],
    }
    if status["is_trading_day"]:
        return status

    if today.weekday() >= 5:
        status.update({"reason": "weekend", "reason_label": "週末休市"})
        return status

    reason, checked = fetch_twse_holiday_reason(today)
    status["checked_sources"].extend(checked)
    if reason:
        label = reason.get("name") or "預定休市"
        desc = reason.get("description") or ""
        status.update({
            "reason": "scheduled_holiday",
            "reason_label": f"{label}：{desc}" if desc else label,
        })
        return status

    weather, checked = fetch_dgpa_weather_closure(today)
    status["checked_sources"].extend(checked)
    if weather:
        status.update({
            "reason": "weather_closure",
            "reason_label": weather.get("description") or weather.get("name") or "天然災害停市",
        })
        return status

    status.update({
        "reason": "no_new_close",
        "reason_label": "尚未取得今日收盤資料，保守沿用前次籌碼報告",
    })
    return status


def refresh_daily_chip_report(latest_trade_date=None, max_age_minutes: float = 30.0) -> None:
    """跑 fetch_daily_chip_report.py 更新首頁每日籌碼報告。

    官方來源偶爾會延遲或短暫失敗，因此採 subprocess 隔離；失敗時首頁沿用前次 cache。
    """
    import subprocess, time
    needs_catchup = daily_chip_cache_needs_refresh(latest_trade_date) if latest_trade_date is not None else False
    if latest_trade_date is not None:
        market_status = describe_market_status(latest_trade_date)
        if not market_status["is_trading_day"] and not needs_catchup:
            print(
                "[daily-chip] skip: "
                f"{market_status['date']} 非交易日或尚無收盤資料；"
                f"latest={market_status['latest_trade_date']}；"
                f"reason={market_status['reason']} ({market_status['reason_label']})"
            )
            return
        if not market_status["is_trading_day"] and needs_catchup:
            print(
                "[daily-chip] non-trading day but cache is stale; "
                f"try catch-up for latest={market_status['latest_trade_date']} "
                f"({market_status['reason_label']})"
            )
    if DAILY_CHIP_JSON.exists():
        age_minutes = (time.time() - DAILY_CHIP_JSON.stat().st_mtime) / 60
        if age_minutes < max_age_minutes and not needs_catchup:
            print(f"[daily-chip] cache {age_minutes:.0f} 分鐘內，跳過抓取（{DAILY_CHIP_JSON.name}）")
            return
    script = SITE_DIR / "fetch_daily_chip_report.py"
    if not script.exists():
        print(f"[daily-chip] 跳過：找不到 {script.name}")
        return
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            timeout=120,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if proc.returncode == 0:
            tail = [l for l in proc.stdout.splitlines() if l.strip()][-8:]
            for l in tail:
                print(f"  {l}")
        else:
            print(f"[daily-chip] exit {proc.returncode}（沿用前次 cache）")
            if proc.stderr:
                print(proc.stderr[-500:])
    except subprocess.TimeoutExpired:
        print("[daily-chip] 抓取逾時 120s，沿用前次 cache")
    except Exception as e:
        print(f"[daily-chip] 抓取例外：{e}（沿用前次 cache）")


def load_daily_chip_report() -> dict | None:
    """讀取每日籌碼報告 cache，失敗時回 None，首頁會自動隱藏區塊。"""
    if not DAILY_CHIP_JSON.exists():
        return None
    try:
        report = json.loads(DAILY_CHIP_JSON.read_text(encoding="utf-8"))
        try:
            from fetch_daily_chip_report import normalize_report_for_template

            report = normalize_report_for_template(report)
        except Exception as normalize_error:
            print(f"[daily-chip] cache schema normalize failed: {normalize_error}")
        return report
    except Exception as e:
        print(f"[daily-chip] 讀取 cache 失敗：{e}")
        return None


def _daily_chip_date_key(value) -> date | None:
    if not value:
        return None
    return normalize_date(str(value).replace("/", "-"))


def _daily_chip_section_date(report: dict, section: str) -> date | None:
    part = report.get(section)
    return _daily_chip_date_key(part.get("date")) if isinstance(part, dict) else None


def daily_chip_cache_needs_refresh(latest_trade_date) -> bool:
    latest = normalize_date(latest_trade_date)
    if not latest:
        return False
    report = load_daily_chip_report()
    if not report:
        return True
    if _daily_chip_date_key(report.get("report_date")) != latest:
        return True
    for section in ("spot", "margin", "futures", "options", "vix"):
        section_date = _daily_chip_section_date(report, section)
        if section_date and section_date < latest:
            return True
        if not section_date and not report.get(section):
            return True
    return False


def _fetch_tpex_official_recent() -> pd.Series:
    """從 TPEx 官方 OpenAPI 抓最近約 17 日櫃買指數收盤值（含當日）。

    端點：https://www.tpex.org.tw/openapi/v1/tpex_index
    用途：FinLab `stock_index_price:收盤指數` 常延遲 1-3 日，本函數提供即時補丁。
    回傳 pd.Series (index=日期, value=收盤值)；失敗時回空 Series。
    """
    import requests
    url = "https://www.tpex.org.tw/openapi/v1/tpex_index"
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return pd.Series(dtype=float, name="tpex")
        dates  = [pd.Timestamp(row["Date"]) for row in rows]   # "20260427" pandas 自動解析
        closes = [float(row["Close"]) for row in rows]
        s = pd.Series(closes, index=pd.DatetimeIndex(dates), name="tpex").sort_index()
        return s
    except Exception as e:
        print(f"[indices] TPEx 官方備援抓取失敗：{e}")
        return pd.Series(dtype=float, name="tpex")


def load_market_indices(use_cache: bool = True) -> dict:
    """載入台股兩大盤指數收盤價：上市加權 + 櫃買。

    來源：FinLab 'stock_index_price:收盤指數'
      - taiex: 上市加權股價指數（≈ ^TWII）
      - tpex:  櫃買指數
    回傳 {'taiex': pd.Series, 'tpex': pd.Series}。
    """
    if use_cache and INDICES_CACHE.exists():
        try:
            df = pd.read_parquet(INDICES_CACHE)
            df.index = pd.to_datetime(df.index)
            out = {col: df[col].dropna() for col in df.columns}
            print(f"[indices] 從 cache 讀取（{len(df)} 個交易日，{list(out.keys())}）")
            return out
        except Exception as e:
            print(f"[indices] cache 讀取失敗：{e}，改抓 FinLab")
    out: dict = {}
    try:
        from finlab import data as _fl_data
        # 加權指數：用 world_index 的 ^TWII（即時更新到當日，跟 close 同步）
        try:
            wi = _fl_data.get("world_index:close")
            if "^TWII" in wi.columns:
                s = wi["^TWII"].dropna()
                s.name = "taiex"
                out["taiex"] = s
                print(f"[indices] 加權指數（^TWII，即時源）：{len(s)} 日，最新 {s.index.max().date()}")
        except Exception as e:
            print(f"[indices] world_index:^TWII 抓取失敗：{e}")
        # 櫃買指數：用 stock_index_price（每日批次更新，可能延遲 1-3 日）
        try:
            si = _fl_data.get("stock_index_price:收盤指數")
            if "上櫃櫃買指數:指數" in si.columns:
                s = si["上櫃櫃買指數:指數"].dropna()
                s.name = "tpex"
                out["tpex"] = s
                print(f"[indices] 櫃買指數（stock_index_price，批次源）：{len(s)} 日，最新 {s.index.max().date()}")
        except Exception as e:
            print(f"[indices] stock_index_price:櫃買指數 抓取失敗：{e}")
        # === 網路備援：TPEx 官方 OpenAPI 覆蓋櫃買最近約 17 日（即時源）===
        if "tpex" in out and not out["tpex"].empty:
            official = _fetch_tpex_official_recent()
            if not official.empty:
                finlab_last = out["tpex"].index.max().date()
                merged = out["tpex"].copy()
                merged.update(official)  # 同日 finlab 有則用官方覆蓋
                # 官方有但 finlab 沒的日期（最新延遲日）也補進來
                new_dates = official.index.difference(merged.index)
                if len(new_dates) > 0:
                    merged = pd.concat([merged, official.loc[new_dates]]).sort_index()
                out["tpex"] = merged
                new_last = merged.index.max().date()
                print(f"[indices] 櫃買備援：TPEx 官方覆蓋 {len(official)} 日；finlab 原最新 {finlab_last} → 補丁後 {new_last}")
        if out:
            try:
                pd.concat(list(out.values()), axis=1).to_parquet(INDICES_CACHE)
                print(f"[indices] 寫入 cache：{ {k: len(v) for k,v in out.items()} }")
            except Exception as e:
                print(f"[indices] cache 寫入失敗：{e}")
        else:
            print("[indices] FinLab 兩個來源都失敗")
        return out
    except Exception as e:
        print(f"[indices] FinLab 抓取失敗：{e}")
        if INDICES_CACHE.exists():
            df = pd.read_parquet(INDICES_CACHE)
            return {col: df[col].dropna() for col in df.columns}
        return {}


def load_taiex(use_cache: bool = True) -> pd.Series:
    """向後兼容：只回傳加權指數 Series。新呼叫請改用 load_market_indices()。"""
    indices = load_market_indices(use_cache=use_cache)
    return indices.get("taiex", pd.Series(dtype=float, name="taiex"))


def load_futures_flags() -> dict:
    """讀 .cache_futures.json，回傳 {symbol: {'stock':True, 'mini':True, 'etf':True, 'mini_etf':True}}。
    四個 key 任一為 True 即代表該證券有對應的期貨商品。
    """
    if not FUTURES_JSON.exists():
        return {}
    try:
        raw = json.loads(FUTURES_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[futures] 讀取 cache 失敗：{e}")
        return {}
    flags: dict[str, dict] = {}
    for sym in raw.get("stock_futures", []):
        flags.setdefault(sym, {})["stock"] = True
    for sym in raw.get("mini_stock_futures", []):
        flags.setdefault(sym, {})["mini"] = True
    for sym in raw.get("etf_futures", []):
        flags.setdefault(sym, {})["etf"] = True
    for sym in raw.get("mini_etf_futures", []):
        flags.setdefault(sym, {})["mini_etf"] = True
    print(f"[futures] 載入 {len(flags)} 檔有期貨之證券（as_of={raw.get('as_of','?')}）")
    return flags


def _safe_num(value, default=None):
    """把 JSON / pandas 裡的數字轉成 float；空值回傳 default。"""
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("%", "")
        if not text or text in {"-", "—", "nan", "NaN"}:
            return default
        value = text
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value, default=None):
    num = _safe_num(value, default=None)
    if num is None:
        return default
    return int(round(num))


def _stock_future_category_rows(sym: str, flags: dict, name: str, spot_price: float | None) -> list[dict]:
    """官方排行 cache 不存在時，依既有股期清單建立可操作的降級列。"""
    rows = []
    specs = [
        ("stock", "個股期貨", 2000, flags.get("stock"), f"{name}期貨"),
        ("mini_stock", "小型個股期貨", 100, flags.get("mini"), f"小型{name}期貨"),
        ("etf", "ETF期貨", 10000, flags.get("etf"), f"{name}ETF期貨"),
        ("mini_etf", "小型ETF期貨", 1000, flags.get("mini_etf"), f"小型{name}ETF期貨"),
    ]
    for category, label, multiplier, enabled, product_name in specs:
        if not enabled:
            continue
        price = spot_price
        margin_rate = 0.135
        initial_margin = round(price * multiplier * margin_rate) if price is not None else None
        rows.append({
            "product_id": f"{sym}-{category}",
            "product_code": "",
            "product_name": product_name,
            "category": category,
            "type_label": label,
            "underlying_symbol": sym,
            "underlying_name": name,
            "underlying_short_name": name,
            "contract_month": "",
            "future_price": price,
            "change": None,
            "change_pct": None,
            "volume": None,
            "avg_volume_20d": None,
            "avg_volume_days": 0,
            "amplitude": None,
            "open_interest": None,
            "open_interest_change": None,
            "spot_price": spot_price,
            "basis": 0 if spot_price is not None and price is not None else None,
            "contract_multiplier": multiplier,
            "initial_margin": initial_margin,
            "initial_margin_rate": margin_rate,
            "notional": price * multiplier if price is not None else None,
            "leverage": (price * multiplier / initial_margin) if price is not None and initial_margin else None,
            "data_time": "",
            "source_status": "fallback",
            "search_key": f"{sym} {name} {product_name}".lower(),
        })
    return rows


INDEX_FUTURE_SPECS = {
    "TX": {
        "product_name": "臺股期貨",
        "contract_multiplier": 200,
        "aliases": "台指 臺指 台股指數期貨 臺股指數期貨 加權指數",
    },
    "MTX": {
        "product_name": "小型臺指期貨",
        "contract_multiplier": 50,
        "aliases": "小台 小臺 小型台指 小型臺指 台指 臺指 加權指數",
    },
    "TMF": {
        "product_name": "微型臺指期貨",
        "contract_multiplier": 10,
        "aliases": "微台 微臺 微型台指 微型臺指 台指 臺指 加權指數",
    },
}


def load_stock_futures_page_data(
    data: dict,
    stock_metrics: pd.DataFrame,
    futures_flags: dict,
    company_topics: dict | None = None,
    market_indices: dict | None = None,
) -> dict:
    """載入股期排行 cache，並補上現貨價、名目金額、槓桿等頁面欄位。"""
    raw = {}
    if STOCK_FUTURES_RANKING_JSON.exists():
        try:
            raw = json.loads(STOCK_FUTURES_RANKING_JSON.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[stock-futures] 讀取 cache 失敗：{e}")
            raw = {}

    name_map = data.get("name_map", {})
    close_df = data.get("close")

    def spot_for(sym: str) -> float | None:
        if sym in stock_metrics.index and "close" in stock_metrics.columns:
            val = _safe_num(stock_metrics.at[sym, "close"])
            if val is not None:
                return val
        if close_df is not None and sym in close_df.columns:
            s = close_df[sym].dropna()
            if len(s):
                return _safe_num(s.iloc[-1])
        return None

    def latest_market_index(name: str) -> tuple[str, float | None]:
        series = (market_indices or {}).get(name)
        if series is None or len(series) == 0:
            return "", None
        try:
            s = series.dropna()
            if len(s) == 0:
                return "", None
            idx = s.index[-1]
            dt = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
            return dt, _safe_num(s.iloc[-1])
        except Exception:
            return "", None

    def make_index_future_rows() -> list[dict]:
        index_rows = raw.get("index_futures", []) if isinstance(raw.get("index_futures"), list) else []
        index_by_code = {
            str(item.get("product_code") or item.get("product_id") or "").strip().upper(): item
            for item in index_rows
            if item
        }
        margin_by_code = raw.get("index_margins", {}) if isinstance(raw.get("index_margins"), dict) else {}
        taiex_date, taiex_value = latest_market_index("taiex")
        out = []
        for code, spec in INDEX_FUTURE_SPECS.items():
            item = index_by_code.get(code, {})
            margin_info = margin_by_code.get(code, {}) if isinstance(margin_by_code.get(code), dict) else {}
            multiplier = spec["contract_multiplier"]
            future_price = _safe_num(item.get("future_price") or item.get("last_price") or item.get("settlement_price"))
            price_source = item.get("source_status") or "official"
            if future_price is None:
                future_price = taiex_value
                price_source = "fallback_index"
            spot_price = taiex_value
            initial_margin = _safe_num(item.get("initial_margin") or margin_info.get("initial_margin"))
            notional = future_price * multiplier if future_price is not None else None
            leverage = notional / initial_margin if notional is not None and initial_margin else None
            change = _safe_num(item.get("change"))
            basis = (future_price - spot_price) if future_price is not None and spot_price is not None else None
            out.append({
                "product_id": code,
                "product_code": code,
                "product_name": spec["product_name"],
                "category": "index_future",
                "type_label": "指數期貨",
                "underlying_symbol": "TAIEX",
                "underlying_name": "臺灣加權股價指數",
                "underlying_short_name": "加權指數",
                "contract_month": item.get("contract_month") or "",
                "future_price": future_price,
                "change": change,
                "change_pct": _safe_num(item.get("change_pct")),
                "volume": _safe_int(item.get("volume")),
                "avg_volume_20d": _safe_int(item.get("avg_volume_20d")),
                "avg_volume_days": _safe_int(item.get("avg_volume_days"), 0) or 0,
                "amplitude": None,
                "open_interest": _safe_int(item.get("open_interest")),
                "open_interest_change": _safe_int(item.get("open_interest_change")),
                "spot_price": spot_price,
                "basis": basis,
                "contract_multiplier": multiplier,
                "initial_margin": initial_margin,
                "initial_margin_rate": None,
                "notional": notional,
                "leverage": leverage,
                "data_time": item.get("trade_date") or taiex_date or raw.get("as_of") or "",
                "source_status": price_source,
                "search_key": f"{code} {spec['product_name']} TAIEX 加權指數 {spec['aliases']} 指數期貨".lower(),
            })
        return out

    rows = []
    raw_rows = raw.get("rows", []) if isinstance(raw.get("rows"), list) else []
    for item in raw_rows:
        sym = str(item.get("underlying_symbol") or "").strip().upper()
        if not sym:
            continue
        name = name_map.get(sym) if isinstance(name_map.get(sym), str) and name_map.get(sym).strip() else item.get("underlying_short_name") or sym
        future_price = _safe_num(item.get("future_price") or item.get("last_price") or item.get("settlement_price"))
        spot_price = spot_for(sym)
        multiplier = _safe_int(item.get("contract_multiplier"), 0) or 0
        initial_margin = _safe_num(item.get("initial_margin"))
        margin_rate = _safe_num(item.get("initial_margin_rate"))
        if initial_margin is None and margin_rate is not None and future_price is not None and multiplier:
            initial_margin = round(future_price * multiplier * margin_rate)
        notional = future_price * multiplier if future_price is not None and multiplier else None
        leverage = notional / initial_margin if notional is not None and initial_margin else None
        change = _safe_num(item.get("change"))
        prev_price = (future_price - change) if future_price is not None and change is not None else None
        high_price = _safe_num(item.get("high_price"))
        low_price = _safe_num(item.get("low_price"))
        amplitude = None
        if high_price is not None and low_price is not None and prev_price not in (None, 0):
            amplitude = (high_price - low_price) / prev_price
        basis = (future_price - spot_price) if future_price is not None and spot_price is not None else None
        product_name = item.get("product_name") or f"{name}期貨"
        product_code = str(item.get("product_code") or "").strip().upper()
        category = item.get("category") or ""
        type_label = item.get("type_label") or category or "股票期貨"
        row = {
            "product_id": product_code or f"{sym}-{category}-{len(rows)}",
            "product_code": product_code,
            "product_name": product_name,
            "category": category,
            "type_label": type_label,
            "underlying_symbol": sym,
            "underlying_name": item.get("underlying_name") or name,
            "underlying_short_name": name,
            "contract_month": item.get("contract_month") or "",
            "future_price": future_price,
            "change": change,
            "change_pct": _safe_num(item.get("change_pct")),
            "volume": _safe_int(item.get("volume")),
            "avg_volume_20d": _safe_int(item.get("avg_volume_20d")),
            "avg_volume_days": _safe_int(item.get("avg_volume_days"), 0) or 0,
            "amplitude": amplitude,
            "open_interest": _safe_int(item.get("open_interest")),
            "open_interest_change": _safe_int(item.get("open_interest_change")),
            "spot_price": spot_price,
            "basis": basis,
            "contract_multiplier": multiplier,
            "initial_margin": initial_margin,
            "initial_margin_rate": margin_rate,
            "notional": notional,
            "leverage": leverage,
            "data_time": item.get("trade_date") or raw.get("as_of") or "",
            "source_status": item.get("source_status") or "official",
            "search_key": f"{product_code} {product_name} {sym} {name} {type_label}".lower(),
        }
        rows.append(row)

    if not rows:
        for sym, flags in sorted(futures_flags.items()):
            spot = spot_for(sym)
            nm = name_map.get(sym) if isinstance(name_map.get(sym), str) and name_map.get(sym).strip() else sym
            rows.extend(_stock_future_category_rows(sym, flags, nm, spot))

    rows.sort(key=lambda r: (-(r.get("volume") or 0), r.get("product_name") or ""))
    selectable_products = rows + make_index_future_rows()
    status = "official" if raw.get("rows") and rows else "fallback"
    symbols = sorted({str(r.get("underlying_symbol") or "").strip().upper() for r in rows if r.get("underlying_symbol")})
    topic_payload = {
        sym: list((company_topics or {}).get(sym, []))[:8]
        for sym in symbols
        if (company_topics or {}).get(sym)
    }

    def _series_tail_payload(series, limit: int = 260) -> list[dict]:
        if series is None or len(series) == 0:
            return []
        try:
            s = series.dropna().tail(limit)
        except Exception:
            return []
        out = []
        for idx, val in s.items():
            try:
                dt = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
                out.append({"date": dt, "value": float(val)})
            except Exception:
                continue
        return out

    def _market_payload(indices: dict | None) -> dict:
        indices = indices or {}
        taiex = _series_tail_payload(indices.get("taiex"))
        tpex = _series_tail_payload(indices.get("tpex"))
        by_date: dict[str, dict] = {}
        for item in taiex:
            by_date.setdefault(item["date"], {"date": item["date"]})["taiex"] = item["value"]
        for item in tpex:
            by_date.setdefault(item["date"], {"date": item["date"]})["tpex"] = item["value"]

        def _current(items):
            if not items:
                return {"date": "", "value": None}
            last = items[-1]
            return {"date": last["date"], "value": last["value"]}

        return {
            "current": {
                "taiex": _current(taiex),
                "tpex": _current(tpex),
            },
            "history": [by_date[d] for d in sorted(by_date.keys())],
        }

    source_payload = {
        "daily_market": "https://www.taifex.com.tw/data_gov/taifex_open_data.asp?data_name=DailyMarketReportFut",
        "stock_lists": "https://www.taifex.com.tw/cht/2/stockLists",
        "margining": "https://www.taifex.com.tw/cht/5/stockMarginingDetail",
        "index_margining": INDEX_MARGINING_URL,
    }
    if isinstance(raw.get("source"), dict):
        source_payload.update(raw.get("source") or {})
    source_payload["index_margining"] = source_payload.get("index_margining") or INDEX_MARGINING_URL

    # FinLab history（只塞 close 給前端用，OI 已被 ranking 預處理進 row.open_interest_change）
    futures_history_payload: dict[str, dict] = {}
    finlab_history_path = SITE_DIR / ".cache_stock_futures_finlab_history.json"
    if finlab_history_path.exists():
        try:
            finlab_raw = json.loads(finlab_history_path.read_text(encoding="utf-8"))
            if isinstance(finlab_raw, dict):
                futures_history_payload = {
                    k: (v.get("close") or {})
                    for k, v in finlab_raw.items()
                    if isinstance(v, dict)
                }
        except Exception as e:
            print(f"[stock-futures] 讀取 FinLab history 失敗：{e}")

    return {
        "as_of": raw.get("as_of") or data["close"].index[-1].strftime("%Y-%m-%d"),
        "generated_at": raw.get("generated_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": status,
        "source": source_payload,
        "rows": rows,
        "selectable_products": selectable_products,
        "company_topics": topic_payload,
        "concept_topics": sorted(CONCEPT_STOCK_TOPICS),
        "market_indices": _market_payload(market_indices),
        "futures_history": futures_history_payload,
        "counts": {
            "rows": len(rows),
            "selectable_products": len(selectable_products),
            "official_rows": len(raw.get("rows", [])) if isinstance(raw.get("rows"), list) else 0,
            "futures_history_products": len(futures_history_payload),
        },
    }


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


def load_memos() -> list[dict]:
    """讀取使用者手動維護的個股 Memo（site/memos.json）作為 fallback 備份。
    主要資料源為前端 localStorage；此處僅供 localStorage 清空時作保底。
    """
    if not MEMOS_JSON.exists():
        return []
    try:
        raw = json.loads(MEMOS_JSON.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []
        valid = [
            m for m in raw
            if isinstance(m, dict)
            and m.get("stock_id") and m.get("stock_name")
            and m.get("date") and m.get("content")
        ]
        valid.sort(key=lambda m: m.get("date", ""), reverse=True)
        print(f"[memos] 載入 {len(valid)} 筆備份資料")
        return valid
    except Exception:
        return []


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

_DISPLAY_SOURCE_REPLACEMENTS = (
    ("與 [[Yahoo 股市]] ", ""),
    ("與[[Yahoo 股市]] ", ""),
    ("／[[Yahoo 股市]]", ""),
    ("/[[Yahoo 股市]]", ""),
    ("、[[Yahoo 股市]]", ""),
    ("[[Yahoo 股市]]／", ""),
    ("[[Yahoo 股市]]/", ""),
    ("[[Yahoo 股市]]、", ""),
    ("[[Yahoo 股市]]", ""),
    ("Yahoo 股市", ""),
    ("Yahoo股市", ""),
)


def strip_hidden_source_names(text: str) -> str:
    """移除不希望在網站顯示的來源名稱。"""
    if not isinstance(text, str) or "Yahoo" not in text:
        return text
    for old, new in _DISPLAY_SOURCE_REPLACEMENTS:
        text = text.replace(old, new)
    return text


def _coverage_inline(text: str) -> str:
    """Convert inline MD (wikilinks + bold) to HTML. Input may already contain raw chars."""
    text = strip_hidden_source_names(text)
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


def load_stock_profiles() -> dict:
    """載入 concept_taxonomy/stock_profiles.json（三維畫像，用於個股頁的供應鏈位階徽章）。

    Schema 詳見 concept_taxonomy/validator/schema.py::StockProfile。
    缺檔 fallback {} —— 不影響網站建置。
    """
    path = ROOT_DIR / "concept_taxonomy" / "stock_profiles.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [warn] load_stock_profiles 失敗：{e}")
        return {}


# 27 位階 enum → 中文標籤（對應 concept_taxonomy/validator/schema.py::SUPPLY_CHAIN_POSITIONS）
SUPPLY_CHAIN_POSITION_LABELS = {
    "IP": "IP / 矽智財", "IC_DESIGN": "IC 設計 / Fabless",
    "ASIC_SVC": "ASIC 設計服務", "FOUNDRY": "晶圓代工",
    "IDM_DRAM": "DRAM 製造 / IDM", "IDM_NAND": "NAND Flash 製造",
    "OSAT_ADV": "先進封裝 (OSAT)", "OSAT_TRAD": "一般封測",
    "TEST_INTF": "測試介面 / 探針卡", "TEST_SVC": "測試代工",
    "EQUIP": "半導體設備", "MAT_WAFER": "矽晶圓 / 上游材料",
    "MAT_CHEM": "半導體化學品 / 特用氣體", "SUBSTRATE": "載板 / 基板",
    "CONNECTOR": "連接器 / Socket", "PASSIVE": "被動元件",
    "PCB_HDI": "高階 PCB / HDI", "PCB_FPC": "軟板 FPC",
    "THERMAL": "散熱模組", "CHASSIS": "機構件 / 機殼",
    "ODM_SYS": "系統組裝 / ODM", "BRAND": "品牌商 / OEM",
    "END_USER": "終端應用商", "DISTRIB": "通路 / 代理",
    "POWER_MOD": "電源模組 / BBU", "OPTIC_MOD": "光通訊模組",
    "OPTIC_COMP": "光通訊元件", "SVC_SAAS": "軟體 / SaaS",
}


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
    "broker_top15_buy", "broker_top15_sell",
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

    print("  [FinLab] 下載主力分點 Top15 買賣...")
    d["broker_top15_buy"] = _safe_get(data, "etl:broker_transactions:top15_buy")
    d["broker_top15_sell"] = _safe_get(data, "etl:broker_transactions:top15_sell")

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

    # 同步刷新大盤指數 cache（加權 + 櫃買），避免 daily_build 跑 finlab 時 indices 卡舊值
    print("  [FinLab] 下載大盤指數（上市加權 + 櫃買）...")
    try:
        load_market_indices(use_cache=False)
    except Exception as e:
        print(f"  [警告] 大盤指數刷新失敗：{e}（沿用前次 cache）")
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
    foreign = d.get("foreign")
    trust = d.get("trust")
    dealer = d.get("dealer")
    broker_top15_buy = d.get("broker_top15_buy")
    broker_top15_sell = d.get("broker_top15_sell")

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

    def add_chip_windows(
        source: pd.DataFrame | None,
        prefix: str,
        scale: float = 1000.0,
        empty_value: float = 0.0,
    ) -> None:
        for days in (1, 5, 10):
            col = f"{prefix}_{days}d"
            if source is not None and not source.empty:
                df[col] = source.iloc[-days:].sum() / scale
            else:
                df[col] = empty_value

    # 三大法人原始單位為股，轉成張。
    add_chip_windows(foreign, "foreign")
    add_chip_windows(trust, "trust")
    add_chip_windows(dealer, "dealer")

    # 主力採 FinLab 前 15 大券商分點買賣差，資料單位已是張。
    main_chip = None
    if (
        broker_top15_buy is not None and not broker_top15_buy.empty
        and broker_top15_sell is not None and not broker_top15_sell.empty
    ):
        main_chip = broker_top15_buy.sub(broker_top15_sell, fill_value=0)
    add_chip_windows(main_chip, "main", scale=1.0, empty_value=float("nan"))

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


def compute_company_topics() -> dict:
    """每檔股票反查所屬題材"""
    result = defaultdict(list)
    for group, members in CONCEPT_GROUPS.items():
        for s in members:
            result[s].append(group)
    return dict(result)


def compute_member_related_topics(
    members,
    company_topics: dict,
    exclude_group: str | None = None,
    top_n: int = 5,
) -> list:
    """從成分股的其他題材統計重複次數，取前 N 大相關題材。"""
    unique_members = list(dict.fromkeys(members or []))
    member_count = len(unique_members)
    topic_counts = defaultdict(int)

    for sym in unique_members:
        for topic in company_topics.get(sym, []):
            if topic == exclude_group:
                continue
            topic_counts[topic] += 1

    related = []
    for topic, shared in topic_counts.items():
        topic_members = set(CONCEPT_GROUPS.get(topic, []))
        union = member_count + len(topic_members) - shared
        related.append({
            "name": topic,
            "jaccard": round(shared / union, 3) if union else 0,
            "shared": shared,
        })

    related.sort(key=lambda r: (-r["shared"], -r["jaccard"], r["name"]))
    return related[:top_n]


def compute_related_topics(company_topics: dict, top_n=5) -> dict:
    """替每個題材彙總成分股最常重複出現的其他題材。"""
    return {
        group: compute_member_related_topics(
            members,
            company_topics,
            exclude_group=group,
            top_n=top_n,
        )
        for group, members in CONCEPT_GROUPS.items()
    }


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
        # 簡單算術平均（每檔股各 1 票）
        cat_ret_simple = float(rows["ret_1d"].mean(skipna=True) or 0)
        # 代表題材：該 category 下按成交額排序取 Top 3
        top_groups = sorted(
            [(g, group_metrics.get(g, {}).get("amount_sum_mn", 0)) for g in groups],
            key=lambda x: -x[1],
        )[:3]
        top_names = [g for g, _ in top_groups]
        # color 用 CATEGORY_COLORS
        result.append({
            "name":            cat,
            "n_groups":        len(groups),
            "n_stocks":        len(unique_syms),
            "total_amt":       total_amt,
            "ret_mean":        cat_ret,           # 加權（預設）
            "ret_mean_simple": cat_ret_simple,    # 算術
            "top_groups":      top_names,
            "color":           CATEGORY_COLORS.get(cat, "#64748b"),
        })
    result.sort(key=lambda x: -x["total_amt"])
    return result


def is_etf_like_symbol(sym: str, name: str = "") -> bool:
    """排除 ETF / ETN / 指數型商品，避免首頁公司數把金融商品算進上市櫃公司。"""
    name_upper = str(name).upper()
    if sym.startswith("00") and 4 <= len(sym) <= 6:
        return True
    fund_keywords = ("ETF", "ETN", "指數", "正2", "反1", "受益", "REIT")
    return any(keyword in name_upper for keyword in fund_keywords)


def get_listed_otc_symbols(stock_metrics: pd.DataFrame, name_map: dict, market_map: dict) -> list[str]:
    """首頁統計口徑：只計上市、上櫃，且需有正式股名。"""
    symbols: list[str] = []
    for sym in stock_metrics.index:
        if market_map.get(sym) not in {"sii", "otc"}:
            continue
        name = name_map.get(sym)
        if not (isinstance(name, str) and name.strip() and name.strip() != sym):
            continue
        if is_etf_like_symbol(sym, name):
            continue
        symbols.append(sym)
    return symbols


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

        # 籌碼資料對齊 K 線日期軸：法人股數轉張；分點主力資料已是張。
        def chip_series(key, scale=1000.0):
            df = d.get(key)
            if df is None or sym not in df.columns:
                return None
            return df[sym].reindex(idx) / scale

        foreign_s = chip_series("foreign")
        trust_s   = chip_series("trust")
        dealer_s  = chip_series("dealer")
        broker_top15_buy_s = chip_series("broker_top15_buy", scale=1.0)
        broker_top15_sell_s = chip_series("broker_top15_sell", scale=1.0)
        main_s = (
            broker_top15_buy_s.sub(broker_top15_sell_s, fill_value=0)
            if broker_top15_buy_s is not None and broker_top15_sell_s is not None
            else None
        )

        def r0(s, i):
            if s is None:
                return None
            val = s.iloc[i]
            return round(float(val), 0) if pd.notna(val) else None

        show_from = max(0, len(idx) - days)
        rng_slice = range(show_from, len(idx))

        has_foreign = foreign_s is not None and bool(foreign_s.notna().any())
        has_trust   = trust_s   is not None and bool(trust_s.notna().any())
        has_dealer  = dealer_s  is not None and bool(dealer_s.notna().any())
        has_main    = main_s    is not None and bool(main_s.notna().any())

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
            "main_net":    [r0(main_s,    i) for i in rng_slice] if has_main else None,
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

    # 主力（分點 Top 15）：原始單位本來就是「張」，不 ÷1000
    main_buy_s  = series_tail("broker_top15_buy",  to_lots=False)
    main_sell_s = series_tail("broker_top15_sell", to_lots=False)
    if main_buy_s is not None:
        out["main_buy"]  = [round(float(x), 0) for x in main_buy_s.values]
        dates_ref = main_buy_s.index if dates_ref is None else dates_ref.union(main_buy_s.index)
    if main_sell_s is not None:
        out["main_sell"] = [round(float(x), 0) for x in main_sell_s.values]
        dates_ref = main_sell_s.index if dates_ref is None else dates_ref.union(main_sell_s.index)
    if main_buy_s is not None and main_sell_s is not None:
        net_s = main_buy_s.sub(main_sell_s, fill_value=0)
        out["main_net"] = [round(float(x), 0) for x in net_s.values]

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


_DISPOSAL_MATCH_RE_AR = re.compile(r"每\s*(\d+)\s*分鐘撮合")
_DISPOSAL_MATCH_RE_CN = re.compile(r"每\s*([零一二三四五六七八九十兩]+)\s*分鐘撮合")
# 中文數字 → 阿拉伯（只 cover 處置實務會用到的值：5/10/15/20/25/30）
_CN_MIN_MAP = {
    "五": 5,
    "十": 10,
    "十五": 15,
    "二十": 20,
    "二十五": 25,
    "三十": 30,
}


def parse_disposal_match_minutes(info: dict) -> int | None:
    """從處置資訊文字 parse 出撮合分鐘（5/10/20/25…），無法判斷回 None。
    台股慣例：第一次處置 5 分撮合、第二次處置 20 分撮合（部分為 25 分），
    上市櫃文字裡都會寫『每 X 分鐘撮合一次』；
    TPEx 用半形阿拉伯數字（每5分鐘），TWSE 用全形漢字（每五分鐘），兩種都要對齊。"""
    if not info:
        return None
    text = " ".join([
        info.get("action") or "",
        info.get("detail") or "",
        info.get("reason") or "",
    ])
    # 1) 半形阿拉伯
    m = _DISPOSAL_MATCH_RE_AR.search(text)
    if m:
        try:
            return int(m.group(1))
        except (ValueError, TypeError):
            pass
    # 2) 中文數字（TWSE 文字慣用）
    m = _DISPOSAL_MATCH_RE_CN.search(text)
    if m:
        return _CN_MIN_MAP.get(m.group(1))
    return None


def _enrich_disposal_match_level(info: dict) -> dict:
    """為 disposal info dict 注入 match_minutes / match_label 兩個欄位（in-place，且只跑一次）。"""
    if not info or "match_minutes" in info:
        return info
    mm = parse_disposal_match_minutes(info)
    info["match_minutes"] = mm
    info["match_label"] = f"{mm} 分撮合" if mm else ""
    return info


def get_disposal_info(disposal_map: dict, sym: str) -> dict | None:
    """從 fetch_extras 的處置股字典查該檔。
    對 4 碼上市櫃個股做 .lstrip('0') / 純數字 fallback 容錯；
    5-6 碼 ETF（00 開頭）只做精確匹配，避免 '006208'.lstrip('0') 撞 4 碼股票（如日揚 6208）。
    回傳前會注入 match_minutes / match_label（撮合分鐘分級）。"""
    if not disposal_map:
        return None
    info = disposal_map.get(sym)
    if info is not None:
        return _enrich_disposal_match_level(info)
    # ETF 樣式（00 開頭、≥5 碼）只做精確匹配
    if sym.startswith("00") and len(sym) >= 5:
        return None
    info = disposal_map.get(sym.lstrip("0"))
    if info is None:
        # 字母後綴（例：1522A）主代號 fallback
        base = "".join(c for c in sym if c.isdigit())
        if base and base != sym:
            info = disposal_map.get(base)
    return _enrich_disposal_match_level(info) if info else None


def get_holder_info(holder_history: dict, levels: list, sym: str) -> dict | None:
    """從 holders_history 查該檔所有週的 15 級資料，轉成前端用的 view。
    5-6 碼 ETF（00 開頭）只做精確匹配，避免跨類型撞 4 碼股票的集保資料。"""
    if not holder_history:
        return None
    hist_by_date = holder_history.get(sym)
    if hist_by_date is None:
        # ETF 樣式（00 開頭、≥5 碼）只做精確匹配
        if sym.startswith("00") and len(sym) >= 5:
            return None
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
    """產生 ECharts treemap 格式。兩層：group > stock。
    第一層直接鋪 190 族群（依當期成交額降序），點擊下鑽看個股。
    每個節點的顏色 Python 端就算好塞進 itemStyle.color，繞開 ECharts 多層 color mapping 的坑。"""
    data_by_tf = {}
    for tf, col in [("daily", "ret_1d"), ("weekly", "ret_5d"), ("monthly", "ret_20d")]:
        group_nodes = []
        for group, members in CONCEPT_GROUPS.items():
            meta = get_meta(group)
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
            group_nodes.append({
                "name":      group,
                "value":     [total_amt_group, avg_ret_pct],
                "category":  meta["category"],
                "children":  stock_leaves,
                "itemStyle": {"color": ret_to_color(avg_ret_pct, tf)},
            })
        # 依族群成交額大→小排序
        group_nodes.sort(key=lambda g: -g["value"][0])
        data_by_tf[tf] = group_nodes
    return data_by_tf


def build_search_data(
    stock_metrics: pd.DataFrame,
    name_map: dict,
    industry_map: dict,
    company_topics: dict,
    disposal_map: dict | None = None,
    market_map: dict | None = None,
    ai_summaries: dict | None = None,
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
        desc = get_topic_summary_text(group, ai_summaries, limit=50)
        items.append({
            "type":  "topic",
            "label": group,
            "sub":   desc,
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
            mm = disp_info.get("match_minutes")
            if mm:
                badges.append(f"⚠處置中 {mm}分")
                tags += [f"{mm}分處置", f"{mm}分撮合"]
            else:
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


def urlquote(v) -> str:
    """URL 查詢參數用的百分比編碼。"""
    return quote(str(v or ""), safe="")


def build_env():
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["pct"] = pct
    env.filters["fmt_amount"] = fmt_amount
    env.filters["slugify"] = slugify
    env.filters["tv_symbol"] = tv_symbol_digits
    env.filters["urlquote"] = urlquote
    env.globals["CATEGORY_COLORS"] = CATEGORY_COLORS
    env.globals["get_meta"] = get_meta
    env.globals["STOCK_HIGHLIGHTS"] = STOCK_HIGHLIGHTS
    return env


# ─────── RS 評分（仿 EJFQ 相對強度）───────

def compute_rs_scores(close: pd.DataFrame, name_map: dict, market_map: dict,
                      min_history: int = 50, lookback: int = 240) -> pd.Series:
    """RS 評分：相對全市場過去 N 個交易日的價格報酬 percentile rank (1-99 整數)。

    - close: 收盤價 DataFrame, index=date, columns=symbol
    - 篩選：有公司簡稱、有市場別、且 dropna 後資料 >= min_history（排除新上市未滿 50 個交易日）
    - lookback 預設 240 (台股年線慣例 ≈ 12 個月)；季 RS 傳入 60。資料不足時自動降回可用最大窗口
    """
    if close is None or close.empty:
        return pd.Series(dtype=int)

    valid = []
    for s in close.columns:
        nm = name_map.get(s)
        if not (isinstance(nm, str) and nm.strip() and nm.strip() != s):
            continue
        if not market_map.get(s):
            continue
        if close[s].dropna().shape[0] < min_history:
            continue
        valid.append(s)
    if not valid:
        return pd.Series(dtype=int)

    if len(close) < lookback + 1:
        lookback = len(close) - 1
    px_now = close[valid].iloc[-1]
    px_old = close[valid].iloc[-lookback - 1]
    ret_12m = (px_now / px_old - 1).dropna()
    if ret_12m.empty:
        return pd.Series(dtype=int)

    pct = ret_12m.rank(pct=True) * 98 + 1
    return pct.round(0).astype(int)


def update_rs_history(rs_today: pd.Series, today, path: Path = None,
                      label: str = "year") -> pd.DataFrame:
    """把今日 RS 寫入指定 parquet（若該日已存在則覆蓋）。
    保留近 500 個交易日（約 2 年）。回傳完整歷史 DataFrame。

    - path: 預設為年 RS 的 RS_HISTORY；季 RS 傳入 RS_HISTORY_QUARTER
    - label: 純粹用於 log 訊息，標示這是 year 還是 quarter
    """
    cache_path = path or RS_HISTORY
    if cache_path.exists():
        try:
            hist = pd.read_parquet(cache_path)
            hist.index = pd.to_datetime(hist.index)
        except Exception as e:
            print(f"[rs/{label}] 讀取歷史 cache 失敗：{e}，將從零開始")
            hist = pd.DataFrame()
    else:
        hist = pd.DataFrame()

    today_ts = pd.Timestamp(today).normalize()
    today_df = pd.DataFrame(
        [rs_today.astype("Int64").values],
        index=[today_ts],
        columns=rs_today.index,
    )
    if hist.empty:
        merged = today_df
    else:
        keep = hist[~hist.index.isin([today_ts])]
        merged = pd.concat([keep, today_df]).sort_index()
    merged = merged.tail(500)

    try:
        merged.to_parquet(cache_path)
        print(f"[rs/{label}] 歷史 cache：{len(merged)} 個交易日 × {merged.shape[1]} 檔")
    except Exception as e:
        print(f"[rs/{label}] 寫入歷史 cache 失敗：{e}")
    return merged


def compute_index_ratio(close: pd.DataFrame, index_series: pd.Series,
                        lookback: int = 240, min_periods: int = 120) -> pd.DataFrame:
    """個股對大盤的純比值：ratio_t = stock_close_t / index_close_t。

    - close: 收盤價 DataFrame, index=date, columns=symbol
    - index_series: 大盤指數 Series（taiex 或 tpex）
    - lookback / min_periods: 僅用於決定有效起點，不再做 240 日均值除法

    回傳 DataFrame: index=date, columns=symbol, values=比值（保留 8 位小數，比值通常很小）
    線上揚 = 個股相對大盤水位拉開；線下彎 = 反之。
    無中性線 / 無強弱絕對基準（只看趨勢方向與相對水位變化）。
    """
    if close is None or close.empty or index_series is None or len(index_series) == 0:
        return pd.DataFrame()
    common = close.index.intersection(index_series.index)
    if len(common) < min_periods + 1:
        return pd.DataFrame()
    px = close.loc[common]
    idx = index_series.loc[common]
    ratio = px.div(idx, axis=0)
    return ratio.round(8)


# 向後兼容別名（舊變數名 / 舊呼叫點仍可用）
def compute_mansfield_rs(close: pd.DataFrame, index_series: pd.Series,
                         lookback: int = 240, min_periods: int = 120) -> pd.DataFrame:
    """[已停用] 改用 compute_index_ratio。保留只為避免外部 import 斷裂。"""
    if close is None or close.empty or index_series is None or len(index_series) == 0:
        return pd.DataFrame()
    common = close.index.intersection(index_series.index)
    if len(common) < min_periods + 1:
        return pd.DataFrame()
    px = close.loc[common]
    idx = index_series.loc[common]
    ratio = px.div(idx, axis=0)
    ma = ratio.rolling(window=lookback, min_periods=min_periods).mean()
    mansfield = (ratio / ma - 1) * 100
    return mansfield.round(1)


def compute_cumulative_return(close: pd.DataFrame, index_series: pd.Series,
                               window: int = 250) -> tuple[pd.DataFrame, pd.Series]:
    """以 window 日前為基期 (=0%)，回傳逐日累積報酬 %。

    回傳 (stock_cum_df, index_cum_series)：
      stock_cum_df: index=date, columns=symbol, values=累積報酬 %（保留 1 位）
      index_cum_series: index=date, values=大盤累積報酬 %
    """
    if close is None or close.empty or index_series is None or len(index_series) == 0:
        return pd.DataFrame(), pd.Series(dtype=float)
    common = close.index.intersection(index_series.index)
    if len(common) < window + 1:
        window = len(common) - 1
    if window < 5:
        return pd.DataFrame(), pd.Series(dtype=float)
    px = close.loc[common].iloc[-window-1:]
    idx = index_series.loc[common].iloc[-window-1:]
    base_px = px.iloc[0]
    base_idx = idx.iloc[0]
    stock_cum = (px.div(base_px) - 1) * 100
    index_cum = (idx / base_idx - 1) * 100
    return stock_cum.round(1), index_cum.round(1)


def build_rs_rows(stock_metrics: pd.DataFrame, rs_today: pd.Series, close: pd.DataFrame,
                  name_map: dict, industry_map: dict, market_map: dict,
                  company_topics: dict, lookback: int = 240) -> list[dict]:
    """RS 排名表 row dict list（依 RS 由高到低）。"""
    if rs_today.empty:
        return []
    if len(close) < lookback + 1:
        lookback = len(close) - 1
    px_old = close.iloc[-lookback - 1]
    px_now = close.iloc[-1]
    market_disp_map = {"sii": "上市", "otc": "上櫃", "rotc": "興櫃"}

    rows = []
    for sym in rs_today.index:
        rs = int(rs_today[sym])
        nm = name_map.get(sym, sym)
        if sym in stock_metrics.index:
            m = stock_metrics.loc[sym]
            close_v = float(m["close"]) if m["close"] == m["close"] else None
            ret_1d  = float(m["ret_1d"])  if m["ret_1d"]  == m["ret_1d"]  else None
            ret_5d  = float(m["ret_5d"])  if m["ret_5d"]  == m["ret_5d"]  else None
            ret_20d = float(m["ret_20d"]) if m["ret_20d"] == m["ret_20d"] else None
        else:
            close_v = ret_1d = ret_5d = ret_20d = None

        try:
            old_v = float(px_old[sym])
            new_v = float(px_now[sym])
            r12 = new_v / old_v - 1 if old_v else None
        except (KeyError, TypeError, ZeroDivisionError):
            r12 = None
        if r12 is not None and r12 != r12:
            r12 = None

        m_code = market_map.get(sym, "")
        rows.append({
            "sym": sym,
            "name": nm,
            "industry": industry_map.get(sym, ""),
            "market": market_disp_map.get(m_code, m_code or ""),
            "rs": rs,
            "ret_12m": r12,
            "ret_20d": ret_20d,
            "ret_5d": ret_5d,
            "ret_1d": ret_1d,
            "close": close_v,
            "topics_txt": "、".join(company_topics.get(sym, [])[:3]) if company_topics.get(sym) else "",
        })
    rows.sort(key=lambda r: -r["rs"])
    return rows


def compute_rankings(stock_metrics: pd.DataFrame, rich: dict, extras: dict,
                     name_map: dict, industry_map: dict, company_topics: dict,
                     top_n: int = 20) -> dict:
    """產出四類排行榜資料供 rankings.html 使用。

    返回 dict:
      chips_foreign_buy / chips_foreign_sell  — 近 5 日外資 Top 20
      chips_trust_buy   / chips_trust_sell    — 近 5 日投信 Top 20
      chips_dealer_buy  / chips_dealer_sell   — 近 5 日自營商 Top 20
      chips_*_1d_buy / chips_*_1d_sell        — 當日法人與主力 Top 20
      chips_main_5d_buy / chips_main_5d_sell  — 近 5 日主力分點 Top 20
      chips_main_10d_buy / chips_main_10d_sell — 近 10 日主力 Top 20
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
    def chip_rows(metric: str) -> list[dict]:
        if metric not in stock_metrics.columns:
            return []
        return [
            {**_base_row(s), "value": float(stock_metrics.at[s, metric])}
            for s in syms
            if pd.notna(stock_metrics.at[s, metric])
        ]

    def chip_buy_sell(metric: str) -> tuple[list[dict], list[dict]]:
        rows = chip_rows(metric)
        return (
            sorted(rows, key=lambda r: -r["value"])[:top_n],
            sorted(rows, key=lambda r: r["value"])[:top_n],
        )

    chips_foreign_buy, chips_foreign_sell = chip_buy_sell("foreign_5d")
    chips_trust_buy, chips_trust_sell = chip_buy_sell("trust_5d")
    chips_dealer_buy, chips_dealer_sell = chip_buy_sell("dealer_5d")
    chips_foreign_1d_buy, chips_foreign_1d_sell = chip_buy_sell("foreign_1d")
    chips_trust_1d_buy, chips_trust_1d_sell = chip_buy_sell("trust_1d")
    chips_dealer_1d_buy, chips_dealer_1d_sell = chip_buy_sell("dealer_1d")
    chips_main_1d_buy, chips_main_1d_sell = chip_buy_sell("main_1d")
    chips_main_5d_buy, chips_main_5d_sell = chip_buy_sell("main_5d")
    chips_main_10d_buy, chips_main_10d_sell = chip_buy_sell("main_10d")

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
        "chips_dealer_buy":   chips_dealer_buy,
        "chips_dealer_sell":  chips_dealer_sell,
        "chips_foreign_1d_buy":  chips_foreign_1d_buy,
        "chips_foreign_1d_sell": chips_foreign_1d_sell,
        "chips_trust_1d_buy":    chips_trust_1d_buy,
        "chips_trust_1d_sell":   chips_trust_1d_sell,
        "chips_dealer_1d_buy":   chips_dealer_1d_buy,
        "chips_dealer_1d_sell":  chips_dealer_1d_sell,
        "chips_main_1d_buy":  chips_main_1d_buy,
        "chips_main_1d_sell": chips_main_1d_sell,
        "chips_main_5d_buy":  chips_main_5d_buy,
        "chips_main_5d_sell": chips_main_5d_sell,
        "chips_main_10d_buy": chips_main_10d_buy,
        "chips_main_10d_sell": chips_main_10d_sell,
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


def get_topic_summary_text(group: str, ai_summaries: dict | None = None, limit: int | None = None) -> str:
    """題材卡片優先顯示補好的介紹，避免回落到分類同步用的短句。"""
    payload = (ai_summaries or {}).get(group) or {}
    meta = get_meta(group)
    text = payload.get("hero_desc") or payload.get("analysis") or meta.get("desc", "")
    text = " ".join(str(text).split())
    if limit is not None and len(text) > limit:
        return text[:limit].rstrip() + "..."
    return text


def has_generic_indicators(indicators: list | tuple | None) -> bool:
    if not indicators:
        return False
    generic_labels = {"大族群", "成分股數", "資料狀態"}
    labels = {str(item.get("label", "")) for item in indicators if isinstance(item, dict)}
    return bool(labels & generic_labels)


def select_topic_indicators(meta: dict, ai_summary: dict | None) -> list:
    meta_indicators = meta.get("indicators") or []
    ai_indicators = (ai_summary or {}).get("indicators") or []
    if ai_indicators and (
        meta.get("actual_count") is not None
        or not meta_indicators
        or has_generic_indicators(meta_indicators)
    ):
        return ai_indicators
    return meta_indicators or ai_indicators


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


def render_all(data, stock_metrics, group_metrics, related, company_topics, rich=None, extras=None, coverage=None, stock_profiles=None, ai_summaries=None):
    env = build_env()
    rich = rich or {"basic": {}, "business": {}, "revenue": {}, "financials": {}, "dividends": {}, "director": {}}
    extras = extras or {"disposal": {}, "holders": {}}
    coverage = coverage or {}
    stock_profiles = stock_profiles or {}
    ai_summaries = ai_summaries or load_ai_summaries()
    name_map = data["name_map"]
    last_date = data["close"].index[-1].strftime("%Y-%m-%d")

    limit_up_by_date = load_all_limit_up_data()
    has_limit_up = bool(limit_up_by_date)
    limit_up_dates = sorted(limit_up_by_date.keys()) if limit_up_by_date else []
    latest_lu_date = limit_up_dates[-1] if limit_up_dates else None
    limit_up_data = limit_up_by_date.get(latest_lu_date) if latest_lu_date else None

    # 期貨清單 + RS 評分（年/季）+ 加權指數（在所有頁面渲染前算好，再供 RS 頁、公司頁共用）
    futures_flags = load_futures_flags()
    print("       · 計算 RS 評分（台股慣例：年=240 日、季=60 日 percentile）...")
    last_close_ts = data["close"].index[-1]
    rs_year_today    = compute_rs_scores(data["close"], name_map, data["market_map"], lookback=240)
    rs_quarter_today = compute_rs_scores(data["close"], name_map, data["market_map"], lookback=60)
    print(f"         年 RS 覆蓋 {len(rs_year_today)} 檔；季 RS 覆蓋 {len(rs_quarter_today)} 檔")
    rs_year_history    = update_rs_history(rs_year_today,    last_close_ts, RS_HISTORY,        label="year")
    rs_quarter_history = update_rs_history(rs_quarter_today, last_close_ts, RS_HISTORY_QUARTER, label="quarter")
    # 兼容舊變數名稱（rs.html 使用 rs_today / rs_history）
    rs_today   = rs_year_today
    rs_history = rs_year_history
    # 大盤指數（上市加權 + 櫃買；從快取讀取，首次無 cache 時打 finlab）
    market_indices = load_market_indices(use_cache=True)
    taiex_series = market_indices.get("taiex", pd.Series(dtype=float))
    tpex_series  = market_indices.get("tpex",  pd.Series(dtype=float))
    # 對齊 close 日期軸：FinLab 櫃買 dataset 常延遲 1-3 日，用 ffill 補（用前一交易日收盤值）
    # 避免 vs 櫃買 / 累積 vs 櫃買 在最新日因日期對不上而出現 null 斷點
    if not taiex_series.empty:
        taiex_series = taiex_series.reindex(data["close"].index, method="ffill")
        print(f"       · 加權指數對齊到 close 日期軸：{len(taiex_series)} 日，最新 {taiex_series.dropna().index.max().date()}")
    if not tpex_series.empty:
        last_real = tpex_series.index.max().date()
        tpex_series = tpex_series.reindex(data["close"].index, method="ffill")
        last_filled = tpex_series.dropna().index.max().date()
        if last_real != last_filled:
            print(f"       · 櫃買指數延遲：實際資料到 {last_real}，ffill 到 {last_filled}（用前值補）")
        else:
            print(f"       · 櫃買指數對齊：{len(tpex_series)} 日，最新 {last_filled}")
    # Mansfield 比值法：(個股/大盤) 對 240 日均值的 % 偏離；上揚 = 贏大盤
    print("       · 計算個股 / 大盤純比值（ratio = stock_close / index_close，無中性線）...")
    ratio_taiex_df = compute_index_ratio(data["close"], taiex_series, lookback=240)
    ratio_tpex_df  = compute_index_ratio(data["close"], tpex_series,  lookback=240)
    print(f"         vs 加權覆蓋 {ratio_taiex_df.shape[1] if not ratio_taiex_df.empty else 0} 檔；"
          f"vs 櫃買覆蓋 {ratio_tpex_df.shape[1] if not ratio_tpex_df.empty else 0} 檔")
    # 累積報酬對比（個股 vs 大盤同期 %，250 日基期 0%）
    print("       · 計算累積報酬對比（個股 vs 加權/櫃買，250 日基期 0%）...")
    cum_stock_taiex_df, cum_taiex_s = compute_cumulative_return(data["close"], taiex_series, window=250)
    cum_stock_tpex_df,  cum_tpex_s  = compute_cumulative_return(data["close"], tpex_series,  window=250)

    # 共用資料
    base_ctx = {
        "now": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "last_date": last_date,
        "nav_topics": sorted(
            CONCEPT_GROUPS.keys(),
            key=lambda g: -group_metrics.get(g, {}).get("amount_sum_mn", 0)
        )[:8],
        "has_limit_up": has_limit_up,
        "topic_card_desc": lambda group, limit=96: get_topic_summary_text(group, ai_summaries, limit=limit),
    }

    stock_futures_payload = load_stock_futures_page_data(
        data,
        stock_metrics,
        futures_flags,
        company_topics=company_topics,
        market_indices={"taiex": taiex_series, "tpex": tpex_series},
    )
    print(
        f"       ✓ 股期曝險資料：{len(stock_futures_payload.get('rows', []))} 筆"
        f"（{stock_futures_payload.get('status', 'unknown')}，as_of={stock_futures_payload.get('as_of', '—')}）"
    )

    # Index（每日焦點）
    total_groups = len(CONCEPT_GROUPS)
    listed_otc_symbols = get_listed_otc_symbols(stock_metrics, name_map, data["market_map"])
    listed_otc_rows = stock_metrics.loc[stock_metrics.index.intersection(listed_otc_symbols)]
    total_stocks = len(listed_otc_symbols)
    total_limit_up = int(listed_otc_rows["limit_up"].sum()) if "limit_up" in listed_otc_rows.columns else 0
    total_limit_down = int(listed_otc_rows["limit_down"].sum()) if "limit_down" in listed_otc_rows.columns else 0
    focus_group_items = [
        (g, m)
        for g, m in group_metrics.items()
        if float(m.get("amount_sum_mn") or 0) > FOCUS_TOPIC_MIN_AMOUNT_MN
    ]
    top_gain = sorted(
        focus_group_items,
        key=lambda x: -x[1]["ret_1d_mean"],
    )[:10]
    top_loss = sorted(
        focus_group_items,
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

    # 成值分析（今日成交值前 30 名個股 + 所屬題材）
    top_value = stock_metrics.dropna(subset=["amount_mn"]).copy()
    top_value["display_name"] = [
        (name_map.get(s) if isinstance(name_map.get(s), str) and name_map.get(s).strip() else s)
        for s in top_value.index
    ]
    top_value = top_value.sort_values("amount_mn", ascending=False).head(30)

    category_aggs_all = compute_category_aggregates(stock_metrics, group_metrics)
    homepage_category_names = set(CATEGORY_COLORS.keys())
    category_aggs = [
        cat for cat in category_aggs_all
        if cat.get("name") in homepage_category_names
    ]

    hot_topics = load_hot_topics(top_n=6)
    daily_chip_report = load_daily_chip_report()
    memo_data = load_memos()
    index_html = env.get_template("index.html").render(
        **base_ctx,
        total_groups=total_groups,
        total_stocks=total_stocks,
        total_limit_up=total_limit_up,
        total_limit_down=total_limit_down,
        top_flow=top_flow,
        category_aggs=category_aggs,
        hot_topics=hot_topics,
        daily_chip_report=daily_chip_report,
        memo_data=memo_data,
    )
    write_text_retry(DIST_DIR / "index.html", index_html)

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
            write_text_retry(DIST_DIR / f"limit-up-{d}.html", html)

        # limit-up.html = 最新一天
        latest_html = _render_one(latest_lu_date, limit_up_by_date[latest_lu_date], True)
        write_text_retry(DIST_DIR / "limit-up.html", latest_html)

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
            write_text_retry(DIST_DIR / "limit-up-stats.html", stats_html)
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
        top_value=top_value,                       # 新增：成值分析（成交值前30）
        focus_topic_min_amount_mn=FOCUS_TOPIC_MIN_AMOUNT_MN,
        focus_topic_min_amount_label=FOCUS_TOPIC_MIN_AMOUNT_LABEL,
        name_map=name_map,
        company_topics=company_topics,
        industry_map=data["industry_map"],
    )
    write_text_retry(DIST_DIR / "today.html", today_html)

    # 系統指標題材（每日動態：成交值前20 / 漲停 / 跌停 / 處置股）
    SYSTEM_TOPIC_DEFS = [
        ("每日成交值前20", "system-top-value-20", "#3b82f6", "市場資金最集中的 20 檔個股，反映當日主力進場焦點。"),
        ("每日漲停",       "system-limit-up",     "#ef4444", "當日漲停板個股清單，掌握強勢族群輪動領頭羊。"),
        ("每日跌停",       "system-limit-down",   "#22c55e", "當日跌停板個股清單，警惕弱勢族群與風險訊號。"),
        ("每日處置股",     "system-disposal",     "#f59e0b", "當日所有處置中個股清單，依撮合分級（5/10/20/25 分）標示交易異常風險。"),
    ]
    listed_otc_index = stock_metrics.index.intersection(listed_otc_symbols)
    listed_otc_metrics = stock_metrics.loc[listed_otc_index]
    top_value_syms = listed_otc_metrics.sort_values("amount_mn", ascending=False).head(20).index.tolist()
    if "limit_up" in stock_metrics.columns:
        limit_up_syms = listed_otc_metrics.index[listed_otc_metrics["limit_up"].fillna(False).astype(bool)].tolist()
    else:
        limit_up_syms = []
    if "limit_down" in stock_metrics.columns:
        limit_down_syms = listed_otc_metrics.index[listed_otc_metrics["limit_down"].fillna(False).astype(bool)].tolist()
    else:
        limit_down_syms = []
    # 處置股清單：取 disposal map 所有 key，過濾出在 stock_metrics 索引內的（避免空資料）
    disposal_map_now = extras.get("disposal", {}) or {}
    disposal_syms = [
        s for s in disposal_map_now.keys()
        if s in stock_metrics.index
    ]
    # 依「處置等級重→輕」「成交額大→小」排序：25 分 > 20 分 > 10 分 > 5 分 > 未標分鐘
    def _disposal_sort_key(sym: str):
        info = disposal_map_now.get(sym, {}) or {}
        # 確保 info 已被 enrich（match_minutes 欄位存在）
        if "match_minutes" not in info:
            _enrich_disposal_match_level(info)
        mm = info.get("match_minutes") or 0
        amt = float(stock_metrics.at[sym, "amount_mn"]) if sym in stock_metrics.index else 0.0
        return (-mm, -amt)
    disposal_syms.sort(key=_disposal_sort_key)
    SYSTEM_MEMBERS = {
        "每日成交值前20": top_value_syms,
        "每日漲停":        limit_up_syms,
        "每日跌停":        limit_down_syms,
        "每日處置股":      disposal_syms,
    }
    system_topics = []
    for sname, slug, color, desc in SYSTEM_TOPIC_DEFS:
        members = SYSTEM_MEMBERS[sname]
        rows = stock_metrics.loc[stock_metrics.index.intersection(members)]
        amt_sum = float(rows["amount_mn"].sum()) if len(rows) else 0.0
        ret_mean = float(rows["ret_1d"].mean()) if len(rows) and rows["ret_1d"].notna().any() else 0.0
        system_topics.append({
            "name":           sname,
            "slug":           slug,
            "color":          color,
            "desc":           desc,
            "n_stocks":       len(rows),
            "amount_sum_mn":  amt_sum,
            "ret_1d_mean":    ret_mean,
        })

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
        system_topics=system_topics,                # 新增：總覽區塊系統指標
    )
    write_text_retry(DIST_DIR / "topics.html", topics_html)

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
    write_text_retry(DIST_DIR / "heatmap.html", heatmap_html)

    # AI 分析頁（族群輪動 + 落後補漲）
    liquid_group_items = [
        (g, m)
        for g, m in group_metrics.items()
        if float(m.get("amount_sum_mn") or 0) > FOCUS_TOPIC_MIN_AMOUNT_MN
    ]
    # 落後補漲：20D 弱但 5D 轉強
    laggards = []
    for g, m in liquid_group_items:
        if m["ret_20d_mean"] < -0.03 and m["ret_5d_mean"] > 0.01:
            laggards.append((g, m))
    laggards.sort(key=lambda x: (-x[1]["ret_5d_mean"], -x[1]["amount_sum_mn"]))
    # 強勢延續：20D 強 + 5D 強 + 今日強
    leaders = []
    for g, m in liquid_group_items:
        if m["ret_20d_mean"] > 0.05 and m["ret_5d_mean"] > 0.02 and m["ret_1d_mean"] > 0:
            leaders.append((g, m))
    leaders.sort(key=lambda x: (-(x[1]["ret_5d_mean"] + x[1]["ret_1d_mean"]), -x[1]["amount_sum_mn"]))
    ai_html = env.get_template("ai_analysis.html").render(
        **base_ctx,
        laggards=laggards[:10],
        leaders=leaders[:10],
        min_amount_label=FOCUS_TOPIC_MIN_AMOUNT_LABEL,
        get_meta=get_meta,
    )
    write_text_retry(DIST_DIR / "ai.html", ai_html)

    # 股期曝險頁（個人部位試算 + 股票期貨排行）
    stock_futures_html = env.get_template("stock_futures.html").render(
        **base_ctx,
        stock_futures=stock_futures_payload,
    )
    write_text_retry(DIST_DIR / "stock-futures.html", stock_futures_html)

    # 個股 Memo 公佈欄（獨立頁面）
    memo_html = env.get_template("memo.html").render(
        **base_ctx,
        memo_data=load_memos(),
    )
    write_text_retry(DIST_DIR / "memo.html", memo_html)

    # 每個題材頁 + 快取 topic_series 供 compare 頁共用
    topic_dir = DIST_DIR / "topic"
    topic_dir.mkdir(exist_ok=True)
    for stale_topic in topic_dir.glob("*.html"):
        stale_topic.unlink()
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
            topic_indicators=select_topic_indicators(meta, ai_sum),
        )
        write_text_retry(topic_dir / f"{slugify(group)}.html", html)
        if topic_series:
            all_topic_series[group] = topic_series
            all_topic_meta[group] = {
                "category": meta.get("category", ""),
                "color":    meta.get("color", "#64748b"),
                "slug":     slugify(group),
                "n_stocks": len(rows),
            }

    # 系統指標題材詳情頁（複用 topic_detail.html）
    sys_topic_count = 0
    for sname, slug, color, desc in SYSTEM_TOPIC_DEFS:
        members = SYSTEM_MEMBERS[sname]
        if not members:
            continue
        rows = stock_metrics.loc[stock_metrics.index.intersection(members)].copy()
        if not len(rows):
            continue
        rows["display_name"] = [
            (name_map.get(s) if isinstance(name_map.get(s), str) and name_map.get(s).strip() else s)
            for s in rows.index
        ]
        rows_sorted = rows.sort_values("amount_mn", ascending=False)
        sys_meta = {
            "category":    "系統指標",
            "color":       color,
            "en":          "",
            "desc":        desc,
            "cagr":        "—",
            "market_size": "—",
            "indicators":  [],
        }
        sys_summary = {
            "n_stocks":      len(rows),
            "ret_1d_mean":   float(rows["ret_1d"].mean())  if rows["ret_1d"].notna().any()  else 0.0,
            "ret_5d_mean":   float(rows["ret_5d"].mean())  if rows["ret_5d"].notna().any()  else 0.0,
            "ret_20d_mean":  float(rows["ret_20d"].mean()) if rows["ret_20d"].notna().any() else 0.0,
            "amount_sum_mn": float(rows["amount_mn"].sum()),
            "n_limit_up":    int(rows["limit_up"].sum())   if "limit_up"  in rows.columns else 0,
            "n_limit_down":  int(rows["limit_down"].sum()) if "limit_down" in rows.columns else 0,
            "n_foreign_buy": int((rows.get("foreign_1d", pd.Series(dtype=float)) > 0).sum()),
            "n_trust_buy":   int((rows.get("trust_1d",   pd.Series(dtype=float)) > 0).sum()),
            "top_stock":     rows_sorted.index[0] if len(rows_sorted) else "",
        }
        sys_series = compute_topic_return_series(data, members, days=125)
        sys_related = compute_member_related_topics(
            members,
            company_topics,
            exclude_group=sname,
            top_n=5,
        )
        html = tpl_topic.render(
            **base_ctx,
            group=sname,
            meta=sys_meta,
            stocks=rows_sorted,
            summary=sys_summary,
            related=sys_related,
            name_map=name_map,
            company_topics=company_topics,
            topic_series_json=json.dumps(sys_series, ensure_ascii=False) if sys_series else "null",
            ai_summary=None,
            topic_indicators=[],
        )
        write_text_retry(topic_dir / f"{slug}.html", html)
        sys_topic_count += 1
        # 也加入 compare 來源池（系統指標也可被選來對比）
        if sys_series:
            all_topic_series[sname] = sys_series
            all_topic_meta[sname] = {
                "category": "系統指標",
                "color":    color,
                "slug":     slug,
                "n_stocks": len(rows),
            }
    print(f"       ✓ 系統指標題材詳情頁 {sys_topic_count} 頁（成交值前20 / 漲停 / 跌停 / 處置股）")

    # 個股 6 個月累積報酬 series（compare 頁內嵌使用，另輸出 JSON 作為伺服器模式備援）
    stock_data_dir = DIST_DIR / "data" / "stock_series"
    stock_data_dir.mkdir(parents=True, exist_ok=True)
    stock_index = []
    stock_series_map = {}
    stock_series_count = 0
    close_cols = set(data["close"].columns)
    for sym in stock_metrics.index:
        if sym not in close_cols:
            continue
        series = compute_topic_return_series(data, [sym], days=125)
        if not series:
            continue
        stock_series_map[sym] = series
        write_text_retry(stock_data_dir / f"{sym}.json", json.dumps(series, ensure_ascii=False))
        nm = name_map.get(sym)
        nm = nm if isinstance(nm, str) and nm.strip() else sym
        stock_index.append({
            "sym":      sym,
            "name":     nm,
            "industry": data["industry_map"].get(sym, ""),
            "topics":   (company_topics.get(sym) or [])[:2],
        })
        stock_series_count += 1
    print(f"       ✓ 個股累積報酬 series {stock_series_count} 檔（dist/data/stock_series/）")

    # 題材對比頁（前端選 2-5 個題材或個股疊加走勢）
    compare_html = env.get_template("compare.html").render(
        **base_ctx,
        topic_series_json=json.dumps(all_topic_series, ensure_ascii=False),
        topic_meta_json=json.dumps(all_topic_meta, ensure_ascii=False),
        stock_index_json=json.dumps(stock_index, ensure_ascii=False),
        stock_series_json=json.dumps(stock_series_map, ensure_ascii=False),
    )
    write_text_retry(DIST_DIR / "compare.html", compare_html)

    # 排行榜頁（籌碼 / 月營收 YoY / EPS 年增 / 大戶變化）
    rankings = compute_rankings(
        stock_metrics, rich, extras,
        name_map, data["industry_map"], company_topics, top_n=20,
    )
    rankings_html = env.get_template("rankings.html").render(
        **base_ctx,
        rankings=rankings,
    )
    write_text_retry(DIST_DIR / "rankings.html", rankings_html)

    # RS 評分頁（全市場 RS 排名 + 強勢股精選）
    rs_rows = build_rs_rows(
        stock_metrics, rs_today, data["close"],
        name_map, data["industry_map"], data["market_map"],
        company_topics,
    )
    strong_by_industry: dict[str, list] = defaultdict(list)
    for row in rs_rows:
        if row["rs"] >= 80 and row["industry"]:
            strong_by_industry[row["industry"]].append(row)
    strong_groups = sorted(
        [(ind, rs_list[:5]) for ind, rs_list in strong_by_industry.items()],
        key=lambda x: (-len(strong_by_industry[x[0]]), x[0]),
    )
    industries_for_rs = sorted({r["industry"] for r in rs_rows if r["industry"]})
    rs_html = env.get_template("rs.html").render(
        **base_ctx,
        rs_rows=rs_rows,
        strong_groups=strong_groups,
        industries=industries_for_rs,
        total_count=len(rs_rows),
        strong_count=sum(1 for r in rs_rows if r["rs"] >= 80),
    )
    write_text_retry(DIST_DIR / "rs.html", rs_html)
    print(f"       ✓ RS 評分頁：{len(rs_rows)} 檔 / 強勢股 {sum(1 for r in rs_rows if r['rs']>=80)} 檔 / 強勢產業 {len(strong_groups)} 個")

    # 公司資料庫頁（上市櫃清單 + 前端搜尋/篩選/排序）
    industries_list = sorted({
        data["industry_map"].get(sym, "")
        for sym in listed_otc_symbols
        if isinstance(data["industry_map"].get(sym, ""), str) and data["industry_map"].get(sym, "").strip()
    })
    db_rows = []
    for sym in listed_otc_symbols:
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
    write_text_retry(DIST_DIR / "database.html", db_html)

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
        write_text_retry(
            DIST_DIR / "data" / "delisted.json",
            json.dumps(sorted(delisted), ensure_ascii=False, indent=2),
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
        # 三維畫像：取 supply_chain_position + 中文標籤（族群驗證系統 v2 產出）
        taxonomy_profile = stock_profiles.get(sym, {})
        taxonomy_position = taxonomy_profile.get("supply_chain_position", "")
        taxonomy_position_label = SUPPLY_CHAIN_POSITION_LABELS.get(taxonomy_position, "")
        basic = rich["basic"].get(sym)
        business = rich["business"].get(sym)
        revenue = rich["revenue"].get(sym)
        financials = rich["financials"].get(sym)
        dividends = rich["dividends"].get(sym)
        director_pct = rich["director"].get(sym)
        coverage_tabs = build_coverage_tabs(coverage.get(sym))
        # 期貨標示與 RS 評分
        futures = futures_flags.get(sym, {})
        rs_year_score    = int(rs_year_today[sym])    if sym in rs_year_today.index    else None
        rs_quarter_score = int(rs_quarter_today[sym]) if sym in rs_quarter_today.index else None
        # 同時相容舊變數名（其它模板若引用）
        rs_score = rs_year_score
        # 走勢圖 payload：年 RS / 季 RS / 加權指數，以聯集日期軸對齊
        rs_chart_payload = None
        year_s    = rs_year_history[sym].dropna().tail(250)    if sym in rs_year_history.columns    else pd.Series(dtype=float)
        quarter_s = rs_quarter_history[sym].dropna().tail(250) if sym in rs_quarter_history.columns else pd.Series(dtype=float)
        if len(year_s) >= 2 or len(quarter_s) >= 2:
            all_dates = sorted(set(year_s.index) | set(quarter_s.index))
            def _align(s):
                if len(s) == 0:
                    return None
                return [int(s.loc[d]) if d in s.index and pd.notna(s.loc[d]) else None for d in all_dates]
            def _align_index(series):
                if series.empty:
                    return None
                t = series.reindex(pd.DatetimeIndex(all_dates), method="ffill")
                return [None if pd.isna(v) else round(float(v), 2) for v in t.values]
            def _align_ratio(df):
                if df is None or df.empty or sym not in df.columns:
                    return None
                s = df[sym].dropna()
                if len(s) < 5:
                    return None
                t = s.reindex(pd.DatetimeIndex(all_dates))
                # Normalize：以顯示窗口第一個非 NaN 為基期 100
                non_null = t.dropna()
                if non_null.empty:
                    return None
                base = float(non_null.iloc[0])
                if base == 0:
                    return None
                normalized = (t / base) * 100
                return [None if pd.isna(v) else round(float(v), 1) for v in normalized.values]
            def _align_cum_stock(df):
                if df is None or df.empty or sym not in df.columns:
                    return None
                s = df[sym].dropna()
                if len(s) < 5:
                    return None
                t = s.reindex(pd.DatetimeIndex(all_dates))
                return [None if pd.isna(v) else round(float(v), 1) for v in t.values]
            def _align_cum_index(s):
                if s is None or len(s) == 0:
                    return None
                t = s.reindex(pd.DatetimeIndex(all_dates))
                return [None if pd.isna(v) else round(float(v), 1) for v in t.values]
            # 預設顯示哪個指數：上櫃 → 櫃買；其他 → 加權
            default_idx = "tpex" if data["market_map"].get(sym) == "otc" else "taiex"
            rs_chart_payload = {
                "dates":              [d.strftime("%y/%m/%d") for d in all_dates],
                "year":               _align(year_s),
                "quarter":            _align(quarter_s),
                "ratio_taiex":        _align_ratio(ratio_taiex_df),
                "ratio_tpex":         _align_ratio(ratio_tpex_df),
                "cum_stock_vs_taiex": _align_cum_stock(cum_stock_taiex_df),
                "cum_taiex":          _align_cum_index(cum_taiex_s),
                "cum_stock_vs_tpex":  _align_cum_stock(cum_stock_tpex_df),
                "cum_tpex":           _align_cum_index(cum_tpex_s),
                "twii":               _align_index(taiex_series),
                "tpex":               _align_index(tpex_series),
                "default_index":      default_idx,
            }
        # 兼容舊 rs_history 變數（若舊模板仍引用）
        rs_history_data = None
        html = tpl_company.render(
            **base_ctx,
            symbol=sym,
            name=name,
            industry=data["industry_map"].get(sym, ""),
            market=market_disp,
            row=row,
            topics=[(t, get_meta(t)) for t in topics],
            taxonomy_position=taxonomy_position,
            taxonomy_position_label=taxonomy_position_label,
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
            futures=futures,
            rs_score=rs_score,
            rs_year_score=rs_year_score,
            rs_quarter_score=rs_quarter_score,
            rs_chart=rs_chart_payload,
            rs_chart_json=json.dumps(rs_chart_payload, ensure_ascii=False) if rs_chart_payload else "null",
        )
        write_text_retry(company_dir / f"{sym}.html", html)
        n_pages += 1
    print(f"       ✓ 個股頁 {n_pages} 檔（全資料庫可用標的）")


def copy_static():
    """複製靜態檔案"""
    dst = DIST_DIR / "static"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(STATIC_SRC, dst)

    # admin SPA / 共用組件 / paywall — Cloudflare Pages Functions 後台需要
    for sub in ("admin", "components"):
        src = SITE_DIR / sub
        if not src.exists():
            continue
        target = DIST_DIR / sub
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(src, target)

    paywall_src = SITE_DIR / "paywall.html"
    if paywall_src.exists():
        shutil.copy2(paywall_src, DIST_DIR / "paywall.html")


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
    write_text_retry(DIST_DIR / "robots.txt", ROBOTS_TXT_CONTENT)


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
    """清洗 payload：groupAnalysis.text、stocks.reason、chipObservation.* 的文字欄位。
    並把新版 schema {group, count, analysis} 標準化為 template 使用的舊版 {name, text}。"""
    for ga in payload.get("groupAnalysis", []) or []:
        # schema 標準化：新版 (group/count/analysis) → 舊版 (name/text)
        if "name" not in ga and "group" in ga:
            grp = ga.get("group", "")
            cnt = ga.get("count")
            ga["name"] = f"{grp}（{cnt} 檔）" if cnt is not None else grp
        if "text" not in ga and "analysis" in ga:
            ga["text"] = ga["analysis"]
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
        write_text_retry(data_dir / f"heatmap_{tf}.json", json.dumps(nodes, ensure_ascii=False))
    # 搜尋資料輸出 .js 檔（script 載入避免 file:// CORS）
    write_text_retry(
        data_dir / "search-data.js",
        "window.SEARCH_DATA = " + json.dumps(search_data, ensure_ascii=False) + ";",
    )
    # 同步輸出純 JSON，避免舊版 search.json 殘留造成題材反查抽查誤判。
    write_text_retry(data_dir / "search.json", json.dumps(search_data, ensure_ascii=False))


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

    print("\n[0/5] 更新個股期貨清單（期交所，週更）...")
    refresh_futures_list()

    print("\n[0/5] 更新股票期貨排行資料（公開資料，每日收盤）...")
    print("       · 先拉 FinLab 近 1 年歷史「收盤價 + OI」（給 ranking OI 增減 fallback + 前端歷史價修正）...")
    refresh_stock_futures_finlab_history()
    refresh_stock_futures_ranking()

    print("\n[0b/5] 每日籌碼報告：等待主行情確認最新交易日...")

    print("\n[1/5] 載入資料...")
    data = load_data(use_cache=args.skip_finlab)
    refresh_daily_chip_report(latest_trade_date=data["close"].index[-1])

    print("[2/5] 計算個股指標...")
    stock_metrics = compute_stock_metrics(data)
    print(f"       ✓ {len(stock_metrics)} 檔個股")

    print("[3/5] 計算族群指標 + 相關題材...")
    group_metrics = compute_group_metrics(stock_metrics)
    company_topics = compute_company_topics()
    related = compute_related_topics(company_topics)
    print(f"       ✓ {len(group_metrics)} 個族群")

    print("[4/5] 產生 JSON 資料（熱力圖 + 搜尋）...")
    extras = load_extras()
    ai_summaries = load_ai_summaries()
    heatmap_data = build_heatmap_data(stock_metrics, data["name_map"])
    search_data = build_search_data(
        stock_metrics,
        data["name_map"],
        data["industry_map"],
        company_topics,
        disposal_map=extras.get("disposal", {}),
        market_map=data.get("market_map", {}),
        ai_summaries=ai_summaries,
    )
    write_json_data(heatmap_data, search_data)

    print("[5/5] 渲染 HTML...")
    copy_static()
    write_robots_txt()
    rich = load_company_rich()
    coverage = load_coverage()
    stock_profiles = load_stock_profiles()
    render_all(data, stock_metrics, group_metrics, related, company_topics, rich=rich, extras=extras, coverage=coverage, stock_profiles=stock_profiles, ai_summaries=ai_summaries)

    idx = DIST_DIR / "index.html"
    print(f"\n✓ 建置完成！打開：{idx}")
    if args.open:
        webbrowser.open(idx.as_uri())


if __name__ == "__main__":
    main()
