"""
fetch_stock_futures_ranking.py - 以公開資料建立股票期貨排行資料。

資料源：
  - 期交所股票期貨/選擇權交易標的：商品代碼、標的證券、契約乘數
  - 期交所股票類保證金：原始保證金比例或 ETF 固定保證金
  - 政府開放資料：期貨每日交易行情

輸出：
  site/.cache_stock_futures_ranking.json

說明：
  本腳本不依賴 WantGoo。20 日均量與 OI 增減會用本地 history cache
  逐日累積；首次執行若只有一天資料，會標示可用天數。
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests


SITE_DIR = Path(__file__).resolve().parent
OUTPUT = SITE_DIR / ".cache_stock_futures_ranking.json"
HISTORY = SITE_DIR / ".cache_stock_futures_history.json"

STOCK_LIST_URL = "https://www.taifex.com.tw/cht/2/stockLists"
MARGIN_URL = "https://www.taifex.com.tw/cht/5/stockMarginingDetail"
INDEX_MARGIN_URL = "https://www.taifex.com.tw/cht/5/indexMarging"
DAILY_MARKET_URL = "https://www.taifex.com.tw/data_gov/taifex_open_data.asp?data_name=DailyMarketReportFut"
HISTORICAL_ZIP_URL = "https://www.taifex.com.tw/file/taifex/Dailydownload/DailydownloadCSV/Daily_{Y}_{M}_{D}.zip"

TIMEOUT = 35
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

SIZE_TO_CATEGORY = {
    "2000": "stock",
    "100": "mini_stock",
    "10000": "etf",
    "1000": "mini_etf",
}

TYPE_LABELS = {
    "stock": "個股期貨",
    "mini_stock": "小型個股期貨",
    "etf": "ETF期貨",
    "mini_etf": "小型ETF期貨",
}

INDEX_FUTURE_SPECS = {
    "TX": {"product_name": "臺股期貨", "contract_multiplier": 200},
    "MTX": {"product_name": "小型臺指期貨", "contract_multiplier": 50},
    "TMF": {"product_name": "微型臺指期貨", "contract_multiplier": 10},
}

ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
TD_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")


def clean_cell(value: str) -> str:
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    value = TAG_RE.sub("", value)
    value = value.replace("&nbsp;", " ").replace("\xa0", " ")
    value = value.replace("　", " ")
    return re.sub(r"\s+", " ", value).strip()


def fetch_text(url: str, encoding: str | None = None) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    if encoding:
        return r.content.decode(encoding, errors="ignore")
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "—", "nan", "NaN"}:
        return None
    text = text.replace(",", "").replace("%", "")
    text = text.replace("▲", "").replace("▼", "")
    try:
        return float(text)
    except ValueError:
        return None


def to_int(value: Any) -> int | None:
    num = to_float(value)
    if num is None:
        return None
    return int(round(num))


def parse_percent(value: Any) -> float | None:
    num = to_float(value)
    if num is None:
        return None
    return num / 100.0


def product_name(short_name: str, category: str) -> str:
    short_name = short_name.strip()
    if category == "stock":
        return f"{short_name}期貨"
    if category == "mini_stock":
        return f"小型{short_name}期貨"
    if category == "etf":
        return f"{short_name}期貨" if "ETF" in short_name.upper() else f"{short_name}ETF期貨"
    if category == "mini_etf":
        if "ETF" in short_name.upper():
            return f"小型{short_name}期貨"
        return f"小型{short_name}ETF期貨"
    return f"{short_name}期貨"


def parse_stock_lists(html: str) -> dict[str, dict]:
    products: dict[str, dict] = {}
    for row in ROW_RE.finditer(html):
        cells = [clean_cell(c) for c in TD_RE.findall(row.group(1))]
        if len(cells) < 12:
            continue
        code = cells[0].strip().upper()
        underlying_symbol = cells[2].strip().upper()
        short_name = cells[3].strip()
        size = cells[11].replace(",", "").strip()
        category = SIZE_TO_CATEGORY.get(size)
        if not category:
            continue
        if not re.fullmatch(r"[0-9A-Z]{2,5}", code):
            continue
        if not re.fullmatch(r"[0-9A-Z]{4,8}", underlying_symbol):
            continue
        multiplier = int(size)
        products[code] = {
            "product_code": code,
            "underlying_symbol": underlying_symbol,
            "underlying_name": cells[1].strip(),
            "underlying_short_name": short_name,
            "product_name": product_name(short_name, category),
            "category": category,
            "type_label": TYPE_LABELS.get(category, category),
            "contract_multiplier": multiplier,
            "regular_session": cells[-2] if len(cells) >= 2 else "",
            "after_hours_session": cells[-1] if len(cells) >= 1 else "",
        }
    return products


def parse_margining(html: str) -> dict[str, dict]:
    margins: dict[str, dict] = {}
    for row in ROW_RE.finditer(html):
        cells = [clean_cell(c) for c in TD_RE.findall(row.group(1))]
        if len(cells) < 7:
            continue
        code_raw = cells[1].strip().upper() if len(cells) > 1 else ""
        symbol = cells[2].strip().upper() if len(cells) > 2 else ""
        if not code_raw.endswith("F"):
            continue
        if not re.fullmatch(r"[0-9A-Z]{4,8}", symbol):
            continue
        code = code_raw[:-1]
        product = cells[3].strip() if len(cells) > 3 else ""
        last = cells[-1]
        info = {
            "product_code": code,
            "underlying_symbol": symbol,
            "product_name": product,
        }
        if "%" in last:
            info["settlement_margin_rate"] = parse_percent(cells[-3])
            info["maintenance_margin_rate"] = parse_percent(cells[-2])
            info["initial_margin_rate"] = parse_percent(cells[-1])
            info["margin_mode"] = "ratio"
        else:
            info["settlement_margin"] = to_int(cells[-3])
            info["maintenance_margin"] = to_int(cells[-2])
            info["initial_margin"] = to_int(cells[-1])
            info["margin_mode"] = "fixed"
        margins[code] = info
    return margins


def parse_index_margining(html: str) -> dict[str, dict]:
    margins: dict[str, dict] = {}
    for row in ROW_RE.finditer(html):
        cells = [clean_cell(c) for c in TD_RE.findall(row.group(1))]
        if len(cells) < 2:
            continue
        joined = " ".join(cells).upper()
        for code in INDEX_FUTURE_SPECS:
            if not re.search(rf"(^|[^A-Z]){code}([^A-Z]|$)", joined):
                continue
            nums = [to_int(cell) for cell in cells]
            nums = [num for num in nums if num is not None]
            if not nums:
                continue
            info = {
                "product_code": code,
                "initial_margin": nums[-1],
                "margin_mode": "fixed",
            }
            if len(nums) >= 3:
                info["settlement_margin"] = nums[-3]
                info["maintenance_margin"] = nums[-2]
            margins[code] = info
    return margins


def decode_csv_bytes(content: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "big5", "cp950"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("big5", errors="ignore")


def normalize_header(header: str) -> str:
    return (
        header.strip()
        .replace("*", "")
        .replace(" ", "")
        .replace("\ufeff", "")
    )


def parse_daily_market(content: bytes, product_codes: set[str]) -> tuple[str | None, dict[str, dict]]:
    text = decode_csv_bytes(content)
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for raw in reader:
        row = {normalize_header(k or ""): (v or "").strip() for k, v in raw.items()}
        if row:
            rows.append(row)
    if not rows:
        return None, {}

    date_keys = ("交易日期", "日期")
    code_keys = ("契約", "商品代號")
    month_keys = ("到期月份(週別)", "到期月份", "到期月")
    session_keys = ("交易時段",)

    def pick(row: dict, keys: tuple[str, ...]) -> str:
        for key in keys:
            if key in row:
                return row.get(key, "")
        return ""

    def normalize_contract_code(code: str) -> str:
        code = code.strip().upper()
        if code in product_codes:
            return code
        # 每日行情的股票期貨契約常帶 F 後綴（例：CD 股票清單、CDF 每日行情）。
        if code.endswith("F") and code[:-1] in product_codes:
            return code[:-1]
        return code

    dated_rows = []
    for row in rows:
        code = normalize_contract_code(pick(row, code_keys))
        if code not in product_codes:
            continue
        d = pick(row, date_keys).replace("/", "-")
        if not d:
            continue
        if re.fullmatch(r"\d{8}", d):
            d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        dated_rows.append((d, row))
    if not dated_rows:
        return None, {}

    latest_date = max(d for d, _ in dated_rows)
    latest_rows = [row for d, row in dated_rows if d == latest_date]
    regular_rows = [
        row for row in latest_rows
        if any("一般" in pick(row, session_keys) for _ in (0,))
    ]
    if regular_rows:
        latest_rows = regular_rows

    grouped: dict[str, list[dict]] = {}
    for row in latest_rows:
        code = normalize_contract_code(pick(row, code_keys))
        month = pick(row, month_keys).strip()
        if "/" in month:
            continue
        grouped.setdefault(code, []).append(row)

    selected: dict[str, dict] = {}
    for code, code_rows in grouped.items():
        def sort_key(row: dict):
            month = pick(row, month_keys).strip()
            digits = re.sub(r"\D", "", month)
            if not digits:
                digits = "99999999"
            price = to_float(row.get("最後成交價") or row.get("收盤價") or row.get("結算價"))
            has_price = 0 if price is not None else 1
            return (digits, has_price)

        row = sorted(code_rows, key=sort_key)[0]
        last_price = to_float(row.get("最後成交價") or row.get("收盤價"))
        settlement_price = to_float(row.get("結算價"))
        price = last_price if last_price is not None else settlement_price
        selected[code] = {
            "product_code": code,
            "trade_date": latest_date,
            "contract_month": pick(row, month_keys).strip(),
            "open_price": to_float(row.get("開盤價")),
            "high_price": to_float(row.get("最高價")),
            "low_price": to_float(row.get("最低價")),
            "future_price": price,
            "last_price": last_price,
            "change": to_float(row.get("漲跌價")),
            "change_pct": parse_percent(row.get("漲跌%")),
            "volume": to_int(row.get("合計成交量") or row.get("成交量")),
            "settlement_price": settlement_price,
            "open_interest": to_int(row.get("未沖銷契約數") or row.get("未沖銷契約量")),
            "best_bid": to_float(row.get("最後最佳買價")),
            "best_ask": to_float(row.get("最後最佳賣價")),
            "historical_high": to_float(row.get("歷史最高價")),
            "historical_low": to_float(row.get("歷史最低價")),
            "trading_session": pick(row, session_keys),
        }
    return latest_date, selected


def load_history() -> list[dict]:
    if not HISTORY.exists():
        return []
    try:
        data = json.loads(HISTORY.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def save_history(history: list[dict]) -> None:
    dates = sorted({str(r.get("trade_date")) for r in history if r.get("trade_date")})
    keep_dates = set(dates[-80:])
    trimmed = [r for r in history if str(r.get("trade_date")) in keep_dates]
    HISTORY.write_text(json.dumps(trimmed, ensure_ascii=False, indent=2), encoding="utf-8")


def load_finlab_history_oi() -> dict[str, dict[str, int]]:
    """Load FinLab cached OI series（{product_code: {date: oi}}），找不到則回空 dict。"""
    cache = SITE_DIR / ".cache_stock_futures_finlab_history.json"
    if not cache.exists():
        return {}
    try:
        raw = json.loads(cache.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, int]] = {}
    for code, slot in raw.items():
        if isinstance(slot, dict):
            oi_map = slot.get("open_interest")
            if isinstance(oi_map, dict):
                out[str(code)] = oi_map
    return out


def enrich_with_history(rows: dict[str, dict], trade_date: str | None) -> None:
    if not trade_date:
        return
    history = load_history()
    key = lambda r: (str(r.get("trade_date")), str(r.get("product_code")))
    current = []
    for row in rows.values():
        current.append({
            "trade_date": trade_date,
            "product_code": row.get("product_code"),
            "volume": row.get("volume"),
            "open_interest": row.get("open_interest"),
        })
    existing = {key(r): r for r in history}
    for row in current:
        existing[key(row)] = row
    history = list(existing.values())
    save_history(history)

    # FinLab cache：優先用，解決本地 80 天累積 cache 在第一次跑或假日空白的問題
    finlab_oi = load_finlab_history_oi()

    by_code: dict[str, list[dict]] = {}
    for row in history:
        by_code.setdefault(str(row.get("product_code")), []).append(row)
    for code, row in rows.items():
        series = sorted(by_code.get(code, []), key=lambda r: str(r.get("trade_date")))
        vols = [to_float(r.get("volume")) for r in series if to_float(r.get("volume")) is not None]
        last20 = vols[-20:]
        row["avg_volume_20d"] = round(sum(last20) / len(last20)) if last20 else None
        row["avg_volume_days"] = len(last20)

        # OI 增減：先試 FinLab → 找不到回退到本地 80 天 cache
        oi_change = None
        finlab_series = finlab_oi.get(code) or {}
        if finlab_series:
            dates_sorted = sorted(finlab_series.keys())
            if trade_date in dates_sorted:
                idx = dates_sorted.index(trade_date)
                if idx > 0 and row.get("open_interest") is not None:
                    try:
                        prev_oi = int(finlab_series[dates_sorted[idx - 1]])
                        oi_change = int(row["open_interest"]) - prev_oi
                    except (TypeError, ValueError):
                        pass
            else:
                # trade_date 不在 FinLab series — 取最末日當「昨日」近似（適用於剛收盤、FinLab 還沒同步）
                if dates_sorted and row.get("open_interest") is not None:
                    try:
                        prev_oi = int(finlab_series[dates_sorted[-1]])
                        oi_change = int(row["open_interest"]) - prev_oi
                    except (TypeError, ValueError):
                        pass
        if oi_change is None:
            prev = None
            for item in reversed(series[:-1]):
                if item.get("open_interest") is not None:
                    prev = item
                    break
            if prev and row.get("open_interest") is not None:
                oi_change = int(row["open_interest"]) - int(prev["open_interest"])
        row["open_interest_change"] = oi_change


def parse_oi_for_date(content: bytes, target_date: str, product_codes: set[str]) -> dict[str, dict]:
    """從歷史 CSV 中擷取 target_date 當日，每個 product_code 最近月的 (volume, open_interest)。"""
    text = decode_csv_bytes(content)
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict] = []
    for raw in reader:
        row = {normalize_header(k or ""): (v or "").strip() for k, v in raw.items()}
        if row:
            rows.append(row)
    if not rows:
        return {}

    date_keys = ("交易日期", "日期")
    code_keys = ("契約", "商品代號")
    month_keys = ("到期月份(週別)", "到期月份", "到期月")
    session_keys = ("交易時段",)

    def pick(row: dict, keys: tuple[str, ...]) -> str:
        for key in keys:
            if key in row:
                return row.get(key, "")
        return ""

    def normalize_contract_code(code: str) -> str:
        code = code.strip().upper()
        if code in product_codes:
            return code
        if code.endswith("F") and code[:-1] in product_codes:
            return code[:-1]
        return code

    same_day: list[tuple[str, dict]] = []
    for row in rows:
        code = normalize_contract_code(pick(row, code_keys))
        if code not in product_codes:
            continue
        d = pick(row, date_keys).replace("/", "-")
        if not d:
            continue
        if re.fullmatch(r"\d{8}", d):
            d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        if d != target_date:
            continue
        same_day.append((code, row))
    if not same_day:
        return {}

    regular = [(c, r) for c, r in same_day if "一般" in pick(r, session_keys)]
    if regular:
        same_day = regular

    grouped: dict[str, list[dict]] = {}
    for code, row in same_day:
        month = pick(row, month_keys).strip()
        if "/" in month:
            continue
        grouped.setdefault(code, []).append(row)

    out: dict[str, dict] = {}
    for code, code_rows in grouped.items():
        def sort_key(row: dict):
            month = pick(row, month_keys).strip()
            digits = re.sub(r"\D", "", month)
            return digits or "99999999"

        chosen = sorted(code_rows, key=sort_key)[0]
        out[code] = {
            "volume": to_int(chosen.get("合計成交量") or chosen.get("成交量")),
            "open_interest": to_int(chosen.get("未沖銷契約數") or chosen.get("未沖銷契約量")),
        }
    return out


def fetch_historical_csv(d: date) -> bytes | None:
    """從 TAIFEX 抓指定日期的 ZIP，解壓後回傳 CSV bytes。週末/休市 / 缺檔回 None。"""
    url = HISTORICAL_ZIP_URL.format(Y=d.strftime("%Y"), M=d.strftime("%m"), D=d.strftime("%d"))
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT, allow_redirects=False)
    except Exception as exc:
        print(f"[backfill] {d.isoformat()} 抓取錯誤：{exc}")
        return None
    if r.status_code in (302, 303, 307, 308, 404):
        return None
    if r.status_code != 200:
        print(f"[backfill] {d.isoformat()} 非預期 status：{r.status_code}")
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not csv_names:
                print(f"[backfill] {d.isoformat()} ZIP 內無 CSV")
                return None
            return zf.read(csv_names[0])
    except zipfile.BadZipFile:
        print(f"[backfill] {d.isoformat()} 非有效 ZIP")
        return None


def backfill_history(days: int) -> int:
    """從今日往回掃描，抓最多 `days` 個交易日的 OI 寫進 history。週末/休市自動略過。"""
    print(f"[backfill] 抓取交易標的：{STOCK_LIST_URL}")
    products = parse_stock_lists(fetch_text(STOCK_LIST_URL))
    product_codes = set(products) | set(INDEX_FUTURE_SPECS)
    print(f"[backfill] 目標契約 {len(product_codes)} 個")

    history = load_history()
    existing_keys = {(str(r.get("trade_date")), str(r.get("product_code"))) for r in history}

    new_rows: list[dict] = []
    fetched = 0
    today = date.today()
    max_offset = max(days * 2 + 5, days + 7)
    for offset in range(1, max_offset + 1):
        if fetched >= days:
            break
        d = today - timedelta(days=offset)
        if d.weekday() >= 5:
            continue
        content = fetch_historical_csv(d)
        if content is None:
            print(f"[backfill] {d.isoformat()} 無資料（休市/缺檔），略過")
            time.sleep(0.3)
            continue
        contracts = parse_oi_for_date(content, d.isoformat(), product_codes)
        added = 0
        for code, info in contracts.items():
            key = (d.isoformat(), code)
            if key in existing_keys:
                continue
            new_rows.append({
                "trade_date": d.isoformat(),
                "product_code": code,
                "volume": info.get("volume"),
                "open_interest": info.get("open_interest"),
            })
            existing_keys.add(key)
            added += 1
        print(f"[backfill] {d.isoformat()} → {len(contracts)} contracts（新增 {added}）")
        fetched += 1
        time.sleep(0.3)

    if not new_rows:
        print("[backfill] 沒有新增任何 history rows")
        return 0

    save_history(history + new_rows)
    print(f"[backfill] 累計寫入 {len(new_rows)} rows 到 {HISTORY.name}")
    return 0


def build_index_futures(quotes: dict[str, dict], margins: dict[str, dict]) -> list[dict]:
    rows = []
    for code, spec in INDEX_FUTURE_SPECS.items():
        quote = quotes.get(code, {})
        margin = margins.get(code, {})
        if not quote and not margin:
            continue
        merged = {
            "product_code": code,
            "underlying_symbol": "TAIEX",
            "underlying_name": "臺灣加權股價指數",
            "underlying_short_name": "加權指數",
            "product_name": spec["product_name"],
            "category": "index_future",
            "type_label": "指數期貨",
            "contract_multiplier": spec["contract_multiplier"],
            **quote,
        }
        for key in (
            "margin_mode",
            "initial_margin",
            "maintenance_margin",
            "settlement_margin",
        ):
            if key in margin:
                merged[key] = margin[key]
        merged["source_status"] = "official" if quote else "margin_only"
        rows.append(merged)
    return rows


def build_payload() -> dict:
    print(f"[stock-futures] 抓取交易標的：{STOCK_LIST_URL}")
    products = parse_stock_lists(fetch_text(STOCK_LIST_URL))
    print(f"[stock-futures] 交易標的 {len(products)} 筆")

    print(f"[stock-futures] 抓取保證金：{MARGIN_URL}")
    margins = parse_margining(fetch_text(MARGIN_URL))
    print(f"[stock-futures] 保證金 {len(margins)} 筆")

    print(f"[stock-futures] 抓取股價指數類保證金：{INDEX_MARGIN_URL}")
    try:
        index_margins = parse_index_margining(fetch_text(INDEX_MARGIN_URL))
    except Exception as exc:
        print(f"[stock-futures] 股價指數類保證金抓取失敗，改以 cache/fallback：{exc}")
        index_margins = {}
    print(f"[stock-futures] 股價指數類保證金 {len(index_margins)} 筆")

    print(f"[stock-futures] 抓取每日行情：{DAILY_MARKET_URL}")
    daily_resp = requests.get(DAILY_MARKET_URL, headers={"User-Agent": UA}, timeout=TIMEOUT)
    daily_resp.raise_for_status()
    trade_date, quotes = parse_daily_market(daily_resp.content, set(products) | set(INDEX_FUTURE_SPECS))
    print(f"[stock-futures] 每日行情 {len(quotes)} 筆（{trade_date or '無日期'}）")
    enrich_with_history(quotes, trade_date)

    rows = []
    for code, product in products.items():
        quote = quotes.get(code)
        if not quote:
            continue
        margin = margins.get(code, {})
        merged = {**product, **quote}
        if margin.get("product_name"):
            merged["product_name"] = margin["product_name"]
        for key in (
            "margin_mode",
            "initial_margin_rate",
            "maintenance_margin_rate",
            "settlement_margin_rate",
            "initial_margin",
            "maintenance_margin",
            "settlement_margin",
        ):
            if key in margin:
                merged[key] = margin[key]
        merged["source_status"] = "official"
        rows.append(merged)

    rows.sort(key=lambda r: (-(r.get("volume") or 0), r.get("product_code") or ""))
    index_futures = build_index_futures(quotes, index_margins)
    return {
        "as_of": trade_date or date.today().isoformat(),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": {
            "daily_market": DAILY_MARKET_URL,
            "stock_lists": STOCK_LIST_URL,
            "margining": MARGIN_URL,
            "index_margining": INDEX_MARGIN_URL,
        },
        "rows": rows,
        "index_futures": index_futures,
        "index_margins": index_margins,
        "counts": {
            "products": len(products),
            "margins": len(margins),
            "index_margins": len(index_margins),
            "quotes": len(quotes),
            "rows": len(rows),
            "index_futures": len(index_futures),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="抓取股票期貨排行；支援 --backfill-days 補 OI 歷史")
    parser.add_argument(
        "--backfill-days",
        type=int,
        default=0,
        help="從今日往回抓 N 個交易日的 OI 寫進 history（不更新當日 ranking）",
    )
    args = parser.parse_args(argv)

    if args.backfill_days > 0:
        return backfill_history(args.backfill_days)

    try:
        payload = build_payload()
    except Exception as exc:
        print(f"[stock-futures] 抓取失敗：{exc}")
        if OUTPUT.exists():
            print(f"[stock-futures] 沿用前次 cache：{OUTPUT.name}")
            return 0
        return 1

    if not payload["rows"]:
        print("[stock-futures] 警告：沒有可用排行列")
        if OUTPUT.exists():
            print(f"[stock-futures] 沿用前次 cache：{OUTPUT.name}")
            return 0
        return 1

    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[stock-futures] OK 已寫入 {OUTPUT.name}：{len(payload['rows'])} 筆")
    return 0


if __name__ == "__main__":
    sys.exit(main())
