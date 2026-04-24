"""
回補 TDCC 集保分級歷史資料（per-stock × per-week）。

用法：
  # 從快取讀現有股票清單 + 回補最近 4 週（本週已由 fetch_extras.py 抓過）
  python site/fetch_holders_history.py --weeks 4

  # 抓指定日期（YYYYMMDD）
  python site/fetch_holders_history.py --dates 20260410,20260402,20260327,20260320

  # 限制前 N 檔（測試用）
  python site/fetch_holders_history.py --weeks 4 --limit 50

  # 從指定股票清單
  python site/fetch_holders_history.py --weeks 4 --symbols 2330,2317,2454

機制：
  1. GET TDCC portal → 取 JSESSIONID + SYNCHRONIZER_TOKEN
  2. 逐 (stock, date) POST → 解析 HTML 表格
  3. 併入 site/.cache_extras.json 的 holders_history
  4. rate-limit ~3 req/s，遇 429/5xx 自動退避
"""
from __future__ import annotations
import argparse
import http.cookiejar
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / ".cache_extras.json"

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

PORTAL = "https://www.tdcc.com.tw/portal/zh/smWeb/qryStock"

# 只保留 level 1-15 的 <tr>（16 差異調整、17 合計 跳過）
_ROW_RE = re.compile(
    r'<tr[^>]*>\s*'
    r'<td[^>]*>\s*(\d+)\s*</td>\s*'         # 序（1-17）
    r'<td[^>]*>([^<]+)</td>\s*'             # 分級文字
    r'<td[^>]*>\s*([\d,]+)\s*</td>\s*'      # 人數
    r'<td[^>]*>\s*([\d,]+)\s*</td>\s*'      # 股數
    r'<td[^>]*>\s*([\d.]+)\s*</td>\s*'      # 佔比 %
    r'</tr>', re.S
)

_DATE_RE = re.compile(r"資料日期[:：]\s*(\d+)年(\d+)月(\d+)日")


def roc_to_iso(matched) -> str:
    y, m, d = matched.group(1), matched.group(2), matched.group(3)
    return f"{int(y)+1911:04d}-{int(m):02d}-{int(d):02d}"


class TDCCSession:
    """共用 JSESSIONID 的 session。SYNCHRONIZER_TOKEN 每次 POST 後會換新，
    所以每次 POST 前要重新 GET portal 拿 token。"""

    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=_SSL_CTX),
            urllib.request.HTTPCookieProcessor(self.jar),
        )
        self.opener.addheaders = [
            ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"),
        ]

    def _get_token(self, retries: int = 5) -> str | None:
        """GET portal 拿 CSRF token，遇 network 錯誤自動重試。"""
        for attempt in range(retries):
            try:
                with self.opener.open(PORTAL, timeout=30) as r:
                    html = r.read().decode("utf-8", "replace")
                m = re.search(r'name="SYNCHRONIZER_TOKEN"\s+value="([^"]+)"', html)
                if m:
                    return m.group(1)
                # 拿不到 token 但也沒 exception，短暫等再試
                time.sleep(1.0 * (attempt + 1))
            except Exception as e:
                wait = 2.0 * (attempt + 1)
                print(f"    [token retry {attempt+1}/{retries}] {type(e).__name__} → 等 {wait}s")
                time.sleep(wait)
        return None

    def query(self, stock_no: str, sca_date: str, retries: int = 3) -> str | None:
        """回傳指定股票/日期的 response HTML；網路錯誤自動重試。"""
        for attempt in range(retries):
            token = self._get_token()
            if token is None:
                return None
            form = urllib.parse.urlencode({
                "SYNCHRONIZER_TOKEN": token,
                "SYNCHRONIZER_URI": "/portal/zh/smWeb/qryStock",
                "method": "submit",
                "firDate": "20260417",
                "scaDate": sca_date,
                "SqlMethod": "StockNo",
                "StockNameChk": "",
                "stockNo": stock_no,
                "radioStockNo": "on",
                "REQ_OPR": "SELECT",
            }).encode("utf-8")
            req = urllib.request.Request(
                PORTAL, data=form, method="POST",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": PORTAL,
                },
            )
            try:
                with self.opener.open(req, timeout=30) as r:
                    return r.read().decode("utf-8", "replace")
            except Exception as e:
                wait = 1.5 * (attempt + 1)
                print(f"    [POST retry {attempt+1}/{retries}] {stock_no}@{sca_date} {type(e).__name__} → 等 {wait}s")
                time.sleep(wait)
        return None


