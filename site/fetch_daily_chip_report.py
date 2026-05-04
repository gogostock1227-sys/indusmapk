"""
每日台股籌碼報告抓取器。

資料來源：
- TWSE：上市三大法人買賣金額、上市信用交易統計
- TPEx：上櫃三大法人買賣金額、上櫃融資融券餘額
- TAIFEX：期貨三大法人、選擇權買賣權分計、臺指選擇權波動率指數

輸出：site/.cache_daily_chip_report.json
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd
import requests

try:
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    urllib3 = None


SITE_DIR = Path(__file__).resolve().parent
OUTPUT = SITE_DIR / ".cache_daily_chip_report.json"
TAIPEI_TZ = timezone(timedelta(hours=8))
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def now_taipei() -> datetime:
    return datetime.now(TAIPEI_TZ)


def parse_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("\u3000", "")
    if text in {"", "-", "--", "nan", "NaN"}:
        return None
    try:
        return int(float(text))
    except Exception:
        return None


def normalize_label(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").replace("\u3000", "")).strip()


def ymd_to_slash(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip().replace("/", "")
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}/{text[4:6]}/{text[6:]}"
    return str(value)


def slash_to_ymd(value: str) -> str:
    return value.replace("/", "")


def roc_to_ad_date(value: str | None) -> str:
    """將 115/04/30 轉成 2026/04/30；已是西元則原樣回傳。"""
    if not value:
        return ""
    parts = re.findall(r"\d+", str(value))
    if len(parts) < 3:
        return str(value)
    year = int(parts[0])
    if year < 1911:
        year += 1911
    return f"{year:04d}/{int(parts[1]):02d}/{int(parts[2]):02d}"


def fmt_yi_from_ntd(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value / 100_000_000:+,.2f} 億"


def fmt_yi_from_thousand(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value / 100_000:+,.2f} 億"


def fmt_yi_from_thousand_plain(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value / 100_000:,.2f} 億"


def fmt_yi_delta_from_thousand(value: int | None) -> str:
    if value is None:
        return "—"
    if value > 0:
        return f"{value / 100_000:,.2f} 億"
    return f"{value / 100_000:,.2f} 億"


def fmt_lots(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value:+,} 口"


def fmt_balance(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value:,} 張"


def fmt_delta_shares(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value:+,} 張"


def fmt_percent(value: int | float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f}%"


def class_for(value: int | float | None) -> str:
    if value is None:
        return "neutral"
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "neutral"


def trend_word(value: int | float | None, positive: str = "買超", negative: str = "賣超") -> str:
    if value is None:
        return "—"
    if value > 0:
        return positive
    if value < 0:
        return negative
    return "持平"


def metric(value: int | float | None, fmt: str = "yi_ntd") -> dict[str, Any]:
    if fmt == "lots":
        text = fmt_lots(int(value)) if value is not None else "—"
        cls = class_for(value)
    elif fmt == "balance":
        text = fmt_balance(int(value)) if value is not None else "—"
        cls = "neutral"
    elif fmt == "shares":
        text = fmt_delta_shares(int(value)) if value is not None else "—"
        cls = class_for(value)
    elif fmt == "yi_thousand":
        text = fmt_yi_from_thousand(int(value)) if value is not None else "—"
        cls = class_for(value)
    elif fmt == "yi_thousand_plain":
        text = fmt_yi_from_thousand_plain(int(value)) if value is not None else "—"
        cls = "neutral"
    elif fmt == "yi_thousand_delta":
        text = fmt_yi_delta_from_thousand(int(value)) if value is not None else "—"
        cls = class_for(value)
    elif fmt == "percent":
        text = fmt_percent(float(value)) if value is not None else "—"
        cls = "neutral"
    elif fmt == "percent_signed":
        text = f"{float(value):+,.2f}%" if value is not None else "—"
        cls = class_for(value)
    elif fmt == "balance_lots":
        text = f"{int(value):,} 口" if value is not None else "—"
        cls = "neutral"
    elif fmt == "number":
        text = f"{value:+,.2f}" if isinstance(value, float) else (f"{value:+,}" if value is not None else "—")
        cls = class_for(value)
    else:
        text = fmt_yi_from_ntd(int(value)) if value is not None else "—"
        cls = class_for(value)
    return {"value": value, "text": text, "class": cls}


def http_get_json(url: str, params: dict[str, Any] | None = None, verify: bool = True) -> dict:
    r = requests.get(
        url,
        params=params,
        headers={"User-Agent": UA},
        timeout=25,
        verify=verify,
    )
    r.raise_for_status()
    return r.json()


def http_post_json(url: str, data: dict[str, Any] | None = None, verify: bool = True) -> dict:
    r = requests.post(
        url,
        data=data or {},
        headers={"User-Agent": UA},
        timeout=25,
        verify=verify,
    )
    r.raise_for_status()
    return r.json()


def recent_dates(start_ymd: str, days: int = 12) -> list[str]:
    start = datetime.strptime(start_ymd, "%Y%m%d")
    return [(start - timedelta(days=i)).strftime("%Y%m%d") for i in range(days)]


def recent_months(start_ymd: str, months: int = 4) -> list[str]:
    year = int(start_ymd[:4])
    month = int(start_ymd[4:6])
    out: list[str] = []
    for _ in range(months):
        out.append(f"{year:04d}{month:02d}")
        month -= 1
        if month == 0:
            year -= 1
            month = 12
    return out


def fetch_twse_institution(date_ymd: str | None = None) -> dict:
    params = {"type": "day", "response": "json"}
    if date_ymd:
        params["dayDate"] = date_ymd
    j = http_get_json("https://www.twse.com.tw/rwd/zh/fund/BFI82U", params=params, verify=False)
    if j.get("stat") != "OK":
        raise RuntimeError(f"TWSE 法人資料失敗：{j.get('stat')}")
    return j


def fetch_previous_twse_institution(current_ymd: str) -> dict | None:
    for ymd in recent_dates(current_ymd, days=10)[1:]:
        try:
            j = fetch_twse_institution(ymd)
            if j.get("date") != current_ymd:
                return j
        except Exception:
            continue
    return None


def fetch_tpex_institution(date_slash: str | None = None) -> dict:
    data = {"type": "Daily", "prod": "1", "response": "json"}
    if date_slash:
        data["date"] = date_slash
    j = http_post_json("https://www.tpex.org.tw/www/zh-tw/insti/summary", data=data, verify=False)
    if j.get("stat") != "ok":
        raise RuntimeError(f"TPEx 法人資料失敗：{j.get('stat')}")
    return j


def fetch_previous_tpex_institution(current_ymd: str) -> dict | None:
    for ymd in recent_dates(current_ymd, days=10)[1:]:
        try:
            slash = ymd_to_slash(ymd)
            j = fetch_tpex_institution(slash)
            if j.get("date") != current_ymd:
                return j
        except Exception:
            continue
    return None


def extract_spot_rows(rows: list[list[str]], market: str) -> dict:
    by_name = {normalize_label(r[0]): r for r in rows if r}

    def net_by(labels: list[str]) -> int:
        total = 0
        found = False
        for label in labels:
            row = by_name.get(normalize_label(label))
            if row and len(row) >= 4:
                val = parse_int(row[3])
                if val is not None:
                    total += val
                    found = True
        return total if found else 0

    foreign = net_by(["外資及陸資(不含外資自營商)", "外資及陸資合計"])
    trust = net_by(["投信"])
    if market == "上市":
        dealer = net_by(["自營商(自行買賣)", "自營商(避險)"])
    else:
        dealer = net_by(["自營商合計"])
    total = foreign + trust + dealer
    return {
        "market": market,
        "foreign": metric(foreign),
        "trust": metric(trust),
        "dealer": metric(dealer),
        "total": metric(total),
        "foreign_word": trend_word(foreign),
        "trust_word": trend_word(trust),
        "dealer_word": trend_word(dealer),
    }


def build_spot_section() -> dict:
    twse = fetch_twse_institution()
    tpex = fetch_tpex_institution()
    twse_prev = fetch_previous_twse_institution(twse.get("date", ""))
    tpex_prev = fetch_previous_tpex_institution(tpex.get("date", ""))

    listed = extract_spot_rows(twse.get("data", []), "上市")
    otc = extract_spot_rows((tpex.get("tables") or [{}])[0].get("data", []), "上櫃")
    combined = {
        "market": "合計",
        "foreign": metric((listed["foreign"]["value"] or 0) + (otc["foreign"]["value"] or 0)),
        "trust": metric((listed["trust"]["value"] or 0) + (otc["trust"]["value"] or 0)),
        "dealer": metric((listed["dealer"]["value"] or 0) + (otc["dealer"]["value"] or 0)),
        "total": metric((listed["total"]["value"] or 0) + (otc["total"]["value"] or 0)),
    }
    leader = max(
        [("外資", combined["foreign"]["value"]), ("投信", combined["trust"]["value"]), ("自營商", combined["dealer"]["value"])],
        key=lambda x: abs(x[1] or 0),
    )
    summary = f"{leader[0]}主導現貨資金，合計三大法人{trend_word(combined['total']['value'])} {combined['total']['text']}。"
    return {
        "date": ymd_to_slash(twse.get("date")),
        "otc_date": ymd_to_slash(tpex.get("date")),
        "previous_date": ymd_to_slash(twse_prev.get("date")) if twse_prev else "",
        "previous_otc_date": ymd_to_slash(tpex_prev.get("date")) if tpex_prev else "",
        "markets": [listed, otc, combined],
        "total": combined,
        "summary": summary,
    }


def fetch_twse_margin(date_ymd: str | None = None) -> dict:
    params = {"selectType": "MS", "response": "json"}
    if date_ymd:
        params["date"] = date_ymd
    j = http_get_json("https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN", params=params, verify=False)
    if j.get("stat") != "OK":
        raise RuntimeError(f"TWSE 信用交易資料失敗：{j.get('stat')}")
    return j


def fetch_tpex_margin(date_slash: str | None = None) -> dict:
    data = {"response": "json"}
    if date_slash:
        data["date"] = date_slash
    j = http_post_json("https://www.tpex.org.tw/www/zh-tw/margin/balance", data=data, verify=False)
    if j.get("stat") != "ok":
        raise RuntimeError(f"TPEx 融資融券資料失敗：{j.get('stat')}")
    return j


def build_margin_from_twse(j: dict) -> dict:
    table = (j.get("tables") or [{}])[0]
    rows = {normalize_label(r[0]): r for r in table.get("data", []) if r}

    def pair(label: str) -> tuple[int | None, int | None]:
        row = rows.get(normalize_label(label))
        if not row:
            return None, None
        prev = parse_int(row[4])
        cur = parse_int(row[5])
        return cur, (cur - prev if cur is not None and prev is not None else None)

    long_bal, long_delta = pair("融資(交易單位)")
    short_bal, short_delta = pair("融券(交易單位)")
    financing_amount_bal, financing_amount_delta = pair("融資金額(仟元)")
    short_margin_ratio = (
        short_bal / long_bal * 100
        if short_bal is not None and long_bal not in {None, 0}
        else None
    )
    return {
        "market": "上市",
        "date": ymd_to_slash(j.get("date")),
        "financing_delta_amount": metric(financing_amount_delta, "yi_thousand_delta"),
        "financing_balance_amount": metric(financing_amount_bal, "yi_thousand_plain"),
        "short_delta": metric(short_delta, "shares"),
        "short_balance": metric(short_bal, "balance"),
        "short_margin_ratio": metric(short_margin_ratio, "percent"),
        "margin_long": metric(long_bal, "balance"),
        "margin_long_delta": metric(long_delta, "shares"),
        "margin_short": metric(short_bal, "balance"),
        "margin_short_delta": metric(short_delta, "shares"),
    }


def fetch_tpex_margin_yahoo() -> dict:
    url = "https://tw.stock.yahoo.com/_td-stock/api/resource/StockServices.twcredits;exchange=TWO"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[warning] fetch Yahoo twcredits failed: {e}", file=sys.stderr)
        return {}


def build_margin_from_tpex(j: dict) -> dict:
    table = (j.get("tables") or [{}])[0]
    fields = table.get("fields", [])
    data = table.get("data", [])

    def sum_field(name: str) -> int:
        if name not in fields:
            return 0
        idx = fields.index(name)
        total = 0
        for row in data:
            val = parse_int(row[idx] if idx < len(row) else None)
            total += val or 0
        return total

    prev_long = sum_field("前資餘額(張)")
    cur_long = sum_field("資餘額")
    prev_short = sum_field("前券餘額(張)")
    cur_short = sum_field("券餘額")
    date = j.get("date") or slash_to_ymd(roc_to_ad_date(table.get("date")))

    yahoo_delta_amount: int | None = None
    yahoo_bal_amount: int | None = None
    try:
        yj = fetch_tpex_margin_yahoo()
        credits_list = yj.get("credits", {}).get("list", [])
        if credits_list:
            latest = credits_list[0]
            # Yahoo unit is Million, our 'yi_thousand' formatter expects Thousand
            yahoo_delta_amount = int(float(latest.get("financingChangeM", 0)) * 1000)
            yahoo_bal_amount = int(float(latest.get("financingTotalM", 0)) * 1000)
    except Exception:
        pass

    return {
        "market": "上櫃",
        "date": ymd_to_slash(date),
        "financing_delta_amount": metric(yahoo_delta_amount, "yi_thousand_delta"),
        "financing_balance_amount": metric(yahoo_bal_amount, "yi_thousand_plain"),
        "short_delta": metric(cur_short - prev_short, "shares"),
        "short_balance": metric(cur_short, "balance"),
        "short_margin_ratio": metric(cur_short / cur_long * 100 if cur_long else None, "percent"),
        "margin_long": metric(cur_long, "balance"),
        "margin_long_delta": metric(cur_long - prev_long, "shares"),
        "margin_short": metric(cur_short, "balance"),
        "margin_short_delta": metric(cur_short - prev_short, "shares"),
        "financing_lots_note": f"融資張數 {fmt_delta_shares(cur_long - prev_long)} / {fmt_balance(cur_long)}",
    }


def build_margin_section() -> dict:
    twse = build_margin_from_twse(fetch_twse_margin())
    tpex = build_margin_from_tpex(fetch_tpex_margin())
    combined_long = (twse["margin_long"]["value"] or 0) + (tpex["margin_long"]["value"] or 0)
    combined_short = (twse["margin_short"]["value"] or 0) + (tpex["margin_short"]["value"] or 0)
    combined_long_delta = (twse["margin_long_delta"]["value"] or 0) + (tpex["margin_long_delta"]["value"] or 0)
    combined_short_delta = (twse["margin_short_delta"]["value"] or 0) + (tpex["margin_short_delta"]["value"] or 0)
    twse_f_delta = twse["financing_delta_amount"]["value"]
    twse_f_bal = twse["financing_balance_amount"]["value"]
    tpex_f_delta_combined = tpex["financing_delta_amount"]["value"]
    tpex_f_bal_combined = tpex["financing_balance_amount"]["value"]
    combined_f_delta = (
        (twse_f_delta or 0) + (tpex_f_delta_combined or 0)
        if (twse_f_delta is not None or tpex_f_delta_combined is not None) else None
    )
    combined_f_bal = (
        (twse_f_bal or 0) + (tpex_f_bal_combined or 0)
        if (twse_f_bal is not None or tpex_f_bal_combined is not None) else None
    )
    combined_ratio = (
        combined_short / combined_long * 100
        if combined_short is not None and combined_long not in {None, 0} else None
    )
    combined = {
        "market": "合計",
        "date": twse["date"] if twse["date"] == tpex["date"] else f"{twse['date']} / {tpex['date']}",
        "margin_long": metric(combined_long, "balance"),
        "margin_long_delta": metric(combined_long_delta, "shares"),
        "margin_short": metric(combined_short, "balance"),
        "margin_short_delta": metric(combined_short_delta, "shares"),
        "financing_delta_amount": metric(combined_f_delta, "yi_thousand_delta"),
        "financing_balance_amount": metric(combined_f_bal, "yi_thousand_plain"),
        "short_delta": metric(combined_short_delta, "shares"),
        "short_balance": metric(combined_short, "balance"),
        "short_margin_ratio": metric(combined_ratio, "percent"),
    }
    financing_delta_value = twse["financing_delta_amount"]["value"]
    short_delta_value = twse["short_delta"]["value"]
    
    tpex_f_delta = tpex["financing_delta_amount"]["value"]
    tpex_summary = f"上櫃融資 {tpex['margin_long_delta']['text']}、融券 {tpex['margin_short_delta']['text']}。"
    if tpex_f_delta is not None:
        tpex_summary = (
            f"上櫃融資金額{trend_word(tpex_f_delta, '增加', '減少')} {tpex['financing_delta_amount']['text'].replace('-', '')}，"
            f"融券{trend_word(tpex['short_delta']['value'], '增加', '減少')} {tpex['short_delta']['text'].replace('+', '').replace('-', '')}。"
        )

    summary = (
        f"上市融資金額較前日{trend_word(financing_delta_value, '增加', '減少')} {twse['financing_delta_amount']['text'].replace('-', '')}，"
        f"融券餘額{trend_word(short_delta_value, '增加', '減少')} {twse['short_delta']['text'].replace('+', '').replace('-', '')}；"
        + tpex_summary
    )
    return {
        "date": twse["date"],
        "market": "上市 / 上櫃",
        "twse": twse,
        "tpex_lots": tpex,
        "rows": [twse, tpex],
        "markets": [twse, tpex, combined],
        "total": combined,
        "summary": summary,
    }


def fetch_taifex_html(endpoint: str, date_slash: str | None = None) -> tuple[str, str]:
    url = f"https://www.taifex.com.tw/cht/3/{endpoint}"
    if date_slash:
        r = requests.post(
            url,
            data={
                "queryType": "1",
                "goDay": "",
                "doQuery": "1",
                "dateaddcnt": "",
                "queryDate": date_slash,
                "commodityId": "",
            },
            headers={"User-Agent": UA},
            timeout=25,
        )
    else:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=25)
    r.raise_for_status()
    r.encoding = "utf-8"
    date_match = re.search(r"value=['\"](\d{4}/\d{2}/\d{2})['\"]", r.text)
    return r.text, (date_slash or (date_match.group(1) if date_match else ""))


def taifex_df(endpoint: str, date_slash: str | None = None) -> tuple[pd.DataFrame, str]:
    html, actual_date = fetch_taifex_html(endpoint, date_slash)
    dfs = pd.read_html(StringIO(html))
    if not dfs:
        raise RuntimeError(f"TAIFEX {endpoint} 無表格")
    df = dfs[-1]
    if df.empty:
        raise RuntimeError(f"TAIFEX {endpoint} 表格為空")
    return df, actual_date


def fetch_previous_taifex_df(endpoint: str, current_slash: str) -> tuple[pd.DataFrame, str] | tuple[None, str]:
    current_ymd = slash_to_ymd(current_slash)
    for ymd in recent_dates(current_ymd, days=10)[1:]:
        slash = ymd_to_slash(ymd)
        try:
            df, actual = taifex_df(endpoint, slash)
            # 非交易日 TAIFEX 會回 shape=(1,2) 的「查無資料」假表，需以欄數過濾
            if not df.empty and df.shape[1] >= 10:
                return df, actual or slash
        except Exception:
            continue
    return None, ""


def future_rows(df: pd.DataFrame) -> pd.DataFrame:
    rows = df.copy()
    rows.columns = [
        "seq", "product", "identity",
        "trade_long_lots", "trade_long_amount",
        "trade_short_lots", "trade_short_amount",
        "trade_net_lots", "trade_net_amount",
        "oi_long_lots", "oi_long_amount",
        "oi_short_lots", "oi_short_amount",
        "oi_net_lots", "oi_net_amount",
    ]
    rows["product_norm"] = rows["product"].map(normalize_label)
    rows["identity_norm"] = rows["identity"].map(normalize_label)
    for col in rows.columns:
        if col.endswith("_lots") or col.endswith("_amount"):
            rows[col] = rows[col].map(parse_int)
    return rows


def option_rows(df: pd.DataFrame) -> pd.DataFrame:
    rows = df.copy()
    rows.columns = [
        "seq", "product", "right_type", "identity",
        "trade_buy_lots", "trade_buy_amount",
        "trade_sell_lots", "trade_sell_amount",
        "trade_net_lots", "trade_net_amount",
        "oi_buy_lots", "oi_buy_amount",
        "oi_sell_lots", "oi_sell_amount",
        "oi_net_lots", "oi_net_amount",
    ]
    rows["product_norm"] = rows["product"].map(normalize_label)
    rows["right_norm"] = rows["right_type"].map(normalize_label)
    rows["identity_norm"] = rows["identity"].map(normalize_label)
    for col in rows.columns:
        if col.endswith("_lots") or col.endswith("_amount"):
            rows[col] = rows[col].map(parse_int)
    return rows


def find_row(rows: pd.DataFrame, product: str, identity: str, right_type: str | None = None) -> pd.Series | None:
    mask = (rows["product_norm"] == normalize_label(product)) & (rows["identity_norm"] == normalize_label(identity))
    if right_type is not None:
        mask &= rows["right_norm"] == normalize_label(right_type)
    picked = rows.loc[mask]
    if picked.empty:
        return None
    return picked.iloc[0]


def futures_metric(current: pd.Series | None, previous: pd.Series | None, label: str) -> dict[str, Any]:
    cur_lots = int(current["oi_net_lots"]) if current is not None and pd.notna(current["oi_net_lots"]) else None
    prev_lots = int(previous["oi_net_lots"]) if previous is not None and pd.notna(previous["oi_net_lots"]) else None
    cur_amount = int(current["oi_net_amount"]) if current is not None and pd.notna(current["oi_net_amount"]) else None
    delta = cur_lots - prev_lots if cur_lots is not None and prev_lots is not None else None
    trade_net = int(current["trade_net_lots"]) if current is not None and pd.notna(current["trade_net_lots"]) else None
    return {
        "label": label,
        "oi_lots": metric(cur_lots, "lots"),
        "oi_amount": metric(cur_amount, "yi_thousand"),
        "delta_lots": metric(delta, "lots"),
        "trade_net_lots": metric(trade_net, "lots"),
        "stance": trend_word(cur_lots, "偏多", "偏空"),
    }


DAILY_MARKET_URL = "https://www.taifex.com.tw/data_gov/taifex_open_data.asp?data_name=DailyMarketReportFut"

RETAIL_PRODUCTS: tuple[tuple[str, str, str], ...] = (
    ("小型臺指期貨", "MTX", "小台指"),
    ("微型臺指期貨", "TMF", "微台指"),
)


def fetch_total_oi_by_product(product_codes: tuple[str, ...] = ("MTX", "TMF")) -> dict[str, int | None]:
    """從 TAIFEX 政府開放資料抓全市場 OI（同商品所有月份合計，僅一般交易時段、排除週別合約）。"""
    try:
        r = requests.get(DAILY_MARKET_URL, headers={"User-Agent": UA}, timeout=25)
        r.raise_for_status()
    except Exception as e:
        print(f"[warning] fetch DailyMarketReportFut failed: {e}", file=sys.stderr)
        return {code: None for code in product_codes}

    text: str | None = None
    for enc in ("utf-8-sig", "utf-8", "big5", "cp950"):
        try:
            text = r.content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = r.content.decode("big5", errors="ignore")

    reader = csv.DictReader(io.StringIO(text))
    code_keys = ("契約", "商品代號")
    month_keys = ("到期月份(週別)", "到期月份", "到期月")
    session_keys = ("交易時段",)
    oi_keys = ("未沖銷契約數", "未沖銷契約量")
    date_keys = ("交易日期", "日期")

    def pick(row: dict, keys: tuple[str, ...]) -> str:
        for key in keys:
            if key in row:
                return (row.get(key) or "").strip()
        return ""

    target_codes = set(product_codes)
    sums: dict[str, int] = {code: 0 for code in target_codes}
    seen: dict[str, bool] = {code: False for code in target_codes}
    latest_date: str = ""

    for raw in reader:
        row = {(k or "").strip().replace("*", "").replace("﻿", ""): (v or "").strip() for k, v in raw.items()}
        if not row:
            continue
        code = pick(row, code_keys).upper()
        if code.endswith("F") and code[:-1] in target_codes:
            code = code[:-1]
        if code not in target_codes:
            continue
        session = pick(row, session_keys)
        if session and "一般" not in session:
            continue
        month = pick(row, month_keys)
        if "/" in month:  # 排除週合約
            continue
        oi_str = ""
        for k in oi_keys:
            if k in row and row[k]:
                oi_str = row[k]
                break
        oi = parse_int(oi_str)
        if oi is None:
            continue
        sums[code] += oi
        seen[code] = True
        d = pick(row, date_keys)
        if d > latest_date:
            latest_date = d

    return {code: (sums[code] if seen[code] else None) for code in target_codes}


def build_retail_longshort_rows(cur_rows: pd.DataFrame) -> list[dict]:
    """根據 §2 已抓的 future_rows DataFrame，計算小台/微台散戶多空比。

    公式：散戶多空比 = -1 × 三大法人淨持倉 / 全市場OI × 100
    其中三大法人 = 外資 + 投信 + 自營商，全市場OI 從 DailyMarketReportFut 各月份加總。
    """
    total_oi = fetch_total_oi_by_product(tuple(code for _, code, _ in RETAIL_PRODUCTS))
    out: list[dict] = []
    for product_norm, code, short_label in RETAIL_PRODUCTS:
        institutional_net: int | None = 0
        for identity in ("外資", "投信", "自營商"):
            r = find_row(cur_rows, product_norm, identity)
            if r is None:
                if identity == "投信":
                    # 小台/微台投信常為零部位，列缺視為 0
                    continue
                institutional_net = None
                break
            v = r.get("oi_net_lots")
            if pd.notna(v):
                institutional_net += int(v)
        market_oi = total_oi.get(code)
        if institutional_net is None or not market_oi:
            ratio = None
            retail_net = None
        else:
            retail_net = -institutional_net
            ratio = retail_net / market_oi * 100
        out.append({
            "label": short_label,
            "product_name": product_norm,
            "product_code": code,
            "ratio": metric(ratio, "percent_signed"),
            "retail_net_lots": metric(retail_net, "lots"),
            "institutional_net_lots": metric(institutional_net, "lots"),
            "total_oi_lots": metric(market_oi, "balance_lots"),
        })
    return out


def build_futures_section() -> dict:
    cur_df, cur_date = taifex_df("futContractsDate")
    prev_df, prev_date = fetch_previous_taifex_df("futContractsDate", cur_date)
    cur = future_rows(cur_df)
    prev = future_rows(prev_df) if prev_df is not None else pd.DataFrame()

    def prev_row(identity: str) -> pd.Series | None:
        if prev.empty:
            return None
        return find_row(prev, "臺股期貨", identity)

    rows = [
        futures_metric(find_row(cur, "臺股期貨", "外資"), prev_row("外資"), "外資"),
        futures_metric(find_row(cur, "臺股期貨", "自營商"), prev_row("自營商"), "自營商"),
    ]

    try:
        retail_rows = build_retail_longshort_rows(cur)
    except Exception as e:
        print(f"[warning] retail longshort failed: {e}", file=sys.stderr)
        retail_rows = []

    return {
        "date": cur_date,
        "previous_date": prev_date,
        "product": "臺股期貨",
        "rows": rows,
        "foreign": rows[0],
        "dealer": rows[1],
        "summary": f"外資臺股期貨未平倉淨額 {rows[0]['oi_lots']['text']}，較前日 {rows[0]['delta_lots']['text']}。",
        "retail_rows": retail_rows,
        "retail_note": "散戶留倉淨額 = 全市場 OI − 三大法人；多空比為反向指標（散戶看多 → 大盤可能回檔）。",
    }


def option_signal(right_type: str, value: int | None) -> dict[str, Any]:
    """依買權/賣權增減判斷 BC、SC、BP、SP 與多空意圖。"""
    if value is None or value == 0:
        return {
            "code": "—",
            "label": "無明顯變化",
            "bias": "中性",
            "bias_key": "neutral",
            "class": "intent-neutral",
        }
    if right_type == "買權":
        if value > 0:
            return {"code": "BC", "label": "Buy Call", "bias": "偏多", "bias_key": "bullish", "class": "intent-bullish"}
        return {"code": "SC", "label": "Sell Call", "bias": "偏空", "bias_key": "bearish", "class": "intent-bearish"}
    if value < 0:
        return {"code": "SP", "label": "Sell Put", "bias": "偏多", "bias_key": "bullish", "class": "intent-bullish"}
    return {"code": "BP", "label": "Buy Put", "bias": "偏空", "bias_key": "bearish", "class": "intent-bearish"}


def option_combo(call_signal: dict[str, Any] | None, put_signal: dict[str, Any] | None) -> dict[str, Any]:
    signals = [s for s in [call_signal, put_signal] if s and s.get("code") != "—"]
    code = "+".join(s["code"] for s in signals) if signals else "—"
    bias_keys = {s["bias_key"] for s in signals if s.get("bias_key") in {"bullish", "bearish"}}
    if bias_keys == {"bullish"}:
        bias, cls = "偏多", "intent-bullish"
    elif bias_keys == {"bearish"}:
        bias, cls = "偏空", "intent-bearish"
    elif bias_keys == {"bullish", "bearish"}:
        bias, cls = "多空分歧", "intent-mixed"
    else:
        bias, cls = "中性", "intent-neutral"
    reading = {
        "BC+SP": "買權加碼、賣權減碼，偏多進攻",
        "SC+BP": "買權減碼、賣權加碼，偏空防守",
        "BC+BP": "買權與賣權同步加碼，偏向波動放大",
        "SC+SP": "買權與賣權同步減碼，偏向區間收斂",
    }.get(code, bias)
    return {"code": code, "bias": bias, "class": cls, "reading": reading}


def option_metric(current: pd.Series | None, previous: pd.Series | None, identity: str, right_type: str) -> dict[str, Any]:
    cur_lots = int(current["oi_net_lots"]) if current is not None and pd.notna(current["oi_net_lots"]) else None
    prev_lots = int(previous["oi_net_lots"]) if previous is not None and pd.notna(previous["oi_net_lots"]) else None
    cur_amount = int(current["oi_net_amount"]) if current is not None and pd.notna(current["oi_net_amount"]) else None
    prev_amount = int(previous["oi_net_amount"]) if previous is not None and pd.notna(previous["oi_net_amount"]) else None
    trade_lots = int(current["trade_net_lots"]) if current is not None and pd.notna(current["trade_net_lots"]) else None
    trade_amount = int(current["trade_net_amount"]) if current is not None and pd.notna(current["trade_net_amount"]) else None
    delta = cur_lots - prev_lots if cur_lots is not None and prev_lots is not None else None
    delta_amount = cur_amount - prev_amount if cur_amount is not None and prev_amount is not None else None
    return {
        "identity": identity,
        "right": right_type,
        "tag": "CALL" if right_type == "買權" else "PUT",
        "oi_lots": metric(cur_lots, "lots"),
        "oi_amount": metric(cur_amount, "yi_thousand"),
        "delta_lots": metric(delta, "lots"),
        "delta_amount": metric(delta_amount, "yi_thousand"),
        "lot_signal": option_signal(right_type, delta),
        "amount_signal": option_signal(right_type, delta_amount),
        "trade_net_lots": metric(trade_lots, "lots"),
        "trade_net_amount": metric(trade_amount, "yi_thousand"),
    }


def build_options_section() -> dict:
    cur_df, cur_date = taifex_df("callsAndPutsDate")
    prev_df, prev_date = fetch_previous_taifex_df("callsAndPutsDate", cur_date)
    cur = option_rows(cur_df)
    prev = option_rows(prev_df) if prev_df is not None else pd.DataFrame()

    rows = []
    for identity in ["外資", "自營商"]:
        for right_type in ["買權", "賣權"]:
            cur_row = find_row(cur, "臺指選擇權", identity, right_type)
            prev_row = None if prev.empty else find_row(prev, "臺指選擇權", identity, right_type)
            rows.append(option_metric(cur_row, prev_row, identity, right_type))

    identities = []
    for identity in ["外資", "自營商"]:
        call_row = next((r for r in rows if r["identity"] == identity and r["right"] == "買權"), None)
        put_row = next((r for r in rows if r["identity"] == identity and r["right"] == "賣權"), None)
        identities.append({
            "identity": identity,
            "call_row": call_row,
            "put_row": put_row,
            "lot_combo": option_combo(call_row.get("lot_signal") if call_row else None, put_row.get("lot_signal") if put_row else None),
            "amount_combo": option_combo(call_row.get("amount_signal") if call_row else None, put_row.get("amount_signal") if put_row else None),
        })

    foreign_call = next((r for r in rows if r["identity"] == "外資" and r["right"] == "買權"), None)
    foreign_put = next((r for r in rows if r["identity"] == "外資" and r["right"] == "賣權"), None)
    foreign_group = next((g for g in identities if g["identity"] == "外資"), None)
    summary = ""
    if foreign_call and foreign_put and foreign_group:
        summary = (
            f"外資口數 {foreign_group['lot_combo']['code']}（{foreign_group['lot_combo']['bias']}），"
            f"資金 {foreign_group['amount_combo']['code']}（{foreign_group['amount_combo']['bias']}）。"
        )
    return {
        "date": cur_date,
        "previous_date": prev_date,
        "product": "臺指選擇權",
        "rows": rows,
        "identities": identities,
        "summary": summary,
    }


def latest_vix_date() -> str:
    r = requests.get("https://www.taifex.com.tw/cht/7/vixMinNew", headers={"User-Agent": UA}, timeout=25)
    r.raise_for_status()
    r.encoding = "utf-8"
    dates = re.findall(r"getVixData\?filesname=(\d{8})", r.text)
    if dates:
        return dates[0]
    return now_taipei().strftime("%Y%m%d")


def fetch_vix_file(date_ymd: str) -> list[tuple[str, str, float]]:
    url = f"https://www.taifex.com.tw/cht/7/getVixData?filesname={date_ymd}"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=25)
    r.raise_for_status()
    text = r.content.decode("big5", errors="ignore")
    rows: list[tuple[str, str, float]] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3 or not parts[0].isdigit():
            continue
        try:
            rows.append((parts[0], parts[1], float(parts[-1])))
        except Exception:
            continue
    return rows


def fetch_vix_daily_month_file(month_ym: str) -> list[tuple[str, str, float]]:
    url = f"https://www.taifex.com.tw/file/taifex/Dailydownload/vix/log2data/{month_ym}new.txt"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=25)
    r.raise_for_status()
    text = r.content.decode("big5", errors="ignore")
    if "<html" in text.lower() or "404" in text[:200]:
        return []
    rows: list[tuple[str, str, float]] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3 or not parts[0].isdigit():
            continue
        try:
            rows.append((parts[0], parts[1] if len(parts) > 1 else "", float(parts[-1])))
        except Exception:
            continue
    return rows


def fetch_recent_vix_daily_rows(start_ymd: str) -> list[tuple[str, str, float]]:
    rows: list[tuple[str, str, float]] = []
    seen: set[tuple[str, str]] = set()
    for month_ym in recent_months(start_ymd, months=4):
        try:
            for row in fetch_vix_daily_month_file(month_ym):
                key = (row[0], row[1])
                if key not in seen:
                    rows.append(row)
                    seen.add(key)
        except Exception:
            continue
    rows.sort(key=lambda row: (row[0], row[1]))
    return rows


def build_vix_section() -> dict:
    listed_date = latest_vix_date()
    daily_rows = fetch_recent_vix_daily_rows(listed_date)
    if not daily_rows:
        raise RuntimeError("TAIFEX VIX 無有效資料")
    latest = daily_rows[-1]
    current_date = latest[0]
    previous = daily_rows[-2] if len(daily_rows) >= 2 else None
    previous_value = previous[2] if previous else None
    previous_date = ymd_to_slash(previous[0]) if previous else ""
    value = latest[2] if latest else None
    change = value - previous_value if value is not None and previous_value is not None else None
    return {
        "date": ymd_to_slash(current_date),
        "time": latest[1] if latest else "",
        "value": value,
        "value_text": f"{value:.2f}" if value is not None else "—",
        "change": metric(change, "number") if change is not None else metric(None, "number"),
        "previous_date": previous_date,
    }


def safe_section(name: str, builder) -> tuple[dict | None, str | None]:
    try:
        return builder(), None
    except Exception as exc:
        return None, f"{name}: {exc}"


REPORT_SECTIONS = ("spot", "margin", "futures", "options", "vix")


def parse_report_date(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text.replace("-", "/") if fmt == "%Y/%m/%d" else text, fmt)
        except Exception:
            continue
    return None


def report_date_key(value: str | None):
    parsed = parse_report_date(value)
    return parsed.date() if parsed else None


def load_existing_report(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[daily-chip] warning: read existing cache failed: {exc}", file=sys.stderr)
    return None


def section_date_key(section: dict | None):
    if not isinstance(section, dict):
        return None
    return report_date_key(section.get("date"))


def merge_report_with_existing_sections(report: dict, existing: dict | None) -> dict:
    if not existing or existing.get("report_date") != report.get("report_date"):
        return report

    recovered = []
    for key in REPORT_SECTIONS:
        if not report.get(key) and existing.get(key):
            report[key] = existing[key]
            recovered.append(key)
            continue
        report_section_date = section_date_key(report.get(key))
        existing_section_date = section_date_key(existing.get(key))
        if existing_section_date and report_section_date and report_section_date < existing_section_date:
            report[key] = existing[key]
            recovered.append(key)

    if not recovered:
        return report

    old_errors = list(report.get("errors") or [])
    prior_recovered = list(existing.get("recovered_sections") or [])
    report["recovered_sections"] = sorted(set(prior_recovered + recovered))
    if old_errors:
        report["recovered_errors"] = old_errors
    if all(report.get(key) for key in REPORT_SECTIONS):
        report["errors"] = []
        report["status"] = "ok"
    else:
        report["status"] = "partial" if report.get("errors") else "ok"
    return report


def _metric_value(row: dict | None, key: str) -> int | float | None:
    if not isinstance(row, dict):
        return None
    item = row.get(key)
    if not isinstance(item, dict):
        return None
    return item.get("value")


def _sum_present(*values):
    picked = [v for v in values if v is not None]
    return sum(picked) if picked else None


def normalize_margin_total_fields(report: dict) -> dict:
    margin = report.get("margin")
    if not isinstance(margin, dict):
        return report
    markets = margin.get("markets")
    if not isinstance(markets, list) or len(markets) < 3:
        return report

    twse = margin.get("twse") if isinstance(margin.get("twse"), dict) else markets[0]
    tpex = margin.get("tpex_lots") if isinstance(margin.get("tpex_lots"), dict) else markets[1]
    total = markets[2]
    if not isinstance(total, dict):
        return report

    if "financing_delta_amount" not in total:
        total["financing_delta_amount"] = metric(
            _sum_present(_metric_value(twse, "financing_delta_amount"), _metric_value(tpex, "financing_delta_amount")),
            "yi_thousand_delta",
        )
    if "financing_balance_amount" not in total:
        total["financing_balance_amount"] = metric(
            _sum_present(_metric_value(twse, "financing_balance_amount"), _metric_value(tpex, "financing_balance_amount")),
            "yi_thousand_plain",
        )
    if "short_delta" not in total:
        total["short_delta"] = total.get("margin_short_delta") or metric(
            _sum_present(_metric_value(twse, "short_delta"), _metric_value(tpex, "short_delta")),
            "shares",
        )
    if "short_balance" not in total:
        total["short_balance"] = total.get("margin_short") or metric(
            _sum_present(_metric_value(twse, "short_balance"), _metric_value(tpex, "short_balance")),
            "balance",
        )
    if "short_margin_ratio" not in total:
        short_bal = _metric_value(total, "short_balance")
        long_bal = _metric_value(total, "margin_long")
        ratio = short_bal / long_bal * 100 if short_bal is not None and long_bal not in {None, 0} else None
        total["short_margin_ratio"] = metric(ratio, "percent")
    return report


def normalize_report_for_template(report: dict) -> dict:
    return normalize_margin_total_fields(report)


def should_preserve_existing_cache(report: dict, existing: dict | None, force: bool) -> bool:
    if force or not existing:
        return False
    report_dt = report_date_key(report.get("report_date"))
    existing_dt = report_date_key(existing.get("report_date"))
    if not report_dt:
        return False
    if existing_dt and report_dt < existing_dt:
        return True
    return False


def build_report() -> dict:
    generated = now_taipei()
    errors: list[str] = []
    spot, err = safe_section("現貨法人", build_spot_section)
    if err:
        errors.append(err)
    margin, err = safe_section("融資融券", build_margin_section)
    if err:
        errors.append(err)
    futures, err = safe_section("期貨", build_futures_section)
    if err:
        errors.append(err)
    options, err = safe_section("選擇權", build_options_section)
    if err:
        errors.append(err)
    vix, err = safe_section("臺指 VIX", build_vix_section)
    if err:
        errors.append(err)

    primary_source_dates = [
        s.get("date")
        for s in [spot, margin, futures, options]
        if isinstance(s, dict) and s.get("date")
    ]
    source_dates = primary_source_dates or [
        s.get("date")
        for s in [vix]
        if isinstance(s, dict) and s.get("date")
    ]
    report_date = max(source_dates) if source_dates else now_taipei().strftime("%Y/%m/%d")
    return {
        "generated_at": generated.isoformat(timespec="seconds"),
        "generated_at_label": generated.strftime("%Y/%m/%d"),
        "status": "partial" if errors else "ok",
        "errors": errors,
        "report_date": report_date,
        "spot": spot,
        "margin": margin,
        "futures": futures,
        "options": options,
        "vix": vix,
        "sources": [
            {"name": "TWSE", "url": "https://www.twse.com.tw/rwd/zh/fund/BFI82U"},
            {"name": "TPEx", "url": "https://www.tpex.org.tw/www/zh-tw/insti/summary"},
            {"name": "TAIFEX 期貨", "url": "https://www.taifex.com.tw/cht/3/futContractsDate"},
            {"name": "TAIFEX 選擇權", "url": "https://www.taifex.com.tw/cht/3/callsAndPutsDate"},
            {"name": "TAIFEX VIX", "url": "https://www.taifex.com.tw/cht/7/vixMinNew"},
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--force", action="store_true", help="force overwrite even when fetched report date is older than today")
    args = parser.parse_args()

    existing = load_existing_report(args.output)
    report = build_report()
    report = merge_report_with_existing_sections(report, existing)
    report = normalize_report_for_template(report)
    if should_preserve_existing_cache(report, existing, args.force):
        print(
            f"[daily-chip] SKIP overwrite: fetched date {report.get('report_date')} "
            f"is older than today; keep existing {args.output.name}"
        )
        return 0

    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[daily-chip] OK：{args.output.name}（status={report['status']}，date={report['report_date']}）")
    if report.get("recovered_sections"):
        print(f"  [recover] sections: {', '.join(report['recovered_sections'])}")
    if report["errors"]:
        for err in report["errors"]:
            print(f"  [warn] {err}")
    return 0 if report["status"] in {"ok", "partial"} else 1


if __name__ == "__main__":
    sys.exit(main())
