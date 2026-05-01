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
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
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
_OPTION_DATE_RE = re.compile(r'<option\s+value="(\d{8})"')


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


# TDCC 集保資料每週公告一次，原則上「每週五」為資料日期，
# 遇國定假日順延到下個工作日（例：清明連假 → 04/02 週四）。
# 抓不到的日期 fetch 端會回 None（query/parse 都有保護），不會炸。
def compute_weekly_fridays(weeks: int = 52, anchor: datetime | None = None) -> list[str]:
    """從 anchor（預設今天）回推最近 N 個週五（YYYYMMDD 字串）。
    最新日期排在最前。週五 = isoweekday() 5。"""
    today = anchor or datetime.now()
    # 找出本週的週五（若今天 ≥ 週五，本週五；否則上週五）
    days_to_friday = today.isoweekday() - 5
    if days_to_friday < 0:
        days_to_friday += 7
    last_friday = today - timedelta(days=days_to_friday)
    return [
        (last_friday - timedelta(weeks=i)).strftime("%Y%m%d")
        for i in range(weeks)
    ]


def fetch_tdcc_available_dates(limit: int) -> list[str]:
    """從 TDCC 查詢頁官方下拉選單讀取可查資料日期（最新在前）。"""
    try:
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=_SSL_CTX),
        )
        req = urllib.request.Request(
            PORTAL,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with opener.open(req, timeout=30) as r:
            html = r.read().decode("utf-8", "replace")
    except Exception as e:
        print(f"[dates] WARN: 無法讀取 TDCC 官方日期清單，改用週五推算：{type(e).__name__}")
        return []

    dates: list[str] = []
    seen: set[str] = set()
    for date in _OPTION_DATE_RE.findall(html):
        if date in seen:
            continue
        seen.add(date)
        dates.append(date)
        if len(dates) >= limit:
            break

    if not dates:
        print("[dates] WARN: TDCC 官方日期清單為空，改用週五推算")
    return dates


# 保留舊常數作為超短回補的 fallback（手動 --dates 仍可指定）
DEFAULT_HISTORICAL_DATES = compute_weekly_fridays(weeks=52)


def load_cache() -> dict:
    if not CACHE.exists():
        print(f"[error] 找不到 {CACHE.name}，先跑 fetch_extras.py")
        sys.exit(1)
    return json.loads(CACHE.read_text(encoding="utf-8"))


def merge_legacy_holder_keys(history: dict, preferred_symbols: list[str] | None = None) -> dict:
    """把舊版去掉前導 0 的 TDCC key 合併回完整代號。

    舊資料可能有 981A / 50；新流程要以 00981A / 0050 為主。
    preferred_symbols 來自 --symbols 或 --symbols-file，可在完整 key 尚未存在時
    指定要把 legacy key 搬到哪個完整代號。
    """
    if not isinstance(history, dict):
        return {}
    normalized = dict(history)
    full_candidates = {
        sym for sym in normalized.keys()
        if isinstance(sym, str) and sym.startswith("0")
    }
    if preferred_symbols:
        full_candidates.update(
            sym for sym in preferred_symbols
            if isinstance(sym, str) and sym.startswith("0")
        )
    for full_sym in sorted(full_candidates):
        legacy_sym = full_sym.lstrip("0")
        if not legacy_sym or legacy_sym == full_sym or legacy_sym not in normalized:
            continue
        merged = dict(normalized.get(legacy_sym, {}))
        merged.update(normalized.get(full_sym, {}))
        normalized[full_sym] = merged
        normalized.pop(legacy_sym, None)
    return normalized


def save_cache(payload: dict):
    payload["holders_history"] = merge_legacy_holder_keys(payload.get("holders_history", {}))
    CACHE.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


# thread-local session：每個 worker 自己一份 cookie jar / token
_thread_local = threading.local()


def _get_session() -> "TDCCSession":
    sess = getattr(_thread_local, "sess", None)
    if sess is None:
        sess = TDCCSession()
        _thread_local.sess = sess
    return sess


def _fetch_one(sym: str, sca_date: str, sleep_s: float) -> tuple[str, str, str | None, dict | None]:
    """Worker：抓單一 (sym, date)。回傳 (sym, iso_date_or_input, status, snap)。
    status ∈ {ok, err}；ok 時 iso_date_or_input 是 server 回傳的 iso，snap 是資料 dict。"""
    sess = _get_session()
    html = sess.query(sym, sca_date)
    if html is None:
        time.sleep(sleep_s * 3)
        return (sym, sca_date, "err", None)
    parsed = parse_response(html)
    if parsed is None:
        time.sleep(sleep_s)
        return (sym, sca_date, "err", None)
    ret_date, snap = parsed
    time.sleep(sleep_s)
    return (sym, ret_date, "ok", snap)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", type=int, default=52,
                    help="回補最近 N 週（動態算過去 N 個週五，預設 52 = 近 1 年）")
    ap.add_argument("--dates", default=None,
                    help="手動指定日期，逗號分隔 YYYYMMDD")
    ap.add_argument("--symbols", default=None,
                    help="逗號分隔股票代號；不指定則用快取裡的全部")
    ap.add_argument("--symbols-file", default=None,
                    help="從文字檔讀 symbols（每行一個代號）；優先於 --symbols，避免 Windows cmd-line 長度上限")
    ap.add_argument("--limit", type=int, default=None,
                    help="只抓前 N 檔（測試用）")
    ap.add_argument("--sleep", type=float, default=0.35,
                    help="每個 worker POST 後 sleep 秒數（worker 內串行）")
    ap.add_argument("--workers", type=int, default=5,
                    help="並行 worker 數（每個獨立 cookie jar / token）。建議 5-10。")
    ap.add_argument("--save-every", type=int, default=500,
                    help="每完成 N 個請求寫一次快取（斷線不丟進度）")
    args = ap.parse_args()

    payload = load_cache()
    history: dict = payload.setdefault("holders_history", {})

    # 要抓的日期（動態算過去 N 個週五，最新在前）
    if args.dates:
        dates = [d.strip() for d in args.dates.split(",") if d.strip()]
    else:
        dates = fetch_tdcc_available_dates(args.weeks)
        if len(dates) < args.weeks:
            fallback_dates = compute_weekly_fridays(weeks=args.weeks)
            dates = dates + [d for d in fallback_dates if d not in set(dates)]
            dates = dates[:args.weeks]
        print(f"[dates] 使用 TDCC 官方/備援資料日 {len(dates)} 筆")

    # 要抓的股票
    if args.symbols_file:
        sf = Path(args.symbols_file)
        if not sf.exists():
            print(f"[error] 找不到 symbols-file：{sf}")
            sys.exit(1)
        symbols = [ln.strip() for ln in sf.read_text(encoding="utf-8").splitlines() if ln.strip()]
        print(f"[symbols] 從檔案讀 {len(symbols)} 檔（{sf}）")
    elif args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = sorted(history.keys())

    history = merge_legacy_holder_keys(history, symbols)
    payload["holders_history"] = history

    if args.limit:
        symbols = symbols[:args.limit]

    # 過濾已有資料的 (sym, date)，產出真正要抓的 task list
    tasks: list[tuple[str, str]] = []
    pre_skip = 0
    for sym in symbols:
        for sca_date in dates:
            iso = f"{sca_date[0:4]}-{sca_date[4:6]}-{sca_date[6:8]}"
            if history.get(sym, {}).get(iso):
                pre_skip += 1
                continue
            tasks.append((sym, sca_date))

    total = len(symbols) * len(dates)
    todo = len(tasks)
    print(f"[start] {len(symbols)} 檔 × {len(dates)} 週 = {total}；已有 {pre_skip} skip；待抓 {todo}")
    print(f"        workers={args.workers}, sleep={args.sleep}s/worker, save-every={args.save_every}")
    if dates:
        print(f"        日期範圍：{dates[-1]} ~ {dates[0]}（最新在前）")

    history_lock = threading.Lock()
    counter = {"ok": 0, "err": 0, "done": 0}
    counter_lock = threading.Lock()
    t0 = time.time()
    last_save_at = [0]
    save_lock = threading.Lock()

    def _maybe_save(force: bool = False):
        with save_lock:
            with counter_lock:
                done = counter["done"]
            if force or (done - last_save_at[0]) >= args.save_every:
                with history_lock:
                    payload["fetched_at"] = datetime.now().isoformat(timespec="seconds")
                    save_cache(payload)
                last_save_at[0] = done
                elapsed = time.time() - t0
                rate = done / max(elapsed, 1)
                remaining = todo - done
                eta_min = (remaining / max(rate, 0.1)) / 60
                with counter_lock:
                    print(f"  [{done:>6}/{todo}] ok={counter['ok']} err={counter['err']} "
                          f"rate={rate:.1f}/s  eta={eta_min:.1f}min  elapsed={elapsed/60:.1f}min",
                          flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(_fetch_one, s, d, args.sleep) for s, d in tasks]
        for fut in as_completed(futures):
            try:
                sym, ret_date, status, snap = fut.result()
            except Exception as e:
                with counter_lock:
                    counter["err"] += 1
                    counter["done"] += 1
                continue
            if status == "ok" and snap is not None:
                with history_lock:
                    history.setdefault(sym, {})[ret_date] = snap
                with counter_lock:
                    counter["ok"] += 1
                    counter["done"] += 1
            else:
                with counter_lock:
                    counter["err"] += 1
                    counter["done"] += 1
            _maybe_save()

    _maybe_save(force=True)
    elapsed = time.time() - t0
    print(f"\n[done] ok={counter['ok']} err={counter['err']} done={counter['done']}  "
          f"耗時 {elapsed/60:.1f} 分鐘  ({counter['done']/max(elapsed,1):.1f} req/s)")

    # 統計合計週數
    all_dates = set()
    for by_date in history.values():
        all_dates.update(by_date.keys())
    print(f"       holders_history 目前覆蓋 {len(history)} 檔 × {len(all_dates)} 個日期")


if __name__ == "__main__":
    main()
