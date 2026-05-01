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
import re
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
    "1-5張",            # 2
    "5-10張",           # 3
    "10-15張",          # 4
    "15-20張",          # 5
    "20-30張",          # 6
    "30-40張",          # 7
    "40-50張",          # 8
    "50-100張",         # 9
    "100-200張",        # 10
    "200-400張",        # 11
    "400-600張",        # 12
    "600-800張",        # 13
    "800-1,000張",      # 14
    "1,000張以上",      # 15
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

# TWSE detail 全文段落抽取：原文用全形數字「１」「２」「３」分段（半形相容）。
# 段 1: 處置原因 / 段 2: 處置期間 / 段 3: 處置措施
_TWSE_REASON_BLOCK = re.compile(
    r"[１1]\s*處置原因[：:]\s*(.+?)(?=\s*[２2]\s*處置期間|\s*[３3]\s*處置措施|$)",
    re.DOTALL,
)
_TWSE_ACTION_BLOCK = re.compile(
    r"[３3]\s*處置措施[：:\s]*(.+)$",
    re.DOTALL,
)


def _normalize_block(text: str) -> str:
    """壓掉多餘空白／換行，保留可讀斷句（句號、a/b/c 列點之間加空格）。"""
    if not text:
        return ""
    # 把連續空白 / 換行壓成單一空格
    t = re.sub(r"\s+", " ", text).strip()
    return t


def _extract_twse_reason_action(detail: str) -> tuple[str, str]:
    """從 TWSE Detail 完整文字抽出『處置原因』與『處置措施』段落純文字。
    抓不到任何一段就回 ('','')，由 caller 退路用短分類欄位。"""
    if not detail:
        return "", ""
    reason = ""
    action = ""
    m = _TWSE_REASON_BLOCK.search(detail)
    if m:
        reason = _normalize_block(m.group(1))
    m = _TWSE_ACTION_BLOCK.search(detail)
    if m:
        action = _normalize_block(m.group(1))
    return reason, action


def fetch_disposal_twse() -> dict:
    """TWSE 上市處置股清單。
    TWSE openapi 的 ReasonsOfDisposition / DispositionMeasures 只是『連續三次』『第一次處置』
    這種短分類；完整文字（含『以人工管制之撮合終端機執行撮合作業（約每五分鐘撮合一次）』等核心
    措施）藏在 Detail 欄位。所以：
      - reason / action：優先用 Detail 抽出的完整段落，抽不到才退到短分類
      - reason_summary / action_summary：保留短分類，前端可顯示為小 tag
      - detail：保留完整原文，**不截斷**（過去截 240 字會把信用交易管控段砍掉）
    """
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
        detail_full     = (row.get("Detail", "") or "").strip()
        reason_summary  = (row.get("ReasonsOfDisposition", "") or "").strip()
        action_summary  = (row.get("DispositionMeasures", "") or "").strip()
        reason_long, action_long = _extract_twse_reason_action(detail_full)
        out[code] = {
            "status":          "處置中",
            "name":            row.get("Name", ""),
            "reason":          reason_long or reason_summary,
            "action":          action_long or action_summary,
            "reason_summary":  reason_summary,
            "action_summary":  action_summary,
            "as_of":           _roc_to_ad(start),
            "end":             _roc_to_ad(end),
            "detail":          detail_full,
            "market":          "上市",
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
            "status":          "處置中",
            "name":            name,
            "reason":          g(row, "處置原因"),
            "action":          g(row, "處置內容"),   # 不截斷，完整保留撮合分鐘 + 信用交易管控段
            "reason_summary":  "",                    # TPEx 無短分類，欄位留空對齊上市結構
            "action_summary":  "",
            "as_of":           _roc_to_ad(start),
            "end":             _roc_to_ad(end),
            "detail":          "",
            "market":          "上櫃",
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
        # TDCC 的代號必須保留原樣。ETF / 主動 ETF 會有 0050、00981A
        # 這類前導 0；若去掉，個股頁以完整代號查詢時會找不到資料。
        sym = str(code).strip()
        if not sym or len(sym) > 6:
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


def merge_holders_history(prev_hist: dict, new_date: str, new_snap: dict, keep_weeks: int = 60) -> dict:
    """把新一週併入現有歷史，保留最近 keep_weeks 週（預設 60 ≈ 1 年再多 8 週緩衝）。
    結構：{sym: {date: {h, s, p}}, ...}"""
    hist = dict(prev_hist) if isinstance(prev_hist, dict) else {}

    # 舊版曾把 TDCC 代號做 lstrip("0")，例如 00981A -> 981A、0050 -> 50。
    # 這裡以最新 open data 的完整代號為準，把舊 key 的歷史搬回正確 key。
    for full_sym in sorted(new_snap.keys()):
        legacy_sym = full_sym.lstrip("0")
        if (
            legacy_sym
            and legacy_sym != full_sym
            and legacy_sym in hist
        ):
            merged = dict(hist.get(legacy_sym, {}))
            merged.update(hist.get(full_sym, {}))
            hist[full_sym] = merged
            hist.pop(legacy_sym, None)

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
            payload.get("holders_history", {}), new_date, new_snap, keep_weeks=60,
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