def parse_response(html: str) -> tuple[str, dict] | None:
    """抽出資料日期 + 15 級 {h:[15], s:[15], p:[15]}。沒資料回 None。"""
    if "找不到資料" in html or "查無資料" in html:
        return None
    date_m = _DATE_RE.search(html)
    if not date_m:
        return None
    iso_date = roc_to_iso(date_m)

    rows = _ROW_RE.findall(html)
    if not rows:
        return None

    by_level = {int(lv): (h, s, p) for lv, _lbl, h, s, p in rows}
    # 必須有 level 15（最大），否則視為無效
    if 15 not in by_level:
        return None

    h = [0] * 15
    s = [0] * 15
    p = [0.0] * 15
    for lv in range(1, 16):
        if lv in by_level:
            hc, sc, pc = by_level[lv]
            h[lv-1] = int(hc.replace(",", ""))
            s[lv-1] = int(sc.replace(",", ""))
            p[lv-1] = float(pc)
    return iso_date, {"h": h, "s": s, "p": p}


# TDCC 歷史常見的週五日期（若夾帶 bridge 日，抓取端會處理）
DEFAULT_HISTORICAL_DATES = [
    "20260410", "20260402", "20260327", "20260320",  # 最近 4 個可用週
]


def load_cache() -> dict:
    if not CACHE.exists():
        print(f"[error] 找不到 {CACHE.name}，先跑 fetch_extras.py")
        sys.exit(1)
    return json.loads(CACHE.read_text(encoding="utf-8"))


def save_cache(payload: dict):
    CACHE.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", type=int, default=4,
                    help="回補最近 N 週（使用 DEFAULT_HISTORICAL_DATES）")
    ap.add_argument("--dates", default=None,
                    help="手動指定日期，逗號分隔 YYYYMMDD")
    ap.add_argument("--symbols", default=None,
                    help="逗號分隔股票代號；不指定則用快取裡的全部")
    ap.add_argument("--limit", type=int, default=None,
                    help="只抓前 N 檔（測試用）")
    ap.add_argument("--sleep", type=float, default=0.35,
                    help="每次 POST 間隔秒數（預設 0.35s ≈ 3 req/s）")
    ap.add_argument("--save-every", type=int, default=200,
                    help="每 N 次寫一次快取（斷線不丟進度）")
    args = ap.parse_args()

    payload = load_cache()
    history: dict = payload.setdefault("holders_history", {})

    # 要抓的日期
    if args.dates:
        dates = [d.strip() for d in args.dates.split(",") if d.strip()]
    else:
        dates = DEFAULT_HISTORICAL_DATES[:args.weeks]

    # 要抓的股票
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = sorted(history.keys())

    if args.limit:
        symbols = symbols[:args.limit]

    total = len(symbols) * len(dates)
    print(f"[start] {len(symbols)} 檔 × {len(dates)} 週 = {total} 請求，每次 {args.sleep}s")
    print(f"        日期：{dates}")

    sess = TDCCSession()
    ok = skip = err = 0
    t0 = time.time()
    for i, sym in enumerate(symbols):
        for sca_date in dates:
            # 已經有這週資料就跳過（省時）
            iso = f"{sca_date[0:4]}-{sca_date[4:6]}-{sca_date[6:8]}"
            if history.get(sym, {}).get(iso):
                skip += 1
                continue

            html = sess.query(sym, sca_date)
            if html is None:
                err += 1
                time.sleep(args.sleep * 3)  # 退避
                continue
            parsed = parse_response(html)
            if parsed is None:
                err += 1
            else:
                ret_date, snap = parsed
                history.setdefault(sym, {})[ret_date] = snap
                ok += 1
            time.sleep(args.sleep)

        if (i + 1) % args.save_every == 0:
            save_cache(payload)
            elapsed = time.time() - t0
            rate = (ok + skip + err) / max(elapsed, 1)
            remaining = (len(symbols) - i - 1) * len(dates)
            eta = remaining / max(rate, 0.1)
            print(f"  [{i+1:>5}/{len(symbols)}] ok={ok} skip={skip} err={err} "
                  f"rate={rate:.1f}/s  eta={eta/60:.1f}min")

    payload["fetched_at"] = datetime.now().isoformat(timespec="seconds")
    save_cache(payload)
    elapsed = time.time() - t0
    print(f"\n[done] ok={ok} skip={skip} err={err}  耗時 {elapsed/60:.1f} 分鐘")

    # 統計合計週數
    all_dates = set()
    for by_date in history.values():
        all_dates.update(by_date.keys())
    print(f"       holders_history 目前覆蓋 {len(history)} 檔 × {len(all_dates)} 個日期")


if __name__ == "__main__":
    main()
