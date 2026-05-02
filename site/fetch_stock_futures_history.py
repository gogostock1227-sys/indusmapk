"""
fetch_stock_futures_history.py — 從 FinLab 拉股票期貨「收盤價 + OI」近 1 年資料。

資料源：
  - data.get('futures_price:收盤價')
  - data.get('futures_price:未沖銷契約數')

Mapping: {TAIFEX_product_code} + 'F一般' → 近月一般時段
（盤後資料以 'F盤後' 作 fallback）

輸出：
  site/.cache_stock_futures_history.json — { code: { close: {date: price}, open_interest: {date: oi} } }
  site/.cache_stock_futures_history.meta.json — TTL / 找不到的 codes 清單

用法：
  python fetch_stock_futures_history.py [--force] [--days=N]
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

SITE_DIR = Path(__file__).resolve().parent
RANKING_CACHE = SITE_DIR / ".cache_stock_futures_ranking.json"
OUT = SITE_DIR / ".cache_stock_futures_finlab_history.json"
META = SITE_DIR / ".cache_stock_futures_finlab_history.meta.json"

DEFAULT_DAYS_BACK = 365
SESSION_PRIORITY = ("F一般", "F盤後")


def need_refresh(max_age_hours: float) -> bool:
    if not OUT.exists() or not META.exists():
        return True
    try:
        meta = json.loads(META.read_text(encoding="utf-8"))
        return (time.time() - float(meta.get("ts", 0))) > max_age_hours * 3600
    except Exception:
        return True


def load_ranking_codes() -> set[str]:
    if not RANKING_CACHE.exists():
        return set()
    try:
        data = json.loads(RANKING_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return set()
    rows = data.get("rows") or data
    if not isinstance(rows, list):
        return set()
    return {str(r["product_code"]) for r in rows if r.get("product_code")}


def fetch_via_finlab(codes: set[str], days_back: int) -> tuple[dict, list]:
    from finlab import data as fl_data

    token = os.environ.get("FINLAB_TOKEN")
    if token:
        try:
            from finlab import login

            login(token)
        except Exception:
            pass

    df_close = fl_data.get("futures_price:收盤價")
    df_oi = fl_data.get("futures_price:未沖銷契約數")
    cutoff = (date.today() - timedelta(days=days_back)).isoformat()
    df_close = df_close[df_close.index >= cutoff]
    df_oi = df_oi[df_oi.index >= cutoff]

    out: dict[str, dict] = {}
    miss: list[str] = []
    for code in sorted(codes):
        col = None
        for suffix in SESSION_PRIORITY:
            cand = f"{code}{suffix}"
            if cand in df_close.columns:
                col = cand
                break
        if col is None:
            miss.append(code)
            continue
        close_series = df_close[col].dropna()
        oi_series = df_oi[col].dropna() if col in df_oi.columns else None
        if close_series.empty:
            miss.append(code)
            continue
        slot: dict[str, dict] = {
            "close": {str(d.date() if hasattr(d, "date") else d)[:10]: float(v) for d, v in close_series.items()},
        }
        if oi_series is not None and not oi_series.empty:
            slot["open_interest"] = {
                str(d.date() if hasattr(d, "date") else d)[:10]: int(v)
                for d, v in oi_series.items()
                if v == v  # NaN guard
            }
        out[code] = slot
    return out, miss


def main(max_age_hours: float = 22.0, force: bool = False, days_back: int = DEFAULT_DAYS_BACK) -> None:
    if not force and not need_refresh(max_age_hours):
        print(f"[history] cache 仍在 {max_age_hours}h TTL 內，跳過")
        return
    codes = load_ranking_codes()
    if not codes:
        print("[history] ranking cache 不存在，請先跑 fetch_stock_futures_ranking.py")
        return
    print(f"[history] 從 FinLab 拉 {len(codes)} 檔商品近 {days_back} 天 [收盤價 + OI]...")
    try:
        history, missing = fetch_via_finlab(codes, days_back=days_back)
    except Exception as e:
        print(f"[history] ⚠️ FinLab 抓取失敗：{type(e).__name__}: {e}")
        sys.exit(1)
    OUT.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
    META.write_text(
        json.dumps(
            {"ts": time.time(), "products": len(history), "missing": missing, "days_back": days_back},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    close_pts = sum(len((v.get("close") or {})) for v in history.values())
    oi_pts = sum(len((v.get("open_interest") or {})) for v in history.values())
    print(
        f"[history] ✓ 寫入 {len(history)} 商品 / 收盤價 {close_pts} 點 / OI {oi_pts} 點 → {OUT.name}"
    )
    if missing:
        head = missing[:10]
        tail = " …" if len(missing) > 10 else ""
        print(f"[history] ⚠️ FinLab 找不到 {len(missing)} 檔: {head}{tail}")


if __name__ == "__main__":
    force = "--force" in sys.argv
    days = DEFAULT_DAYS_BACK
    for arg in sys.argv[1:]:
        if arg.startswith("--days="):
            try:
                days = int(arg.split("=", 1)[1])
            except ValueError:
                pass
    main(force=force, days_back=days)
