"""
抓取外部開放資料：
  1. 處置股清單（TWSE + TPEx）
  2. 集保戶股權分散表（TDCC 每週）

輸出 site/.cache_extras.json，供 build_site.py 讀取。

用法：
  python site/fetch_extras.py           # 全抓（建議週一跑一次）
  python site/fetch_extras.py --only disposal
  python site/fetch_extras.py --only holders
"""
from __future__ import annotations
import argparse
import io
import json
import ssl
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
OUT  = HERE / ".cache_extras.json"

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

# TDCC 持股分級 代號 → 人類可讀名
# 1-999 / 1K-5K / 5K-10K / 10K-15K / 15K-20K / 20K-30K / 30K-40K / 40K-50K
# / 50K-100K / 100K-200K / 200K-400K / 400K-600K / 600K-800K / 800K-1M / 1M+
# (16 差異調整、17 合計 → 跳過，只保留 1-15)
LEVEL_LABELS = [
    "1-999",            # 1
    "1,000-5,000",      # 2
    "5,001-10,000",     # 3
    "10,001-15,000",    # 4
    "15,001-20,000",    # 5
    "20,001-30,000",    # 6
    "30,001-40,000",    # 7
    "40,001-50,000",    # 8
    "50,001-100,000",   # 9
    "100,001-200,000",  # 10
    "200,001-400,000",  # 11
    "400,001-600,000",  # 12
    "600,001-800,000",  # 13
    "800,001-1,000,000",# 14
    "1,000,001 以上",   # 15
]
# 三類分群用（1 張 = 1,000 股）
# 散戶: level 1-8 (≤50 張)
# 中實戶: level 9-11 (50~400 張)
# 大戶: level 12-15 (>400 張)
RETAIL_LEVELS = list(range(1, 9))
MID_LEVELS    = list(range(9, 12))
BIG_LEVELS    = list(range(12, 16))


def _fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"},
    )
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
        return r.read()


def _roc_to_ad(s: str) -> str:
    """民國日期 115/04/17 → 2026-04-17"""
    s = (s or "").strip().replace("-", "/").replace(".", "/")
    parts = s.split("/")
    if len(parts) == 3 and parts[0].isdigit():
        yr = int(parts[0])
        if yr < 200:
            yr += 1911
        try:
            return f"{yr:04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
        except ValueError:
            return s
    return s


# ═══════════════════════════════════════════
#   處置股
# ═══════════════════════════════════════════

def fetch_disposal_twse() -> dict:
    """TWSE 上市處置股清單。"""
    raw = _fetch("https://openapi.twse.com.tw/v1/announcement/punish")
    data = json.loads(raw)
    out = {}
    for row in data:
        code = str(row.get("Code", "")).strip()
        if not code or len(code) > 5:  # 過濾 6 碼權證
            continue
        period = row.get("DispositionPeriod", "") or ""
        start = end = ""
        for sep in ["～", "~", "至"]:
            if sep in period:
                start, end = period.split(sep, 1)
                break
        out[code] = {
            "status":  "處置中",
            "name":    row.get("Name", ""),
            "reason":  row.get("ReasonsOfDisposition", ""),
            "action":  row.get("DispositionMeasures", ""),
            "as_of":   _roc_to_ad(start),
            "end":     _roc_to_ad(end),
            "detail":  (row.get("Detail", "") or "").strip()[:240],
            "market":  "上市",
        }
    return out


def fetch_disposal_tpex() -> dict:
    """TPEx 上櫃處置股清單。"""
    raw = _fetch(
        "https://www.tpex.org.tw/web/bulletin/disposal_information/"
        "disposal_information_result.php?l=zh-tw"
    )
    data = json.loads(raw)
    out = {}
    tables = data.get("tables", [])
    if not tables:
        return out
    fields = tables[0].get("fields", [])
    col = {f: i for i, f in enumerate(fields)}
    def g(row, key, default=""):
        i = col.get(key)
        if i is None or i >= len(row):
            return default
        return str(row[i] if row[i] is not None else default)

    for row in tables[0].get("data", []):
        code = g(row, "證券代號").strip()
        if not code or len(code) > 5:
            continue
        period = g(row, "處置起訖時間")
        start = end = ""
        for sep in ["~", "～", "至"]:
            if sep in period:
                start, end = period.split(sep, 1)
                break
        name_raw = g(row, "證券名稱")
        name = name_raw.split("(")[0].strip() if "(" in name_raw else name_raw
        out[code] = {
            "status":  "處置中",
            "name":    name,
            "reason":  g(row, "處置原因"),
            "action":  g(row, "處置內容")[:240],
            "as_of":   _roc_to_ad(start),
            "end":     _roc_to_ad(end),
            "detail":  "",
            "market":  "上櫃",
        }
    return out


