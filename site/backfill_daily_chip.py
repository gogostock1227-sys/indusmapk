"""每日籌碼歷史回補腳本（256 個交易日 ≈ 1 年）。

用途：抓過去交易日的 4 個核心指標寫入 site/data/chip_history/YYYY-MM-DD.json，
供前端「歷史籌碼」頁面繪圖使用。

使用：
    python site/backfill_daily_chip.py                # 預設回補 270 個自然日（足夠覆蓋 1 年 252 交易日）
    python site/backfill_daily_chip.py --days 30      # 只補 30 天
    python site/backfill_daily_chip.py --start 2025-05-01 --end 2025-12-31

輸出 schema (精簡版，每天 ~600 bytes)：
{
  "date": "2026-05-04",
  "vix": 35.59,
  "spot":    {"foreign_yi": 632.85, "trust_yi": 55.14, "dealer_yi": 112.44, "total_yi": 800.42},
  "margin":  {"financing_balance_yi": 6413.43, "short_balance_lots": 234406},
  "futures": {"foreign_oi_lots": -43504, "dealer_oi_lots": -1964,
              "retail_mtx_net_lots": -2236, "retail_tmf_net_lots": -19070}
}

附加 site/data/chip_history/index.json 列出所有已抓日期 + 最近 30 天摘要。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from fetch_daily_chip_report import (
    RETAIL_PRODUCTS,
    extract_spot_rows,
    fetch_taifex_html,
    fetch_tpex_institution,
    fetch_tpex_margin,
    fetch_twse_institution,
    fetch_twse_margin,
    fetch_vix_file,
    find_row,
    future_rows,
    parse_int,
    recent_dates,
    slash_to_ymd,
    ymd_to_slash,
)


HISTORY_DIR = Path(__file__).parent / "data" / "chip_history"
INDEX_PATH = HISTORY_DIR / "index.json"
SLEEP_SECONDS = 1.2  # rate-limit 緩衝，避免 TWSE/TAIFEX 擋下


def _to_yi(value_ntd: float | int | None) -> float | None:
    """元 → 億，保留 2 位小數。"""
    if value_ntd is None:
        return None
    return round(float(value_ntd) / 1e8, 2)


def _to_yi_from_thousand(value_thousand: float | int | None) -> float | None:
    """仟元 → 億，保留 2 位小數。"""
    if value_thousand is None:
        return None
    return round(float(value_thousand) / 1e5, 2)


def _build_spot(date_ymd: str) -> dict | None:
    try:
        twse = fetch_twse_institution(date_ymd)
    except Exception:
        return None
    try:
        tpex = fetch_tpex_institution(ymd_to_slash(date_ymd))
    except Exception:
        tpex = {}

    listed = extract_spot_rows(twse.get("data", []), "上市")
    otc = extract_spot_rows((tpex.get("tables") or [{}])[0].get("data", []), "上櫃") if tpex else None

    def add(a: int | None, b: int | None) -> int | None:
        if a is None and b is None:
            return None
        return (a or 0) + (b or 0)

    foreign_total = add(listed["foreign"]["value"] if listed else None, otc["foreign"]["value"] if otc else None)
    trust_total = add(listed["trust"]["value"] if listed else None, otc["trust"]["value"] if otc else None)
    dealer_total = add(listed["dealer"]["value"] if listed else None, otc["dealer"]["value"] if otc else None)
    grand_total = add(listed["total"]["value"] if listed else None, otc["total"]["value"] if otc else None)

    if grand_total is None:
        return None
    return {
        "foreign_yi": _to_yi(foreign_total),
        "trust_yi": _to_yi(trust_total),
        "dealer_yi": _to_yi(dealer_total),
        "total_yi": _to_yi(grand_total),
    }


def _build_margin(date_ymd: str) -> dict | None:
    """從 TWSE+TPEx 融資融券拿合計餘額（億 / 張）。歷史日不查 Yahoo（Yahoo 只給最新）。"""
    try:
        twse = fetch_twse_margin(date_ymd)
    except Exception:
        return None
    try:
        tpex = fetch_tpex_margin(ymd_to_slash(date_ymd))
    except Exception:
        tpex = {}

    # TWSE 融資金額（仟元）
    twse_table = (twse.get("tables") or [{}])[0]
    twse_rows = {(r[0] or "").strip(): r for r in twse_table.get("data", []) if r}
    fin_amount_row = twse_rows.get("融資金額(仟元)")
    fin_amount_bal = parse_int(fin_amount_row[5]) if fin_amount_row else None

    # TWSE 融資 / 融券張數
    long_row = twse_rows.get("融資(交易單位)")
    short_row = twse_rows.get("融券(交易單位)")
    twse_long_bal = parse_int(long_row[5]) if long_row else None
    twse_short_bal = parse_int(short_row[5]) if short_row else None

    # TPEx 融資 / 融券張數（從 tables 加總）
    tpex_table = (tpex.get("tables") or [{}])[0] if tpex else {}
    fields = tpex_table.get("fields", [])
    data = tpex_table.get("data", [])

    def sum_field(name: str) -> int | None:
        if name not in fields:
            return None
        idx = fields.index(name)
        total = 0
        for row in data:
            v = parse_int(row[idx] if idx < len(row) else None)
            total += v or 0
        return total

    tpex_long_bal = sum_field("資餘額")
    tpex_short_bal = sum_field("券餘額")

    long_total_lots = (twse_long_bal or 0) + (tpex_long_bal or 0) if (twse_long_bal or tpex_long_bal) else None
    short_total_lots = (twse_short_bal or 0) + (tpex_short_bal or 0) if (twse_short_bal or tpex_short_bal) else None

    if long_total_lots is None and fin_amount_bal is None:
        return None
    return {
        "financing_balance_yi": _to_yi_from_thousand(fin_amount_bal),  # 上市融資金額（億），上櫃金額不易查歷史，先記上市
        "financing_lots_total": long_total_lots,                       # 融資餘額（張）：上市 + 上櫃
        "short_balance_lots": short_total_lots,                        # 融券餘額（張）：上市 + 上櫃
    }


def _build_futures(date_slash: str) -> dict | None:
    """期貨外資/自營 OI + 散戶留倉淨額（小台/微台）。"""
    try:
        from io import StringIO
        html, _ = fetch_taifex_html("futContractsDate", date_slash)
        dfs = pd.read_html(StringIO(html))
        if not dfs:
            return None
        df = dfs[-1]
        if df.empty or df.shape[1] < 10:
            return None
        rows = future_rows(df)
    except Exception:
        return None

    def oi_net(product: str, identity: str) -> int | None:
        r = find_row(rows, product, identity)
        if r is None:
            return None
        v = r.get("oi_net_lots")
        return int(v) if pd.notna(v) else None

    foreign_oi = oi_net("臺股期貨", "外資")
    dealer_oi = oi_net("臺股期貨", "自營商")

    def retail_net(product: str) -> int | None:
        total: int | None = 0
        for ident in ("外資", "投信", "自營商"):
            r = find_row(rows, product, ident)
            if r is None:
                if ident == "投信":
                    continue
                return None
            v = r.get("oi_net_lots")
            if pd.notna(v):
                total += int(v)
        return -total if total is not None else None

    return {
        "foreign_oi_lots": foreign_oi,
        "dealer_oi_lots": dealer_oi,
        "retail_mtx_net_lots": retail_net("小型臺指期貨"),
        "retail_tmf_net_lots": retail_net("微型臺指期貨"),
    }


def _build_vix(date_ymd: str) -> float | None:
    try:
        rows = fetch_vix_file(date_ymd)
        if not rows:
            return None
        # rows: list[(date_str, time_str, value)]，取當日最後一筆
        return round(float(rows[-1][2]), 2)
    except Exception:
        return None


def fetch_one_day(date_ymd: str) -> dict | None:
    """抓某一交易日完整 4 指標 JSON。任何 section 失敗整天跳過（避免存半殘資料）。"""
    spot = _build_spot(date_ymd)
    if spot is None:
        return None  # spot 失敗多半是非交易日，整天跳

    margin = _build_margin(date_ymd)
    futures = _build_futures(ymd_to_slash(date_ymd))
    vix = _build_vix(date_ymd)

    if margin is None and futures is None:
        return None  # 至少一個 chip section 才存

    return {
        "date": f"{date_ymd[:4]}-{date_ymd[4:6]}-{date_ymd[6:8]}",
        "vix": vix,
        "spot": spot,
        "margin": margin,
        "futures": futures,
    }


def write_index(history_dir: Path) -> None:
    """掃描所有 YYYY-MM-DD.json，重寫 index.json。"""
    files = sorted(history_dir.glob("*.json"))
    files = [f for f in files if f.name != "index.json"]
    dates = []
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            dates.append({
                "date": d["date"],
                "has_spot": d.get("spot") is not None,
                "has_margin": d.get("margin") is not None,
                "has_futures": d.get("futures") is not None,
                "has_vix": d.get("vix") is not None,
            })
        except Exception:
            continue
    index = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(dates),
        "first_date": dates[0]["date"] if dates else None,
        "last_date": dates[-1]["date"] if dates else None,
        "dates": [d["date"] for d in dates],  # 純日期列，前端 lazy fetch 用
    }
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[index] {len(dates)} days {dates[0]['date'] if dates else '—'} ~ {dates[-1]['date'] if dates else '—'}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=270, help="從今天往前回補 N 個自然日（預設 270，覆蓋 ~252 交易日）")
    parser.add_argument("--start", type=str, default=None, help="起始日 YYYY-MM-DD（覆蓋 --days）")
    parser.add_argument("--end", type=str, default=None, help="結束日 YYYY-MM-DD（預設今天）")
    parser.add_argument("--force", action="store_true", help="覆寫已存在的 JSON 檔（預設跳過）")
    parser.add_argument("--limit", type=int, default=None, help="本次最多抓 N 個交易日（debug 用）")
    args = parser.parse_args()

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    # 構造日期序列（從新到舊）
    end_dt = datetime.strptime(args.end, "%Y-%m-%d") if args.end else datetime.today()
    if args.start:
        start_dt = datetime.strptime(args.start, "%Y-%m-%d")
        days_span = (end_dt - start_dt).days + 1
    else:
        days_span = args.days
    candidates = [(end_dt - timedelta(days=i)) for i in range(days_span)]

    print(f"[backfill] target span: {candidates[-1].date()} ~ {candidates[0].date()} ({len(candidates)} 自然日)")

    fetched = 0
    skipped_existing = 0
    skipped_nodata = 0
    failed = 0
    for dt in candidates:
        ymd = dt.strftime("%Y%m%d")
        date_iso = dt.strftime("%Y-%m-%d")
        out_path = HISTORY_DIR / f"{date_iso}.json"
        if out_path.exists() and not args.force:
            skipped_existing += 1
            continue
        try:
            day_data = fetch_one_day(ymd)
        except KeyboardInterrupt:
            print("[backfill] interrupted")
            break
        except Exception as e:
            print(f"  [{date_iso}] EXC {e}")
            failed += 1
            time.sleep(SLEEP_SECONDS)
            continue
        if day_data is None:
            skipped_nodata += 1
        else:
            out_path.write_text(json.dumps(day_data, ensure_ascii=False, indent=2), encoding="utf-8")
            fetched += 1
            sp = day_data.get("spot") or {}
            fu = day_data.get("futures") or {}
            print(
                f"  [{date_iso}] OK  spot.total={sp.get('total_yi')}  fut.foreign={fu.get('foreign_oi_lots')}  vix={day_data.get('vix')}"
            )
        time.sleep(SLEEP_SECONDS)

        if args.limit and fetched >= args.limit:
            print(f"[backfill] hit --limit {args.limit}, stop")
            break

    print(f"\n[backfill] done: fetched={fetched}, skipped_existing={skipped_existing}, "
          f"skipped_nodata={skipped_nodata}, failed={failed}")

    write_index(HISTORY_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
