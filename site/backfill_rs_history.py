"""
backfill_rs_history.py — 一次性回填 RS 歷史（年 + 季）

從 .cache.parquet 的收盤價，逐日重算 RS 評分並寫入兩個 parquet：
  .cache_rs_history.parquet         — 年 RS（lookback 240 日，台股年線慣例）
  .cache_rs_history_quarter.parquet — 季 RS（lookback 60 日，台股季線慣例）

通常只需執行一次（首次部署或 cache 被刪後）。

用法：
  python site/backfill_rs_history.py                       # 回填近 250 日（年+季）
  python site/backfill_rs_history.py --days 60             # 自訂天數
  python site/backfill_rs_history.py --kind year           # 只回填年 RS
  python site/backfill_rs_history.py --kind quarter        # 只回填季 RS
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

SITE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SITE_DIR))

from build_site import compute_rs_scores, RS_HISTORY, RS_HISTORY_QUARTER, CACHE_FILE, CACHE_META

KIND_CONFIG = {
    "year":    {"lookback": 240, "path": RS_HISTORY,         "label": "年 RS"},
    "quarter": {"lookback": 60,  "path": RS_HISTORY_QUARTER, "label": "季 RS"},
}


def backfill_one(kind: str, close: pd.DataFrame, name_map: dict, market_map: dict, n_days: int) -> int:
    cfg = KIND_CONFIG[kind]
    lookback = cfg["lookback"]
    path = cfg["path"]
    label = cfg["label"]

    available = len(close) - lookback
    if available <= 0:
        print(f"[{kind}] 資料不足 {lookback}+1 日，無法回填")
        return 1
    days = min(n_days, available)
    print(f"[{kind}] 回填近 {days} 日 {label}（lookback={lookback}）...")

    history = {}
    for offset in range(days, 0, -1):
        sub = close.iloc[: len(close) - offset + 1]
        if len(sub) < lookback + 1:
            continue
        rs = compute_rs_scores(sub, name_map, market_map, lookback=lookback)
        if rs.empty:
            continue
        date = sub.index[-1]
        history[date] = rs
        idx = days - offset + 1
        if idx % 25 == 0 or idx == days:
            print(f"  [{kind}][{idx:>3}/{days}] {date.strftime('%Y-%m-%d')} 樣本 {len(rs)}")

    if not history:
        print(f"[{kind}] 未產出任何 RS，請檢查資料")
        return 1

    df = pd.DataFrame(history).T.sort_index().astype("Int64")
    print(f"[{kind}] 寫入 {path.name}: {df.shape}")
    df.to_parquet(path)
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=250, help="回填的歷史天數（默認 250）")
    p.add_argument("--kind", choices=["year", "quarter", "both"], default="both",
                   help="回填類型：year / quarter / both（默認 both）")
    args = p.parse_args()

    if not CACHE_FILE.exists() or not CACHE_META.exists():
        print(f"[backfill] 找不到 {CACHE_FILE.name}，請先跑 build_site.py")
        return 1

    print(f"[backfill] 從 {CACHE_FILE.name} 讀取收盤價...")
    combo = pd.read_parquet(CACHE_FILE)
    cols = [c for c in combo.columns if c.startswith("close|")]
    close = combo[cols].copy()
    close.columns = [c.split("|", 1)[1] for c in cols]
    print(f"[backfill] close shape: {close.shape}")

    meta = json.loads(CACHE_META.read_text(encoding="utf-8"))
    name_map = meta.get("name_map", {})
    market_map = meta.get("market_map", {})

    kinds = ["year", "quarter"] if args.kind == "both" else [args.kind]
    rc = 0
    for k in kinds:
        rc |= backfill_one(k, close, name_map, market_map, args.days)
    print("[backfill] OK 回填完成" if rc == 0 else "[backfill] 部分失敗")
    return rc


if __name__ == "__main__":
    sys.exit(main())