def fetch_disposal() -> dict:
    print("[disposal] 抓 TWSE 上市...")
    try:
        twse = fetch_disposal_twse()
        print(f"         ✓ {len(twse)} 檔")
    except Exception as e:
        print(f"         ✗ TWSE 失敗：{type(e).__name__}: {e}")
        twse = {}
    print("[disposal] 抓 TPEx 上櫃...")
    try:
        tpex = fetch_disposal_tpex()
        print(f"         ✓ {len(tpex)} 檔")
    except Exception as e:
        print(f"         ✗ TPEx 失敗：{type(e).__name__}: {e}")
        tpex = {}
    merged = {**twse, **tpex}
    print(f"[disposal] 合計 {len(merged)} 檔")
    return merged


# ═══════════════════════════════════════════
#   集保戶股權分散（TDCC）
# ═══════════════════════════════════════════

def fetch_holders_snapshot() -> tuple[str, dict]:
    """抓 TDCC 最新一週集保分級，回傳 (資料日, {sym: {h:[15], s:[15], p:[15]}})。"""
    print("[holders] 抓 TDCC 集保分級（約 2MB）...")
    raw = _fetch("https://opendata.tdcc.com.tw/getOD.ashx?id=1-5", timeout=90)
    text = raw.decode("utf-8-sig", errors="replace")
    df = pd.read_csv(io.StringIO(text), dtype={"證券代號": str, "持股分級": int})
    df = df.rename(columns={
        "占集保庫存數比例%": "pct",
        "股數": "shares",
        "人數": "holders",
    })
    df["shares"]  = pd.to_numeric(df["shares"],  errors="coerce").fillna(0)
    df["holders"] = pd.to_numeric(df["holders"], errors="coerce").fillna(0)
    df["pct"]     = pd.to_numeric(df["pct"],     errors="coerce").fillna(0)

    latest_date = str(df["資料日期"].iloc[0]) if "資料日期" in df.columns else ""
    if len(latest_date) == 8:
        latest_date = f"{latest_date[0:4]}-{latest_date[4:6]}-{latest_date[6:8]}"

    snap: dict = {}
    for code, sub in df.groupby("證券代號"):
        sym = str(code).strip().lstrip("0") or str(code).strip()
        if len(sym) > 5:
            continue
        # 只保留 level 1-15（忽略 16 差異調整、17 合計）
        sub = sub[(sub["持股分級"] >= 1) & (sub["持股分級"] <= 15)]
        if sub.empty:
            continue
        sub = sub.set_index("持股分級")
        h = [int(sub["holders"].get(i, 0)) for i in range(1, 16)]
        s = [int(sub["shares"].get(i, 0))  for i in range(1, 16)]
        p = [round(float(sub["pct"].get(i, 0.0)), 2) for i in range(1, 16)]
        if sum(h) == 0:
            continue
        snap[sym] = {"h": h, "s": s, "p": p}

    print(f"[holders] ✓ {len(snap)} 檔，資料日 {latest_date}")
    return latest_date, snap


def merge_holders_history(prev_hist: dict, new_date: str, new_snap: dict, keep_weeks: int = 20) -> dict:
    """把新一週併入現有歷史，保留最近 keep_weeks 週。
    結構：{sym: {date: {h, s, p}}, ...}"""
    hist = dict(prev_hist) if isinstance(prev_hist, dict) else {}
    all_syms = set(hist.keys()) | set(new_snap.keys())
    out = {}
    for sym in all_syms:
        by_date = dict(hist.get(sym, {}))
        if sym in new_snap:
            by_date[new_date] = new_snap[sym]
        # 依日期排序並保留最近 keep_weeks
        sorted_dates = sorted(by_date.keys())[-keep_weeks:]
        out[sym] = {d: by_date[d] for d in sorted_dates}
    return out


# ═══════════════════════════════════════════
#   主流程
# ═══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["disposal", "holders"], default=None)
    args = parser.parse_args()

    # 讀舊的，保留未更新的鍵
    prev = {}
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            prev = {}

    payload = {
        "fetched_at":       datetime.now().isoformat(timespec="seconds"),
        "disposal":         prev.get("disposal", {}),
        "holders_history":  prev.get("holders_history", {}),
        "holder_levels":    LEVEL_LABELS,
    }

    if args.only in (None, "disposal"):
        payload["disposal"] = fetch_disposal()
    if args.only in (None, "holders"):
        new_date, new_snap = fetch_holders_snapshot()
        payload["holders_history"] = merge_holders_history(
            payload.get("holders_history", {}), new_date, new_snap, keep_weeks=20,
        )
        # 統計：合併後有多少日期
        all_dates = set()
        for by_date in payload["holders_history"].values():
            all_dates.update(by_date.keys())
        print(f"[holders] 歷史週數：{len(all_dates)}（最新 {new_date}）")

    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    n_stocks = len(payload["holders_history"])
    print(f"[寫入] {OUT.name}  disposal={len(payload['disposal'])}  holders_stocks={n_stocks}")


if __name__ == "__main__":
    main()
