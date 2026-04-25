"""
fetch_futures_list.py — 從台灣期交所抓取個股期貨清單

來源：https://www.taifex.com.tw/cht/2/stockLists
頁面為單一表格（14 欄），用「契約規格」欄區分四類：
  2,000  → 個股期貨        (stock_futures)
  100    → 小型個股期貨    (mini_stock_futures)
  10,000 → ETF 期貨        (etf_futures)
  1,000  → 小型 ETF 期貨   (mini_etf_futures)

輸出：site/.cache_futures.json
{
  "as_of": "YYYY-MM-DD",
  "stock_futures":      ["2330", ...],
  "mini_stock_futures": ["2330", ...],
  "etf_futures":        ["0050", ...],
  "mini_etf_futures":   ["0050", ...],
}

採 subprocess 隔離（被 build_site.py 呼叫時失敗不影響 build）。
"""
from __future__ import annotations
import json
import re
import sys
from datetime import date
from pathlib import Path

import requests

URL = "https://www.taifex.com.tw/cht/2/stockLists"
OUTPUT = Path(__file__).resolve().parent / ".cache_futures.json"
TIMEOUT = 30
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

SIZE_TO_CATEGORY = {
    "2000":  "stock_futures",
    "100":   "mini_stock_futures",
    "10000": "etf_futures",
    "1000":  "mini_etf_futures",
}

ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.S)
TD_RE  = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
TAG_RE = re.compile(r"<[^>]+>")
SYM_RE = re.compile(r"^[0-9A-Z]{4,8}$")


def parse(html: str) -> dict:
    result = {k: [] for k in SIZE_TO_CATEGORY.values()}
    for m in ROW_RE.finditer(html):
        tds = TD_RE.findall(m.group(1))
        if len(tds) != 14:
            continue
        sym  = TAG_RE.sub("", tds[2]).strip()
        size = TAG_RE.sub("", tds[11]).strip().replace(",", "")
        if not SYM_RE.match(sym):
            continue
        cat = SIZE_TO_CATEGORY.get(size)
        if cat is None:
            continue
        result[cat].append(sym)
    return {k: sorted(set(v)) for k, v in result.items()}


def main() -> int:
    print(f"[futures] 抓取 {URL} ...")
    try:
        r = requests.get(URL, headers={"User-Agent": UA}, timeout=TIMEOUT)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
        html = r.text
    except Exception as e:
        print(f"[futures] 抓取失敗：{e}")
        if OUTPUT.exists():
            print(f"[futures] 沿用前次 cache：{OUTPUT.name}")
            return 0
        return 1

    try:
        result = parse(html)
    except Exception as e:
        print(f"[futures] 解析失敗：{e}")
        if OUTPUT.exists():
            print(f"[futures] 沿用前次 cache：{OUTPUT.name}")
            return 0
        return 1

    counts = {k: len(v) for k, v in result.items()}
    if counts["stock_futures"] < 100 or counts["etf_futures"] < 5:
        print(f"[futures] 警告：抓到的數量異常少 {counts}，疑似頁面結構變更")
        if OUTPUT.exists():
            print("[futures] 沿用前次 cache，本次不覆寫")
            return 0

    payload = {"as_of": date.today().isoformat(), **result}
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[futures] OK 已寫入 {OUTPUT.name}")
    print(f"  個股期貨   : {counts['stock_futures']:>3} 檔")
    print(f"  小型個股期 : {counts['mini_stock_futures']:>3} 檔")
    print(f"  ETF 期貨   : {counts['etf_futures']:>3} 檔")
    print(f"  小型ETF期  : {counts['mini_etf_futures']:>3} 檔")
    return 0


if __name__ == "__main__":
    sys.exit(main())
